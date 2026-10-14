import pytest
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.models import Provider, Appointment, PendingAction, VerificationSession, ConversationSession, Patient
from app.services.availability_service import (
    IST, get_now_ist, resolve_natural_date, get_available_slots, parse_iso_datetime
)
from app.services.booking_service import (
    prepare_booking, prepare_reschedule, prepare_cancellation,
    confirm_pending_action, find_appointment_verified, validate_slot_availability
)
from app.services.verification_service import verify_booking_access, is_session_verified_for_booking
from app.agent.tools import ToolExecutor
from app.config import settings

def create_test_session(db: Session, token: str = "test-session-1") -> ConversationSession:
    sess = db.query(ConversationSession).filter(ConversationSession.session_token == token).first()
    if not sess:
        sess = ConversationSession(session_token=token, channel="text")
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return sess

# Criterion 1: A user can book an available slot
def test_user_can_book_available_slot(db: Session):
    sess = create_test_session(db, "book-session")
    provider = db.query(Provider).first()
    
    # Target date: next Tuesday
    target_date = resolve_natural_date("next tuesday")
    slots = get_available_slots(db, provider.id, target_date)
    assert len(slots) > 0, "Provider should have open slots"
    
    chosen_slot = slots[0]
    
    # 1. Prepare
    prepared = prepare_booking(
        db=db,
        session_id=sess.id,
        patient_name="Pooja Hegde",
        patient_phone="+91 99000 11223",
        provider_id=provider.id,
        start_time_iso=chosen_slot["start_time"]
    )
    assert prepared["action_id"] is not None
    assert prepared["action_type"] == "BOOK"
    
    # 2. Confirm
    result = confirm_pending_action(
        db=db,
        session_id=sess.id,
        action_id=prepared["action_id"],
        confirmed=True
    )
    assert result["success"] is True
    assert result["status"] == "CONFIRMED"
    booking_ref = result["booking_reference"]
    assert booking_ref.startswith("CB-")
    
    # Verify in DB
    app_db = db.query(Appointment).filter(Appointment.booking_reference == booking_ref).first()
    assert app_db is not None
    assert app_db.patient.full_name == "Pooja Hegde"
    assert app_db.status == "CONFIRMED"

# Criterion 2: An unverified user cannot read or change an appointment
def test_unverified_user_cannot_read_or_change_appointment(db: Session):
    sess = create_test_session(db, "unverified-sess")
    target_ref = "CB-1001"
    
    # Ensure session is unverified
    assert not is_session_verified_for_booking(db, sess.id, target_ref)
    
    # 1. Reading should raise PermissionError
    with pytest.raises(PermissionError) as exc_read:
        find_appointment_verified(db, sess.id, target_ref)
    assert "Access denied" in str(exc_read.value)
    
    # 2. Rescheduling should raise PermissionError
    with pytest.raises(PermissionError) as exc_resched:
        prepare_reschedule(db, sess.id, target_ref, "2026-10-15T11:00:00+05:30")
    assert "Access denied" in str(exc_resched.value)

# Criterion 3: A reschedule requires confirmation
def test_reschedule_requires_confirmation(db: Session):
    sess = create_test_session(db, "resched-sess")
    ref = "CB-1001"
    
    # Verify access first
    success, _ = verify_booking_access(db, sess.id, ref, "4821")
    assert success is True
    
    app_before = db.query(Appointment).filter(Appointment.booking_reference == ref).first()
    original_start = app_before.start_time
    
    # Prepare reschedule using dynamic future available slot
    slots = get_available_slots(db, app_before.provider_id, resolve_natural_date("next thursday"))
    new_slot_iso = slots[0]["start_time"]
    prep = prepare_reschedule(db, sess.id, ref, new_slot_iso)
    action_id = prep["action_id"]
    
    # Verify DB appointment was NOT changed before confirmation
    db.refresh(app_before)
    assert app_before.start_time == original_start
    assert app_before.status == "CONFIRMED"

# Criterion 4: Declining confirmation leaves data unchanged
def test_declining_confirmation_leaves_data_unchanged(db: Session):
    sess = create_test_session(db, "decline-sess")
    ref = "CB-1002"
    
    # Verify
    verify_booking_access(db, sess.id, ref, "7390")
    app_before = db.query(Appointment).filter(Appointment.booking_reference == ref).first()
    orig_start = app_before.start_time
    orig_status = app_before.status
    
    # Prepare reschedule using dynamic future slot
    slots = get_available_slots(db, app_before.provider_id, resolve_natural_date("next friday"))
    new_slot_iso = slots[0]["start_time"]
    prep = prepare_reschedule(db, sess.id, ref, new_slot_iso)
    
    # Decline
    res = confirm_pending_action(db, sess.id, prep["action_id"], confirmed=False)
    assert res["status"] == "REJECTED"
    
    db.refresh(app_before)
    assert app_before.start_time == orig_start
    assert app_before.status == orig_status

