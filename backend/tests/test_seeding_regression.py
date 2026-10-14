import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Appointment
from app.seed import seed_database

def test_rerunning_seed_preserves_cancelled_and_rescheduled_appointments(db: Session):
    """
    Regression Test: Normal seeding must be non-destructive.
    Rerunning the seed must never modify existing appointment dates
    or revive cancelled / rescheduled appointments.
    """
    # 1. Initial seed
    seed_database(db)

    # 2. Find seeded appointments
    app1001 = db.query(Appointment).filter(Appointment.booking_reference == "CB-1001").first()
    app1002 = db.query(Appointment).filter(Appointment.booking_reference == "CB-1002").first()
    assert app1001 is not None
    assert app1002 is not None

    # 3. Simulate patient cancelling CB-1001 and rescheduling CB-1002
    custom_date_1 = app1001.start_time
    app1001.status = "CANCELLED"

    custom_date_2 = app1002.start_time + timedelta(days=5)
    app1002.start_time = custom_date_2
    app1002.end_time = custom_date_2 + timedelta(minutes=30)
    app1002.status = "RESCHEDULED"
    db.commit()

    # 4. Rerun normal seeding (non-destructive)
    seed_database(db, force_reset=False)

    # 5. Verify appointments were preserved and NOT overwritten or revived
    app1001_after = db.query(Appointment).filter(Appointment.booking_reference == "CB-1001").first()
    app1002_after = db.query(Appointment).filter(Appointment.booking_reference == "CB-1002").first()

    assert app1001_after.status == "CANCELLED", "CB-1001 must remain CANCELLED after re-seeding"
    assert app1001_after.start_time == custom_date_1, "CB-1001 start_time must not be altered"

    assert app1002_after.status == "RESCHEDULED", "CB-1002 must remain RESCHEDULED after re-seeding"
    assert app1002_after.start_time == custom_date_2, "CB-1002 rescheduled date must not be reverted"

def test_force_reset_restores_synthetic_baseline(db: Session):
    """
    Explicit force_reset (used exclusively by admin reset operation)
    restores appointments to CONFIRMED baseline.
    """
    seed_database(db)
    app1001 = db.query(Appointment).filter(Appointment.booking_reference == "CB-1001").first()
    app1001.status = "CANCELLED"
    db.commit()

    # Admin explicit force reset
    seed_database(db, force_reset=True)

    app1001_reset = db.query(Appointment).filter(Appointment.booking_reference == "CB-1001").first()
    assert app1001_reset.status == "CONFIRMED"
