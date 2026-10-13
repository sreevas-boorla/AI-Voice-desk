import uuid
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse, ConfirmActionRequest
from app.services.verification_service import get_or_create_session
from app.services.booking_service import confirm_pending_action
from app.agent.engine import process_agent_message
from app.models import Message, ConversationSession, VerificationSession, PendingAction

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

@router.get("/action-result/{action_id}")
def get_action_result(
    action_id: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Retrieves the authoritative persisted result of a confirmed or rejected action.
    Pure read-only operation: does NOT execute or repeat mutations.
    Requires Authorization: Bearer <session_token> header. Rejects missing, malformed,
    or invalid authorization without retaining query-string authentication.
    Enforces session isolation and rejects pending, superseded, or expired actions.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <session_token>'."
        )

    session_token = parts[1]
    if not session_token:
        raise HTTPException(status_code=401, detail="Invalid session token.")

    session = db.query(ConversationSession).filter(ConversationSession.session_token == session_token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    pending = db.query(PendingAction).filter(
        PendingAction.id == action_id
    ).first()

    if not pending:
        raise HTTPException(status_code=404, detail="Action not found.")

    # Cross-session verification: reject if action belongs to a different session
    if pending.session_id != session.id:
        raise HTTPException(status_code=403, detail="Cross-session action access forbidden.")

    # Reject actions that have not reached a final persisted result state
    if pending.status == "PENDING":
        raise HTTPException(status_code=400, detail="Action is still pending confirmation.")
    if pending.status == "SUPERSEDED":
        raise HTTPException(status_code=400, detail="Action was superseded by a newer scheduling request.")
    if pending.status == "EXPIRED":
        raise HTTPException(status_code=400, detail="Action has expired.")

    payload = json.loads(pending.payload_json) if pending.payload_json else {}

    # Format authoritative message based on persisted database state
    if pending.status == "CONFIRMED":
        if pending.action_type == "BOOK":
            ref = payload.get("booking_reference", "")
            message = f"Your appointment has been successfully booked with reference {ref}."
        elif pending.action_type == "RESCHEDULE":
            ref = payload.get("booking_reference", "")
            new_date = payload.get("new_formatted_date", "")
            new_time = payload.get("new_formatted_time", "")
            if new_date and new_time:
                message = f"Appointment {ref} has been successfully rescheduled for {new_date} at {new_time}."
            else:
                message = f"Appointment {ref} has been successfully rescheduled."
        elif pending.action_type == "CANCEL":
            ref = payload.get("booking_reference", "")
            message = f"Appointment {ref} has been successfully cancelled."
        else:
            message = "Your request has been successfully confirmed."
    elif pending.status == "REJECTED":
        message = "Action was cancelled. No changes were made to any appointments."
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action status: {pending.status}")

    return {
        "action_id": pending.id,
        "status": pending.status,
        "action_type": pending.action_type,
        "message": message,
        "details": payload
    }
