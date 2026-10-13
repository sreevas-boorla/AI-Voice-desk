"""
VoiceDesk LiveKit Agent Worker
Runs as a WebRTC voice agent connecting to LiveKit rooms,
transcribing audio with STT, routing conversational logic and tool execution
through the CareBridge Clinic FastAPI backend, and streaming spoken audio with TTS.
Compatible with LiveKit Agents SDK 1.8.6+.
"""

import os
import sys
import json
import time
import uuid
import re
import asyncio
import logging
from typing import Optional, Dict, Any, Set
from dotenv import load_dotenv
import httpx

# Add voice-worker directory to sys.path so components can be imported directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turn_manager import TurnQueueManager
from speech_manager import ConfirmationSpeechManager, play_speech

load_dotenv()


class SensitiveDataFilter(logging.Filter):
    """
    Sanitizes any sensitive patterns (session tokens, room names, bearer tokens,
    verification codes, phone numbers, API keys) from log records.
    """
    SENSITIVE_PATTERNS = [
        (re.compile(r"room_sess_[a-zA-Z0-9_\-]+", re.IGNORECASE), "[ROOM_REDACTED]"),
        (re.compile(r"sess_[a-zA-Z0-9_\-]+", re.IGNORECASE), "[SESSION_REDACTED]"),
        (re.compile(r"Bearer\s+[a-zA-Z0-9._\-]+", re.IGNORECASE), "Bearer [REDACTED]"),
        (re.compile(r"(\+?\d{1,3}[\s-]?)?(\d{5}[\s-]?\d{5}|\d{3}[\s-]?\d{3}[\s-]?\d{4}|\d{10})"), "[PHONE_REDACTED]"),
        (re.compile(r"\b\d{4}\b"), "[CODE_REDACTED]"),
        (re.compile(r"(gsk_[a-zA-Z0-9_\-]+|lk_[a-zA-Z0-9_\-]+)", re.IGNORECASE), "[API_KEY_REDACTED]")
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, repl in self.SENSITIVE_PATTERNS:
                record.msg = pattern.sub(repl, record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(self._sanitize_value(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: self._sanitize_value(v) for k, v in record.args.items()}
        return True

    def _sanitize_value(self, val: Any) -> Any:
        if isinstance(val, str):
            for pattern, repl in self.SENSITIVE_PATTERNS:
                val = pattern.sub(repl, val)
        return val


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("voicedesk-worker")
logger.addFilter(SensitiveDataFilter())

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000/api")


def check_credentials() -> Dict[str, bool]:
    """Inspects credential presence without leaking raw secrets into logs."""
    return {
        "livekit": bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET),
        "deepgram_stt": bool(DEEPGRAM_API_KEY),
        "cartesia_tts": bool(CARTESIA_API_KEY),
        "llm_provider": bool(GROQ_API_KEY)
    }


async def call_backend_agent(session_token: str, message: str, correlation_id: str = "worker") -> Dict[str, Any]:
    """
    Reuses the backend's core booking, verification, and confirmation rules.
    Ensures one user utterance produces exactly one agent response.
    Never exposes raw message content or session tokens in log telemetry.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            res = await client.post(
                f"{BACKEND_API_URL}/agent/chat",
                json={
                    "message": message,
                    "session_token": session_token,
                    "channel": "voice"
                }
            )
            if res.status_code != 200:
                logger.error(f"[{correlation_id}] Backend agent error HTTP {res.status_code}")
                return {"reply": "I'm having trouble connecting to CareBridge Clinic server. Please try again."}
            return res.json()
        except Exception as e:
            logger.error(f"[{correlation_id}] Connection error calling backend agent: {type(e).__name__}")
            return {"reply": "The clinic appointment system is temporarily unreachable. Please try again."}


def run_worker():
    status = check_credentials()
    logger.info("VoiceDesk LiveKit Agent Worker Initializing...")
    logger.info(f"Credential Status: {status}")

    if not status["livekit"]:
        logger.warning(
            "LIVEKIT_URL / API_KEY / API_SECRET not configured. "
            "Worker cannot connect to LiveKit server. "
            "Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in your environment to enable WebRTC voice."
        )
        return

    try:
        import livekit.rtc as rtc
        from livekit.agents import JobContext, WorkerOptions, cli
        from livekit.agents.voice import Agent, AgentSession, UserInputTranscribedEvent
        from livekit.plugins import deepgram, cartesia, silero

        logger.info("LiveKit Agents SDK 1.8.6+ loaded successfully.")

        async def entrypoint(ctx: JobContext):
            room_name = ctx.room.name
            session_token = room_name.replace("room_", "") if "room_" in room_name else room_name

            # Generate random correlation ID completely unrelated to session tokens or secrets
            correlation_id = f"corr-{uuid.uuid4().hex[:8]}"
            logger.info(f"[{correlation_id}] Connecting to LiveKit room")

            await ctx.connect()

            # Wait for patient participant to join
            participant = await ctx.wait_for_participant()
            logger.info(f"[{correlation_id}] Remote participant joined voice session")

            if not status["deepgram_stt"] or not status["cartesia_tts"]:
                logger.error(f"[{correlation_id}] DEEPGRAM_API_KEY or CARTESIA_API_KEY missing. Audio pipeline cannot stream.")
                await ctx.room.local_participant.publish_data(
                    json.dumps({
                        "type": "error",
                        "message": "Speech pipeline credentials missing on voice worker."
                    }),
                    reliable=True
                )
                return

            stt = deepgram.STT(api_key=DEEPGRAM_API_KEY)
            tts = cartesia.TTS(api_key=CARTESIA_API_KEY)
            vad = silero.VAD.load()

            agent = Agent(
                instructions="You are VoiceDesk, the receptionist for CareBridge Clinic.",
                stt=stt,
                vad=vad,
                tts=tts,
                allow_interruptions=True
            )

            session = AgentSession(
                stt=stt,
                vad=vad,
                tts=tts,
                allow_interruptions=True
            )

            # TurnQueueManager handles FIFO sequencing, deduplication, and safe shutdown
            turn_mgr = TurnQueueManager(deduplication_window_seconds=2.0)

            # ConfirmationSpeechManager handles authoritative confirmation retrieval and playback
            speech_mgr = ConfirmationSpeechManager(
                session_token=session_token,
                correlation_id=correlation_id,
                backend_api_url=BACKEND_API_URL
            )

            async def handle_user_turn(user_text: str):
                t0 = time.time()
                logger.info(f"[{correlation_id}] Dispatching turn to backend agent (chars={len(user_text)})")

                resp = await call_backend_agent(session_token, user_text, correlation_id=correlation_id)
                reply_text = resp.get("reply", "I am standing by.")
                tool_events = resp.get("tool_events", [])
                pending_action = resp.get("pending_action")
                duration = time.time() - t0

                logger.info(
                    f"[{correlation_id}] Backend turn completed in {duration:.2f}s "
                    f"(tools={len(tool_events)}, pending_action={bool(pending_action)})"
                )

                # Publish structured event to room data channel
                try:
                    packet = json.dumps({
                        "type": "agent_response",
                        "user_text": user_text,
                        "reply": reply_text,
                        "tool_events": tool_events,
                        "pending_action": pending_action
                    })
                    await ctx.room.local_participant.publish_data(packet, reliable=True)
                except Exception as pe:
                    logger.warning(f"[{correlation_id}] Failed to publish room data packet: {type(pe).__name__}")

                # Synthesize voice response back to the room audio track using play_speech
                logger.info(f"[{correlation_id}] Streaming synthesized agent response via TTS (chars={len(reply_text)})")
                await play_speech(session, reply_text)

            # Start sequential consumer task
            consumer_task = turn_mgr.start_consumer(handle_user_turn)

            # Register async shutdown callback to cleanly cancel and await consumer and speech tasks
            async def on_shutdown():
                logger.info(f"[{correlation_id}] Room shutting down; draining turn consumer and speech tasks.")
                await turn_mgr.shutdown()
                await speech_mgr.shutdown()

            ctx.add_shutdown_callback(on_shutdown)

            # Listen for transcribed user turns
            @session.on("user_input_transcribed")
            def on_user_speech(event: UserInputTranscribedEvent):
                if not event.is_final or not event.transcript.strip():
                    return
                user_text = event.transcript.strip()
                enqueued = turn_mgr.enqueue(user_text)
                if enqueued:
                    logger.info(f"[{correlation_id}] Final user speech committed & enqueued (chars={len(user_text)})")
                else:
                    logger.info(f"[{correlation_id}] Rapid duplicate transcript filtered")

            # Listen for data messages from client (authoritative confirmation result notifications)
            @ctx.room.on("data_received")
            def on_data_received(packet: rtc.DataPacket):
                try:
                    raw_text = packet.data.decode("utf-8")
                    data = json.loads(raw_text)
                    if data.get("type") == "confirmation_result":
                        sender_identity = getattr(packet.participant, "identity", None)
                        speech_mgr.handle_notification(
                            sender_identity=sender_identity,
                            expected_identity=participant.identity,
                            packet_payload=data,
                            speaker=session
                        )
                except Exception as de:
                    logger.warning(f"[{correlation_id}] Error handling room data packet: {type(de).__name__}")

            await session.start(agent=agent, room=ctx.room)
            logger.info(f"[{correlation_id}] LiveKit AgentSession active.")

        options = WorkerOptions(entrypoint_fnc=entrypoint)
        # Default to "start" command if invoked without explicit CLI subcommand
        if len(sys.argv) == 1:
            sys.argv.append("start")
        cli.run_app(options)

    except ImportError as e:
        logger.warning(f"LiveKit agent plugins not installed: {e}. Install via `pip install -r requirements.txt`.")
    except Exception as e:
        logger.error(f"LiveKit agent worker runtime error: {e}")


if __name__ == "__main__":
    run_worker()
