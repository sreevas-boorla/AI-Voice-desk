from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.models import (
    Provider, Service, ProviderSchedule, BlockedSlot,
    Patient, Appointment, AdminUser
)
from app.auth import hash_password
from app.config import settings

def seed_database(db: Session):
    # 1. Admin User
    admin = db.query(AdminUser).filter(AdminUser.username == settings.ADMIN_USERNAME).first()
    if not admin:
        admin = AdminUser(
            username=settings.ADMIN_USERNAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role="ADMIN"
        )
        db.add(admin)

    # 2. Services
    services_data = [
        {"name": "General Physician Consultation", "duration_minutes": 30, "fee": 800, "description": "Consultation with internal medicine specialist for routine or acute ailments."},
        {"name": "Pediatric Consultation", "duration_minutes": 30, "fee": 1000, "description": "Child health assessment, wellness checkup, and developmental guidance."},
        {"name": "Dermatology Consultation", "duration_minutes": 30, "fee": 1200, "description": "Skin, hair, and aesthetic health evaluation."},
        {"name": "Follow-up Visit", "duration_minutes": 30, "fee": 400, "description": "Review within 7 days of primary consultation."},
        {"name": "Comprehensive Health Checkup", "duration_minutes": 30, "fee": 2500, "description": "Full clinical screening, vitals analysis, and preventative consultation."}
    ]
    services = {}
    for s in services_data:
        obj = db.query(Service).filter(Service.name == s["name"]).first()
        if not obj:
            obj = Service(**s)
            db.add(obj)
            db.flush()
        services[s["name"]] = obj

    # 3. Providers
    providers_data = [
        {
            "name": "Dr. Aisha Rao",
            "title": "Senior Consultant - Internal Medicine",
            "specialty": "General Physician",
            "bio": "MD Internal Medicine with 14 years of clinical experience in preventative care, chronic disease management, and family medicine.",
            "consultation_fee": 800,
            "avatar_url": "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=300",
            # Mon-Fri: 09:00 - 13:00, 14:00 - 17:00 (Break: 13:00 - 14:00)
            "days": [0, 1, 2, 3, 4],
            "start": "09:00",
            "end": "17:00",
            "b_start": "13:00",
            "b_end": "14:00"
        },
        {
            "name": "Dr. Vikram Patel",
            "title": "Lead Pediatrician & Neonatologist",
            "specialty": "Pediatrician",
            "bio": "DNB Pediatrics with 11 years of experience in newborn care, immunization, developmental monitoring, and adolescent health.",
            "consultation_fee": 1000,
            "avatar_url": "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=300",
            # Mon-Sat: 10:00 - 14:00, 16:00 - 19:00 (Break: 14:00 - 16:00)
            "days": [0, 1, 2, 3, 4, 5],
            "start": "10:00",
            "end": "19:00",
            "b_start": "14:00",
            "b_end": "16:00"
        },
        {
            "name": "Dr. Meera Nambiar",
            "title": "Consultant Dermatologist & Cosmetologist",
            "specialty": "Dermatologist",
            "bio": "MD Dermatology with 9 years of specialization in medical dermatology, acne therapies, allergic disorders, and clinical aesthetics.",
            "consultation_fee": 1200,
            "avatar_url": "https://images.unsplash.com/photo-1594824813627-7f9185a6a090?auto=format&fit=crop&q=80&w=300",
            # Tue-Sat: 11:00 - 15:00, 16:30 - 19:30 (Break: 15:00 - 16:30)
            "days": [1, 2, 3, 4, 5],
            "start": "11:00",
            "end": "19:30",
            "b_start": "15:00",
            "b_end": "16:30"
        }
    ]

    providers = {}
    for p_info in providers_data:
        p = db.query(Provider).filter(Provider.name == p_info["name"]).first()
        if not p:
            p = Provider(
                name=p_info["name"],
                title=p_info["title"],
                specialty=p_info["specialty"],
                bio=p_info["bio"],
                consultation_fee=p_info["consultation_fee"],
                avatar_url=p_info["avatar_url"],
                is_active=True
            )
            db.add(p)
            db.flush()

            for d in p_info["days"]:
                sched = ProviderSchedule(
                    provider_id=p.id,
                    day_of_week=d,
                    start_time=p_info["start"],
                    end_time=p_info["end"],
                    break_start=p_info["b_start"],
                    break_end=p_info["b_end"],
                    is_active=True
                )
                db.add(sched)
        providers[p_info["name"]] = p

    # 4. Blocked Slot for demonstration
    aisha = providers["Dr. Aisha Rao"]
    b_slot = db.query(BlockedSlot).filter(BlockedSlot.provider_id == aisha.id).first()
    if not b_slot:
        db.add(BlockedSlot(
            provider_id=aisha.id,
            start_time=datetime(2026, 10, 14, 14, 0),
            end_time=datetime(2026, 10, 14, 15, 0),
            reason="Hospital Clinical Board Meeting"
        ))

    # 5. Synthetic Patients & Appointments
    patients_data = [
        {"name": "Rahul Sharma", "phone": "+91 98765 43210", "email": "rahul.sharma@example.com"},
        {"name": "Ananya Reddy", "phone": "+91 91234 56789", "email": "ananya.reddy@example.com"},
        {"name": "Karthik Verma", "phone": "+91 99887 76655", "email": "karthik.v@example.com"}
    ]
    patients = {}
    for pt in patients_data:
        p = db.query(Patient).filter(Patient.phone == pt["phone"]).first()
        if not p:
            p = Patient(full_name=pt["name"], phone=pt["phone"], email=pt["email"])
            db.add(p)
            db.flush()
        patients[pt["phone"]] = p

    sample_appointments = [
        {
            "reference": "CB-1001",
            "patient_phone": "+91 98765 43210",
            "provider_name": "Dr. Aisha Rao",
            "service_name": "General Physician Consultation",
            "start": datetime(2026, 10, 13, 10, 0),
            "end": datetime(2026, 10, 13, 10, 30),
            "code": "4821",
            "notes": "Follow-up for mild seasonal allergy."
        },
        {
            "reference": "CB-1002",
            "patient_phone": "+91 91234 56789",
            "provider_name": "Dr. Vikram Patel",
            "service_name": "Pediatric Consultation",
            "start": datetime(2026, 10, 14, 11, 30),
            "end": datetime(2026, 10, 14, 12, 0),
            "code": "7390",
            "notes": "Routine vaccination checkup."
        },
        {
            "reference": "CB-1003",
            "patient_phone": "+91 99887 76655",
            "provider_name": "Dr. Meera Nambiar",
            "service_name": "Dermatology Consultation",
            "start": datetime(2026, 10, 15, 15, 0),
            "end": datetime(2026, 10, 15, 15, 30),
            "code": "1945",
            "notes": "Skin patch allergy consultation."
        }
    ]

    for app in sample_appointments:
        existing_app = db.query(Appointment).filter(Appointment.booking_reference == app["reference"]).first()
        if not existing_app:
            pt = patients[app["patient_phone"]]
            pr = providers[app["provider_name"]]
            srv = services[app["service_name"]]
            db.add(Appointment(
                booking_reference=app["reference"],
                patient_id=pt.id,
                provider_id=pr.id,
                service_id=srv.id,
                start_time=app["start"],
                end_time=app["end"],
                status="CONFIRMED",
                verification_code=app["code"],
                notes=app["notes"]
            ))

    db.commit()

if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        seed_database(db)
    print("Database successfully initialized and seeded.")
