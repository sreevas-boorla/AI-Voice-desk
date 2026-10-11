import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ConversationSession, Message, VerificationSession, PendingAction
from app.agent.tools import ToolExecutor, TOOLS_SCHEMA
from app.agent.simulator import AgentSimulator
from app.schemas import ChatResponse, ToolExecutionEvent, PendingActionSummary

SYSTEM_PROMPT = f"""You are the agentic AI receptionist for CareBridge Clinic, a premier clinic located at Road No. 36, Jubilee Hills, Hyderabad, India.
Today's local date is Sunday, October 11, 2026, in the Asia/Kolkata timezone (IST, UTC+5:30).
Tomorrow is Monday, October 12, 2026.

Operating Guidelines:
1. Handle administrative inquiries only: scheduling, rescheduling, cancellations, clinic hours, location, services, and consultation fees.
2. NEVER diagnose health conditions, suggest treatments, or prescribe medication. If a patient describes urgent symptoms, offer to connect them to emergency services or create a handoff request.
3. For existing appointments: you MUST verify access using 'verify_booking_access' with both the booking reference (e.g. CB-1001) and verification code before retrieving or modifying it.
4. For bookings, reschedules, or cancellations: ALWAYS call the respective prepare tool (prepare_booking, prepare_reschedule, prepare_cancellation). Show the exact doctor, date, time, and fee. Require explicit confirmation before calling 'confirm_pending_action'.
5. Keep conversational responses concise, clear, and professional.
"""

def process_agent_message(
    db: Session,
    session_id: int,
    user_message: str,
    channel: str = "text"
) -> ChatResponse:
    """Processes a user message through the tool-calling agent engine."""
    # Persist user message
    user_msg_record = Message(
        session_id=session_id,
        role="user",
        content=user_message,
        created_at=datetime.utcnow()
    )
    db.add(user_msg_record)
    db.commit()

    executor = ToolExecutor(db=db, session_id=session_id)
    
    # Check if live LLM is configured and not in forced demo mode
    # For robust deterministic evaluation & local demo, simulator is always available
    use_live_llm = False
    if not settings.DEMO_MODE and (settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENAI_API_KEY):
        use_live_llm = True

    tool_events: List[ToolExecutionEvent] = []
    pending_action_out: Optional[PendingActionSummary] = None
    reply_text = ""

    if use_live_llm and settings.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            # Fetch last 10 messages for context
            history = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at.asc()).all()[-10:]
            messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}]
            for h in history:
                messages_payload.append({"role": h.role if h.role in ("user", "assistant") else "user", "content": h.content})

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages_payload,
                tools=[{"type": "function", "function": t} for t in TOOLS_SCHEMA],
                tool_choice="auto"
            )
            choice = response.choices[0].message
            if choice.tool_calls:
                for tc in choice.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    ev = executor.execute_tool(fn_name, fn_args)
                    tool_events.append(ToolExecutionEvent(
                        tool_name=ev["tool_name"],
                        status=ev["status"],
                        duration_ms=ev["duration_ms"],
                        arguments=ev["arguments"],
                        result_summary=ev["result_summary"],
                        timestamp=datetime.utcnow().isoformat()
                    ))
                # Second turn with tool response
                reply_text = choice.content or ev["result_summary"]
            else:
                reply_text = choice.content or "How may I help you at CareBridge Clinic?"
        except Exception as e:
            # Fallback to simulator if LLM call fails
            sim = AgentSimulator(executor)
            reply_text, raw_events, raw_pending = sim.process(user_message)
            for ev in raw_events:
                tool_events.append(ToolExecutionEvent(
                    tool_name=ev["tool_name"],
                    status=ev["status"],
                    duration_ms=ev["duration_ms"],
                    arguments=ev["arguments"],
                    result_summary=ev["result_summary"],
                    timestamp=datetime.utcnow().isoformat()
                ))
            if raw_pending:
                pending_action_out = PendingActionSummary(
                    action_id=raw_pending["action_id"],
                    action_type=raw_pending["action_type"],
                    summary_text=raw_pending["summary_text"],
                    expires_at=raw_pending["expires_at"],
                    details=raw_pending["details"]
                )
    else:
        # High-reliability Agent Simulator
        sim = AgentSimulator(executor)
        reply_text, raw_events, raw_pending = sim.process(user_message)
        for ev in raw_events:
            tool_events.append(ToolExecutionEvent(
                tool_name=ev["tool_name"],
                status=ev["status"],
                duration_ms=ev["duration_ms"],
                arguments=ev["arguments"],
                result_summary=ev["result_summary"],
                timestamp=datetime.utcnow().isoformat()
            ))
        if raw_pending:
            pending_action_out = PendingActionSummary(
                action_id=raw_pending["action_id"],
                action_type=raw_pending["action_type"],
                summary_text=raw_pending["summary_text"],
                expires_at=raw_pending["expires_at"],
                details=raw_pending["details"]
            )

    # Persist Assistant reply
    asst_msg = Message(
        session_id=session_id,
        role="assistant",
        content=reply_text,
        tool_calls_json=json.dumps([e.model_dump() for e in tool_events]) if tool_events else None,
        created_at=datetime.utcnow()
    )
    db.add(asst_msg)
    db.commit()

    # Get session token and verification status
    session = db.query(ConversationSession).filter(ConversationSession.id == session_id).first()
    verified_ref = None
    v_rec = db.query(VerificationSession).filter(
        VerificationSession.session_id == session_id,
        VerificationSession.is_verified == True,
        VerificationSession.expires_at > datetime.utcnow()
    ).first()
    if v_rec:
        verified_ref = v_rec.booking_reference

    # If pending action wasn't set in this turn, check if an unexpired one is awaiting confirmation
    if not pending_action_out:
        active_pending = db.query(PendingAction).filter(
            PendingAction.session_id == session_id,
            PendingAction.status == "PENDING",
            PendingAction.expires_at > datetime.utcnow()
        ).order_by(PendingAction.created_at.desc()).first()
        if active_pending:
            p_data = json.loads(active_pending.payload_json)
            summary_text = (
                f"Pending {active_pending.action_type}: {p_data.get('formatted_date', '')} "
                f"with {p_data.get('provider_name', '')}."
            )
            pending_action_out = PendingActionSummary(
                action_id=active_pending.id,
                action_type=active_pending.action_type,
                summary_text=summary_text,
                expires_at=active_pending.expires_at.isoformat(),
                details=p_data
            )

    return ChatResponse(
        session_token=session.session_token if session else "",
        reply=reply_text,
        pending_action=pending_action_out,
        tool_events=tool_events,
        verified_reference=verified_ref
    )
