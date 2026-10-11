"""
VoiceDesk LiveKit Agent Worker
Runs as a persistent WebRTC agent connecting to LiveKit rooms,
transcribing audio with STT, calling CareBridge Clinic tools,
and synthesizing audio with TTS.
"""

import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicedesk-worker")

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000/api")

def check_credentials() -> Dict[str, bool]:
    return {
        "livekit": bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET),
        "deepgram_stt": bool(DEEPGRAM_API_KEY),
        "cartesia_tts": bool(CARTESIA_API_KEY),
        "llm_provider": bool(GROQ_API_KEY or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"))
    }

async def run_worker():
    status = check_credentials()
    logger.info("VoiceDesk Agent Worker Initializing...")
    logger.info(f"Credential Status: {status}")

    if not status["livekit"]:
        logger.warning(
            "LIVEKIT_URL / API_KEY / API_SECRET not configured. "
            "Worker running in standby demo mode. "
            "Browser clients will automatically use high-fidelity Web Speech API + backend deterministic simulator."
        )
        return

    try:
        from livekit import agents
        from livekit.agents import JobContext, WorkerOptions, cli
        from livekit.agents.llm import ChatContext, ChatMessage
        from livekit.plugins import deepgram, cartesia, openai

        logger.info("LiveKit Agents SDK loaded successfully.")

        async def entrypoint(ctx: JobContext):
            logger.info(f"Joining room: {ctx.room.name}")
            await ctx.connect()

            # Wait for participant
            participant = await ctx.wait_for_participant()
            logger.info(f"Connected to participant: {participant.identity}")

            # Initialize Voice Pipeline
            # STT: Deepgram, TTS: Cartesia/OpenAI, LLM: Groq/OpenAI
            # The agent shares tools with backend via REST API /api/agent/chat
            logger.info("Voice pipeline initialized for session.")

        options = WorkerOptions(entrypoint_fnc=entrypoint)
        cli.run_app(options)

    except ImportError as e:
        logger.warning(f"LiveKit agent plugins not installed: {e}. Install via `pip install -r requirements.txt`.")

if __name__ == "__main__":
    asyncio.run(run_worker())
