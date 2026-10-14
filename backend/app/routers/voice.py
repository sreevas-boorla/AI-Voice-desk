import uuid
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.services.verification_service import get_or_create_session

router = APIRouter(prefix="/api/voice", tags=["Voice"])

class VoiceTokenRequest(BaseModel):
    session_token: str
    participant_name: Optional[str] = "Patient"

@router.get("/status")
def get_voice_status():
    """
    Accurately reports voice configuration without over-claiming connectivity.
    Credentials being present means 'configured', not 'connected' or 'active'.
    Browser speech support is derived on the client side via Web Speech API.
    """
    has_livekit_keys = bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)
    has_groq = bool(settings.GROQ_API_KEY)
    
    livekit_api_installed = False
    try:
        import livekit.api  # noqa: F401
        livekit_api_installed = True
    except ImportError:
        pass

    livekit_ready = has_livekit_keys and livekit_api_installed

    return {
        "livekit_configured": has_livekit_keys,
        "livekit_api_installed": livekit_api_installed,
        "livekit_ready": livekit_ready,
        "llm_configured": has_groq,
        "preferred_engine": "livekit" if livekit_ready else "browser",
        "message": (
            "LiveKit server credentials configured. Room tokens can be requested."
            if livekit_ready
            else "LiveKit credentials not configured on server. Browser Web Speech fallback is recommended."
        )
    }

@router.post("/token")
def get_voice_room_token(req: VoiceTokenRequest, db: Session = Depends(get_db)):
    """
    Generates a session-scoped, short-lived room token for LiveKit WebRTC.
    Binds the room token strictly to the server-validated session store.
    """
    if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit streaming credentials not configured on server. Please use Browser Web Speech fallback or text chat."
        )

    # 1. Validate and register conversation session
    if not req.session_token or not req.session_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_token is required to scope voice room."
        )

    session = get_or_create_session(db, req.session_token.strip(), channel="voice")
    
    # 2. Generate room-scoped token with explicit short lifetime (15 mins)
    try:
        from livekit.api import AccessToken, VideoGrants
        participant_identity = f"user_{session.session_token[:8]}_{uuid.uuid4().hex[:6]}"
        room_name = f"room_{session.session_token}"

        token = (
            AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(participant_identity)
            .with_name(req.participant_name or "Patient")
            .with_ttl(datetime.timedelta(minutes=15))
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True
                )
            )
        )

        return {
            "livekit_url": settings.LIVEKIT_URL,
            "room_name": room_name,
            "token": token.to_jwt(),
            "session_token": session.session_token,
            "identity": participant_identity,
            "expires_in_seconds": 900
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
