import re
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.database import get_db
from app.models import (
    AdminUser, Appointment, Provider, ProviderSchedule, BlockedSlot,
    HandoffRequest, ConversationSession, Message, AuditEvent, Patient
)
from app.auth import verify_password, create_access_token, get_current_admin
from app.schemas import AdminLoginRequest, TokenResponse, AdminDashboardStats, HandoffOut
from app.services.availability_service import IST

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.post("/login", response_model=TokenResponse)
def admin_login(req: AdminLoginRequest, db: Session = Depends(get_db)):
    admin = db.query(AdminUser).filter(AdminUser.username == req.username).first()
    if not admin or not verify_password(req.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    token = create_access_token(data={"sub": admin.username, "role": admin.role})
    return TokenResponse(access_token=token)

@router.get("/me")
def get_current_admin_user(current_admin: AdminUser = Depends(get_current_admin)):
    return {"username": current_admin.username, "role": current_admin.role}

@router.get("/stats", response_model=AdminDashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    total = db.query(Appointment).count()
    confirmed = db.query(Appointment).filter(Appointment.status == "CONFIRMED").count()
    rescheduled = db.query(Appointment).filter(Appointment.status == "RESCHEDULED").count()
    cancelled = db.query(Appointment).filter(Appointment.status == "CANCELLED").count()

    today_ist = datetime.now(IST).date()
    start_today = datetime.combine(today_ist, time.min)
    end_today = datetime.combine(today_ist, time.max)
    today_count = db.query(Appointment).filter(
        Appointment.start_time >= start_today,
        Appointment.start_time <= end_today
    ).count()

    open_handoffs = db.query(HandoffRequest).filter(HandoffRequest.status == "OPEN").count()
    active_providers = db.query(Provider).filter(Provider.is_active == True).count()

    return AdminDashboardStats(
        total_appointments=total,
        confirmed_appointments=confirmed,
        rescheduled_appointments=rescheduled,
        cancelled_appointments=cancelled,
        today_appointments=today_count,
        open_handoffs=open_handoffs,
        active_providers=active_providers
    )

@router.get("/appointments")
def list_appointments(
    search: Optional[str] = Query(None),
    provider_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    date_filter: Optional[str] = Query(None),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    query = db.query(Appointment).join(Patient).join(Provider)

    if provider_id:
        query = query.filter(Appointment.provider_id == provider_id)
    if status and status.upper() != "ALL":
        query = query.filter(Appointment.status == status.upper())
    if date_filter:
        try:
            d = datetime.strptime(date_filter, "%Y-%m-%d").date()
            query = query.filter(
                Appointment.start_time >= datetime.combine(d, time.min),
                Appointment.start_time <= datetime.combine(d, time.max)
            )
        except ValueError:
            pass

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Appointment.booking_reference.ilike(s),
                Patient.full_name.ilike(s),
                Patient.phone.ilike(s),
                Provider.name.ilike(s)
            )
        )

    total_records = query.count()
    appointments = query.order_by(Appointment.start_time.desc()).offset(offset).limit(limit).all()

    items = []
    for app in appointments:
        start_aware = app.start_time.replace(tzinfo=IST) if app.start_time.tzinfo is None else app.start_time.astimezone(IST)
        end_aware = app.end_time.replace(tzinfo=IST) if app.end_time.tzinfo is None else app.end_time.astimezone(IST)
        items.append({
            "id": app.id,
            "booking_reference": app.booking_reference,
            "patient_name": app.patient.full_name,
            "patient_phone": app.patient.phone,
            "provider_id": app.provider_id,
            "provider_name": app.provider.name,
            "provider_specialty": app.provider.specialty,
            "service_name": app.service.name if app.service else "Consultation",
            "fee": app.service.fee if app.service else app.provider.consultation_fee,
            "start_time": start_aware.isoformat(),
            "end_time": end_aware.isoformat(),
            "formatted_date": start_aware.strftime("%d %b %Y"),
            "formatted_time": f"{start_aware.strftime('%I:%M %p')} - {end_aware.strftime('%I:%M %p')}",
            "status": app.status,
            "verification_code": app.verification_code,
            "notes": app.notes,
            "created_at": app.created_at.isoformat()
        })

    return {"total": total_records, "items": items}

@router.get("/schedules")
def get_schedules_overview(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    providers = db.query(Provider).filter(Provider.is_active == True).all()
    results = []
    days_map = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for p in providers:
        p_scheds = []
        for s in p.schedules:
            p_scheds.append({
                "id": s.id,
                "day_of_week": s.day_of_week,
                "day_name": days_map[s.day_of_week],
                "start_time": s.start_time,
                "end_time": s.end_time,
                "break_start": s.break_start,
                "break_end": s.break_end,
                "is_active": s.is_active
            })
        p_blocked = []
        for b in p.blocked_slots:
            p_blocked.append({
                "id": b.id,
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "reason": b.reason
            })
        results.append({
            "provider_id": p.id,
            "provider_name": p.name,
            "specialty": p.specialty,
            "schedules": p_scheds,
            "blocked_slots": p_blocked
        })
    return results

@router.get("/handoffs", response_model=List[HandoffOut])
def list_handoffs(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    query = db.query(HandoffRequest)
    if status and status.upper() != "ALL":
        query = query.filter(HandoffRequest.status == status.upper())
    return query.order_by(HandoffRequest.created_at.desc()).all()

@router.put("/handoffs/{handoff_id}")
def update_handoff_status(
    handoff_id: int,
    status: str = Query(..., description="OPEN, IN_PROGRESS, RESOLVED"),
    notes: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    handoff = db.query(HandoffRequest).filter(HandoffRequest.id == handoff_id).first()
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff request not found.")
        
    handoff.status = status.upper()
    if notes:
        handoff.notes = notes
    if status.upper() == "RESOLVED":
        handoff.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Handoff status updated", "handoff_id": handoff_id, "status": handoff.status}

@router.get("/transcripts")
def get_redacted_transcripts(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Returns conversation transcripts with sensitive verification codes
    and patient phone numbers masked for HIPAA/data privacy compliance.
    """
    sessions = db.query(ConversationSession).order_by(ConversationSession.last_active_at.desc()).limit(limit).all()
    out = []

    for s in sessions:
        msgs = db.query(Message).filter(Message.session_id == s.id).order_by(Message.created_at.asc()).all()
        redacted_msgs = []
        for m in msgs:
            # Mask 4-digit verification codes and phone numbers in transcript preview
            content_masked = re.sub(r"(code\s*(?:is)?\s*)\b\d{4}\b", r"\1****", m.content, flags=re.IGNORECASE)
            content_masked = re.sub(r"(\+?\d[\d\s-]{6,10})(\d{4})", r"****-****-\2", content_masked)
            redacted_msgs.append({
                "id": m.id,
                "role": m.role,
                "content": content_masked,
                "created_at": m.created_at.isoformat()
            })
        out.append({
            "session_id": s.id,
            "session_token": s.session_token[:8] + "...",
            "channel": s.channel,
            "message_count": len(msgs),
            "created_at": s.created_at.isoformat(),
            "messages": redacted_msgs
        })
    return out

@router.get("/audit-logs")
def get_audit_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    events = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "action": e.action,
            "actor_type": e.actor_type,
            "details": e.details_json,
            "created_at": e.created_at.isoformat()
        }
        for e in events
    ]
