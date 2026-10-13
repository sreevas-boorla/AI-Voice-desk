from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db, Base, engine
from app.config import settings
from app.models import Provider, Service
from app.seed import seed_database
from app.auth import get_current_admin

router = APIRouter(prefix="/api/system", tags=["System"])

@router.get("/clinic-info")
def get_clinic_info(db: Session = Depends(get_db)):
    providers = db.query(Provider).filter(Provider.is_active == True).all()
    services = db.query(Service).filter(Service.is_active == True).all()

    return {
        "name": settings.CLINIC_NAME,
        "tagline": "Compassionate, accessible healthcare in Jubilee Hills, Hyderabad",
        "location": settings.CLINIC_LOCATION,
        "address": settings.CLINIC_ADDRESS,
        "phone": settings.CLINIC_PHONE,
        "timezone": settings.CLINIC_TIMEZONE,
        "hours": {
            "Monday to Friday": "08:30 AM - 08:00 PM",
            "Saturday": "08:30 AM - 07:00 PM",
            "Sunday": "Closed for routine visits (Emergency triage referral only)"
        },
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "fee": s.fee,
                "duration_minutes": s.duration_minutes,
                "description": s.description
            }
            for s in services
        ],
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "title": p.title,
                "specialty": p.specialty,
                "fee": p.consultation_fee,
                "bio": p.bio,
                "avatar_url": p.avatar_url
            }
            for p in providers
        ],
        "faqs": [
            {"q": "How long are consultation slots?", "a": "All appointments are scheduled for fixed 30-minute intervals."},
            {"q": "Can I reschedule or cancel my appointment?", "a": "Yes, appointments can be modified up to 2 hours before the scheduled time after identity verification."},
            {"q": "What happens if I need emergency triage?", "a": "VoiceDesk receptionist will immediately forward your details to our on-duty emergency clinical staff."}
        ]
    }

@router.get("/status")
def get_system_status():
    """Provides provider connection and health indicators without exposing secrets."""
    has_livekit = bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)
    has_llm = bool(settings.GROQ_API_KEY)

    return {
        "database": {
            "status": "connected",
            "type": "PostgreSQL" if "postgres" in settings.DATABASE_URL else "SQLite (Local Concurrency Protected)"
        },
        "voice_provider": {
            "configured": has_livekit,
            "provider": "LiveKit WebRTC (Cloud)" if has_livekit else "Browser Web Speech API",
            "mode": "livekit" if has_livekit else "browser",
            "note": "Browser speech recognition utilizes your browser vendor's speech engine."
        },
        "llm_provider": {
            "configured": has_llm,
            "provider": f"Groq ({settings.GROQ_MODEL})" if has_llm else "VoiceDesk Deterministic Simulator",
            "mode": "live" if (has_llm and not settings.DEMO_MODE) else "demo"
        },
        "environment": settings.ENVIRONMENT,
        "demo_mode": settings.DEMO_MODE
    }

@router.get("/demo-references")
def get_demo_references(db: Session = Depends(get_db)):
    """Returns active seeded appointments for the demo guidance panel."""
    if not settings.DEMO_MODE:
        return []

    from app.models import Appointment
    apps = db.query(Appointment).filter(
        Appointment.booking_reference.in_(["CB-1001", "CB-1002", "CB-1003"])
    ).all()

    return [
        {
            "ref": a.booking_reference,
            "code": a.verification_code,
            "patient": a.patient.full_name if a.patient else "Patient",
            "provider": f"{a.provider.name} ({a.provider.specialty})" if a.provider else "CareBridge Specialist",
            "date": a.start_time.strftime("%a, %d %b %Y at %I:%M %p"),
            "status": a.status
        }
        for a in apps
    ]

@router.post("/reset-demo")
def reset_demo_data(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    """Restores synthetic seed data. Strictly forbidden in production."""
    if settings.ENVIRONMENT == "production" or not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo reset is disabled in production environments."
        )

    # Re-create and seed tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_database(db)

    return {"message": "Demo data successfully reset to synthetic baseline."}
