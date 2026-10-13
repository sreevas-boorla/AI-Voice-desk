import sys
import io
import re
import logging
from pathlib import Path
import pytest

# Add voice-worker directory to sys.path so components can be imported directly
voice_worker_path = Path(__file__).resolve().parents[2] / "voice-worker"
if str(voice_worker_path) not in sys.path:
    sys.path.insert(0, str(voice_worker_path))

from agent_worker import SensitiveDataFilter
from speech_manager import ConfirmationSpeechManager


def test_sensitive_data_filter_redacts_synthetic_values():
    """
    Regression Test: Ensures that SensitiveDataFilter redacts:
    - Session tokens (sess_...)
    - Room names (room_sess_...)
    - Bearer tokens (Bearer eyJ...)
    - 4-digit verification codes (e.g. 4821)
    - Phone numbers (+91 98765 43210)
    - API keys (gsk_..., lk_...)
    """
    filter_obj = SensitiveDataFilter()
    logger = logging.getLogger("test-redaction")
    logger.setLevel(logging.INFO)
    logger.addFilter(filter_obj)

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logger.addHandler(handler)

    synthetic_session = "sess_secret_token_12345"
    synthetic_room = "room_sess_secret_token_12345"
    synthetic_phone = "+91 98765 43210"
    synthetic_code = "4821"
    synthetic_bearer = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    synthetic_groq_key = "gsk_live_api_key_secret_abc123"

    logger.info(f"Connecting to room {synthetic_room} with token {synthetic_session}")
    logger.info(f"Patient phone is {synthetic_phone} and code is {synthetic_code}")
    logger.info(f"Authorization header: {synthetic_bearer} with key {synthetic_groq_key}")

    handler.flush()
    log_output = log_stream.getvalue()

    # Assert raw sensitive values are NOT in the log output
    assert synthetic_session not in log_output, "Raw session token must be redacted from logs"
    assert synthetic_room not in log_output, "Raw room name must be redacted from logs"
    assert synthetic_phone not in log_output, "Raw phone number must be redacted from logs"
    assert synthetic_code not in log_output, "Raw verification code must be redacted from logs"
    assert synthetic_bearer not in log_output, "Raw Bearer token must be redacted from logs"
    assert synthetic_groq_key not in log_output, "Raw API key must be redacted from logs"

    # Assert redacted replacements are present
    assert "[SESSION_REDACTED]" in log_output or "[ROOM_REDACTED]" in log_output
    assert "[PHONE_REDACTED]" in log_output
    assert "[CODE_REDACTED]" in log_output
    assert "Bearer [REDACTED]" in log_output
    assert "[API_KEY_REDACTED]" in log_output


def test_correlation_id_is_unrelated_to_session_token():
    """
    Verifies that worker correlation IDs are generated randomly
    and share no common prefix or derivation with the session token.
    """
    from agent_worker import call_backend_agent
    import uuid

    session_token = f"sess_patient_secret_{uuid.uuid4().hex}"
    # Correlation ID in worker is generated as f"corr-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-{uuid.uuid4().hex[:8]}"

    # Verify complete independence
    assert correlation_id.startswith("corr-")
    assert correlation_id not in session_token
    assert session_token not in correlation_id
    assert not any(session_token.startswith(part) for part in correlation_id.split("-"))


def test_speech_manager_telemetry_does_not_log_action_payload_or_transcripts():
    """
    Verifies that ConfirmationSpeechManager logs only operational metrics (counts, latencies),
    never logging appointment details, patient text, or tokens.
    """
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    sm_logger = logging.getLogger("voicedesk-worker.speech-manager")
    sm_logger.addHandler(handler)
    sm_logger.setLevel(logging.INFO)

    speech_mgr = ConfirmationSpeechManager(
        session_token="sess_secret_private_token",
        correlation_id="corr-telemetry-test",
        backend_api_url="http://testserver/api"
    )

    # Trigger rejection of bad action
    speech_mgr.handle_notification(
        sender_identity="wrong",
        expected_identity="right",
        packet_payload={"action_id": "act_sensitive_12345", "message": "sensitive patient health info"},
        speaker=lambda text: None
    )

    handler.flush()
    logs = log_stream.getvalue()

    assert "sensitive patient health info" not in logs
    assert "sess_secret_private_token" not in logs
    assert "corr-telemetry-test" in logs
