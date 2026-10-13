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
import asyncio
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("voicedesk-worker")

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

async def call_backend_agent(session_token: str, message: str) -> Dict[str, Any]:
    """
    Reuses the backend's core booking, verification, and confirmation rules.
    Ensures one user utterance produces exactly one agent response,
    avoiding duplicate or diverging state between worker and server.
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
                logger.error(f"Backend agent returned HTTP {res.status_code}")
                return {"reply": "I'm having trouble connecting to CareBridge Clinic server. Please try again."}
            return res.json()
        except Exception as e:
            logger.error(f"Error calling backend agent: {e}")
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
        from livekit.agents import JobContext, WorkerOptions, cli
        from livekit.agents.voice import Agent, AgentSession, UserInputTranscribedEvent
        from livekit.plugins import deepgram, cartesia, silero

        logger.info("LiveKit Agents SDK 1.8.6+ loaded successfully.")

        async def entrypoint(ctx: JobContext):
            room_name = ctx.room.name
            session_token = room_name.replace("room_", "") if "room_" in room_name else room_name
            logger.info(f"Connecting to LiveKit room: {room_name} (Session: {session_token})")

            await ctx.connect()

            # Wait for patient participant to join
            participant = await ctx.wait_for_participant()
            logger.info(f"Participant joined room: {participant.identity}")

            if not status["deepgram_stt"] or not status["cartesia_tts"]:
                logger.error("DEEPGRAM_API_KEY or CARTESIA_API_KEY missing. Audio pipeline cannot stream.")
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

            # Sequential FIFO turn queue to prevent overlapping requests or out-of-order execution
            turn_queue: asyncio.Queue[str] = asyncio.Queue()
            last_processed = {"text": "", "time": 0.0}

            async def process_turns_sequentially():
                while True:
                    try:
                        user_text = await turn_queue.get()
                        await handle_user_turn(session, ctx.room, session_token, user_text)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Error handling turn in session {session_token}: {e}")
                    finally:
                        turn_queue.task_done()

            # Start background worker task for sequential turns
            worker_task = asyncio.create_task(process_turns_sequentially())
            ctx.add_shutdown_callback(lambda: worker_task.cancel())

            @session.on("user_input_transcribed")
            def on_user_speech(event: UserInputTranscribedEvent):
                if not event.is_final or not event.transcript.strip():
                    return
                user_text = event.transcript.strip()
                now = asyncio.get_event_loop().time()

                # Deduplicate rapid repeat of exact transcript within 2.0s
                if user_text.lower() == last_processed["text"].lower() and (now - last_processed["time"]) < 2.0:
                    logger.info(f"Duplicate transcript discarded in session {session_token}: '{user_text}'")
                    return
                last_processed["text"] = user_text
                last_processed["time"] = now

                logger.info(f"User utterance queued in session {session_token}: '{user_text}'")
                turn_queue.put_nowait(user_text)

            await session.start(agent=agent, room=ctx.room)
            logger.info(f"LiveKit AgentSession active in room {room_name}.")

        async def handle_user_turn(session, room, session_token: str, user_text: str):
            # Call backend REST agent (single source of truth for all tools and bookings)
            resp = await call_backend_agent(session_token, user_text)
            reply_text = resp.get("reply", "I am standing by.")
            tool_events = resp.get("tool_events", [])
            pending_action = resp.get("pending_action")

            # Publish structured event to room data channel so frontend UI updates transcripts, tool logs, & confirmation cards
            try:
                packet = json.dumps({
                    "type": "agent_response",
                    "user_text": user_text,
                    "reply": reply_text,
                    "tool_events": tool_events,
                    "pending_action": pending_action
                })
                await room.local_participant.publish_data(packet, reliable=True)
            except Exception as pe:
                logger.warning(f"Could not publish room data packet: {pe}")

            # Synthesize voice response back to the room audio track
            await session.say(reply_text, allow_interruptions=True)

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
