import pytest
from types import SimpleNamespace
from unittest.mock import Mock
import groq
from app.config import settings, Settings
from app.agent.engine import process_agent_message
from app.services.verification_service import get_or_create_session
from app.services.availability_service import get_now_ist, resolve_natural_date, get_available_slots
from app.services.booking_service import prepare_booking, confirm_pending_action
from app.models import Provider, PendingAction


def test_live_tool_results_return_to_model(db, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'GROQ_API_KEY', 'test-placeholder')
    call = SimpleNamespace(id='call1', function=SimpleNamespace(name='list_providers', arguments='{}'))
    first = SimpleNamespace(content=None, tool_calls=[call], model_dump=lambda **kwargs: {
        'role': 'assistant', 'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {'name': 'list_providers', 'arguments': '{}'}}]})
    final = SimpleNamespace(content='Three providers are available.', tool_calls=None)
    create = Mock(side_effect=[SimpleNamespace(choices=[SimpleNamespace(message=first)]), SimpleNamespace(choices=[SimpleNamespace(message=final)])])
    monkeypatch.setattr(groq, 'Groq', lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    session = get_or_create_session(db, 'live-test-session', 'text')
    result = process_agent_message(db, session.id, 'List providers')
    assert result.reply == 'Three providers are available.'
    assert create.call_count == 2
    payload = create.call_args.kwargs
    assert any(m.get('role') == 'tool' and m.get('tool_call_id') == 'call1' for m in payload['messages'])
    assert get_now_ist().date().isoformat() in payload['messages'][0]['content']
    assert all(t['function']['name'] != 'confirm_pending_action' for t in payload['tools'])


def test_live_error_does_not_silently_simulate(db, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'GROQ_API_KEY', 'test-placeholder')
    monkeypatch.setattr(groq, 'Groq', Mock(side_effect=RuntimeError('provider unavailable')))
    session = get_or_create_session(db, 'live-error-session', 'text')
    result = process_agent_message(db, session.id, 'Book an appointment')
    assert 'unavailable' in result.reply
    assert result.tool_events == []


def test_live_auth_error_message(db, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_MODE', False)
    monkeypatch.setattr(settings, 'GROQ_API_KEY', 'bad-api-key')
    
    # Create mock AuthenticationError
    class MockAuthError(Exception):
        pass
    MockAuthError.__name__ = "AuthenticationError"

    monkeypatch.setattr(groq, 'Groq', Mock(side_effect=MockAuthError('Invalid API Key')))
    session = get_or_create_session(db, 'live-auth-err-session', 'text')
    result = process_agent_message(db, session.id, 'Hello doctor')
    assert 'rejected authentication' in result.reply.lower() or 'groq_api_key' in result.reply.lower()


def test_superseded_pending_action_rejected(db):
    session = get_or_create_session(db, 'supersede-sess', 'text')
    provider = db.query(Provider).first()
    target_date = resolve_natural_date("next tuesday")
    slots = get_available_slots(db, provider.id, target_date)
    assert len(slots) >= 2

    # 1. First prepare
    prep1 = prepare_booking(db, session.id, "Patient Old", "+91 91111 22222", provider.id, slots[0]["start_time"])
    action1_id = prep1["action_id"]

    # 2. Second prepare with different time supersedes the first
    prep2 = prepare_booking(db, session.id, "Patient New", "+91 91111 22222", provider.id, slots[1]["start_time"])
    action2_id = prep2["action_id"]

    # 3. Attempting to confirm the superseded action must fail
    res1 = confirm_pending_action(db, session.id, action1_id, confirmed=True)
    assert res1["success"] is False
    assert res1["status"] == "SUPERSEDED"

    # 4. Confirming the latest action succeeds
    res2 = confirm_pending_action(db, session.id, action2_id, confirmed=True)
    assert res2["success"] is True
    assert res2["status"] == "CONFIRMED"


def test_production_hardening_refuses_default_secrets():
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="carebridge-voicedesk-secret-key-2026-secure",
        ADMIN_PASSWORD="CareBridge2026!",
        DEMO_MODE=False
    )
    with pytest.raises(ValueError) as exc:
        prod_settings.validate_production_hardening()
    assert "insecure SECRET_KEY" in str(exc.value)

    prod_settings_key_ok = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a-strong-custom-production-secret-key-32chars!",
        ADMIN_PASSWORD="CareBridge2026!",
        DEMO_MODE=False
    )
    with pytest.raises(ValueError) as exc2:
        prod_settings_key_ok.validate_production_hardening()
    assert "default ADMIN_PASSWORD" in str(exc2.value)
