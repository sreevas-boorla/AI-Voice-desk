# Run the verified browser demo

The supported voice path uses browser SpeechRecognition and SpeechSynthesis. LiveKit's worker is scaffolding and is not connected; no API reports it as active. Text chat works without microphone access. Use Chrome on localhost or HTTPS for browser voice; browser support varies.

From the repository root (Windows PowerShell), run in terminal 1:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.txt
cd backend
..\.venv\Scripts\python -m app.seed
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In terminal 2:

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://localhost:5180. The frontend proxies `/api` to port 8000.

Default DEMO_MODE=true uses a deterministic simulator and real local database tools. For real LLM responses create `backend/.env` with `DEMO_MODE=false` and `GROQ_API_KEY` set locally, then restart the backend. Only Groq is implemented. Never commit this file. Live mode uses confirmation cards for mutations. No live provider call has been validated without credentials.

## Original project documentation (historical design)

The LiveKit and production-readiness claims below describe intended scope, not verified capabilities.

# VoiceDesk — Agentic AI Receptionist for CareBridge Clinic

VoiceDesk is a portfolio prototype of an agentic AI receptionist built for **CareBridge Clinic**, a fictional multi-specialty healthcare practice in Jubilee Hills, Hyderabad, India. Operating in the `Asia/Kolkata` (IST, UTC+5:30) timezone, VoiceDesk handles clinic inquiries, checks provider availability, books appointments, verifies patient identity, reschedules/cancels visits with explicit two-phase confirmation, and escalates unresolved matters to human receptionists.

---

## Architecture Overview

```
                                      +--------------------------------------------+
                                      |            React + Vite Frontend           |
                                      |  (Tailwind CSS, Web Speech API / WebRTC)   |
                                      +---------------------+----------------------+
                                                            | HTTP / WebSocket
                                                            v
                                      +--------------------------------------------+
                                      |          FastAPI Application Server        |
                                      |  - Session & Token Authorization Gate     |
                                      |  - Tool Orchestration & Audit Event Logger |
                                      |  - Concurrency Lock & Availability Service |
                                      +----------+----------------------+----------+
                                                 |                      |
                            +--------------------+                      +--------------------+
                            v                                                                v
+--------------------------------------------+                      +--------------------------------------------+
|             Agentic AI Engine              |                      |           PostgreSQL / SQLite DB           |
|  - Live Mode: Tool-Calling LLM             |                      |  - Providers, Services, Schedules          |
|  - Demo Mode: Deterministic Rules Engine   |                      |  - Appointments, PendingActions, Audit     |
+--------------------------------------------+                      +--------------------------------------------+
                            ^                                                                ^
                            |                                                                |
                            +--------------------+                      +--------------------+
                                                 |                      |
                                      +----------+----------------------+----------+
                                      |         LiveKit Persistent Worker          |
                                      |  (WebRTC Audio, STT / TTS Pipeline)        |
                                      +--------------------------------------------+
```

---

## Core Capabilities & Engineering Safeguards

1. **Strict 2-Phase Mutation Cycle**:
   - Booking, rescheduling, and cancellation generate a server-bound, 10-minute expiring `PendingAction`.
   - The user is presented with the exact doctor, date, time, and fee.
   - Persistence occurs *only* after explicit user confirmation (`confirm_pending_action`).
2. **Session-Bound Identity Verification**:
   - Patient appointment details and mutations require a valid `booking_reference` and 4-digit verification code.
   - Access is cryptographically bound to the server session with rate-limiting (max 5 failed attempts). Unverified users cannot read or mutate records.
3. **Database-Level Concurrency Protection**:
   - Dual-layer protection: application-level transaction verification and partial unique index on `(provider_id, start_time)` for active appointments.
   - Simultaneous competing requests cannot double-book a slot.
4. **Atomic Rescheduling with Rollback Safety**:
   - If a new target slot conflicts or fails revalidation at commit time, the original appointment remains untouched.
5. **IST Timezone & Natural Date Resolution**:
   - All schedules and appointments resolve in `Asia/Kolkata` (IST). Phrases like *"tomorrow afternoon"* or *"next Tuesday"* correctly resolve to available 30-minute intervals between 12:00 PM and 5:00 PM.
6. **Dual Mode Architecture**:
   - **Live Mode**: Uses LiveKit WebRTC with Deepgram STT, Groq/Gemini/OpenAI LLM tool calling, and Cartesia TTS.
   - **Demo Mode**: Operates in zero-API-key environments using high-fidelity browser SpeechRecognition/SpeechSynthesis and a deterministic simulator running the identical business tools and database transactions.

---

## Project Structure

