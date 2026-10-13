"""
VoiceDesk LiveKit Agent Worker
Runs as a persistent WebRTC agent connecting to LiveKit rooms,
transcribing audio with STT, calling CareBridge Clinic tools via backend REST API,
and synthesizing audio with TTS.
"""

import os
import sys
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
    return {
        "livekit": bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET),
        "deepgram_stt": bool(DEEPGRAM_API_KEY),
        "cartesia_tts": bool(CARTESIA_API_KEY),
        "llm_provider": bool(GROQ_API_KEY)
    }

async def call_backend_agent(session_token: str, message: str) -> Dict[str, Any]:
    """Reuses the backend's core booking, verification, and confirmation rules."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{BACKEND_API_URL}/agent/chat",
            json={
                "message": message,
                "session_token": session_token,
                "channel": "voice"
            }
        )
        if res.status_code != 200:
            logger.error(f"Backend agent error ({res.status_code}): {res.text}")
            return {"reply": "I'm having trouble connecting to the clinic server. Please check your connection."}
        return res.json()

async def run_worker():
    status = check_credentials()
    logger.info("VoiceDesk LiveKit Agent Worker Initializing...")
    logger.info(f"Credential Status: {status}")

    if not status["livekit"]:
        logger.warning(
            "LIVEKIT_URL / API_KEY / API_SECRET not configured. "
            "LiveKit worker cannot start. "
            "Clients will automatically use Browser Web Speech API + backend deterministic simulator."
        )
        return

    try:
        from livekit import agents
        from livekit.agents import JobContext, WorkerOptions, cli
        from livekit.agents.voice_assistant import VoiceAssistant
        from livekit.plugins import deepgram, cartesia, openai

        logger.info("LiveKit Agents SDK loaded successfully.")

        async def entrypoint(ctx: JobContext):
            room_name = ctx.room.name
            session_token = room_name.replace("room_", "") if "room_" in room_name else room_name
            logger.info(f"Connecting to LiveKit room: {room_name} (Session: {session_token})")

            await ctx.connect()

            # Wait for user participant to join
            participant = await ctx.wait_for_participant()
            logger.info(f"Participant joined room: {participant.identity}")

            # Initialize STT and TTS
            stt = deepgram.STT() if status["deepgram_stt"] else None
            tts = cartesia.TTS() if status["cartesia_tts"] else None

            if not stt or not tts:
                logger.error("STT or TTS credentials missing for LiveKit audio pipeline.")
                return

            # LiveKit VoiceAssistant orchestration
            assistant = VoiceAssistant(
                vad=agents.vad.VAD.load(),
                stt=stt,
                llm=openai.LLM.with_groq(model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")) if status["llm_provider"] else None,
                tts=tts,
            )

            # Custom turn handler to invoke backend tools and state machine
            @assistant.on("user_speech_committed")
            def on_user_speech(msg):
                asyncio.create_task(handle_user_turn(assistant, session_token, msg.content))

            assistant.start(ctx.room)
            logger.info("LiveKit VoiceAssistant active for participant.")

        async def handle_user_turn(assistant, session_token: str, user_text: str):
            if not user_text.strip():
                return
            logger.info(f"User spoken input in {session_token}: '{user_text}'")
            resp = await call_backend_agent(session_token, user_text)
            reply_text = resp.get("reply", "I am standing by.")
            logger.info(f"Agent reply to stream via TTS: '{reply_text}'")
            await assistant.say(reply_text)

        options = WorkerOptions(entrypoint_fnc=entrypoint)
        cli.run_app(options)

    except ImportError as e:
        logger.warning(f"LiveKit agent plugins not installed: {e}. Install via `pip install -r requirements.txt`.")
    except Exception as e:
        logger.error(f"LiveKit agent worker runtime error: {e}")

if __name__ == "__main__":
    asyncio.run(run_worker())
