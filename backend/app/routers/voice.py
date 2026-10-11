import time
import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.config import settings

router = APIRouter(prefix="/api/voice", tags=["Voice"])

class VoiceTokenRequest(BaseModel):
    session_token: str
    room_name: Optional[str] = "carebridge-reception"
    participant_name: Optional[str] = "Patient"

class VoiceTokenResponse(BaseModel):
    mode: str  # "live" or "demo"
    room_name: str
    token: Optional[str] = None
    server_url: Optional[str] = None
    message: str

@router.get("/status")
def get_voice_status():
    has_livekit = bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)
    return {
        "live_mode": has_livekit and not settings.DEMO_MODE,
        "mode_label": "Live Mode (LiveKit WebRTC)" if (has_livekit and not settings.DEMO_MODE) else "Demo Mode (Simulation & Web Speech)",
        "livekit_configured": has_livekit,
        "llm_configured": bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENAI_API_KEY),
        "stt_tts_provider": "Deepgram + Cartesia / OpenAI" if has_livekit else "Browser Web Speech API (Local STT & TTS)",
        "message": (
            "Live WebRTC audio streaming active."
            if (has_livekit and not settings.DEMO_MODE)
            else "Running in Demo Mode. Uses browser SpeechRecognition & SpeechSynthesis with real database tools."
        )
    }

@router.post("/token", response_model=VoiceTokenResponse)
def get_voice_room_token(req: VoiceTokenRequest):
    has_livekit = bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)
    
    if has_livekit and not settings.DEMO_MODE:
        try:
            # Generate short-lived LiveKit Access Token
            now = int(time.time())
            claims = {
                "sub": f"patient_{req.session_token[:8]}",
                "iss": settings.LIVEKIT_API_KEY,
                "nbf": now - 5,
                "exp": now + 600,  # 10 minutes
                "name": req.participant_name,
                "video": {
                    "room": req.room_name,
                    "roomJoin": True,
                    "canPublish": True,
                    "canSubscribe": True,
                    "canPublishData": True
                }
            }
            token = jwt.encode(claims, settings.LIVEKIT_API_SECRET, algorithm="HS256")
            return VoiceTokenResponse(
                mode="live",
                room_name=req.room_name or "carebridge-reception",
                token=token,
                server_url=settings.LIVEKIT_URL,
                message="Short-lived room token generated for LiveKit session."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate LiveKit token: {str(e)}")

    # Return demo mode descriptor
    return VoiceTokenResponse(
        mode="demo",
        room_name=req.room_name or "carebridge-reception",
        token="demo_simulated_token",
        server_url="simulated://local-webrtc",
        message="Demo simulation mode active. Frontend operates local SpeechRecognition/SpeechSynthesis with backend tool execution."
    )
