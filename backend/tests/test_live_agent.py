from types import SimpleNamespace
from unittest.mock import Mock
import groq
from app.config import settings
from app.agent.engine import process_agent_message
from app.services.verification_service import get_or_create_session
from app.services.availability_service import get_now_ist


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
