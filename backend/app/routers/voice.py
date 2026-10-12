from fastapi import APIRouter, HTTPException
from app.config import settings

router = APIRouter(prefix="/api/voice", tags=["Voice"])

@router.get("/status")
def get_voice_status():
    return {
        "live_mode": False,
        "mode_label": "Browser voice",
        "livekit_configured": bool(settings.LIVEKIT_URL),
        "llm_configured": bool(settings.GROQ_API_KEY),
        "stt_tts_provider": "Browser SpeechRecognition / SpeechSynthesis",
        "message": "Browser voice is available where supported. LiveKit streaming is not implemented. Speech recognition may use your browser vendor's remote service."
    }

@router.post("/token")
def get_voice_room_token():
    raise HTTPException(status_code=501, detail="LiveKit streaming is not implemented. Use browser voice or text chat.")
