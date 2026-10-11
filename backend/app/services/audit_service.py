import json
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import AuditEvent

def log_audit_event(
    db: Session,
    entity_type: str,
    action: str,
    actor_type: str = "AGENT",
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> AuditEvent:
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        details_json=json.dumps(details) if details else None,
        created_at=datetime.utcnow()
    )
    db.add(event)
    db.flush()
    return event
