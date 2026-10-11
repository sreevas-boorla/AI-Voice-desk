from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

# --- Provider & Service ---
class ProviderScheduleOut(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    break_start: Optional[str] = None
    break_end: Optional[str] = None

    class Config:
        from_attributes = True

class ProviderOut(BaseModel):
    id: int
    name: str
    title: str
    specialty: str
    bio: str
    consultation_fee: int
    avatar_url: Optional[str] = None
    is_active: bool
    schedules: List[ProviderScheduleOut] = []

    class Config:
        from_attributes = True

class ServiceOut(BaseModel):
    id: int
    name: str
    duration_minutes: int
    fee: int
    description: str

    class Config:
        from_attributes = True

# --- Availability ---
class SlotOut(BaseModel):
    start_time: str   # ISO string in IST
    end_time: str     # ISO string in IST
    formatted_time: str  # "10:00 AM - 10:30 AM"
    is_available: bool

class AvailabilityResponse(BaseModel):
    provider_id: int
    provider_name: str
    date: str
    slots: List[SlotOut]

# --- Appointments ---
class AppointmentOut(BaseModel):
    id: int
    booking_reference: str
    patient_name: str
    patient_phone: str
    provider_id: int
    provider_name: str
    provider_specialty: str
    service_name: str
    fee: int
    start_time: str
    end_time: str
    status: str
    notes: Optional[str] = None
    verification_code: Optional[str] = None

    class Config:
        from_attributes = True

# --- Verification ---
class VerifyAccessRequest(BaseModel):
    booking_reference: str
    verification_code: str
    session_token: str

class VerifyAccessResponse(BaseModel):
    success: bool
    message: str
    booking_reference: str
    is_verified: bool

# --- Pending Action ---
class PendingActionSummary(BaseModel):
    action_id: str
    action_type: str  # "BOOK", "RESCHEDULE", "CANCEL"
    summary_text: str
    expires_at: str
    details: Dict[str, Any]

class ConfirmActionRequest(BaseModel):
    session_token: str
    action_id: str
    confirmed: bool

# --- Agent Chat & Tool Activity ---
class ToolExecutionEvent(BaseModel):
    tool_name: str
    status: str  # "executing", "success", "error"
    duration_ms: int
    arguments: Dict[str, Any]
    result_summary: str
    timestamp: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_token: Optional[str] = None
    message: str
    channel: str = "text"  # "text" or "voice"

class ChatResponse(BaseModel):
    session_token: str
    reply: str
    pending_action: Optional[PendingActionSummary] = None
    tool_events: List[ToolExecutionEvent] = []
    verified_reference: Optional[str] = None

# --- Handoff ---
class HandoffCreateRequest(BaseModel):
    session_token: Optional[str] = None
    patient_name: str
    patient_phone: str
    reason: str

class HandoffOut(BaseModel):
    id: int
    patient_name: str
    patient_phone: str
    reason: str
    status: str
    notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Admin ---
class AdminLoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AdminDashboardStats(BaseModel):
    total_appointments: int
    confirmed_appointments: int
    rescheduled_appointments: int
    cancelled_appointments: int
    today_appointments: int
    open_handoffs: int
    active_providers: int

# --- Demo & Clinic Info ---
class ClinicInfoResponse(BaseModel):
    name: str
    tagline: str
    address: str
    phone: str
    timezone: str
    hours: Dict[str, str]
    services: List[ServiceOut]
    providers: List[ProviderOut]
