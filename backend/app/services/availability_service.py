import re
from datetime import datetime, date, time, timedelta
from typing import List, Optional, Tuple, Dict, Any
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models import Provider, ProviderSchedule, BlockedSlot, Appointment
from app.config import settings

IST = ZoneInfo(settings.CLINIC_TIMEZONE)

def get_now_ist() -> datetime:
    """Returns the current timezone-aware datetime in Asia/Kolkata."""
    return datetime.now(IST)

def resolve_natural_date(date_str: str, base_dt: Optional[datetime] = None) -> date:
    """
    Resolves human phrases like 'today', 'tomorrow', 'next Monday', or 'YYYY-MM-DD'
    into a concrete date in Asia/Kolkata timezone.
    """
    if base_dt is None:
        base_dt = get_now_ist()
    base_date = base_dt.date()
    
    clean_str = date_str.strip().lower()
    
    if clean_str in ("today", "this day"):
        return base_date
    if clean_str in ("tomorrow", "tmrw"):
        return base_date + timedelta(days=1)
    if clean_str in ("day after tomorrow", "day after tmrw"):
        return base_date + timedelta(days=2)
    
    # Day names
    days_map = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6
    }
    
    for day_name, day_idx in days_map.items():
        if day_name in clean_str:
            current_day_idx = base_date.weekday()
            days_ahead = (day_idx - current_day_idx) % 7
            if days_ahead == 0 and "next" in clean_str:
                days_ahead = 7
            elif days_ahead == 0 and clean_str != day_name:
                days_ahead = 7
            elif days_ahead == 0:
                days_ahead = 0
            if "next" in clean_str and days_ahead < 7:
                days_ahead += 7
            return base_date + timedelta(days=days_ahead)

    # Standard date formats: YYYY-MM-DD or DD/MM/YYYY or DD-MM-YYYY
    try:
        return datetime.strptime(clean_str, "%Y-%m-%d").date()
    except ValueError:
        pass
    
    try:
        return datetime.strptime(clean_str, "%d-%m-%Y").date()
    except ValueError:
        pass
        
    try:
        return datetime.strptime(clean_str, "%d/%m/%Y").date()
    except ValueError:
        pass

    # Month name like "12 Oct", "October 12", "12 October 2026"
    for fmt in ("%d %b %Y", "%d %B %Y", "%d %b", "%d %B", "%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(clean_str, fmt).date()
            year = base_date.year if parsed.year == 1900 else parsed.year
            return parsed.replace(year=year)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: '{date_str}'. Please provide in YYYY-MM-DD format.")

def parse_time_str(time_str: str) -> time:
    """Parses '09:00', '9:00', '2:30 PM', '14:30' into datetime.time."""
    clean = time_str.strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            return datetime.strptime(clean, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time format: {time_str}")

def parse_iso_datetime(dt_str: str) -> datetime:
    """Parses ISO string and converts/ensures Asia/Kolkata timezone."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return dt

def generate_slots_for_schedule(
    target_date: date,
    schedule: ProviderSchedule,
    slot_minutes: int = 30
) -> List[Tuple[datetime, datetime]]:
    """Generates 30-min slot intervals for a given day schedule."""
    start_t = datetime.strptime(schedule.start_time, "%H:%M").time()
    end_t = datetime.strptime(schedule.end_time, "%H:%M").time()
    
    break_start_t = datetime.strptime(schedule.break_start, "%H:%M").time() if schedule.break_start else None
    break_end_t = datetime.strptime(schedule.break_end, "%H:%M").time() if schedule.break_end else None

    current_dt = datetime.combine(target_date, start_t, tzinfo=IST)
    day_end_dt = datetime.combine(target_date, end_t, tzinfo=IST)
    
    slots = []
    slot_delta = timedelta(minutes=slot_minutes)
    
    while current_dt + slot_delta <= day_end_dt:
        slot_start = current_dt
        slot_end = current_dt + slot_delta
        current_dt += slot_delta

        # Check if overlaps with break
        if break_start_t and break_end_t:
            b_start = datetime.combine(target_date, break_start_t, tzinfo=IST)
            b_end = datetime.combine(target_date, break_end_t, tzinfo=IST)
            if not (slot_end <= b_start or slot_start >= b_end):
                continue  # Slot is during break

        slots.append((slot_start, slot_end))
        
    return slots

def get_available_slots(
    db: Session,
    provider_id: int,
    target_date: date,
    time_of_day: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns available 30-min slots for a provider on a given date.
    Filters out:
    - Non-working days or out-of-schedule slots
    - Slots during breaks
    - Blocked slots
    - Existing confirmed or rescheduled appointments
    - Past slots (relative to current IST time)
    """
    now_ist = get_now_ist()
    weekday = target_date.weekday()

    # Find provider active schedule for this weekday
    schedules = db.query(ProviderSchedule).filter(
        ProviderSchedule.provider_id == provider_id,
        ProviderSchedule.day_of_week == weekday,
        ProviderSchedule.is_active == True
    ).all()

    if not schedules:
        return []

    # Get blocked slots for this date
    start_of_day = datetime.combine(target_date, time.min, tzinfo=IST)
    end_of_day = datetime.combine(target_date, time.max, tzinfo=IST)
    
    # Note: sqlite stores datetime without tz, so we compare naive or aware
    blocked = db.query(BlockedSlot).filter(
        BlockedSlot.provider_id == provider_id,
        BlockedSlot.start_time < end_of_day.replace(tzinfo=None),
        BlockedSlot.end_time > start_of_day.replace(tzinfo=None)
    ).all()

    # Get active booked appointments
    appointments = db.query(Appointment).filter(
        Appointment.provider_id == provider_id,
        Appointment.status.in_(["CONFIRMED", "RESCHEDULED"]),
        Appointment.start_time >= start_of_day.replace(tzinfo=None),
        Appointment.start_time < end_of_day.replace(tzinfo=None)
    ).all()
    
    booked_starts = {app.start_time.replace(tzinfo=IST) if app.start_time.tzinfo is None else app.start_time.astimezone(IST) for app in appointments}

    all_slots = []
    for sched in schedules:
        intervals = generate_slots_for_schedule(target_date, sched)
        for s_start, s_end in intervals:
            # Past check
            if s_start <= now_ist:
                continue

            # Blocked slot check
            is_blocked = False
            for b in blocked:
                b_start = b.start_time.replace(tzinfo=IST) if b.start_time.tzinfo is None else b.start_time.astimezone(IST)
                b_end = b.end_time.replace(tzinfo=IST) if b.end_time.tzinfo is None else b.end_time.astimezone(IST)
                if not (s_end <= b_start or s_start >= b_end):
                    is_blocked = True
                    break
            if is_blocked:
                continue

            # Booked check
            if any(s_start == b_time for b_time in booked_starts):
                continue

            # Time of day filter
            if time_of_day:
                tod = time_of_day.lower()
                slot_hour = s_start.hour
                if tod == "morning" and not (slot_hour < 12):
                    continue
                elif tod == "afternoon" and not (12 <= slot_hour < 17):
                    continue
                elif tod == "evening" and not (17 <= slot_hour < 21):
                    continue

            all_slots.append({
                "start_time": s_start.isoformat(),
                "end_time": s_end.isoformat(),
                "formatted_time": f"{s_start.strftime('%I:%M %p')} - {s_end.strftime('%I:%M %p')}",
                "is_available": True
            })

    return all_slots

def find_alternative_slots(
    db: Session,
    provider_id: int,
    preferred_dt: datetime,
    count: int = 3
) -> List[Dict[str, Any]]:
    """Finds up to `count` available alternative slots closest to the preferred datetime."""
    alternatives = []
    search_date = preferred_dt.date()
    
    for day_offset in range(7):
        target = search_date + timedelta(days=day_offset)
        slots = get_available_slots(db, provider_id, target)
        for s in slots:
            s_dt = datetime.fromisoformat(s["start_time"])
            if s_dt > get_now_ist() and s_dt != preferred_dt:
                alternatives.append(s)
                if len(alternatives) >= count:
                    return alternatives
    return alternatives
