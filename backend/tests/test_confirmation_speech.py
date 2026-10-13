import sys
import json
import uuid
import asyncio
import inspect
from pathlib import Path
from datetime import datetime, timedelta
import pytest
import httpx
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# Add voice-worker directory to sys.path so SpeechManager can be imported directly
voice_worker_path = Path(__file__).resolve().parents[2] / "voice-worker"
if str(voice_worker_path) not in sys.path:
    sys.path.insert(0, str(voice_worker_path))

from speech_manager import ConfirmationSpeechManager, play_speech
from app.models import ConversationSession, PendingAction


class MockSpeechHandle:
    """An awaitable SpeechHandle object mimicking LiveKit Agents SDK (not a coroutine)."""
    def __init__(self, should_fail: bool = False, delay: float = 0.01):
        self.should_fail = should_fail
        self.delay = delay
        self.played = False

    def __await__(self):
        async def _run():
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            if self.should_fail:
                raise RuntimeError("Speech synthesis error")
            self.played = True
            return "done"
        return _run().__await__()


class MockSpeaker:
    def __init__(self, handle_factory=None):
        self.handle_factory = handle_factory or (lambda text: MockSpeechHandle())
        self.spoken_texts = []

    def say(self, text: str, allow_interruptions: bool = True):
        self.spoken_texts.append(text)
        return self.handle_factory(text)


def test_speech_handle_is_awaitable_not_coroutine():
    """
    Verifies that MockSpeechHandle mimics LiveKit's SpeechHandle:
    It implements __await__ but is NOT a coroutine function or coroutine object.
    Passing it directly to asyncio.create_task() must fail with TypeError,
    proving that play_speech() wrapper is required.
    """
    handle = MockSpeechHandle()
    assert hasattr(handle, "__await__")
    assert not inspect.iscoroutine(handle)

    async def scenario():
        with pytest.raises(TypeError, match="a coroutine was expected"):
            asyncio.create_task(handle)  # Direct task creation must fail

        # Wrapping with play_speech must succeed cleanly
        speaker = MockSpeaker()
        await play_speech(speaker, "Hello world")
        assert speaker.spoken_texts == ["Hello world"]

    asyncio.run(scenario())


