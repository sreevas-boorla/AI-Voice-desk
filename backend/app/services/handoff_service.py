from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import HandoffRequest
from app.services.audit_service import log_audit_event

def create_handoff_request(
    db: Session,
    session_id: Optional[int],
    patient_name: str,
    patient_phone: str,
    reason: str
) -> Dict[str, Any]:
    """Creates a human handoff request when inquiries cannot be automated."""
    handoff = HandoffRequest(
        session_id=session_id,
        patient_name=patient_name.strip(),
        patient_phone=patient_phone.strip(),
        reason=reason.strip(),
        status="OPEN"
    )
    db.add(handoff)
    db.commit()
    db.refresh(handoff)

    log_audit_event(
        db=db,
        entity_type="HANDOFF",
        action="HANDOFF_CREATED",
        entity_id=str(handoff.id),
        details={"patient_name": patient_name, "reason": reason}
    )

    return {
        "handoff_id": handoff.id,
        "patient_name": handoff.patient_name,
        "patient_phone": handoff.patient_phone,
        "status": handoff.status,
        "message": f"Your request has been forwarded to our human receptionist team. A coordinator will call you back at {handoff.patient_phone} shortly."
    }
