import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse, ConfirmActionRequest
from app.services.verification_service import get_or_create_session
from app.services.booking_service import confirm_pending_action
from app.agent.engine import process_agent_message
from app.models import Message, ConversationSession, VerificationSession
from datetime import datetime

router = APIRouter(prefix="/api/agent", tags=["Agent"])

@router.post("/chat", response_model=ChatResponse)
def chat_with_agent(req: ChatRequest, db: Session = Depends(get_db)):
    session_token = req.session_token or f"sess_{uuid.uuid4().hex[:12]}"
    session = get_or_create_session(db, session_token=session_token, channel=req.channel)
    
    response = process_agent_message(
        db=db,
        session_id=session.id,
        user_message=req.message,
        channel=req.channel
    )
    return response

@router.post("/confirm")
def confirm_action_endpoint(req: ConfirmActionRequest, db: Session = Depends(get_db)):
    session = db.query(ConversationSession).filter(ConversationSession.session_token == req.session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    try:
        result = confirm_pending_action(
            db=db,
            session_id=session.id,
            action_id=req.action_id,
            confirmed=req.confirmed
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/session/{session_token}")
def get_session_history(session_token: str, db: Session = Depends(get_db)):
    session = db.query(ConversationSession).filter(ConversationSession.session_token == session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    messages = db.query(Message).filter(Message.session_id == session.id).order_by(Message.created_at.asc()).all()
    
    v_rec = db.query(VerificationSession).filter(
        VerificationSession.session_id == session.id,
        VerificationSession.is_verified == True,
        VerificationSession.expires_at > datetime.utcnow()
    ).first()

    return {
        "session_token": session.session_token,
        "channel": session.channel,
        "verified_reference": v_rec.booking_reference if v_rec else None,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls_json,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ]
    }
