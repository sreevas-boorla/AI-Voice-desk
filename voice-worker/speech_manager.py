"""
SpeechManager Component
Handles authoritative action confirmation retrieval, verified participant checks,
concurrency guarding, awaitable SpeechHandle playback, and graceful task lifecycle management.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Set, Callable
import httpx

logger = logging.getLogger("voicedesk-worker.speech-manager")


async def play_speech(speaker: Any, text: str):
    """
    Safely executes speech synthesis. LiveKit Agents session.say() returns an
    awaitable SpeechHandle, NOT a coroutine accepted directly by asyncio.create_task().
    This async wrapper awaits the SpeechHandle cleanly.
    """
    res = speaker.say(text, allow_interruptions=True) if hasattr(speaker, "say") else speaker(text)
    if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
        await res


class ConfirmationSpeechManager:
    def __init__(self, session_token: str, correlation_id: str, backend_api_url: str):
        self.session_token = session_token
        self.correlation_id = correlation_id
        self.backend_api_url = backend_api_url
        self.in_flight_actions: Set[str] = set()
        self.spoken_actions: Set[str] = set()
        self.active_tasks: Set[asyncio.Task] = set()

    async def fetch_authoritative_result(
        self,
        action_id: str,
        client: Optional[httpx.AsyncClient] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves the persisted authoritative result for the action from the backend.
        Rejects unknown, cross-session, pending, superseded, or expired actions.
        """
        url = f"{self.backend_api_url}/agent/action-result/{action_id}"
        headers = {"Authorization": f"Bearer {self.session_token}"}

        async def _do_req(c: httpx.AsyncClient):
            try:
                res = await c.get(url, headers=headers, timeout=10.0)
                if res.status_code == 200:
                    return res.json()
                logger.warning(
                    f"[{self.correlation_id}] Backend action-result lookup failed: "
                    f"HTTP {res.status_code} for action"
                )
                return None
            except Exception as e:
                logger.warning(
                    f"[{self.correlation_id}] Error connecting to backend for action result: "
                    f"{type(e).__name__}"
                )
                return None

        if client:
            return await _do_req(client)
        else:
            async with httpx.AsyncClient() as c:
                return await _do_req(c)

    def handle_notification(
        self,
        sender_identity: Optional[str],
        expected_identity: str,
        packet_payload: Dict[str, Any],
        speaker: Any,
        client: Optional[httpx.AsyncClient] = None
    ) -> Optional[asyncio.Task]:
        """
        Validates sender identity and schedules authoritative speech playback.
        Treats room message as an untrusted notification: NEVER uses client-provided text.
        Prevents concurrent duplicate notifications from scheduling duplicate speech.
        Returns the spawned task if scheduled, or None if rejected/ignored.
        """
        # 1. Verify sender participant identity
        if not sender_identity or sender_identity != expected_identity:
            logger.warning(
                f"[{self.correlation_id}] Rejected notification from unverified participant"
            )
            return None

        # 2. Extract action_id
        action_id = packet_payload.get("action_id")
        if not action_id or not isinstance(action_id, str):
            logger.warning(
                f"[{self.correlation_id}] Missing or invalid action_id in notification"
            )
            return None

        # 3. Guard against concurrent or duplicate notifications
        if action_id in self.spoken_actions or action_id in self.in_flight_actions:
            logger.info(
                f"[{self.correlation_id}] Duplicate notification ignored for action"
            )
            return None

        self.in_flight_actions.add(action_id)

        # 4. Define async task wrapping lookup and speech playback
        async def _speech_coroutine():
            try:
                # Retrieve authoritative result from backend (never trusting client text)
                data = await self.fetch_authoritative_result(action_id, client=client)
                if not data or not data.get("message"):
                    logger.warning(
                        f"[{self.correlation_id}] No authoritative message available for action"
                    )
                    return

                msg_to_speak = data["message"]
                logger.info(
                    f"[{self.correlation_id}] Speaking authoritative confirmation result "
                    f"(chars={len(msg_to_speak)})"
                )

                # Play speech and await completion
                await play_speech(speaker, msg_to_speak)

                # Mark as spoken strictly AFTER successful playback
                self.spoken_actions.add(action_id)
                logger.info(
                    f"[{self.correlation_id}] Authoritative confirmation speech completed successfully"
                )
            except asyncio.CancelledError:
                logger.info(
                    f"[{self.correlation_id}] Confirmation speech cancelled or interrupted"
                )
                raise
            except Exception as e:
                logger.error(
                    f"[{self.correlation_id}] Confirmation speech playback failed: {type(e).__name__}"
                )
            finally:
                self.in_flight_actions.discard(action_id)

        task = asyncio.create_task(_speech_coroutine())
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)
        return task

    async def shutdown(self):
        """Cancels and awaits all active speech tasks."""
        if not self.active_tasks:
            return
        logger.info(f"[{self.correlation_id}] Cancelling {len(self.active_tasks)} active speech tasks")
        for t in list(self.active_tasks):
            t.cancel()
        await asyncio.gather(*self.active_tasks, return_exceptions=True)
        self.active_tasks.clear()
