# VoiceDesk — Agentic AI Receptionist for CareBridge Clinic

VoiceDesk is an agentic AI receptionist built for **CareBridge Clinic**, a fictional multi-specialty healthcare practice in Jubilee Hills, Hyderabad, India. Operating in the `Asia/Kolkata` (IST, UTC+5:30) timezone, VoiceDesk handles clinic inquiries, checks doctor availability, books appointments, verifies patient identity, reschedules/cancels visits with explicit two-phase confirmation, and escalates complex requests to human staff.

---

## Architecture Overview

```
                                      +--------------------------------------------+
                                      |            React + Vite Frontend           |
                                      |         Port 5180 (Proxies /api to 8000)   |
                                      |  (Tailwind CSS, LiveKit WebRTC / Fallback) |
                                      +---------------------+----------------------+
                                                            | HTTP / WebRTC Data Channel
                                                            v
                                      +--------------------------------------------+
                                      |          FastAPI Application Server        |
                                      |                  Port 8000                 |
                                      |  - Session & Token Authorization Gate      |
                                      |  - Tool Orchestration & Audit Event Logger  |
                                      |  - Concurrency Lock & Availability Service |
                                      +----------+----------------------+----------+
                                                 |                      |
                            +--------------------+                      +--------------------+
                            v                                                                v
+--------------------------------------------+                      +--------------------------------------------+
|             Agentic AI Engine              |                      |           PostgreSQL / SQLite DB           |
|  - Live Mode: Groq LLaMA 3.3 Tool Calling  |                      |  - Providers, Services, Schedules          |
|  - Demo Mode: Deterministic Rules Engine   |                      |  - Appointments, PendingActions, Audit     |
+--------------------------------------------+                      +--------------------------------------------+
                            ^                                                                ^
                            |                                                                |
                            +--------------------+                      +--------------------+
                                                 |                      |
                                      +----------+----------------------+----------+
                                      |         LiveKit Persistent Worker          |
                                      |     (voice-worker/agent_worker.py)         |
                                      |  - Deepgram STT -> Server -> Cartesia TTS  |
                                      |  - LiveKit Agents SDK 1.8.6+               |
                                      +--------------------------------------------+
```

---

## Core Capabilities & Engineering Safeguards

1. **Strict 2-Phase Mutation Cycle**:
   - Booking, rescheduling, and cancellation generate a server-bound, 10-minute expiring `PendingAction`.
   - The user is presented with the exact doctor, date, time, and consultation fee before committing.
   - Persistence occurs *only* after explicit user confirmation (`confirm_pending_action`).
   - If the patient changes the requested date, time, or doctor, any prior pending action is immediately invalidated and superseded.
2. **Session-Bound Identity Verification**:
   - Patient appointment details and mutations require a valid `booking_reference` and 4-digit verification code.
   - Access is cryptographically bound to the server session with rate-limiting (max 5 failed attempts). Unverified users cannot read or mutate records.
3. **Database-Level Concurrency Protection**:
   - Dual-layer protection: application-level transaction verification and partial unique index on `(provider_id, start_time)` for active appointments.
   - Simultaneous competing requests cannot double-book a slot.
4. **Atomic Rescheduling with Rollback Safety**:
   - If a new target slot conflicts or fails revalidation at commit time, the original appointment remains untouched.
5. **IST Timezone & Dynamic Date Resolution**:
   - All schedules and appointments resolve in `Asia/Kolkata` (IST). Phrases like *"tomorrow afternoon"* or *"next Wednesday"* correctly resolve to available 30-minute intervals between 12:00 PM and 5:00 PM based on the dynamic clock.
6. **Dual Voice Architecture**:
   - **LiveKit WebRTC Stream**: Official `livekit-client` integration connecting to session-scoped rooms (`room_<session_token>`). Subscribes to agent audio, publishes local microphone audio, and carries transcripts, tool activity, and pending confirmation cards over reliable room data packets.
   - **Browser Web Speech Mode (Fallback)**: Browser-native speech recognition and synthesis. Includes microphone echo prevention (filtering assistant output from speech recognition), intentional spoken interruption handling, and an explicit "Stop Speaking" button in the toolbar.
7. **Non-Destructive Seeding**:
   - Normal seeding (`python -m app.seed` or startup) only generates missing synthetic records on open provider slots. Existing past, rescheduled, or cancelled appointments are never overwritten or revived.
   - Full baseline restoration is strictly isolated behind the admin-protected `/api/system/reset-demo` endpoint.

---

## Quick Start (Local Windows PowerShell)

The local setup uses backend port **8000** and frontend port **5180**.

### Terminal 1: Backend Setup & Seed

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment (if not already created)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies (FastAPI, SQLAlchemy, livekit-api, etc.)
pip install -r requirements.txt

# Initialize & non-destructively seed database with dynamic IST dates
python -m app.seed

# Start FastAPI backend on port 8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Backend API will be accessible at `http://127.0.0.1:8000` with Swagger docs at `http://127.0.0.1:8000/docs`.

### Terminal 2: Frontend Setup

