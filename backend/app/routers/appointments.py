from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Provider, Appointment, ConversationSession
from app.schemas import ProviderOut, AvailabilityResponse, SlotOut, AppointmentOut, VerifyAccessRequest, VerifyAccessResponse
from app.services.availability_service import resolve_natural_date, get_available_slots
from app.services.verification_service import verify_booking_access, is_session_verified_for_booking, get_or_create_session
from app.services.booking_service import find_appointment_verified

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])

@router.get("/providers", response_model=List[ProviderOut])
def get_providers(db: Session = Depends(get_db)):
    providers = db.query(Provider).filter(Provider.is_active == True).all()
    return providers

@router.get("/availability", response_model=AvailabilityResponse)
def check_availability_endpoint(
    provider_id: int,
    date: str = Query(..., description="Date phrase like 'tomorrow' or 'YYYY-MM-DD'"),
    time_of_day: Optional[str] = Query(None, description="morning, afternoon, or evening"),
    db: Session = Depends(get_db)
):
    provider = db.query(Provider).filter(Provider.id == provider_id, Provider.is_active == True).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")

    try:
        target_date = resolve_natural_date(date)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    raw_slots = get_available_slots(db, provider_id=provider.id, target_date=target_date, time_of_day=time_of_day)
    
    slots_out = [
        SlotOut(
            start_time=s["start_time"],
            end_time=s["end_time"],
            formatted_time=s["formatted_time"],
            is_available=s["is_available"]
        )
        for s in raw_slots
    ]

    return AvailabilityResponse(
        provider_id=provider.id,
        provider_name=provider.name,
        date=target_date.isoformat(),
        slots=slots_out
    )

@router.post("/verify", response_model=VerifyAccessResponse)
def verify_access_endpoint(req: VerifyAccessRequest, db: Session = Depends(get_db)):
    session = get_or_create_session(db, session_token=req.session_token)
    success, message = verify_booking_access(
        db=db,
        session_id=session.id,
        booking_reference=req.booking_reference,
        verification_code=req.verification_code
    )
    if not success:
        raise HTTPException(status_code=401, detail=message)
        
    return VerifyAccessResponse(
        success=True,
        message=message,
        booking_reference=req.booking_reference.upper(),
        is_verified=True
    )

@router.get("/{booking_reference}")
def get_appointment_details(
    booking_reference: str,
    session_token: str = Query(..., description="Active session token"),
    db: Session = Depends(get_db)
):
    session = db.query(ConversationSession).filter(ConversationSession.session_token == session_token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session invalid. Verification required.")

    try:
        app_data = find_appointment_verified(db=db, session_id=session.id, booking_reference=booking_reference)
        return app_data
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
