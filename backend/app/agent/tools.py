import time
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import Provider, Service, Appointment
from app.config import settings
from app.services.availability_service import (
    resolve_natural_date, get_available_slots, parse_iso_datetime, get_now_ist
)
from app.services import booking_service, verification_service, handoff_service

# Tool Definitions Metadata for LLM Function Calling schemas
TOOLS_SCHEMA = [
    {
        "name": "get_clinic_information",
        "description": "Get official information about CareBridge Clinic including address, hours, location, services, fees, and clinic policies.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category filter: 'hours', 'location', 'fees', 'services', 'policies'."
                }
            }
        }
    },
    {
        "name": "list_providers",
        "description": "List all active physicians and specialists at CareBridge Clinic with their specialties, fees, and bio.",
        "parameters": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Filter by medical specialty (e.g. 'General Physician', 'Pediatrician', 'Dermatologist')."
                }
            }
        }
    },
    {
        "name": "check_availability",
        "description": "Check open 30-minute appointment slots for a specific doctor on a given date. Handles natural dates like 'today', 'tomorrow', 'next Monday' in Asia/Kolkata timezone.",
        "parameters": {
            "type": "object",
            "properties": {
                "provider_name_or_id": {
                    "type": "string",
                    "description": "Provider full name or provider ID (e.g. 'Dr. Aisha Rao' or '1')."
                },
                "date": {
                    "type": "string",
                    "description": "Target date string (e.g. 'tomorrow', '2026-10-12', 'next Monday')."
                },
                "time_of_day": {
                    "type": "string",
                    "description": "Optional time of day filter: 'morning', 'afternoon', or 'evening'."
                }
            },
            "required": ["provider_name_or_id", "date"]
        }
    },
    {
        "name": "verify_booking_access",
        "description": "Verify access to an existing appointment using the booking reference and 4-digit verification code. Required before viewing, rescheduling, or cancelling an appointment.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_reference": {
                    "type": "string",
                    "description": "The unique booking reference (e.g. 'CB-1001')."
                },
                "verification_code": {
                    "type": "string",
                    "description": "The 4-digit verification code associated with the appointment (e.g. '4821')."
                }
            },
            "required": ["booking_reference", "verification_code"]
        }
    },
    {
        "name": "find_appointment",
        "description": "Retrieve details of an appointment after access has been verified for the current session. Shows doctor, date, time, patient name, and status.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_reference": {
                    "type": "string",
                    "description": "The unique booking reference (e.g. 'CB-1001')."
                }
            },
            "required": ["booking_reference"]
        }
    },
    {
        "name": "prepare_booking",
        "description": "Stage a new appointment booking. Validates availability and generates a pending confirmation card. Does NOT commit until confirmed.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string", "description": "Patient's full name."},
                "patient_phone": {"type": "string", "description": "Patient's 10-digit phone number with country code."},
                "provider_id": {"type": "integer", "description": "ID of the doctor."},
                "start_time": {"type": "string", "description": "Exact slot start time in ISO format (from check_availability)."},
                "service_id": {"type": "integer", "description": "Optional service ID."},
                "notes": {"type": "string", "description": "Optional consultation reason or symptoms."}
            },
            "required": ["patient_name", "patient_phone", "provider_id", "start_time"]
        }
    },
    {
        "name": "prepare_reschedule",
        "description": "Stage a reschedule for an existing appointment to a new slot. Requires verified session access.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_reference": {"type": "string", "description": "The booking reference to reschedule (e.g. 'CB-1001')."},
                "new_start_time": {"type": "string", "description": "New ISO start time slot."}
            },
            "required": ["booking_reference", "new_start_time"]
        }
    },
    {
        "name": "prepare_cancellation",
        "description": "Stage the cancellation of an existing appointment. Requires verified session access.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_reference": {"type": "string", "description": "The booking reference to cancel (e.g. 'CB-1001')."},
                "reason": {"type": "string", "description": "Reason for cancellation."}
            },
            "required": ["booking_reference"]
        }
    },
    {
        "name": "confirm_pending_action",
        "description": "Explicitly confirm or decline a staged pending action (booking, reschedule, cancellation). Executes atomic database commit.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "The UUID action_id from the prepare step."},
                "confirmed": {"type": "boolean", "description": "true to confirm and execute, false to cancel/decline."}
            },
            "required": ["action_id", "confirmed"]
        }
    },
    {
        "name": "create_handoff_request",
        "description": "Escalate the patient request to a human receptionist when questions exceed administrative scope, medical triage is requested, or technical issues occur.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string", "description": "Name of the person requesting assistance."},
                "patient_phone": {"type": "string", "description": "Contact phone number for callback."},
                "reason": {"type": "string", "description": "Detailed reason for escalation."}
            },
            "required": ["patient_name", "patient_phone", "reason"]
        }
    }
]