def test_backend_action_result_endpoint_enforces_authoritative_rules(client: TestClient, db: Session):
    """
    Verifies the backend endpoint /api/agent/action-result/{action_id}:
    - Returns authoritative text for CONFIRMED and REJECTED states
    - Enforces session isolation (403 on cross-session access)
    - Rejects PENDING, SUPERSEDED, and EXPIRED actions
    - Rejects unknown actions (404)
    """
    # 1. Create two test sessions
    sess_a = ConversationSession(session_token=f"sess_test_a_{uuid.uuid4().hex[:6]}", channel="voice")
    sess_b = ConversationSession(session_token=f"sess_test_b_{uuid.uuid4().hex[:6]}", channel="voice")
    db.add(sess_a)
    db.add(sess_b)
    db.flush()

    # 2. Confirmed booking action on Session A
    action_book = PendingAction(
        id=f"act_book_{uuid.uuid4().hex[:8]}",
        session_id=sess_a.id,
        action_type="BOOK",
        status="CONFIRMED",
        payload_json=json.dumps({"booking_reference": "CB-9901"}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    # 3. Confirmed reschedule action on Session A
    action_resched = PendingAction(
        id=f"act_resched_{uuid.uuid4().hex[:8]}",
        session_id=sess_a.id,
        action_type="RESCHEDULE",
        status="CONFIRMED",
        payload_json=json.dumps({
            "booking_reference": "CB-9901",
            "new_formatted_date": "Wednesday, 14 October 2026",
            "new_formatted_time": "11:00 AM - 11:30 AM"
        }),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    # 4. Rejected action on Session A
    action_rejected = PendingAction(
        id=f"act_rej_{uuid.uuid4().hex[:8]}",
        session_id=sess_a.id,
        action_type="BOOK",
        status="REJECTED",
        payload_json=json.dumps({}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    # 5. Pending action on Session A
    action_pending = PendingAction(
        id=f"act_pend_{uuid.uuid4().hex[:8]}",
        session_id=sess_a.id,
        action_type="BOOK",
        status="PENDING",
        payload_json=json.dumps({}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    # 6. Superseded action on Session A
    action_superseded = PendingAction(
        id=f"act_sup_{uuid.uuid4().hex[:8]}",
        session_id=sess_a.id,
        action_type="BOOK",
        status="SUPERSEDED",
        payload_json=json.dumps({}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )

    db.add_all([action_book, action_resched, action_rejected, action_pending, action_superseded])
    db.commit()

    # A. Confirmed booking check
    res = client.get(f"/api/agent/action-result/{action_book.id}?session_token={sess_a.session_token}")
    assert res.status_code == 200
    assert "CB-9901" in res.json()["message"]
    assert res.json()["status"] == "CONFIRMED"

    # B. Confirmed reschedule check
    res = client.get(f"/api/agent/action-result/{action_resched.id}?session_token={sess_a.session_token}")
    assert res.status_code == 200
    assert "14 October 2026" in res.json()["message"]

    # C. Rejected action check
    res = client.get(f"/api/agent/action-result/{action_rejected.id}?session_token={sess_a.session_token}")
    assert res.status_code == 200
    assert "cancelled" in res.json()["message"].lower()

    # D. Cross-session access check (Session B trying to access Session A action)
    res = client.get(f"/api/agent/action-result/{action_book.id}?session_token={sess_b.session_token}")
    assert res.status_code == 403
    assert "Cross-session" in res.json()["detail"]

    # E. Pending action rejected
    res = client.get(f"/api/agent/action-result/{action_pending.id}?session_token={sess_a.session_token}")
    assert res.status_code == 400
    assert "still pending" in res.json()["detail"]

    # F. Superseded action rejected
    res = client.get(f"/api/agent/action-result/{action_superseded.id}?session_token={sess_a.session_token}")
    assert res.status_code == 400
    assert "superseded" in res.json()["detail"]

    # G. Unknown action rejected
    res = client.get(f"/api/agent/action-result/non_existent_action?session_token={sess_a.session_token}")
    assert res.status_code == 404


def test_confirmation_speech_ignores_forged_client_text(client: TestClient, db: Session):
    """
    Verifies that the ConfirmationSpeechManager ignores any client-provided 'message'
    in the room data packet and speaks strictly the backend's authoritative text.
    """
    sess = ConversationSession(session_token=f"sess_{uuid.uuid4().hex[:6]}", channel="voice")
    db.add(sess)
    db.flush()

    action = PendingAction(
        id=f"act_{uuid.uuid4().hex[:8]}",
        session_id=sess.id,
        action_type="BOOK",
        status="CONFIRMED",
        payload_json=json.dumps({"booking_reference": "CB-AUTHORITATIVE"}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(action)
    db.commit()

    async def scenario():
        speaker = MockSpeaker()
        speech_mgr = ConfirmationSpeechManager(
            session_token=sess.session_token,
            correlation_id="corr-test",
            backend_api_url="http://testserver/api"
        )

        # Use httpx.AsyncClient with app transport
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_async_client:
            # Client sends a packet with malicious forged text
            task = speech_mgr.handle_notification(
                sender_identity="patient-123",
                expected_identity="patient-123",
                packet_payload={
                    "type": "confirmation_result",
                    "action_id": action.id,
                    "message": "MALICIOUS FORGED CONFIRMATION MESSAGE"
                },
                speaker=speaker,
                client=test_async_client
            )
            assert task is not None
            await task

        # Speaker must have spoken the AUTHORITATIVE text, NOT the forged text!
        assert len(speaker.spoken_texts) == 1
        assert "CB-AUTHORITATIVE" in speaker.spoken_texts[0]
        assert "MALICIOUS" not in speaker.spoken_texts[0]
        assert action.id in speech_mgr.spoken_actions

    asyncio.run(scenario())


def test_confirmation_speech_rejects_wrong_participant():
    """
    Verifies that notifications from unauthorized or mismatched room participants
    are immediately discarded without calling the backend or speaking.
    """
    speech_mgr = ConfirmationSpeechManager(
        session_token="sess_test",
        correlation_id="corr-test",
        backend_api_url="http://testserver/api"
    )
    speaker = MockSpeaker()

    # Attacker tries to send notification from a different participant identity
    task = speech_mgr.handle_notification(
        sender_identity="attacker-identity",
        expected_identity="legitimate-patient-identity",
        packet_payload={"type": "confirmation_result", "action_id": "act_test"},
        speaker=speaker
    )
    assert task is None
    assert len(speaker.spoken_texts) == 0


def test_confirmation_speech_prevents_duplicate_notifications(client: TestClient, db: Session):
    """
    Verifies that concurrent or repeated notifications for the same action ID
    only schedule and speak the authoritative message strictly once.
    """
    sess = ConversationSession(session_token=f"sess_{uuid.uuid4().hex[:6]}", channel="voice")
    db.add(sess)
    db.flush()

    action = PendingAction(
        id=f"act_{uuid.uuid4().hex[:8]}",
        session_id=sess.id,
        action_type="BOOK",
        status="CONFIRMED",
        payload_json=json.dumps({"booking_reference": "CB-ONCE"}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(action)
    db.commit()

    async def scenario():
        speaker = MockSpeaker()
        speech_mgr = ConfirmationSpeechManager(
            session_token=sess.session_token,
            correlation_id="corr-test",
            backend_api_url="http://testserver/api"
        )

        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_async_client:
            # Send notification #1
            t1 = speech_mgr.handle_notification(
                sender_identity="patient-123",
                expected_identity="patient-123",
                packet_payload={"type": "confirmation_result", "action_id": action.id},
                speaker=speaker,
                client=test_async_client
            )
            # Rapid duplicate notification #2 while #1 is in flight
            t2 = speech_mgr.handle_notification(
                sender_identity="patient-123",
                expected_identity="patient-123",
                packet_payload={"type": "confirmation_result", "action_id": action.id},
                speaker=speaker,
                client=test_async_client
            )
            assert t1 is not None
            assert t2 is None  # Dropped because #1 is in flight!

            await t1

            # Subsequent notification #3 after #1 has finished speaking
            t3 = speech_mgr.handle_notification(
                sender_identity="patient-123",
                expected_identity="patient-123",
                packet_payload={"type": "confirmation_result", "action_id": action.id},
                speaker=speaker,
                client=test_async_client
            )
            assert t3 is None  # Dropped because #1 was already spoken!

        assert len(speaker.spoken_texts) == 1
        assert "CB-ONCE" in speaker.spoken_texts[0]

    asyncio.run(scenario())


def test_confirmation_speech_handles_backend_failure_without_marking_spoken():
    """
    Verifies that if backend returns an error (or is unreachable),
    speech is not synthesized and the action is NOT marked as spoken.
    """
    async def scenario():
        speaker = MockSpeaker()
        speech_mgr = ConfirmationSpeechManager(
            session_token="sess_test",
            correlation_id="corr-test",
            backend_api_url="http://unreachable-backend.example.com/api"
        )

        task = speech_mgr.handle_notification(
            sender_identity="patient-123",
            expected_identity="patient-123",
            packet_payload={"type": "confirmation_result", "action_id": "act_fail"},
            speaker=speaker
        )
        assert task is not None
        await task

        assert len(speaker.spoken_texts) == 0
        assert "act_fail" not in speech_mgr.spoken_actions
        assert "act_fail" not in speech_mgr.in_flight_actions

    asyncio.run(scenario())


def test_confirmation_speech_handles_playback_failure(client: TestClient, db: Session):
    """
    Verifies that if speech synthesis fails (e.g. TTS error),
    the action is NOT permanently marked as spoken.
    """
    sess = ConversationSession(session_token=f"sess_{uuid.uuid4().hex[:6]}", channel="voice")
    db.add(sess)
    db.flush()

    action = PendingAction(
        id=f"act_{uuid.uuid4().hex[:8]}",
        session_id=sess.id,
        action_type="BOOK",
        status="CONFIRMED",
        payload_json=json.dumps({"booking_reference": "CB-FAIL-TTS"}),
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(action)
    db.commit()

    async def scenario():
        # Speaker whose SpeechHandle raises an exception
        speaker = MockSpeaker(handle_factory=lambda text: MockSpeechHandle(should_fail=True))
        speech_mgr = ConfirmationSpeechManager(
            session_token=sess.session_token,
            correlation_id="corr-test",
            backend_api_url="http://testserver/api"
        )

        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_async_client:
            task = speech_mgr.handle_notification(
                sender_identity="patient-123",
                expected_identity="patient-123",
                packet_payload={"type": "confirmation_result", "action_id": action.id},
                speaker=speaker,
                client=test_async_client
            )
            assert task is not None
            await task

        # Crucial: action must NOT be marked as spoken since playback failed!
        assert action.id not in speech_mgr.spoken_actions
        assert action.id not in speech_mgr.in_flight_actions

    asyncio.run(scenario())


def test_confirmation_speech_shutdown_cancels_active_tasks():
    """
    Verifies that shutdown cancels and awaits in-flight speech tasks cleanly.
    """
    async def scenario():
        # Long running speech handle
        speaker = MockSpeaker(handle_factory=lambda text: MockSpeechHandle(delay=5.0))
        speech_mgr = ConfirmationSpeechManager(
            session_token="sess_test",
            correlation_id="corr-test",
            backend_api_url="http://testserver/api"
        )

        async def mock_fetch(action_id, client=None):
            return {"message": "Test long speech"}

        speech_mgr.fetch_authoritative_result = mock_fetch

        task = speech_mgr.handle_notification(
            sender_identity="patient-123",
            expected_identity="patient-123",
            packet_payload={"type": "confirmation_result", "action_id": "act_long"},
            speaker=speaker
        )
        assert task is not None
        # Give task time to enter speech playback
        await asyncio.sleep(0.02)

        # Trigger shutdown
        await speech_mgr.shutdown()

        assert task.done()
        assert len(speech_mgr.active_tasks) == 0
        assert "act_long" not in speech_mgr.spoken_actions

    asyncio.run(scenario())
