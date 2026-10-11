import json
import random
import string
from datetime import datetime, timedelta, time
from typing import Optional, Dict, Any, Tuple, List
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import (
    Provider, Service, Patient, Appointment, PendingAction,
    ConversationSession, ProviderSchedule, BlockedSlot
)
from app.config import settings
from app.services.availability_service import (
    IST, get_now_ist, parse_iso_datetime, get_available_slots,
    find_alternative_slots
)
from app.services.verification_service import is_session_verified_for_booking
from app.services.audit_service import log_audit_event

def generate_booking_reference(db: Session) -> str:
    """Generates a unique reference like CB-8492."""
    for _ in range(20):
        suffix = "".join(random.choices(string.digits, k=4))
        ref = f"CB-{suffix}"
        if not db.query(Appointment).filter(Appointment.booking_reference == ref).first():
            return ref
    return f"CB-{random.randint(10000, 99999)}"

def generate_verification_code() -> str:
    """Generates a 4-digit numeric verification code."""
    return "".join(random.choices(string.digits, k=4))

def validate_slot_availability(
    db: Session,
    provider_id: int,
    start_dt: datetime,
    end_dt: datetime,
    exclude_appointment_id: Optional[int] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validates whether a slot can be reserved:
    - Must not be in the past.
    - Must align with provider schedule.
    - Must not overlap breaks.
    - Must not overlap blocked slots.
    - Must not overlap existing active appointments.
    """
    now_ist = get_now_ist()
    if start_dt <= now_ist:
        return False, "Cannot book an appointment in the past."

    weekday = start_dt.date().weekday()
    schedules = db.query(ProviderSchedule).filter(
        ProviderSchedule.provider_id == provider_id,
        ProviderSchedule.day_of_week == weekday,
        ProviderSchedule.is_active == True
    ).all()

    if not schedules:
        return False, "Provider is not scheduled to work on this day."

    # Verify fits in one schedule window and doesn't collide with break
    fits_schedule = False
    for sched in schedules:
        sched_start = time.fromisoformat(sched.start_time)
        sched_end = time.fromisoformat(sched.end_time)
        s_time = start_dt.time()
        e_time = end_dt.time()

        if s_time >= sched_start and e_time <= sched_end:
            # Check break
            if sched.break_start and sched.break_end:
                b_start = time.fromisoformat(sched.break_start)
                b_end = time.fromisoformat(sched.break_end)
                if not (e_time <= b_start or s_time >= b_end):
                    return False, f"Requested time falls during provider's scheduled break ({sched.break_start} - {sched.break_end})."
            fits_schedule = True
            break

    if not fits_schedule:
        return False, "Requested time is outside provider's operating hours."

    # Check blocked slots
    # Compare with naive datetime if database stores naive
    dt_start_naive = start_dt.replace(tzinfo=None)
    dt_end_naive = end_dt.replace(tzinfo=None)

    blocked = db.query(BlockedSlot).filter(
        BlockedSlot.provider_id == provider_id,
        BlockedSlot.start_time < dt_end_naive,
        BlockedSlot.end_time > dt_start_naive
    ).first()
    if blocked:
        return False, f"Provider is unavailable during this time: {blocked.reason}."

    # Check active appointments
    query = db.query(Appointment).filter(
        Appointment.provider_id == provider_id,
        Appointment.status.in_(["CONFIRMED", "RESCHEDULED"]),
        Appointment.start_time == dt_start_naive
    )
    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)
        
    existing = query.first()
    if existing:
        return False, "This appointment slot is already booked."

    return True, None

# --- Prepare Mutations ---

def prepare_booking(
    db: Session,
    session_id: int,
    patient_name: str,
    patient_phone: str,
    provider_id: int,
    start_time_iso: str,
    service_id: Optional[int] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Prepares a pending booking action with validation and preview."""
    provider = db.query(Provider).filter(Provider.id == provider_id, Provider.is_active == True).first()
    if not provider:
        raise ValueError(f"Provider ID {provider_id} not found or inactive.")

    if not service_id:
        service = db.query(Service).filter(Service.is_active == True).first()
    else:
        service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise ValueError("Service not found.")

    start_dt = parse_iso_datetime(start_time_iso)
    end_dt = start_dt + timedelta(minutes=service.duration_minutes)

    is_valid, error_msg = validate_slot_availability(db, provider_id, start_dt, end_dt)
    if not is_valid:
        alternatives = find_alternative_slots(db, provider_id, start_dt, count=3)
        alt_str = ", ".join([a["formatted_time"] + f" ({a['start_time'][:10]})" for a in alternatives]) if alternatives else "None available soon"
        raise ValueError(f"{error_msg} Alternatives: {alt_str}")

    payload = {
        "action": "BOOK",
        "patient_name": patient_name.strip(),
        "patient_phone": patient_phone.strip(),
        "provider_id": provider.id,
        "provider_name": provider.name,
        "provider_specialty": provider.specialty,
        "service_id": service.id,
        "service_name": service.name,
        "fee": service.fee,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "formatted_date": start_dt.strftime("%A, %d %B %Y"),
        "formatted_time": f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}",
        "notes": notes
    }

    pending = PendingAction(
        session_id=session_id,
        action_type="BOOK",
        payload_json=json.dumps(payload),
        status="PENDING",
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    summary_text = (
        f"Booking with {provider.name} ({provider.specialty}) on {payload['formatted_date']} "
        f"at {payload['formatted_time']} for {patient_name} (Fee: ₹{service.fee})."
    )

    return {
        "action_id": pending.id,
        "action_type": "BOOK",
        "summary_text": summary_text,
        "expires_at": pending.expires_at.isoformat(),
        "details": payload
    }

def prepare_reschedule(
    db: Session,
    session_id: int,
    booking_reference: str,
    new_start_time_iso: str
) -> Dict[str, Any]:
    """Prepares an atomic reschedule pending action. Requires verified session access."""
    ref_clean = booking_reference.strip().upper()
    if not is_session_verified_for_booking(db, session_id, ref_clean):
        raise PermissionError(
            f"Access denied: You must verify booking reference {ref_clean} with your verification code before rescheduling."
        )

    appointment = db.query(Appointment).filter(Appointment.booking_reference == ref_clean).first()
    if not appointment:
        raise ValueError(f"Appointment {ref_clean} not found.")

    if appointment.status not in ("CONFIRMED", "RESCHEDULED"):
        raise ValueError(f"Appointment {ref_clean} cannot be rescheduled because its status is {appointment.status}.")

    new_start_dt = parse_iso_datetime(new_start_time_iso)
    duration = appointment.service.duration_minutes if appointment.service else 30
    new_end_dt = new_start_dt + timedelta(minutes=duration)

    is_valid, error_msg = validate_slot_availability(
        db, appointment.provider_id, new_start_dt, new_end_dt, exclude_appointment_id=appointment.id
    )
    if not is_valid:
        alternatives = find_alternative_slots(db, appointment.provider_id, new_start_dt, count=3)
        alt_str = ", ".join([a["formatted_time"] + f" ({a['start_time'][:10]})" for a in alternatives]) if alternatives else "None"
        raise ValueError(f"{error_msg} Alternatives: {alt_str}")

    old_start_aware = appointment.start_time.replace(tzinfo=IST) if appointment.start_time.tzinfo is None else appointment.start_time.astimezone(IST)

    payload = {
        "action": "RESCHEDULE",
        "appointment_id": appointment.id,
        "booking_reference": ref_clean,
        "patient_name": appointment.patient.full_name,
        "patient_phone": appointment.patient.phone,
        "provider_id": appointment.provider_id,
        "provider_name": appointment.provider.name,
        "old_start_time": old_start_aware.isoformat(),
        "old_formatted_date": old_start_aware.strftime("%A, %d %B %Y at %I:%M %p"),
        "new_start_time": new_start_dt.isoformat(),
        "new_end_time": new_end_dt.isoformat(),
        "new_formatted_date": new_start_dt.strftime("%A, %d %B %Y"),
        "new_formatted_time": f"{new_start_dt.strftime('%I:%M %p')} - {new_end_dt.strftime('%I:%M %p')}"
    }

    pending = PendingAction(
        session_id=session_id,
        action_type="RESCHEDULE",
        payload_json=json.dumps(payload),
        status="PENDING",
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    summary_text = (
        f"Reschedule appointment {ref_clean} for {appointment.patient.full_name} with {appointment.provider.name} "
        f"from {payload['old_formatted_date']} to {payload['new_formatted_date']} at {payload['new_formatted_time']}."
    )

    return {
        "action_id": pending.id,
        "action_type": "RESCHEDULE",
        "summary_text": summary_text,
        "expires_at": pending.expires_at.isoformat(),
        "details": payload
    }

def prepare_cancellation(
    db: Session,
    session_id: int,
    booking_reference: str,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """Prepares a cancellation pending action. Requires verified session access."""
    ref_clean = booking_reference.strip().upper()
    if not is_session_verified_for_booking(db, session_id, ref_clean):
        raise PermissionError(
            f"Access denied: You must verify booking reference {ref_clean} with your verification code before cancelling."
        )

    appointment = db.query(Appointment).filter(Appointment.booking_reference == ref_clean).first()
    if not appointment:
        raise ValueError(f"Appointment {ref_clean} not found.")

    if appointment.status == "CANCELLED":
        raise ValueError(f"Appointment {ref_clean} is already cancelled.")

    start_aware = appointment.start_time.replace(tzinfo=IST) if appointment.start_time.tzinfo is None else appointment.start_time.astimezone(IST)

    payload = {
        "action": "CANCEL",
        "appointment_id": appointment.id,
        "booking_reference": ref_clean,
        "patient_name": appointment.patient.full_name,
        "provider_name": appointment.provider.name,
        "formatted_date": start_aware.strftime("%A, %d %B %Y at %I:%M %p"),
        "reason": reason or "Patient requested cancellation"
    }

    pending = PendingAction(
        session_id=session_id,
        action_type="CANCEL",
        payload_json=json.dumps(payload),
        status="PENDING",
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    summary_text = (
        f"Cancel appointment {ref_clean} for {appointment.patient.full_name} with {appointment.provider.name} "
        f"scheduled on {payload['formatted_date']}."
    )

    return {
        "action_id": pending.id,
        "action_type": "CANCEL",
        "summary_text": summary_text,
        "expires_at": pending.expires_at.isoformat(),
        "details": payload
    }

# --- Commit / Confirm Pending Action ---

def confirm_pending_action(
    db: Session,
    session_id: int,
    action_id: str,
    confirmed: bool
) -> Dict[str, Any]:
    """
    Executes or rejects a pending action with idempotency and atomic transactional safety.
    """
    pending = db.query(PendingAction).filter(
        PendingAction.id == action_id,
        PendingAction.session_id == session_id
    ).first()

    if not pending:
        raise ValueError(f"Pending action '{action_id}' not found for this session.")

    # Idempotency check: if already confirmed, return success without duplicating
    if pending.status == "CONFIRMED":
        payload = json.loads(pending.payload_json)
        return {
            "success": True,
            "status": "CONFIRMED",
            "message": "This action has already been confirmed and executed.",
            "action_type": pending.action_type,
            "details": payload
        }

    if pending.status == "REJECTED":
        return {
            "success": False,
            "status": "REJECTED",
            "message": "This action was previously declined.",
            "action_type": pending.action_type
        }

    if pending.expires_at < datetime.utcnow():
        pending.status = "EXPIRED"
        db.commit()
        raise ValueError("This confirmation request has expired. Please request a new slot.")

    if not confirmed:
        pending.status = "REJECTED"
        db.commit()
        log_audit_event(
            db=db,
            entity_type="PENDING_ACTION",
            action="ACTION_DECLINED_BY_USER",
            entity_id=action_id,
            details={"action_type": pending.action_type}
        )
        return {
            "success": True,
            "status": "REJECTED",
            "message": "Action was cancelled by user. No changes were made to any bookings.",
            "action_type": pending.action_type
        }

    # Execute Confirmed Action
    payload = json.loads(pending.payload_json)
    action_type = pending.action_type

    if action_type == "BOOK":
        start_dt = parse_iso_datetime(payload["start_time"])
        end_dt = parse_iso_datetime(payload["end_time"])

        # Revalidate slot right at commit time
        is_valid, error_msg = validate_slot_availability(db, payload["provider_id"], start_dt, end_dt)
        if not is_valid:
            raise ValueError(f"Cannot complete booking: {error_msg}")

        # Find or create patient
        patient = db.query(Patient).filter(Patient.phone == payload["patient_phone"]).first()
        if not patient:
            patient = Patient(
                full_name=payload["patient_name"],
                phone=payload["patient_phone"]
            )
            db.add(patient)
            db.flush()

        booking_ref = generate_booking_reference(db)
        verif_code = generate_verification_code()

        appointment = Appointment(
            booking_reference=booking_ref,
            patient_id=patient.id,
            provider_id=payload["provider_id"],
            service_id=payload["service_id"],
            start_time=start_dt.replace(tzinfo=None),
            end_time=end_dt.replace(tzinfo=None),
            status="CONFIRMED",
            verification_code=verif_code,
            notes=payload.get("notes")
        )

        try:
            db.add(appointment)
            pending.status = "CONFIRMED"
            payload["booking_reference"] = booking_ref
            payload["verification_code"] = verif_code
            pending.payload_json = json.dumps(payload)
            db.commit()
            db.refresh(appointment)
        except IntegrityError:
            db.rollback()
            raise ValueError("Conflict detected: This slot was just booked by another patient. Please choose an alternative.")

        log_audit_event(
            db=db,
            entity_type="APPOINTMENT",
            action="BOOKED",
            entity_id=booking_ref,
            details=payload
        )

        # Automatically verify current session for this new appointment
        from app.services.verification_service import verify_booking_access
        verify_booking_access(db, session_id, booking_ref, verif_code)

        return {
            "success": True,
            "status": "CONFIRMED",
            "message": f"Appointment successfully booked with reference {booking_ref}.",
            "action_type": "BOOK",
            "booking_reference": booking_ref,
            "verification_code": verif_code,
            "details": payload
        }

    elif action_type == "RESCHEDULE":
        appointment = db.query(Appointment).filter(Appointment.id == payload["appointment_id"]).first()
        if not appointment:
            raise ValueError("Target appointment not found.")

        new_start_dt = parse_iso_datetime(payload["new_start_time"])
        new_end_dt = parse_iso_datetime(payload["new_end_time"])

        # Re-verify availability at commit time
        is_valid, error_msg = validate_slot_availability(
            db, appointment.provider_id, new_start_dt, new_end_dt, exclude_appointment_id=appointment.id
        )
        if not is_valid:
            # Atomic: original appointment remains intact!
            raise ValueError(f"Cannot complete reschedule: {error_msg}")

        try:
            appointment.start_time = new_start_dt.replace(tzinfo=None)
            appointment.end_time = new_end_dt.replace(tzinfo=None)
            appointment.status = "RESCHEDULED"
            appointment.updated_at = datetime.utcnow()
            pending.status = "CONFIRMED"
            db.commit()
            db.refresh(appointment)
        except IntegrityError:
            db.rollback()
            raise ValueError("Conflict detected: Target slot was just booked by another patient. Original appointment is preserved.")

        log_audit_event(
            db=db,
            entity_type="APPOINTMENT",
            action="RESCHEDULED",
            entity_id=appointment.booking_reference,
            details=payload
        )

        return {
            "success": True,
            "status": "CONFIRMED",
            "message": f"Appointment {appointment.booking_reference} has been successfully rescheduled.",
            "action_type": "RESCHEDULE",
            "booking_reference": appointment.booking_reference,
            "details": payload
        }

    elif action_type == "CANCEL":
        appointment = db.query(Appointment).filter(Appointment.id == payload["appointment_id"]).first()
        if not appointment:
            raise ValueError("Target appointment not found.")

        appointment.status = "CANCELLED"
        appointment.cancellation_reason = payload.get("reason", "Patient requested cancellation")
        appointment.updated_at = datetime.utcnow()
        pending.status = "CONFIRMED"
        db.commit()

        log_audit_event(
            db=db,
            entity_type="APPOINTMENT",
            action="CANCELLED",
            entity_id=appointment.booking_reference,
            details=payload
        )

        return {
            "success": True,
            "status": "CONFIRMED",
            "message": f"Appointment {appointment.booking_reference} has been successfully cancelled.",
            "action_type": "CANCEL",
            "booking_reference": appointment.booking_reference,
            "details": payload
        }

    else:
        raise ValueError(f"Unknown action type: {action_type}")

def find_appointment_verified(
    db: Session,
    session_id: int,
    booking_reference: str
) -> Dict[str, Any]:
    """Finds an appointment after ensuring the session is verified for it."""
    ref_clean = booking_reference.strip().upper()
    if not is_session_verified_for_booking(db, session_id, ref_clean):
        raise PermissionError(
            f"Access denied: Please verify booking reference {ref_clean} with your verification code first."
        )

    appointment = db.query(Appointment).filter(Appointment.booking_reference == ref_clean).first()
    if not appointment:
        raise ValueError(f"Appointment with reference '{ref_clean}' not found.")

    start_aware = appointment.start_time.replace(tzinfo=IST) if appointment.start_time.tzinfo is None else appointment.start_time.astimezone(IST)
    end_aware = appointment.end_time.replace(tzinfo=IST) if appointment.end_time.tzinfo is None else appointment.end_time.astimezone(IST)

    return {
        "booking_reference": appointment.booking_reference,
        "patient_name": appointment.patient.full_name,
        "patient_phone": appointment.patient.phone,
        "provider_name": appointment.provider.name,
        "provider_specialty": appointment.provider.specialty,
        "service_name": appointment.service.name,
        "fee": appointment.service.fee,
        "start_time": start_aware.isoformat(),
        "end_time": end_aware.isoformat(),
        "formatted_date": start_aware.strftime("%A, %d %B %Y"),
        "formatted_time": f"{start_aware.strftime('%I:%M %p')} - {end_aware.strftime('%I:%M %p')}",
        "status": appointment.status,
        "notes": appointment.notes
    }
