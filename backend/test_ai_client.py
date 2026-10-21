"""Unit tests for AI Provider Switch (Anthropic, Gemini, Groq) using fake clients."""

from datetime import datetime
import json
import pytest

import ai_client
import classifier
import config
import db
import responder
import watcher


class MockHttpResponse:
    def __init__(self, status_code: int = 200, json_data: dict = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or json.dumps(self._json_data)
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_data


class MockHttpSession:
    def __init__(self, responses=None):
        self.responses = list(responses) if responses else []
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        if self.responses:
            resp = self.responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return MockHttpResponse(200, {})


class MockAnthropicResponse:
    def __init__(self, text: str, in_tok: int = 10, out_tok: int = 20):
        class Content:
            def __init__(self, t):
                self.text = t
        class Usage:
            def __init__(self, i, o):
                self.input_tokens = i
                self.output_tokens = o
        self.content = [Content(text)]
        self.usage = Usage(in_tok, out_tok)


class MockAnthropicClient:
    def __init__(self, responses=None):
        self.responses = list(responses) if responses else []
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.responses:
            resp = self.responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return MockAnthropicResponse('{"intent": "question", "summary": "Test summary"}')


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Isolate database and reset overrides for each test."""
    test_db = tmp_path / "test_ai_switch.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(ai_client, "RETRY_DELAYS", [0.01, 0.01])
    conn = db.get_db_connection()
    conn.close()

    yield

    ai_client.set_client_override(None)
    ai_client.set_http_session_override(None)
    classifier.set_ai_client_override(None)
    responder.set_ai_client_override(None)


def test_provider_selection_anthropic(monkeypatch):
    """Verify Anthropic provider dispatch and usage logging."""
    monkeypatch.setattr(config, "AI_PROVIDER", "anthropic")
    fake_client = MockAnthropicClient([
        MockAnthropicResponse('{"intent": "interested", "summary": "Wants to attend"}', in_tok=45, out_tok=15)
    ])
    ai_client.set_client_override(fake_client)

    result_text = ai_client.complete("System prompt", "User text", max_tokens=100, purpose="test_anthropic")
    assert "interested" in result_text
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["max_tokens"] == 100

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT purpose, input_tokens, output_tokens FROM ai_usage WHERE purpose = 'test_anthropic'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row["input_tokens"] == 45
    assert row["output_tokens"] == 15


def test_provider_selection_gemini(monkeypatch):
    """Verify Gemini provider dispatch via REST and usage metadata extraction."""
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-gemini-key")

    gemini_resp = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": '{"intent": "question", "summary": "Asking about parking"}'}]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 60,
            "candidatesTokenCount": 20
        }
    }
    mock_http = MockHttpSession([MockHttpResponse(200, gemini_resp)])
    ai_client.set_http_session_override(mock_http)

    result_text = ai_client.complete("System prompt", "User query", max_tokens=120, purpose="test_gemini")
    assert "parking" in result_text
    assert len(mock_http.calls) == 1
    assert "generativelanguage.googleapis.com" in mock_http.calls[0]["url"]
    assert "fake-gemini-key" in mock_http.calls[0]["url"]

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT purpose, input_tokens, output_tokens FROM ai_usage WHERE purpose = 'test_gemini'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row["input_tokens"] == 60
    assert row["output_tokens"] == 20


def test_provider_selection_groq(monkeypatch):
    """Verify Groq provider dispatch via OpenAI-compatible endpoint and usage logging."""
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-groq-key")

    groq_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"intent": "not_interested", "summary": "Cannot make it"}'
                }
            }
        ],
        "usage": {
            "prompt_tokens": 35,
            "completion_tokens": 12
        }
    }
    mock_http = MockHttpSession([MockHttpResponse(200, groq_resp)])
    ai_client.set_http_session_override(mock_http)

    result_text = ai_client.complete("System prompt", "User query", max_tokens=150, purpose="test_groq")
    assert "not_interested" in result_text
    assert len(mock_http.calls) == 1
    assert "api.groq.com" in mock_http.calls[0]["url"]
    assert "Bearer fake-groq-key" in mock_http.calls[0]["kwargs"]["headers"]["Authorization"]

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT purpose, input_tokens, output_tokens FROM ai_usage WHERE purpose = 'test_groq'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row["input_tokens"] == 35
    assert row["output_tokens"] == 12


def test_missing_api_key_shows_clear_message(monkeypatch):
    """Verify that a missing API key for any selected provider raises a clear error."""
    # Anthropic missing key
    monkeypatch.setattr(config, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    with pytest.raises(ValueError) as excinfo:
        ai_client.complete("sys", "user")
    assert "ANTHROPIC_API_KEY is not configured" in str(excinfo.value)

    # Gemini missing key
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(ValueError) as excinfo:
        ai_client.complete("sys", "user")
    assert "GEMINI_API_KEY is not configured" in str(excinfo.value)

    # Groq missing key
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    with pytest.raises(ValueError) as excinfo:
        ai_client.complete("sys", "user")
    assert "GROQ_API_KEY is not configured" in str(excinfo.value)


def test_rate_limit_retry_then_safe_failure_for_classifier(monkeypatch):
    """Verify 429 retries twice (3 attempts total) and watcher leaves reply unclassified without crashing."""
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")

    # 3 consecutive 429s -> exhausts 2 retries
    mock_http = MockHttpSession([
        MockHttpResponse(429, {}, text="Rate limit exceeded"),
        MockHttpResponse(429, {}, text="Rate limit exceeded"),
        MockHttpResponse(429, {}, text="Rate limit exceeded"),
    ])
    ai_client.set_http_session_override(mock_http)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (
                gmail_message_id, thread_id, contact_email, direction,
                subject, body_text, received_at, category, processed
            )
            VALUES ('msg-rate-limit-1', 'thread-rl-1', 'lead@example.com', 'incoming', 'Inquiry', 'When does it start?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        msg_id = cursor.lastrowid

    # watcher calls classify_reply_message; must catch error and leave message unclassified
    res = watcher.classify_reply_message(
        conn,
        message_id=msg_id,
        body_text="When does it start?",
        thread_id="thread-rl-1",
        contact_email="lead@example.com",
    )

    # Must fail safely: returns None
    assert res is None
    # 3 calls made (initial + 2 retries)
    assert len(mock_http.calls) == 3

    # Database record has NULL/empty intent
    cursor = conn.cursor()
    cursor.execute("SELECT intent, summary FROM messages WHERE id = ?", (msg_id,))
    row = cursor.fetchone()
    conn.close()
    assert row["intent"] is None


def test_rate_limit_retry_then_safe_failure_for_responder(monkeypatch):
    """Verify 429 retries twice and responder marks draft as needs_review safely."""
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key")

    mock_http = MockHttpSession([
        MockHttpResponse(429, {}, text="Rate limit exceeded"),
        MockHttpResponse(429, {}, text="Rate limit exceeded"),
        MockHttpResponse(429, {}, text="Rate limit exceeded"),
    ])
    ai_client.set_http_session_override(mock_http)

    res = responder.draft_reply(
        thread_messages=[],
        new_reply="What time does keynote start?",
        facts={"event_name": "Conference", "faqs": [{"question": "What time?", "answer": "10 AM"}], "do_not_answer": []},
    )

    # Must return needs_review with clear reason
    assert res["status"] == "needs_review"
    assert "rate limit" in res["reason"].lower() or "unavailable" in res["reason"].lower()
    # 3 calls made (initial + 2 retries)
    assert len(mock_http.calls) == 3


def test_bad_json_fallback_classifier(monkeypatch):
    """Verify classifier safely falls back to 'other' when model outputs malformed JSON."""
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key")

    groq_resp = {
        "choices": [{"message": {"role": "assistant", "content": "I think the person is interested but no json provided."}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10}
    }
    mock_http = MockHttpSession([MockHttpResponse(200, groq_resp)])
    ai_client.set_http_session_override(mock_http)

    res = classifier.classify("I might want to come!")
    assert res["intent"] == "other"
    assert "could not parse json" in res["summary"].lower() or "empty" in res["summary"].lower()


def test_bad_json_fallback_responder(monkeypatch):
    """Verify responder safely falls back to 'needs_review' when model outputs malformed JSON."""
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")

    gemini_resp = {
        "candidates": [
            {"content": {"parts": [{"text": "Hello, here is a helpful message without valid json"}]}}
        ],
        "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 10}
    }
    mock_http = MockHttpSession([MockHttpResponse(200, gemini_resp)])
    ai_client.set_http_session_override(mock_http)

    res = responder.draft_reply(
        thread_messages=[],
        new_reply="Where is it?",
        facts={"event_name": "Meetup", "faqs": [], "do_not_answer": []},
    )
    assert res["status"] == "needs_review"
    assert "parse" in res["reason"].lower()


def test_call_count_logged_when_tokens_not_returned(monkeypatch):
    """Verify that when a provider doesn't return token counts, call count (0 tokens) is still logged."""
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key")

    # Groq response with missing usage field
    groq_resp = {
        "choices": [
            {"message": {"role": "assistant", "content": '{"intent": "question", "summary": "Question"}'}}
        ]
    }
    mock_http = MockHttpSession([MockHttpResponse(200, groq_resp)])
    ai_client.set_http_session_override(mock_http)

    ai_client.complete("System prompt", "User query", max_tokens=100, purpose="test_call_count_only")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT purpose, input_tokens, output_tokens FROM ai_usage WHERE purpose = 'test_call_count_only'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row["input_tokens"] == 0
    assert row["output_tokens"] == 0
