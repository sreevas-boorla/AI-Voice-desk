import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, Float, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    specialty = Column(String(100), nullable=False, index=True)
    bio = Column(Text, nullable=False)
    consultation_fee = Column(Integer, nullable=False)  # in INR
    avatar_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    schedules = relationship("ProviderSchedule", back_populates="provider", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="provider")
    blocked_slots = relationship("BlockedSlot", back_populates="provider", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    duration_minutes = Column(Integer, default=30)
    fee = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)

    appointments = relationship("Appointment", back_populates="service")


class ProviderSchedule(Base):
    __tablename__ = "provider_schedules"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String(10), nullable=False)  # "09:00"
    end_time = Column(String(10), nullable=False)    # "17:00"
    break_start = Column(String(10), nullable=True)  # "13:00"
    break_end = Column(String(10), nullable=True)    # "14:00"
    is_active = Column(Boolean, default=True)

    provider = relationship("Provider", back_populates="schedules")


class BlockedSlot(Base):
    __tablename__ = "blocked_slots"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=False)

    provider = relationship("Provider", back_populates="blocked_slots")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    phone = Column(String(30), nullable=False, index=True)
    email = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="patient")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    booking_reference = Column(String(32), unique=True, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="CONFIRMED", index=True)  # CONFIRMED, RESCHEDULED, CANCELLED, COMPLETED
    verification_code = Column(String(10), nullable=False, default="1234")
    
    notes = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    rescheduled_from_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="appointments")
    provider = relationship("Provider", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(64), unique=True, nullable=False, index=True)
    channel = Column(String(20), default="text")  # "text", "voice"
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    verification_sessions = relationship("VerificationSession", back_populates="session", cascade="all, delete-orphan")
    pending_actions = relationship("PendingAction", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user", "assistant", "system", "tool"
    content = Column(Text, nullable=False)
    tool_calls_json = Column(Text, nullable=True)
    tool_call_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ConversationSession", back_populates="messages")


class VerificationSession(Base):
    __tablename__ = "verification_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_reference = Column(String(32), nullable=False, index=True)
    verification_code = Column(String(10), nullable=False)
    is_verified = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    verified_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ConversationSession", back_populates="verification_sessions")


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    session_id = Column(Integer, ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(30), nullable=False)  # "BOOK", "RESCHEDULE", "CANCEL"
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING", index=True)  # "PENDING", "CONFIRMED", "REJECTED", "EXPIRED"
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ConversationSession", back_populates="pending_actions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(40), nullable=False, index=True)  # "APPOINTMENT", "VERIFICATION", "HANDOFF", "PENDING_ACTION"
    entity_id = Column(String(64), nullable=True, index=True)
    action = Column(String(40), nullable=False, index=True)
    actor_type = Column(String(20), nullable=False)  # "PATIENT", "AGENT", "ADMIN", "SYSTEM"
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class HandoffRequest(Base):
    __tablename__ = "handoff_requests"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("conversation_sessions.id", ondelete="SET NULL"), nullable=True)
    patient_name = Column(String(120), nullable=False)
    patient_phone = Column(String(30), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="OPEN", index=True)  # "OPEN", "IN_PROGRESS", "RESOLVED"
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="ADMIN")
    created_at = Column(DateTime, default=datetime.utcnow)
