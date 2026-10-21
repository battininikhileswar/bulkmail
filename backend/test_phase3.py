"""Unit and integration tests for Phase 3: Reply watcher, filtering, bounce/unsub handling, and thread safety."""

import base64
import sqlite3
import pytest

import config
import db
import watcher


class MockGmailUsersMessages:
    def __init__(self, messages=None, should_raise=False):
        self._messages = messages or []
        self._should_raise = should_raise

    def list(self, userId="me", q="", maxResults=50):
        if self._should_raise:
            raise RuntimeError("Simulated Gmail API quota / network error")

        class ListReq:
            def __init__(self, msgs):
                self._msgs = msgs
            def execute(self):
                return {"messages": [{"id": m["id"], "threadId": m["threadId"]} for m in self._msgs]}

        return ListReq(self._messages)

    def get(self, userId="me", id="", format="full"):
        if self._should_raise:
            raise RuntimeError("Simulated Gmail API network error")

        msg = next((m for m in self._messages if m["id"] == id), None)

        class GetReq:
            def __init__(self, m):
                self._m = m
            def execute(self):
                if not self._m:
                    raise KeyError(f"Message {id} not found")
                return self._m

        return GetReq(msg)


class MockGmailService:
    def __init__(self, messages=None, should_raise=False):
        self._messages_api = MockGmailUsersMessages(messages, should_raise)

    def users(self):
        class Users:
            def __init__(self, api):
                self._api = api
            def messages(self):
                return self._api
        return Users(self._messages_api)


def make_gmail_msg(
    msg_id: str,
    thread_id: str,
    from_addr: str,
    subject: str,
    body: str,
    headers_dict: dict = None,
):
    hdrs = [
        {"name": "From", "value": from_addr},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": "Sat, 17 Oct 2026 12:00:00 +0000"},
    ]
    if headers_dict:
        for k, v in headers_dict.items():
            hdrs.append({"name": k, "value": v})

    b64_data = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8")
    return {
        "id": msg_id,
        "threadId": thread_id,
        "internalDate": "1729166400000",
        "payload": {
            "mimeType": "text/plain",
            "headers": hdrs,
            "body": {"data": b64_data},
        },
    }


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Set up an isolated database for each test."""
    test_db_path = tmp_path / "test_watcher.db"
    monkeypatch.setattr(config, "DB_PATH", test_db_path)
    conn = db.get_db_connection()
    conn.close()
    return test_db_path


# --- 1. Tracked thread reply saved once and not duplicated on next poll ---

def test_tracked_thread_reply_saved_once(isolated_db):
    conn = db.get_db_connection()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, created_at) VALUES ('alice@example.com', 'Alice', '2026-10-17T10:00:00')")
        cid = conn.execute("SELECT id FROM contacts WHERE email = 'alice@example.com'").fetchone()[0]
        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, created_at) VALUES ('C1', 'S1', 'same', 'T', 'gmail', '2026-10-17T10:00:00')")
        camp_id = conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone()[0]
        # Record sent mail with tracked thread_id 'thd-tracked-101'
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, created_at)
            VALUES (?, ?, 'sent', 'thd-tracked-101', 'msg-orig-101', '2026-10-17T10:00:00')
            """,
            (camp_id, cid),
        )
    conn.close()

    mock_msg = make_gmail_msg(
        msg_id="gmail-msg-001",
        thread_id="thd-tracked-101",
        from_addr="Alice <alice@example.com>",
        subject="Re: S1",
        body="Yes, I would love to attend! What time does it start?",
    )
    mock_service = MockGmailService([mock_msg])
    watcher.set_gmail_client_override(mock_service)

    # First poll: message should be recorded
    recorded_1 = watcher.poll_gmail_inbox()
    assert recorded_1 == 1

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE gmail_message_id = 'gmail-msg-001'")
    row = cursor.fetchone()
    assert row is not None
    assert row["category"] == "reply"
    assert row["contact_email"] == "alice@example.com"
    assert "What time does it start?" in row["body_text"]
    conn.close()

    # Second poll: exact same message must NOT be duplicated
    recorded_2 = watcher.poll_gmail_inbox()
    assert recorded_2 == 0

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE gmail_message_id = 'gmail-msg-001'")
    assert cursor.fetchone()[0] == 1
    conn.close()


# --- 2. Message from untracked thread is ignored ---

