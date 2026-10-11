import re
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
from app.agent.tools import ToolExecutor
from app.models import PendingAction, Appointment, Provider
from app.services.availability_service import get_now_ist, resolve_natural_date, parse_iso_datetime

class AgentSimulator:
    """
    Deterministic rule-based agent simulator for testing and zero-API-key demo mode.
    Executes the exact same ToolExecutor tools and business rules as the live LLM.
    """
    def __init__(self, executor: ToolExecutor):
        self.executor = executor
        self.db = executor.db
        self.session_id = executor.session_id

    def process(self, user_text: str) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        text = user_text.strip().lower()
        tool_events = []
        pending_action_summary = None

        # 1. Check for Active Pending Action confirmation or decline
        active_pending = self.db.query(PendingAction).filter(
            PendingAction.session_id == self.session_id,
            PendingAction.status == "PENDING",
            PendingAction.expires_at > datetime.utcnow()
        ).order_by(PendingAction.created_at.desc()).first()

        confirm_keywords = ["confirm", "yes", "proceed", "sure", "book it", "please confirm", "go ahead", "yep", "ok confirm"]
        decline_keywords = ["decline", "no", "cancel that", "don't confirm", "stop", "nevermind", "change my mind"]

        if active_pending and any(text == k or text.startswith(k + " ") or f" {k}" in text for k in confirm_keywords):
            event = self.executor.execute_tool("confirm_pending_action", {"action_id": active_pending.id, "confirmed": True})
            tool_events.append(event)
            if event["status"] == "success":
                data = event["data"]
                if active_pending.action_type == "BOOK":
                    reply = (
                        f"Your appointment is confirmed! Your booking reference is **{data['booking_reference']}** "
                        f"and your verification code is **{data['verification_code']}**. "
                        f"We have reserved your slot for {data['details']['formatted_date']} at {data['details']['formatted_time']} "
                        f"with {data['details']['provider_name']}. Please keep your reference handy!"
                    )
                elif active_pending.action_type == "RESCHEDULE":
                    reply = (
                        f"Your appointment ({data['booking_reference']}) has been successfully rescheduled to "
                        f"{data['details']['new_formatted_date']} at {data['details']['new_formatted_time']} with {data['details']['provider_name']}."
                    )
                else:
                    reply = f"Your appointment ({data['booking_reference']}) has been cancelled as requested."
            else:
                reply = f"I could not complete your confirmation: {event['result_summary']}"
            return reply, tool_events, None

        if active_pending and any(text == k or f" {k}" in text for k in decline_keywords):
            event = self.executor.execute_tool("confirm_pending_action", {"action_id": active_pending.id, "confirmed": False})
            tool_events.append(event)
            reply = "No problem, I have cancelled the pending action. No changes were made to your records. How else may I assist you?"
            return reply, tool_events, None

        # 2. Human Handoff Request
        if any(phrase in text for phrase in ["human", "receptionist", "speak to someone", "operator", "talk to a person", "agent", "emergency"]):
            # Extract phone or default
            phone_match = re.search(r"(\+?\d[\d\s-]{8,15}\d)", user_text)
            phone = phone_match.group(1) if phone_match else "+91 98765 00000"
            name_match = re.search(r"(?:i am|my name is|for)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
            name = name_match.group(1) if name_match else "Patient"
            
            event = self.executor.execute_tool("create_handoff_request", {
                "patient_name": name,
                "patient_phone": phone,
                "reason": user_text
            })
            tool_events.append(event)
            reply = (
                f"I have notified our clinic reception desk. A member of our team will contact you at "
                f"{phone} shortly to assist you."
            )
            return reply, tool_events, None

        # 3. Verification Intent: e.g. "Verify CB-1001 with code 4821"
        ref_match = re.search(r"(CB-\d{4,5})", user_text, re.IGNORECASE)
        code_str = None
        code_named_match = re.search(r"(?:code|pin|verification)\s*(?:is|:)?\s*(\d{4})", user_text, re.IGNORECASE)
        if code_named_match:
            code_str = code_named_match.group(1)
        elif ref_match:
            ref_digits = ref_match.group(1).split("-")[1]
            all_digits = re.findall(r"\b\d{4}\b", user_text)
            for d in all_digits:
                if d != ref_digits:
                    code_str = d
                    break
        elif re.search(r"\b\d{4}\b", user_text):
            code_str = re.search(r"\b\d{4}\b", user_text).group(0)

        if ("verify" in text or "code" in text or "pin" in text) and ref_match and code_str:
            ref = ref_match.group(1).upper()
            code = code_str
            event = self.executor.execute_tool("verify_booking_access", {
                "booking_reference": ref,
                "verification_code": code
            })
            tool_events.append(event)
            if event["status"] == "success":
                # Automatically find appointment details for user
                find_event = self.executor.execute_tool("find_appointment", {"booking_reference": ref})
                tool_events.append(find_event)
                if find_event["status"] == "success":
                    app = find_event["data"]
                    reply = (
                        f"Access verified for booking **{ref}**! Here are your appointment details:\n"
                        f"- **Patient**: {app['patient_name']}\n"
                        f"- **Doctor**: {app['provider_name']} ({app['provider_specialty']})\n"
                        f"- **Date & Time**: {app['formatted_date']} at {app['formatted_time']}\n"
                        f"- **Status**: {app['status']}\n\n"
                        f"Would you like to keep this, reschedule to another time, or cancel it?"
                    )
                else:
                    reply = f"Verified access for {ref}, but could not retrieve details: {find_event['result_summary']}"
            else:
                reply = f"Verification failed: {event['result_summary']}"
            return reply, tool_events, None

        # 4. Find / Lookup Appointment Intent
        if ref_match and any(w in text for w in ["find", "lookup", "check my", "status", "view", "appointment"]):
            ref = ref_match.group(1).upper()
            event = self.executor.execute_tool("find_appointment", {"booking_reference": ref})
            tool_events.append(event)
            if event["status"] == "success":
                app = event["data"]
                reply = (
                    f"Found your booking **{ref}**:\n"
                    f"- **Patient**: {app['patient_name']}\n"
                    f"- **Doctor**: {app['provider_name']} ({app['provider_specialty']})\n"
                    f"- **Date & Time**: {app['formatted_date']} at {app['formatted_time']}\n"
                    f"- **Status**: {app['status']}."
                )
            else:
                reply = f"I cannot display that appointment: {event['result_summary']}"
            return reply, tool_events, None

        # 5. Cancellation Intent
        if "cancel" in text and (ref_match or "my appointment" in text or "booking" in text):
            ref = ref_match.group(1).upper() if ref_match else None
            if not ref:
                # Check if session has a verified booking
                from app.models import VerificationSession
                v = self.db.query(VerificationSession).filter(
                    VerificationSession.session_id == self.session_id,
                    VerificationSession.is_verified == True,
                    VerificationSession.expires_at > datetime.utcnow()
                ).first()
                if v:
                    ref = v.booking_reference

            if not ref:
                reply = "To cancel an appointment, please provide your booking reference (e.g. CB-1001) and 4-digit verification code."
                return reply, tool_events, None

            event = self.executor.execute_tool("prepare_cancellation", {
                "booking_reference": ref,
                "reason": "Cancelled per patient conversational request"
            })
            tool_events.append(event)
            if event["status"] == "success":
                pending_action_summary = event["data"]
                reply = (
                    f"I have prepared the cancellation for booking **{ref}**.\n\n"
                    f"**Summary**: {event['data']['summary_text']}\n\n"
                    f"Please confirm: Would you like to proceed with cancelling this appointment?"
                )
            else:
                reply = f"Could not prepare cancellation: {event['result_summary']}"
            return reply, tool_events, pending_action_summary

        # 6. Reschedule Intent
        if any(w in text for w in ["reschedule", "change time", "move my appointment", "postpone", "another slot"]):
            ref = ref_match.group(1).upper() if ref_match else None
            if not ref:
                from app.models import VerificationSession
                v = self.db.query(VerificationSession).filter(
                    VerificationSession.session_id == self.session_id,
                    VerificationSession.is_verified == True,
                    VerificationSession.expires_at > datetime.utcnow()
                ).first()
                if v:
                    ref = v.booking_reference

            if not ref:
                reply = "To reschedule, please provide your booking reference (e.g. CB-1001) and your 4-digit verification code first."
                return reply, tool_events, None

            # Get target appointment provider to check availability
            app = self.db.query(Appointment).filter(Appointment.booking_reference == ref).first()
            if not app:
                reply = f"Could not find appointment {ref}."
                return reply, tool_events, None

            # Check date in text or default to tomorrow/next available
            target_date_phrase = "tomorrow"
            for phrase in ["today", "tomorrow", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
                if phrase in text:
                    target_date_phrase = phrase
                    break

            time_of_day = "afternoon" if "afternoon" in text else ("evening" if "evening" in text else None)
            
            # Check availability for provider
            avail_event = self.executor.execute_tool("check_availability", {
                "provider_name_or_id": str(app.provider_id),
                "date": target_date_phrase,
                "time_of_day": time_of_day
            })
            tool_events.append(avail_event)

            if avail_event["status"] == "success" and avail_event["data"]["slots"]:
                slots = avail_event["data"]["slots"]
                # Match specific requested time if provided (e.g. "11:00" or "2pm")
                selected_slot = slots[0]
                time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text)
                if time_match:
                    t_str = time_match.group(1)
                    for s in slots:
                        if t_str in s["formatted_time"].lower():
                            selected_slot = s
                            break

                resched_event = self.executor.execute_tool("prepare_reschedule", {
                    "booking_reference": ref,
                    "new_start_time": selected_slot["start_time"]
                })
                tool_events.append(resched_event)
                if resched_event["status"] == "success":
                    pending_action_summary = resched_event["data"]
                    reply = (
                        f"I have prepared the reschedule for **{ref}**:\n\n"
                        f"{resched_event['data']['summary_text']}\n\n"
                        f"Would you like me to confirm this new slot?"
                    )
                else:
                    reply = f"Could not reschedule: {resched_event['result_summary']}"
            else:
                reply = f"No open slots found for {app.provider.name} on {target_date_phrase}. Would you like to check another day?"
            return reply, tool_events, pending_action_summary

        # 7. Check Availability Intent
        if any(w in text for w in ["available", "availability", "slots", "openings", "free", "when is"]):
            # Identify provider
            provider_str = "Dr. Aisha Rao"
            if "patel" in text or "vikram" in text or "pediatric" in text:
                provider_str = "Dr. Vikram Patel"
            elif "nambiar" in text or "meera" in text or "derma" in text or "skin" in text:
                provider_str = "Dr. Meera Nambiar"

            target_date_str = "tomorrow"
            for phrase in ["today", "tomorrow", "day after tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
                if phrase in text:
                    target_date_str = phrase
                    break

            time_of_day = "afternoon" if "afternoon" in text else ("evening" if "evening" in text else ("morning" if "morning" in text else None))

            event = self.executor.execute_tool("check_availability", {
                "provider_name_or_id": provider_str,
                "date": target_date_str,
                "time_of_day": time_of_day
            })
            tool_events.append(event)
            if event["status"] == "success":
                data = event["data"]
                slots = data["slots"]
                if slots:
                    slot_list = "\n".join([f"- **{s['formatted_time']}**" for s in slots[:5]])
                    reply = (
                        f"Here are available 30-minute slots for **{data['provider_name']}** ({data['specialty']}) "
                        f"on **{data['formatted_date']}** (Consultation fee: ₹{data['fee']}):\n\n"
                        f"{slot_list}\n\n"
                        f"Would you like to book one of these slots? Just reply with your preferred time, your name, and phone number."
                    )
                else:
                    reply = f"No open slots available for {data['provider_name']} on {data['formatted_date']}. Would you like to check another date or another specialist?"
            else:
                reply = f"Could not check availability: {event['result_summary']}"
            return reply, tool_events, None

        # 8. Booking Intent: e.g. "Book Dr Aisha tomorrow at 10 AM for Rahul Sharma, phone 9876543210"
        if any(w in text for w in ["book", "schedule", "reserve", "make an appointment"]):
            # Identify provider
            provider_id = 1
            if "patel" in text or "vikram" in text or "pediatric" in text:
                provider_id = 2
            elif "meera" in text or "nambiar" in text or "derma" in text:
                provider_id = 3

            provider = self.db.query(Provider).filter(Provider.id == provider_id).first()
            target_date_str = "tomorrow"
            for phrase in ["today", "tomorrow", "day after tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
                if phrase in text:
                    target_date_str = phrase
                    break

            # Find available slot
            avail_event = self.executor.execute_tool("check_availability", {
                "provider_name_or_id": str(provider_id),
                "date": target_date_str
            })
            tool_events.append(avail_event)

            if avail_event["status"] == "success" and avail_event["data"]["slots"]:
                slots = avail_event["data"]["slots"]
                selected_slot = slots[0]
                # Try matching time in user text (e.g. 10:00, 10 am, 11:30)
                time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text)
                if time_match:
                    t_str = time_match.group(1).replace(" ", "")
                    for s in slots:
                        if t_str in s["formatted_time"].lower().replace(" ", ""):
                            selected_slot = s
                            break

                # Extract name and phone
                phone_match = re.search(r"(\+?\d[\d\s-]{8,15}\d)", user_text)
                phone = phone_match.group(1) if phone_match else "+91 98765 43210"

                name_match = re.search(r"(?:for|patient|name(?: is)?)\s+([A-Za-z\s]{3,25})", user_text, re.IGNORECASE)
                name = name_match.group(1).strip() if name_match else "Rahul Sharma"
                if any(w in name.lower() for w in ["phone", "dr", "doctor", "appointment", "at", "on"]):
                    name = "Patient"

                prep_event = self.executor.execute_tool("prepare_booking", {
                    "patient_name": name,
                    "patient_phone": phone,
                    "provider_id": provider_id,
                    "start_time": selected_slot["start_time"],
                    "notes": "Booked via receptionist conversational interaction"
                })
                tool_events.append(prep_event)

                if prep_event["status"] == "success":
                    pending_action_summary = prep_event["data"]
                    reply = (
                        f"I have staged your booking with **{provider.name}**!\n\n"
                        f"**Summary**: {prep_event['data']['summary_text']}\n\n"
                        f"Please review the details above. Say **'Yes, confirm'** or click the confirmation button to finalize your reservation."
                    )
                else:
                    reply = f"Could not prepare booking: {prep_event['result_summary']}"
            else:
                reply = f"I'm sorry, no open slots are available for {provider.name} on {target_date_str}. Let me check another date for you."
            return reply, tool_events, pending_action_summary

        # 9. List Providers Intent
        if any(w in text for w in ["doctor", "physician", "provider", "specialist", "pediatrician", "dermatologist", "who works"]):
            event = self.executor.execute_tool("list_providers", {})
            tool_events.append(event)
            if event["status"] == "success":
                provs = event["data"]
                lines = []
                for p in provs:
                    lines.append(f"- **{p['name']}** ({p['title']}): {p['specialty']}, Consultation Fee: ₹{p['consultation_fee']}")
                reply = "Here are our practicing specialists at CareBridge Clinic:\n\n" + "\n".join(lines) + "\n\nWould you like to check availability for any of them?"
            else:
                reply = "Unable to fetch provider directory."
            return reply, tool_events, None

        # 10. General Clinic Info / Hours / Fees / Greeting
        event = self.executor.execute_tool("get_clinic_information", {})
        tool_events.append(event)
        clinic = event["data"]

        if any(w in text for w in ["fee", "cost", "price", "charge", "rate"]):
            services_lines = [f"- **{s['name']}**: ₹{s['fee']} ({s['duration']})" for s in clinic["services"]]
            reply = f"Here is the fee schedule at {clinic['name']}:\n\n" + "\n".join(services_lines) + "\n\nWould you like to schedule a consultation with any of our doctors?"
        elif any(w in text for w in ["hour", "open", "timing", "time", "sunday"]):
            reply = (
                f"{clinic['name']} operates:\n"
                f"- **Monday to Friday**: {clinic['hours']['Monday_to_Friday']}\n"
                f"- **Saturday**: {clinic['hours']['Saturday']}\n"
                f"- **Sunday**: {clinic['hours']['Sunday']}\n\n"
                f"We are located at {clinic['address']}."
            )
        elif any(w in text for w in ["location", "address", "where", "directions"]):
            reply = f"{clinic['name']} is located at **{clinic['address']}**, Hyderabad. Our clinic contact phone is {clinic['phone']}."
        else:
            reply = (
                f"Hello! Welcome to **{clinic['name']}**, Hyderabad. I am your AI receptionist.\n\n"
                f"I can help you check doctor availability, book appointments, reschedule or cancel existing bookings, "
                f"or answer questions regarding our services and consultation fees.\n\n"
                f"How may I assist you today?"
            )
        return reply, tool_events, None
