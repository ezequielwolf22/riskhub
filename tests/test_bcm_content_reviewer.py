"""Tests unitarios de bcm_content_reviewer.py: parseo de respuestas IA
(planes y evidencia) y anonimizacion previa al envio a la API de Anthropic.
"""
from unittest.mock import MagicMock, patch

from app.services.bcm_content_reviewer import (
    _parse_response,
    _parse_evidence_response,
    _call_claude,
)


def test_parse_valid_json():
    raw = '{"score": 85, "covered": ["a", "b"], "missing": ["c"], "summary": "ok"}'
    result = _parse_response(raw)
    assert result["score"] == 85
    assert result["covered"] == ["a", "b"]
    assert result["missing"] == ["c"]
    assert result["summary"] == "ok"


def test_parse_json_with_surrounding_text():
    raw = 'Aqui esta mi analisis:\n{"score": 40, "covered": [], "missing": ["x"]}\nFin.'
    result = _parse_response(raw)
    assert result["score"] == 40
    assert result["missing"] == ["x"]


def test_parse_clamps_out_of_range_score():
    raw = '{"score": 150, "covered": [], "missing": []}'
    result = _parse_response(raw)
    assert result["score"] == 100

    raw_neg = '{"score": -20, "covered": [], "missing": []}'
    result_neg = _parse_response(raw_neg)
    assert result_neg["score"] == 0


def test_parse_missing_score_returns_none():
    assert _parse_response('{"covered": ["a"]}') is None


def test_parse_garbage_returns_none():
    assert _parse_response("no soy json en absoluto") is None
    assert _parse_response("") is None


def test_parse_evidence_response_valid():
    raw = '{"relevant": true, "quality_score": 78, "summary": "Informe de test tabletop con hallazgos"}'
    result = _parse_evidence_response(raw)
    assert result["relevant"] is True
    assert result["quality_score"] == 78


def test_parse_evidence_response_not_relevant():
    raw = '{"relevant": false, "quality_score": 5, "summary": "Captura sin relacion con continuidad"}'
    result = _parse_evidence_response(raw)
    assert result["relevant"] is False
    assert result["quality_score"] == 5


def test_parse_evidence_response_missing_field_returns_none():
    assert _parse_evidence_response('{"relevant": true}') is None


def test_call_claude_anonymizes_text_before_sending(monkeypatch):
    """El texto del documento debe pasar por el anonimizador ANTES de llegar
    a la API de Anthropic — verifica que un email en el texto se sustituye
    por un token [EMAIL_n] en el payload real enviado al SDK."""
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured['messages'] = kwargs['messages']
            msg = MagicMock()
            msg.content = [MagicMock(text='{"score": 50}')]
            return msg

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic = FakeClient

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch.dict('sys.modules', {'anthropic': fake_anthropic}):
        with patch('app.services.bcm_content_reviewer.settings') as mock_settings:
            mock_settings.anthropic_api_key = 'fake-key'
            _call_claude(db, None, 'system prompt', 'Contactar a juan.perez@empresa.com para mas info')

    sent_content = captured['messages'][0]['content']
    assert 'juan.perez@empresa.com' not in sent_content
    assert '[EMAIL_1]' in sent_content