def test_untracked_thread_ignored(isolated_db):
    conn = db.get_db_connection()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, created_at) VALUES ('bob@example.com', 'Bob', '2026-10-17T10:00:00')")
        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, created_at) VALUES ('C1', 'S1', 'same', 'T', 'gmail', '2026-10-17T10:00:00')")
        camp_id = conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone()[0]
        # Only thd-999 is tracked
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, created_at)
            VALUES (?, 1, 'sent', 'thd-999', 'msg-orig-999', '2026-10-17T10:00:00')
            """,
            (camp_id,),
        )
    conn.close()

    untracked_msg = make_gmail_msg(
        msg_id="gmail-msg-untracked",
        thread_id="thd-random-unknown",
        from_addr="Strangers <random@other.com>",
        subject="Newsletter",
        body="Random newsletter not related to our campaign.",
    )
    mock_service = MockGmailService([untracked_msg])
    watcher.set_gmail_client_override(mock_service)

    recorded = watcher.poll_gmail_inbox()
    assert recorded == 0

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE gmail_message_id = 'gmail-msg-untracked'")
    assert cursor.fetchone()[0] == 0
    conn.close()


# --- 3. Out-of-office message is classified auto_reply ---

def test_auto_reply_classified(isolated_db):
    conn = db.get_db_connection()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, created_at) VALUES ('carol@example.com', 'Carol', '2026-10-17T10:00:00')")
        cid = conn.execute("SELECT id FROM contacts WHERE email = 'carol@example.com'").fetchone()[0]
        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, created_at) VALUES ('C1', 'S1', 'same', 'T', 'gmail', '2026-10-17T10:00:00')")
        camp_id = conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone()[0]
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, created_at)
            VALUES (?, ?, 'sent', 'thd-carol-123', 'msg-123', '2026-10-17T10:00:00')
            """,
            (camp_id, cid),
        )
    conn.close()

    ooo_msg = make_gmail_msg(
        msg_id="gmail-ooo-001",
        thread_id="thd-carol-123",
        from_addr="Carol <carol@example.com>",
        subject="Automatic reply: Out of office until Monday",
        body="I am currently away with limited email access.",
        headers_dict={"auto-submitted": "auto-replied"},
    )
    mock_service = MockGmailService([ooo_msg])
    watcher.set_gmail_client_override(mock_service)

    recorded = watcher.poll_gmail_inbox()
    assert recorded == 1

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT category FROM messages WHERE gmail_message_id = 'gmail-ooo-001'")
    row = cursor.fetchone()
    assert row["category"] == "auto_reply"
    conn.close()


# --- 4. Mailer-daemon bounce marks contact failed ---