# Criterion 5: Two concurrent requests cannot book the same slot
def test_two_concurrent_requests_cannot_book_same_slot(db: Session):
    sess1 = create_test_session(db, "concur-sess-1")
    sess2 = create_test_session(db, "concur-sess-2")
    provider = db.query(Provider).first()
    
    target_date = resolve_natural_date("next friday")
    slots = get_available_slots(db, provider.id, target_date)
    assert len(slots) > 0
    slot_time = slots[0]["start_time"]
    
    prep1 = prepare_booking(db, sess1.id, "Patient One", "+91 91111 22222", provider.id, slot_time)
    prep2 = prepare_booking(db, sess2.id, "Patient Two", "+91 93333 44444", provider.id, slot_time)
    
    # First confirmation succeeds
    res1 = confirm_pending_action(db, sess1.id, prep1["action_id"], confirmed=True)
    assert res1["success"] is True
    
    # Second confirmation for same slot MUST fail at commit time revalidation
    with pytest.raises(ValueError) as exc_concur:
        confirm_pending_action(db, sess2.id, prep2["action_id"], confirmed=True)
    assert "already booked" in str(exc_concur.value).lower() or "conflict" in str(exc_concur.value).lower()

# Criterion 6: Repeating a confirmed request does not duplicate the action
def test_repeating_confirmed_request_does_not_duplicate(db: Session):
    sess = create_test_session(db, "idempotent-sess")
    provider = db.query(Provider).first()
    target_date = resolve_natural_date("next wednesday")
    slots = get_available_slots(db, provider.id, target_date)
    slot_time = slots[1]["start_time"]
    
    prep = prepare_booking(db, sess.id, "Idempotent User", "+91 95555 66666", provider.id, slot_time)
    
    res1 = confirm_pending_action(db, sess.id, prep["action_id"], confirmed=True)
    assert res1["success"] is True
    initial_ref = res1["booking_reference"]
    
    count_before = db.query(Appointment).count()
    
    # Second identical confirmation
    res2 = confirm_pending_action(db, sess.id, prep["action_id"], confirmed=True)
    assert res2["success"] is True
    assert res2["status"] == "CONFIRMED"
    
    count_after = db.query(Appointment).count()
    assert count_before == count_after, "Repeated confirmation must not create duplicate appointments"

# Criterion 7: A failed reschedule preserves the original booking
def test_failed_reschedule_preserves_original_booking(db: Session):
    sess = create_test_session(db, "fail-resched-sess")
    ref = "CB-1003"
    verify_booking_access(db, sess.id, ref, "1945")
    
    app_orig = db.query(Appointment).filter(Appointment.booking_reference == ref).first()
    orig_start = app_orig.start_time
    orig_status = app_orig.status
    
    # Attempt to prepare reschedule to a slot in the past
    past_iso = "2020-01-01T10:00:00+05:30"
    with pytest.raises(ValueError) as exc_past:
        prepare_reschedule(db, sess.id, ref, past_iso)
    assert "past" in str(exc_past.value).lower()
    
    # Verify original appointment is intact
    db.refresh(app_orig)
    assert app_orig.start_time == orig_start
    assert app_orig.status == orig_status

# Criterion 8: "Tomorrow afternoon" resolves correctly in Asia/Kolkata
def test_tomorrow_afternoon_resolves_correctly_in_ist(db: Session):
    base_dt = datetime(2026, 10, 11, 15, 6, tzinfo=IST) # Sunday
    target_date = resolve_natural_date("tomorrow", base_dt=base_dt)
    
    assert target_date == datetime(2026, 10, 12).date() # Monday
    
    provider = db.query(Provider).first()
    # Check slots filtered by afternoon (12:00 to 17:00)
    slots = get_available_slots(db, provider.id, target_date, time_of_day="afternoon")
    for s in slots:
        s_dt = parse_iso_datetime(s["start_time"])
        assert 12 <= s_dt.hour < 17, f"Slot {s['formatted_time']} is not in afternoon"

# Criterion 9: Tool failure does not produce a false success message
def test_tool_failure_does_not_produce_false_success(db: Session):
    sess = create_test_session(db, "tool-fail-sess")
    executor = ToolExecutor(db, sess.id)
    
    # Execute check_availability with non-existent provider
    result = executor.execute_tool("check_availability", {
        "provider_name_or_id": "Dr. NonExistentDoctor999",
        "date": "tomorrow"
    })
    
    assert result["status"] == "error"
    assert result["data"] is None
    assert "not found" in result["result_summary"].lower()

# Criterion 10: Unauthenticated users cannot access admin endpoints
def test_unauthenticated_users_cannot_access_admin_endpoints(client):
    res_stats = client.get("/api/admin/stats")
    assert res_stats.status_code == 401, "Admin stats must require authentication"
    
    res_apps = client.get("/api/admin/appointments")
    assert res_apps.status_code == 401, "Admin appointments list must require authentication"