```
voicedesk/
├── backend/
│   ├── app/
│   │   ├── agent/             # Tool definitions, schemas, simulator & engine
│   │   ├── routers/           # Agent, Appointments, Admin, Voice, System APIs
│   │   ├── services/          # Availability, Booking, Verification, Audit services
│   │   ├── auth.py            # JWT token creation and bcrypt password verification
│   │   ├── config.py          # Pydantic BaseSettings environment config
│   │   ├── database.py        # SQLAlchemy engine, session maker, index configuration
│   │   ├── main.py            # FastAPI entry point with CORS and lifespan handler
│   │   ├── models.py          # 11 relational SQLAlchemy data models
│   │   ├── schemas.py         # Pydantic schemas for requests, responses, and tools
│   │   └── seed.py            # Repeatable synthetic seed script for CareBridge
│   ├── alembic/               # Database migrations
│   ├── tests/                 # Automated pytest suite covering all 10 criteria
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/        # AudioVisualizer, ConfirmationCard, ActivityDrawer, Navbar
│   │   ├── pages/             # ReceptionistPage, AdminDashboard, SettingsPage
│   │   ├── services/          # Type-safe API client
│   │   └── types/             # TypeScript interfaces
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── voice-worker/
│   ├── agent_worker.py        # Standalone LiveKit Agents worker script
│   └── requirements.txt
├── tests-e2e/
│   └── test_browser_flow.py   # Playwright E2E browser automation test
├── docker-compose.yml         # Multi-container orchestration (DB, API, Web, Voice)
├── Dockerfile.backend
├── Dockerfile.frontend
├── Dockerfile.voice
├── .env.example
└── README.md
```

---

## Quick Start (Local Development)

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Git

### 2. Backend Setup
```bash
cd backend

# Create virtual environment (optional)
python -m venv venv
source venv/bin/activate # Windows: .\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Initialize & seed database
python -m app.seed

# Run FastAPI backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
The API is live at `http://127.0.0.1:8000` with interactive Swagger docs at `http://127.0.0.1:8000/docs`.

### 3. Frontend Setup
```bash
cd frontend

# Install npm dependencies
npm install

# Start Vite development server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Docker Compose Deployment

To run the complete production stack (PostgreSQL, FastAPI Backend, React Nginx Frontend, and Voice Worker):

```bash
# Clone and enter directory
cd voicedesk

# Launch containers
docker-compose up --build -d
```

Services will be accessible at:
- **Web Receptionist & Admin**: `http://localhost:5173`
- **FastAPI API**: `http://localhost:8000`
- **PostgreSQL Database**: `localhost:5432`

---

## Pre-seeded Demo Credentials

For portfolio inspection, CareBridge Clinic comes seeded with synthetic appointments:

| Booking Reference | PIN Code | Patient Name | Provider & Specialty | Scheduled Time (IST) |
|---|---|---|---|---|
| **CB-1001** | `4821` | Rahul Sharma | Dr. Aisha Rao (General Physician) | Tue, 13 Oct 2026, 10:00 AM |
| **CB-1002** | `7390` | Ananya Reddy | Dr. Vikram Patel (Pediatrician) | Wed, 14 Oct 2026, 11:30 AM |
| **CB-1003** | `1945` | Karthik Verma | Dr. Meera Nambiar (Dermatologist) | Thu, 15 Oct 2026, 03:00 PM |

### Admin Portal Credentials
- **URL**: Click *Admin Portal* tab on navigation bar.
- **Username**: `admin`
- **Password**: `CareBridge2026!`

---

## Running the Automated Test Suites

### 1. Backend Business & Concurrency Suite (`pytest`)
Executes 10 unit and integration tests verifying:
1. Available slot booking.
2. Unverified access blocking.
3. Reschedule confirmation requirement.
4. Decline state preservation.
5. Concurrent double-booking prevention.
6. Idempotent repeated confirmation.
7. Atomic reschedule rollback on conflict.
8. Asia/Kolkata date resolution.
9. Structured error handling without false success.
10. Admin authentication enforcement.

```bash
cd backend
python -m pytest tests/test_all_criteria.py -v
```

### 2. End-to-End Browser Flow (`Playwright`)
Executes browser automation verifying:
`Verified Lookup (CB-1001)` ➔ `Reschedule Request` ➔ `Explicit Confirmation` ➔ `Admin Record Verification`.

```bash
# Ensure backend and frontend are running, then:
python tests-e2e/test_browser_flow.py
```

---

## Demo Walkthrough Script

1. **Ask Clinic Hours & Fees**:
   - Speak or type: *"What are your clinic hours and consultation fees in Hyderabad?"*
   - Agent responds with CareBridge Clinic address (Jubilee Hills) and ₹800 - ₹1200 pricing.
2. **Check Availability**:
   - Say: *"Check Dr. Aisha Rao's available slots tomorrow afternoon."*
   - Agent retrieves available 30-minute intervals between 12:00 PM and 5:00 PM.
3. **Lookup Existing Booking**:
   - Say: *"Please verify booking CB-1001 with code 4821."*
   - Agent verifies access, binds session, and displays appointment card.
4. **Reschedule**:
   - Say: *"Reschedule CB-1001 to tomorrow afternoon."*
   - Interactive confirmation card appears. Click **Confirm & Persist**.
5. **Verify in Admin Portal**:
   - Navigate to *Admin Portal*, login with `admin` / `CareBridge2026!`.
   - Observe `CB-1001` row updated to `RESCHEDULED`.