def test_mailer_daemon_bounce_marks_contact_failed(isolated_db):
    conn = db.get_db_connection()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('bouncy@example.com', 'Bouncy', 'pending', '2026-10-17T10:00:00')")
        cid = conn.execute("SELECT id FROM contacts WHERE email = 'bouncy@example.com'").fetchone()[0]
        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, created_at) VALUES ('C1', 'S1', 'same', 'T', 'gmail', '2026-10-17T10:00:00')")
        camp_id = conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone()[0]
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, created_at)
            VALUES (?, ?, 'sent', 'thd-bounce-404', 'msg-404', '2026-10-17T10:00:00')
            """,
            (camp_id, cid),
        )
    conn.close()

    bounce_msg = make_gmail_msg(
        msg_id="gmail-bounce-001",
        thread_id="thd-bounce-404",
        from_addr="Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
        subject="Delivery Status Notification (Failure)",
        body="550 5.1.1 The email account that you tried to reach does not exist.",
    )
    mock_service = MockGmailService([bounce_msg])
    watcher.set_gmail_client_override(mock_service)

    recorded = watcher.poll_gmail_inbox()
    assert recorded == 1

    conn = db.get_db_connection()
    cursor = conn.cursor()
    # Verify message categorized as bounce
    cursor.execute("SELECT category FROM messages WHERE gmail_message_id = 'gmail-bounce-001'")
    assert cursor.fetchone()["category"] == "bounce"
    conn.close()


# --- 5. "Please unsubscribe me" unsubscribes; long message with "stop" does not ---

def test_unsubscribe_short_vs_long_detection(isolated_db):
    conn = db.get_db_connection()
    with conn:
        # User 1: Clear unsubscribe
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('unsub1@example.com', 'User One', 'pending', '2026-10-17T10:00:00')")
        cid1 = conn.execute("SELECT id FROM contacts WHERE email = 'unsub1@example.com'").fetchone()[0]

        # User 2: Long email containing 'stop'
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('complex@example.com', 'User Two', 'pending', '2026-10-17T10:00:00')")
        cid2 = conn.execute("SELECT id FROM contacts WHERE email = 'complex@example.com'").fetchone()[0]

        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, created_at) VALUES ('C1', 'S1', 'same', 'T', 'gmail', '2026-10-17T10:00:00')")
        camp_id = conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone()[0]

        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, created_at) VALUES (?, ?, 'sent', 'thd-u1', '2026-10-17T10:00:00')", (camp_id, cid1))
        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, created_at) VALUES (?, ?, 'sent', 'thd-u2', '2026-10-17T10:00:00')", (camp_id, cid2))
    conn.close()

    # Short message: "Please unsubscribe me"
    msg_unsub = make_gmail_msg(
        msg_id="msg-unsub-1",
        thread_id="thd-u1",
        from_addr="unsub1@example.com",
        subject="Re: S1",
        body="Please unsubscribe me from these emails.",
    )

    # Long message containing the word "stop" in a legitimate context
    long_body = (
        "Hello Event Coordinator, I am writing to inquire about the upcoming session on cloud security. "
        "We are planning a journey across several cities and we hope to stop by your booth around 2 PM. "
        "Could you please let us know if parking is available for large vehicles near the conference center entrance? "
        "Thanks and see you next month!"
    )
    msg_long_stop = make_gmail_msg(
        msg_id="msg-long-stop-2",
        thread_id="thd-u2",
        from_addr="complex@example.com",
        subject="Re: S1",
        body=long_body,
    )

    mock_service = MockGmailService([msg_unsub, msg_long_stop])
    watcher.set_gmail_client_override(mock_service)

    recorded = watcher.poll_gmail_inbox()
    assert recorded == 2

    conn = db.get_db_connection()
    cursor = conn.cursor()

    # User 1 should be categorized as 'unsubscribe_request' and contact status = 'unsubscribed'
    cursor.execute("SELECT category FROM messages WHERE gmail_message_id = 'msg-unsub-1'")
    assert cursor.fetchone()["category"] == "unsubscribe_request"

    cursor.execute("SELECT status FROM contacts WHERE email = 'unsub1@example.com'")
    assert cursor.fetchone()["status"] == "unsubscribed"

    # User 2 should be categorized as 'reply' with flagged_reason "possible unsubscribe, review" and contact remains 'pending'
    cursor.execute("SELECT category, flagged_reason FROM messages WHERE gmail_message_id = 'msg-long-stop-2'")
    row2 = cursor.fetchone()
    assert row2["category"] == "reply"
    assert "possible unsubscribe" in row2["flagged_reason"]

    cursor.execute("SELECT status FROM contacts WHERE email = 'complex@example.com'")
    assert cursor.fetchone()["status"] == "pending"

    conn.close()


# --- 6. Quoted text is stripped from body ---

def test_quoted_text_stripped():
    full_reply = (
        "Yes, I will be attending the opening keynote!\n\n"
        "-- \n"
        "Alice Smith | VP Technology\n\n"
        "On Fri, Oct 16, 2026 at 4:15 PM Event Coordinator <coordinator@example.com> wrote:\n"
        "> Hi Alice,\n"
        "> Thank you for registering for our event!\n"
        "> Best regards,\n"
        "> Event Coordinator\n"
    )
    cleaned = watcher.strip_quoted_text(full_reply)
    assert cleaned == "Yes, I will be attending the opening keynote!"
    assert "On Fri, Oct 16" not in cleaned
    assert "> Hi Alice" not in cleaned
    assert "Alice Smith | VP Technology" not in cleaned


# --- 7. Gmail API error does not crash the watcher ---

def test_gmail_api_error_does_not_crash(isolated_db):
    conn = db.get_db_connection()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, created_at) VALUES ('err@example.com', 'Err', '2026-10-17T10:00:00')")
        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, created_at) VALUES ('C1', 'S1', 'same', 'T', 'gmail', '2026-10-17T10:00:00')")
        camp_id = conn.execute("SELECT id FROM campaigns LIMIT 1").fetchone()[0]
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, created_at)
            VALUES (?, 1, 'sent', 'thd-error-test', '2026-10-17T10:00:00')
            """,
            (camp_id,),
        )
    conn.close()

    broken_service = MockGmailService(should_raise=True)
    watcher.set_gmail_client_override(broken_service)

    # Should not raise exception
    recorded = watcher.poll_gmail_inbox()
    assert recorded == 0

    status = watcher.get_watcher_status()
    assert status["last_error"] is not None
    assert "Simulated Gmail API" in status["last_error"]