```powershell
# Navigate to frontend directory
cd frontend

# Install npm dependencies (including livekit-client)
npm install

# Start Vite development server on port 5180
npm run dev -- --host 127.0.0.1
```
Open `http://localhost:5180` in Chrome or Edge.

### Terminal 3 (Optional): LiveKit Agent Worker

If you have configured LiveKit server and provider API keys:

```powershell
cd voice-worker
pip install -r requirements.txt
python agent_worker.py
```

---

## Configuration & Environment Variables

Create `.env` in the repository root or in `backend/.env` (both are automatically detected):

```ini
# Database (defaults to local SQLite)
DATABASE_URL=sqlite:///./voicedesk.db

# Security & Admin Access
SECRET_KEY=replace-with-a-random-secret-key-at-least-32-characters-long
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CareBridge2026!
ENVIRONMENT=development
DEMO_MODE=true

# Groq LLM (Required if DEMO_MODE=false)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TIMEOUT_SECONDS=30.0

# LiveKit WebRTC Voice Credentials (Optional - leave empty for Browser Fallback)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Speech-to-Text & Text-to-Speech Plugins (Used by agent_worker.py)
DEEPGRAM_API_KEY=your_deepgram_api_key
CARTESIA_API_KEY=your_cartesia_api_key
```

### Production Hardening
When `ENVIRONMENT=production`, the application refuses startup if:
- Default `SECRET_KEY` is unchanged.
- Default `ADMIN_PASSWORD` is used.
- `DEMO_MODE=true` is enabled.

### Live Credentials Disclosure
> [!NOTE]
> In this local development and portfolio evaluation environment, no live external Groq API key or LiveKit server credentials were configured. The system gracefully operates with its deterministic simulator, dynamic database tools, and browser Web Speech API. Live tool calling, error handlers, and LiveKit token generation have been validated via automated tests.

---

## Pre-seeded Synthetic Demo Appointments

For portfolio testing, CareBridge Clinic seeds dynamic appointments relative to the current Asia/Kolkata date:

| Booking Reference | PIN Code | Patient Name | Provider & Specialty |
|---|---|---|---|
| **CB-1001** | `4821` | Rahul Sharma | Dr. Aisha Rao (General Physician) |
| **CB-1002** | `7390` | Ananya Reddy | Dr. Vikram Patel (Pediatrician) |
| **CB-1003** | `1945` | Karthik Verma | Dr. Meera Nambiar (Dermatologist) |

### Clinic Providers:
- **Dr. Aisha Rao** (General Physician): Mon–Fri 09:00–17:00 (Break: 13:00–14:00) — Fee: ₹800
- **Dr. Vikram Patel** (Pediatrician): Mon–Sat 10:00–19:00 (Break: 14:00–16:00) — Fee: ₹1,000
- **Dr. Meera Nambiar** (Dermatologist): Tue–Sat 11:00–19:30 (Break: 15:00–16:30) — Fee: ₹1,200

### Admin Portal Credentials:
- **URL**: Click *Admin Portal* tab on navigation bar.
- **Username**: `admin`
- **Password**: `CareBridge2026!`

---

## Running Automated Tests

### 1. Backend Business & Concurrency Suite (`pytest`)
Executes 17 tests covering slot booking, unverified access blocking, reschedule confirmation requirement, decline state preservation, concurrent double-booking prevention, idempotent repeated confirmations, atomic reschedule rollbacks, Groq tool-calling loops, superseded pending action invalidation, production hardening, and non-destructive re-seeding regressions.

```powershell
cd backend
python -m pytest tests -v
```

### 2. End-to-End Browser Flow Suite (`Playwright`)
Executes browser automation verifying:
1. `test_browser_flow.py`: Verified lookup (CB-1001) ➔ Reschedule request ➔ Confirmation card ➔ Admin record verification ➔ Responsive layout.
2. `test_voice_and_booking_flows.py`: Text booking flow ➔ Confirmation persistence ➔ Admin verification ➔ Browser microphone recognition ➔ SpeechSynthesis audio playback ➔ Mute/unmute ➔ End call ➔ Missing LiveKit credentials error flow.

```powershell
# Ensure backend (port 8000) and frontend (port 5180) are running
python tests-e2e/test_browser_flow.py
python tests-e2e/test_voice_and_booking_flows.py
```

---

## Docker Compose Configurations

Two clearly separated Docker Compose configurations are provided:

1. **`docker-compose.yml` (Local Demo & Development)**:
   - Sets `ENVIRONMENT: development` and `DEMO_MODE: "true"`.
   - Pre-configures local PostgreSQL, FastAPI backend on port 8000, and Nginx frontend on port 5180.
   - Command: `docker compose up --build`

2. **`docker-compose.prod.yml` (Production Deployment)**:
   - Sets `ENVIRONMENT: production` and `DEMO_MODE: "false"`.
   - Strictly enforces required production secrets via environment variables (`POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_PASSWORD`, `GROQ_API_KEY`).
   - Command: `docker compose -f docker-compose.prod.yml up --build`

*Note: Docker was not available on the current Windows host environment during testing; local execution and end-to-end verification were conducted directly on Windows PowerShell with Python 3.12 and Node 20.*
