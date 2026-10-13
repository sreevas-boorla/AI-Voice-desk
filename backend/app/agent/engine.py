import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ConversationSession, Message, VerificationSession, PendingAction
from app.agent.tools import ToolExecutor, TOOLS_SCHEMA
from app.agent.simulator import AgentSimulator
from app.schemas import ChatResponse, ToolExecutionEvent, PendingActionSummary

SYSTEM_PROMPT = f"""You are the agentic AI receptionist for CareBridge Clinic, a premier clinic located at Road No. 36, Jubilee Hills, Hyderabad, India.
Use the current local date supplied below. Resolve relative dates in Asia/Kolkata.

Operating Guidelines:
1. Handle administrative inquiries only: scheduling, rescheduling, cancellations, clinic hours, location, services, and consultation fees.
2. NEVER diagnose health conditions, suggest treatments, or prescribe medication. If a patient describes urgent symptoms, offer to connect them to emergency services or create a handoff request.
3. For existing appointments: you MUST verify access using 'verify_booking_access' with both the booking reference (e.g. CB-1001) and verification code before retrieving or modifying it.
4. For bookings, reschedules, or cancellations: ALWAYS call the respective prepare tool (prepare_booking, prepare_reschedule, prepare_cancellation). Show the exact doctor, date, time, and fee. Ask the user to use the confirmation card to approve or decline. You cannot confirm actions yourself.
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
            import groq
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY, timeout=settings.GROQ_TIMEOUT_SECONDS)
            # Fetch last 10 messages for context
            history = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at.asc()).all()[-10:]
            messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}]
            for h in history:
                messages_payload.append({"role": h.role if h.role in ("user", "assistant") else "user", "content": h.content})

            messages_payload[0]["content"] += "\nCurrent local date: " + datetime.now(ZoneInfo(settings.CLINIC_TIMEZONE)).strftime("%A, %Y-%m-%d")
            # Tool outputs must reach the model before it can choose its next step.
            for _ in range(8):
                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=messages_payload,
                    tools=[{"type": "function", "function": t} for t in TOOLS_SCHEMA
                           if t["name"] != "confirm_pending_action"],
                    tool_choice="auto",
                    timeout=settings.GROQ_TIMEOUT_SECONDS,
                )
                choice = response.choices[0].message
                if not choice.tool_calls:
                    reply_text = choice.content or "Please review and use the confirmation card to finalize any pending changes."
                    break
                messages_payload.append(choice.model_dump(exclude_none=True))
                for tc in choice.tool_calls:
                    if tc.function.name == "confirm_pending_action":
                        raise ValueError("Mutations require explicit user approval via the confirmation card.")
                    ev = executor.execute_tool(tc.function.name, json.loads(tc.function.arguments))
                    tool_events.append(ToolExecutionEvent(
                        tool_name=ev["tool_name"], status=ev["status"],
                        duration_ms=ev["duration_ms"], arguments={
                            k: ("[redacted]" if k in ("verification_code", "patient_phone") else v)
                            for k, v in ev["arguments"].items()
                        }, result_summary=ev["result_summary"],
                        timestamp=datetime.utcnow().isoformat(),
                    ))
                    if ev["status"] == "success" and ev["tool_name"] in ("prepare_booking", "prepare_reschedule", "prepare_cancellation"):
                        p_data = ev["data"]
                        pending_action_out = PendingActionSummary(
                            action_id=p_data["action_id"],
                            action_type=p_data["action_type"],
                            summary_text=p_data["summary_text"],
                            expires_at=p_data["expires_at"],
                            details=p_data["details"]
                        )
                    messages_payload.append({"role": "tool", "tool_call_id": tc.id,
                        "content": json.dumps({"status": ev["status"], "data": ev["data"],
                                               "summary": ev["result_summary"]}, default=str)})
            else:
                reply_text = "I reached the tool execution limit. Please narrow your request or review any pending confirmation card."
        except Exception as e:
            # Handle specific Groq errors if groq is imported and error is from groq
            err_type = type(e).__name__
            if "AuthenticationError" in err_type or "PermissionDenied" in err_type:
                reply_text = "The live AI provider rejected authentication. Please verify GROQ_API_KEY in your local environment."
            elif "RateLimit" in err_type:
                reply_text = "The live AI provider is currently rate-limited. Please wait a moment and try again."
            elif "Timeout" in err_type or "Connection" in err_type:
                reply_text = "The live AI request timed out or encountered a connection error. Please try again."
            else:
                # Never replay a request through a simulator after tools may have run.
                reply_text = "The live AI service is unavailable. Please try again. No action is confirmed by this message; review any pending confirmation card."
    elif not settings.DEMO_MODE:
        reply_text = "Live AI requires a GROQ_API_KEY on the server. Configure it or explicitly enable DEMO_MODE for the simulator."
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