class ToolExecutor:
    def __init__(self, db: Session, session_id: int):
        self.db = db
        self.session_id = session_id

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a tool by name with arguments and captures execution time & sanitized status."""
        start_t = time.perf_counter()
        handler = getattr(self, f"tool_{tool_name}", None)
        if not handler:
            duration_ms = int((time.perf_counter() - start_t) * 1000)
            return {
                "tool_name": tool_name,
                "status": "error",
                "duration_ms": duration_ms,
                "arguments": args,
                "result_summary": f"Tool '{tool_name}' not implemented.",
                "data": None
            }

        try:
            result_data, summary = handler(**args)
            duration_ms = int((time.perf_counter() - start_t) * 1000)
            return {
                "tool_name": tool_name,
                "status": "success",
                "duration_ms": duration_ms,
                "arguments": args,
                "result_summary": summary,
                "data": result_data
            }
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_t) * 1000)
            return {
                "tool_name": tool_name,
                "status": "error",
                "duration_ms": duration_ms,
                "arguments": args,
                "result_summary": str(e),
                "data": None
            }

    def tool_get_clinic_information(self, category: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        info = {
            "name": settings.CLINIC_NAME,
            "address": settings.CLINIC_ADDRESS,
            "location": settings.CLINIC_LOCATION,
            "phone": settings.CLINIC_PHONE,
            "timezone": settings.CLINIC_TIMEZONE,
            "hours": {
                "Monday_to_Friday": "08:30 AM - 08:00 PM",
                "Saturday": "08:30 AM - 07:00 PM",
                "Sunday": "Closed for routine visits (Emergency triage handoff only)"
            },
            "policies": [
                "30-minute appointment slots",
                "Cancellations and reschedules permitted up to 2 hours prior",
                "Consultation fee payable at clinic reception or digital link",
                "Receptionist handles administrative duties only; no clinical diagnosis or prescription recommendations"
            ]
        }
        services = self.db.query(Service).filter(Service.is_active == True).all()
        info["services"] = [{"name": s.name, "fee": s.fee, "duration": f"{s.duration_minutes} min"} for s in services]
        
        summary = f"{settings.CLINIC_NAME} in Hyderabad. Open Mon-Sat. Services: {len(services)} specialties available."
        return info, summary

    def tool_list_providers(self, specialty: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str]:
        query = self.db.query(Provider).filter(Provider.is_active == True)
        if specialty:
            query = query.filter(Provider.specialty.ilike(f"%{specialty}%"))
        providers = query.all()

        results = []
        for p in providers:
            results.append({
                "id": p.id,
                "name": p.name,
                "title": p.title,
                "specialty": p.specialty,
                "consultation_fee": p.consultation_fee,
                "bio": p.bio
            })
        summary = f"Found {len(results)} active provider(s)."
        return results, summary

    def tool_check_availability(
        self,
        provider_name_or_id: str,
        date: str,
        time_of_day: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str]:
        # Resolve provider
        provider = None
        if provider_name_or_id.isdigit():
            provider = self.db.query(Provider).filter(Provider.id == int(provider_name_or_id)).first()
        else:
            provider = self.db.query(Provider).filter(
                Provider.name.ilike(f"%{provider_name_or_id.strip()}%")
            ).first()

        if not provider:
            raise ValueError(f"Provider '{provider_name_or_id}' not found. Please ask for a listed provider.")

        # Resolve natural date
        target_date = resolve_natural_date(date)
        slots = get_available_slots(self.db, provider.id, target_date, time_of_day)

        date_formatted = target_date.strftime("%A, %d %B %Y")
        summary = f"{len(slots)} available slot(s) for {provider.name} on {date_formatted}."
        if time_of_day:
            summary += f" (Filtered by {time_of_day})"

        return {
            "provider_id": provider.id,
            "provider_name": provider.name,
            "specialty": provider.specialty,
            "fee": provider.consultation_fee,
            "date": target_date.isoformat(),
            "formatted_date": date_formatted,
            "slots": slots
        }, summary

    def tool_verify_booking_access(
        self,
        booking_reference: str,
        verification_code: str
    ) -> Tuple[Dict[str, Any], str]:
        success, message = verification_service.verify_booking_access(
            db=self.db,
            session_id=self.session_id,
            booking_reference=booking_reference,
            verification_code=verification_code
        )
        if not success:
            raise PermissionError(message)

        return {"verified": True, "booking_reference": booking_reference.upper()}, message

    def tool_find_appointment(self, booking_reference: str) -> Tuple[Dict[str, Any], str]:
        app_data = booking_service.find_appointment_verified(
            db=self.db,
            session_id=self.session_id,
            booking_reference=booking_reference
        )
        summary = f"Found booking {app_data['booking_reference']} with {app_data['provider_name']} on {app_data['formatted_date']}."
        return app_data, summary

    def tool_prepare_booking(
        self,
        patient_name: str,
        patient_phone: str,
        provider_id: int,
        start_time: str,
        service_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str]:
        res = booking_service.prepare_booking(
            db=self.db,
            session_id=self.session_id,
            patient_name=patient_name,
            patient_phone=patient_phone,
            provider_id=provider_id,
            start_time_iso=start_time,
            service_id=service_id,
            notes=notes
        )
        return res, res["summary_text"]

    def tool_prepare_reschedule(
        self,
        booking_reference: str,
        new_start_time: str
    ) -> Tuple[Dict[str, Any], str]:
        res = booking_service.prepare_reschedule(
            db=self.db,
            session_id=self.session_id,
            booking_reference=booking_reference,
            new_start_time_iso=new_start_time
        )
        return res, res["summary_text"]

    def tool_prepare_cancellation(
        self,
        booking_reference: str,
        reason: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str]:
        res = booking_service.prepare_cancellation(
            db=self.db,
            session_id=self.session_id,
            booking_reference=booking_reference,
            reason=reason
        )
        return res, res["summary_text"]

    def tool_confirm_pending_action(
        self,
        action_id: str,
        confirmed: bool
    ) -> Tuple[Dict[str, Any], str]:
        res = booking_service.confirm_pending_action(
            db=self.db,
            session_id=self.session_id,
            action_id=action_id,
            confirmed=confirmed
        )
        return res, res["message"]

    def tool_create_handoff_request(
        self,
        patient_name: str,
        patient_phone: str,
        reason: str
    ) -> Tuple[Dict[str, Any], str]:
        res = handoff_service.create_handoff_request(
            db=self.db,
            session_id=self.session_id,
            patient_name=patient_name,
            patient_phone=patient_phone,
            reason=reason
        )
        return res, res["message"]
