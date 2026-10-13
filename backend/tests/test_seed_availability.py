import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Provider, Appointment, Patient, Service
from app.seed import find_valid_seed_slot
from app.services.availability_service import get_available_slots, get_now_ist


def test_seed_slot_avoids_break(db: Session):
    """
    Verifies that find_valid_seed_slot avoids provider break times.
    Dr. Aisha Rao has a break between 13:00 and 14:00 (Mon-Fri).
    When requested at 13:00 (during break), it must pick a valid slot outside the break.
    """
    provider = db.query(Provider).filter(Provider.name == "Dr. Aisha Rao").first()
    assert provider is not None

    now_ist = get_now_ist()
    # Find next working day (Mon-Fri)
    test_date = now_ist.date() + timedelta(days=1)
    while test_date.weekday() not in [0, 1, 2, 3, 4]:
        test_date += timedelta(days=1)

    # Request a start time right inside the break (13:00)
    break_target = datetime(test_date.year, test_date.month, test_date.day, 13, 0)

    start_cand, end_cand = find_valid_seed_slot(db, provider.id, break_target, max_days_ahead=7)

    # Assert start_cand is NOT in [13:00, 14:00)
    assert not (start_cand.hour == 13), f"Chosen slot {start_cand} must not fall within break 13:00-14:00"
    # In fact, it should be the next slot after the break, which is 14:00
    assert start_cand.hour >= 14, f"Expected slot at or after 14:00, got {start_cand}"


def test_seed_slot_avoids_non_working_days(db: Session):
    """
    Verifies that find_valid_seed_slot skips non-working days.
    Dr. Aisha Rao only works Mon-Fri (weekdays 0-4).
    If requested on a Sunday, it must skip to Monday (or the next active working day).
    """
    provider = db.query(Provider).filter(Provider.name == "Dr. Aisha Rao").first()
    assert provider is not None

    now_ist = get_now_ist()
    # Find next Sunday (weekday == 6)
    days_to_sunday = (6 - now_ist.weekday()) % 7
    if days_to_sunday == 0:
        days_to_sunday = 7
    sunday_date = now_ist.date() + timedelta(days=days_to_sunday)
    assert sunday_date.weekday() == 6

    target_dt = datetime(sunday_date.year, sunday_date.month, sunday_date.day, 10, 0)
    start_cand, end_cand = find_valid_seed_slot(db, provider.id, target_dt, max_days_ahead=7)

    # The chosen date must NOT be Sunday (6) or Saturday (5)
    assert start_cand.weekday() in [0, 1, 2, 3, 4], f"Chosen date {start_cand} must be a weekday"
    # In fact, it should be the Monday immediately following that Sunday
    assert start_cand.date() == sunday_date + timedelta(days=1)


def test_seed_slot_rolls_over_when_day_is_fully_booked(db: Session):
    """
    Verifies that if all available slots on a day are booked,
    find_valid_seed_slot correctly rolls over to the next available working day.
    """
    provider = db.query(Provider).filter(Provider.name == "Dr. Aisha Rao").first()
    assert provider is not None
    patient = db.query(Patient).first()
    service = db.query(Service).first()

    now_ist = get_now_ist()
    test_date = now_ist.date() + timedelta(days=2)
    while test_date.weekday() not in [0, 1, 2, 3, 4]:
        test_date += timedelta(days=1)

    # Get all slots on test_date
    slots = get_available_slots(db, provider.id, test_date)
    assert len(slots) > 0, "Initial day must have available slots"

    # Fully book all slots on test_date
    for idx, s in enumerate(slots):
        s_start = datetime.fromisoformat(s["start_time"]).replace(tzinfo=None)
        s_end = datetime.fromisoformat(s["end_time"]).replace(tzinfo=None)
        app = Appointment(
            booking_reference=f"TEST-FULL-{idx}",
            patient_id=patient.id,
            provider_id=provider.id,
            service_id=service.id,
            start_time=s_start,
            end_time=s_end,
            status="CONFIRMED",
            verification_code="0000"
        )
        db.add(app)
    db.commit()

    # Now verify that no slots remain on test_date
    remaining_slots = get_available_slots(db, provider.id, test_date)
    assert len(remaining_slots) == 0, "All slots on test_date must now be booked"

    # Calling find_valid_seed_slot for test_date should roll over to the next working day
    target_dt = datetime(test_date.year, test_date.month, test_date.day, 10, 0)
    start_cand, end_cand = find_valid_seed_slot(db, provider.id, target_dt, max_days_ahead=7)

    assert start_cand.date() > test_date, f"Slot {start_cand} must have rolled over to a future day"
    assert start_cand.weekday() in [0, 1, 2, 3, 4], "Rollover day must be a working day"


def test_seed_slot_raises_error_when_no_slots_in_bound(db: Session):
    """
    Verifies that if no slot is available within max_days_ahead,
    find_valid_seed_slot raises a clear ValueError.
    """
    provider = db.query(Provider).filter(Provider.name == "Dr. Aisha Rao").first()
    assert provider is not None

    now_ist = get_now_ist()
    # Find a Sunday and search with max_days_ahead=1 (so it only checks Sunday)
    days_to_sunday = (6 - now_ist.weekday()) % 7
    if days_to_sunday == 0:
        days_to_sunday = 7
    sunday_date = now_ist.date() + timedelta(days=days_to_sunday)
    sunday_dt = datetime(sunday_date.year, sunday_date.month, sunday_date.day, 10, 0)

    with pytest.raises(ValueError, match="No available slot found"):
        find_valid_seed_slot(db, provider.id, sunday_dt, max_days_ahead=1)
