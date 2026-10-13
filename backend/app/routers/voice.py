import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.config import settings

router = APIRouter(prefix="/api/voice", tags=["Voice"])

class VoiceTokenRequest(BaseModel):
    session_token: str
    participant_name: Optional[str] = "Patient"

@router.get("/status")
def get_voice_status():
    livekit_ready = bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)
    return {
        "livekit_configured": livekit_ready,
        "mode_label": "LiveKit WebRTC" if livekit_ready else "Browser Web Speech",
        "active_engine": "livekit" if livekit_ready else "browser",
        "browser_speech_supported": True,
        "llm_configured": bool(settings.GROQ_API_KEY),
        "message": (
            "LiveKit credentials configured; WebRTC room streaming available."
            if livekit_ready
            else "LiveKit credentials not configured on server. Browser Web Speech mode is active and available."
        )
    }

@router.post("/token")
def get_voice_room_token(req: VoiceTokenRequest):
    if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit streaming server is not configured. Use browser voice or text chat."
        )

    try:
        from livekit.api import AccessToken, VideoGrants
        token = (
            AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(f"user_{uuid.uuid4().hex[:8]}")
            .with_name(req.participant_name or "Patient")
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=f"room_{req.session_token}",
                    can_publish=True,
                    can_subscribe=True
                )
            )
        )
        return {
            "livekit_url": settings.LIVEKIT_URL,
            "room_name": f"room_{req.session_token}",
            "token": token.to_jwt(),
            "session_token": req.session_token
        }
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="livekit-api package is not installed on the server."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate LiveKit room token: {str(e)}"
        )
