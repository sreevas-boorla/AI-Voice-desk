from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models import ConversationSession, VerificationSession, Appointment
from app.services.audit_service import log_audit_event

MAX_ATTEMPTS = 5
VERIFICATION_TTL_MINUTES = 60

def get_or_create_session(db: Session, session_token: str, channel: str = "text") -> ConversationSession:
    """Retrieves an existing conversation session or creates a new one."""
    session = db.query(ConversationSession).filter(
        ConversationSession.session_token == session_token
    ).first()
    
    if not session:
        session = ConversationSession(
            session_token=session_token,
            channel=channel,
            created_at=datetime.utcnow(),
            last_active_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.last_active_at = datetime.utcnow()
        db.commit()
        
    return session

def verify_booking_access(
    db: Session,
    session_id: int,
    booking_reference: str,
    verification_code: str
) -> Tuple[bool, str]:
    """
    Validates a booking reference and verification code.
    If valid, binds verified access to the session for this booking reference.
    Enforces rate-limiting (max 5 failed attempts).
    """
    ref_clean = booking_reference.strip().upper()
    code_clean = verification_code.strip()
    
    # Check existing verification session state for rate limiting
    v_record = db.query(VerificationSession).filter(
        VerificationSession.session_id == session_id,
        VerificationSession.booking_reference == ref_clean
    ).first()

    if v_record and v_record.attempts >= MAX_ATTEMPTS:
        log_audit_event(
            db=db,
            entity_type="VERIFICATION",
            action="VERIFICATION_LOCKED",
            entity_id=ref_clean,
            details={"session_id": session_id, "attempts": v_record.attempts}
        )
        return False, "Maximum verification attempts exceeded for this session. Please contact reception."

    # Find the appointment in database
    appointment = db.query(Appointment).filter(
        Appointment.booking_reference == ref_clean
    ).first()

    if not appointment:
        if v_record:
            v_record.attempts += 1
            db.commit()
        else:
            v_record = VerificationSession(
                session_id=session_id,
                booking_reference=ref_clean,
                verification_code=code_clean,
                is_verified=False,
                attempts=1,
                expires_at=datetime.utcnow() + timedelta(minutes=VERIFICATION_TTL_MINUTES)
            )
            db.add(v_record)
            db.commit()
            
        log_audit_event(
            db=db,
            entity_type="VERIFICATION",
            action="VERIFICATION_FAILED_NOT_FOUND",
            entity_id=ref_clean,
            details={"session_id": session_id}
        )
        return False, f"No appointment found with booking reference '{ref_clean}'."

    # Validate verification code
    if appointment.verification_code.strip() != code_clean:
        if not v_record:
            v_record = VerificationSession(
                session_id=session_id,
                booking_reference=ref_clean,
                verification_code=code_clean,
                is_verified=False,
                attempts=1,
                expires_at=datetime.utcnow() + timedelta(minutes=VERIFICATION_TTL_MINUTES)
            )
            db.add(v_record)
        else:
            v_record.attempts += 1
        db.commit()
        
        log_audit_event(
            db=db,
            entity_type="VERIFICATION",
            action="VERIFICATION_FAILED_INVALID_CODE",
            entity_id=ref_clean,
            details={"session_id": session_id, "attempts": v_record.attempts}
        )
        remaining = MAX_ATTEMPTS - v_record.attempts
        return False, f"Incorrect verification code. {remaining} attempt(s) remaining."

    # Success: record verified session
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=VERIFICATION_TTL_MINUTES)
    
    if not v_record:
        v_record = VerificationSession(
            session_id=session_id,
            booking_reference=ref_clean,
            verification_code=code_clean,
            is_verified=True,
            attempts=1,
            verified_at=now,
            expires_at=expires_at
        )
        db.add(v_record)
    else:
        v_record.is_verified = True
        v_record.verified_at = now
        v_record.expires_at = expires_at

    db.commit()

    log_audit_event(
        db=db,
        entity_type="VERIFICATION",
        action="VERIFICATION_SUCCESSFUL",
        entity_id=ref_clean,
        details={"session_id": session_id}
    )
    return True, f"Successfully verified access for booking reference {ref_clean}."

def is_session_verified_for_booking(
    db: Session,
    session_id: int,
    booking_reference: str
) -> bool:
    """Verifies that the server session currently holds verified access for the booking reference."""
    ref_clean = booking_reference.strip().upper()
    v_record = db.query(VerificationSession).filter(
        VerificationSession.session_id == session_id,
        VerificationSession.booking_reference == ref_clean,
        VerificationSession.is_verified == True,
        VerificationSession.expires_at > datetime.utcnow()
    ).first()
    
    return v_record is not None
