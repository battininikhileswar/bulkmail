"""Unit tests for Phase 6: Draft Approval & Send Workflow (using FakeEmailSender, no real email sending)."""

from datetime import datetime
import json
import pytest
from fastapi.testclient import TestClient

import config
import db
import email_sender
import main
import queue_worker


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Isolate SQLite database to a temporary file and mock email sender for each test."""
    test_db = tmp_path / "test_phase6.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(config, "TEST_MODE", False)
    conn = db.get_db_connection()
    conn.close()

    fake_sender = email_sender.FakeEmailSender(daily_cap=10)
    email_sender.set_email_sender_override(fake_sender)

    yield fake_sender

    email_sender.set_email_sender_override(None)


def test_approve_and_send_draft_success(clean_test_env):
    """Approving a draft sends the email with mandatory footer and thread headers."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO contacts (email, name, status, thread_id, created_at)
            VALUES ('attendee@example.com', 'Alice Smith', 'sent', 'thd-p6-1', ?)
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO messages (
                gmail_message_id, thread_id, contact_email, direction,
                subject, body_text, received_at, category, processed, intent
            )
            VALUES ('msg-incoming-p6', 'thd-p6-1', 'attendee@example.com', 'incoming', 'Parking query', 'Is parking free?', ?, 'reply', 0, 'question')
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-incoming-p6'")
        reply_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-p6-1', 'attendee@example.com', 'Yes, parking is free in Lot 2.', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    # Dispatch approval endpoint
    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "sent"

    # Verify FakeEmailSender captured the email
    assert len(fake_sender.sent_emails) == 1
    sent_item = fake_sender.sent_emails[0]
    assert sent_item["to_email"] == "attendee@example.com"
    assert sent_item["thread_id"] == "thd-p6-1"
    assert sent_item["in_reply_to"] == "msg-incoming-p6"

    # Verify mandatory footer added in code
    body = sent_item["body"]
    assert "Yes, parking is free in Lot 2." in body
    assert config.SENDER_NAME in body
    assert "unsubscribe" in body.lower()

    # Verify database updates
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,))
    assert cursor.fetchone()[0] == "sent"

    cursor.execute("SELECT processed FROM messages WHERE id = ?", (reply_id,))
    assert cursor.fetchone()[0] == 1

    cursor.execute("SELECT * FROM messages WHERE direction = 'outgoing'")
    outgoing_msg = cursor.fetchone()
    assert outgoing_msg is not None
    assert outgoing_msg["contact_email"] == "attendee@example.com"
    assert outgoing_msg["thread_id"] == "thd-p6-1"

    cursor.execute("SELECT action FROM activity_log WHERE action = 'draft_approved_and_sent'")
    assert cursor.fetchone() is not None
    conn.close()


def test_send_unsubscribed_contact_blocked(clean_test_env):
    """An approved draft targeting an unsubscribed contact is strictly blocked."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO contacts (email, name, status, thread_id, created_at)
            VALUES ('unsub@example.com', 'Unsub Attendee', 'unsubscribed', 'thd-unsub-block', ?)
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO messages (
                gmail_message_id, thread_id, contact_email, direction,
                subject, body_text, received_at, category, processed
            )
            VALUES ('msg-unsub-block', 'thd-unsub-block', 'unsub@example.com', 'incoming', 'Query', 'Can I come?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-unsub-block'")
        reply_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-unsub-block', 'unsub@example.com', 'Sure, see you there!', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 400
    assert "unsubscribed" in res.json()["detail"].lower()
    assert len(fake_sender.sent_emails) == 0


def test_send_already_sent_draft_blocked(clean_test_env):
    """A draft that is already sent cannot be sent a second time."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO contacts (email, name, status, thread_id, created_at)
            VALUES ('repeat@example.com', 'Repeat', 'sent', 'thd-repeat', ?)
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-repeat', 'thd-repeat', 'repeat@example.com', 'incoming', 'Hi', 'Hello', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT last_insert_rowid()")
        msg_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-repeat', 'repeat@example.com', 'Already sent response', 'sent', '', ?, ?)
            """,
            (msg_id, now_str, now_str),
        )
        cursor.execute("SELECT last_insert_rowid()")
        draft_id = cursor.fetchone()[0]
    conn.close()

    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 400
    assert "already been sent" in res.json()["detail"].lower()
    assert len(fake_sender.sent_emails) == 0


def test_send_rejected_draft_blocked(clean_test_env):
    """A rejected draft cannot be dispatched."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO contacts (email, name, status, thread_id, created_at)
            VALUES ('rejected@example.com', 'Rejected User', 'sent', 'thd-rej', ?)
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-rej', 'thd-rej', 'rejected@example.com', 'incoming', 'Hi', 'Hello', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT last_insert_rowid()")
        msg_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-rej', 'rejected@example.com', 'Bad response', 'rejected', '', ?, ?)
            """,
            (msg_id, now_str, now_str),
        )
        cursor.execute("SELECT last_insert_rowid()")
        draft_id = cursor.fetchone()[0]
    conn.close()

    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 400
    assert "rejected" in res.json()["detail"].lower()
    assert len(fake_sender.sent_emails) == 0


def test_send_daily_cap_exceeded_blocked(clean_test_env, monkeypatch):
    """When daily sending cap is reached, draft approval send is halted with HTTP 429."""
    fake_sender = clean_test_env
    client = TestClient(main.app)
    monkeypatch.setattr(config, "DAILY_CAP", 1)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        user_row, _ = db.get_or_create_user(conn, "test.user@example.com", "Test User")
        uid = user_row["id"]
        # Pre-fill daily sends
        queue_worker.increment_daily_send_count(conn, config.PROVIDER, user_id=uid)

        conn.execute(
            """
            INSERT INTO contacts (email, name, status, thread_id, created_at, user_id)
            VALUES ('cap@example.com', 'Cap Test', 'sent', 'thd-cap', ?, ?)
            """,
            (now_str, uid),
        )
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed, user_id)
            VALUES ('msg-cap', 'thd-cap', 'cap@example.com', 'incoming', 'Hi', 'Hello', ?, 'reply', 0, ?)
            """,
            (now_str, uid),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT last_insert_rowid()")
        msg_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, user_id)
            VALUES (?, 'thd-cap', 'cap@example.com', 'Response', 'pending_approval', '', ?, ?, ?)
            """,
            (msg_id, now_str, now_str, uid),
        )
        cursor.execute("SELECT last_insert_rowid()")
        draft_id = cursor.fetchone()[0]
    conn.close()

    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 429
    assert "daily send cap" in res.json()["detail"].lower()
    assert len(fake_sender.sent_emails) == 0


def test_edit_draft_before_approval(clean_test_env):
    """Editing draft body via PATCH modifies the draft, and subsequent send uses the edited text."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO contacts (email, name, status, thread_id, created_at)
            VALUES ('edit@example.com', 'Editor', 'sent', 'thd-edit', ?)
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO messages (
                gmail_message_id, thread_id, contact_email, direction,
                subject, body_text, received_at, category, processed
            )
            VALUES ('msg-edit-in', 'thd-edit', 'edit@example.com', 'incoming', 'FAQ', 'Can I bring my laptop?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-edit-in'")
        reply_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-edit', 'edit@example.com', 'Original AI draft', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    # 1. Edit via PATCH
    patch_res = client.patch(f"/api/drafts/{draft_id}", json={"body": "Yes, laptops are welcome with power strips at all tables."})
    assert patch_res.status_code == 200
    assert "power strips" in patch_res.json()["body"]

    # 2. Approve and send
    send_res = client.post(f"/api/drafts/{draft_id}/send")
    assert send_res.status_code == 200

    # 3. Confirm dispatched email has edited text
    assert len(fake_sender.sent_emails) == 1
    sent_body = fake_sender.sent_emails[0]["body"]
    assert "Yes, laptops are welcome with power strips at all tables." in sent_body
    assert config.SENDER_NAME in sent_body


def test_global_pause_sending_blocks_reply_and_status(clean_test_env):
    """Global pause blocks reply dispatch and resumes when toggled."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('pause@test.com', 'Pause Tester', 'sent', ?)", (now_str,))
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-pause', 'thd-pause', 'pause@test.com', 'incoming', 'Pause Q', 'Hello?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-pause'")
        reply_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-pause', 'pause@test.com', 'Here is the response', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    # 1. Pause globally
    p_res = client.post("/api/sending/pause")
    assert p_res.status_code == 200
    assert p_res.json()["paused"] is True
    assert queue_worker.is_global_sending_paused() is True

    status_res = client.get("/api/sending/status")
    assert status_res.status_code == 200
    assert status_res.json()["paused"] is True

    # 2. Attempt to send draft -> blocked with 400
    send_blocked = client.post(f"/api/drafts/{draft_id}/send")
    assert send_blocked.status_code == 400
    assert "paused" in send_blocked.json()["detail"].lower()
    assert len(fake_sender.sent_emails) == 0

    # 3. Resume globally
    r_res = client.post("/api/sending/resume")
    assert r_res.status_code == 200
    assert r_res.json()["paused"] is False
    assert queue_worker.is_global_sending_paused() is False

    # 4. Now send succeeds
    send_ok = client.post(f"/api/drafts/{draft_id}/send")
    assert send_ok.status_code == 200
    assert len(fake_sender.sent_emails) == 1


def test_test_mode_reply_send_diversion_and_no_count(clean_test_env, monkeypatch):
    """In test mode, replies go to test_email with [TEST] prefix and do not count toward daily sends."""
    fake_sender = clean_test_env
    client = TestClient(main.app)
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "verifier@event.local")

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('real@client.com', 'Real Person', 'sent', ?)", (now_str,))
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-tm', 'thd-tm', 'real@client.com', 'incoming', 'Agenda Inquiry', 'What time does it start?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-tm'")
        reply_id = cursor.fetchone()[0]

        conn.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-tm', 'real@client.com', 'It starts at 9:00 AM.', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 200

    # Verify diverted to test address with [TEST]
    assert len(fake_sender.sent_emails) == 1
    sent = fake_sender.sent_emails[0]
    assert sent["to_email"] == "verifier@event.local"
    assert sent["subject"].startswith("[TEST] Re: Agenda Inquiry")

    # Verify not counted as real send
    conn = db.get_db_connection()
    count = queue_worker.get_daily_send_count(conn, config.PROVIDER)
    assert count == 0
    conn.close()


def test_double_send_protection_and_failure_transition(clean_test_env, monkeypatch):
    """Mark draft 'approved' before sending, 'failed' on error, and block sending already approved drafts."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('fail@client.com', 'Fail Test', 'sent', ?)", (now_str,))
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-fail', 'thd-fail', 'fail@client.com', 'incoming', 'Venue', 'Where is it?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-fail'")
        reply_id = cursor.fetchone()[0]

        # Case 1: Draft already approved cannot be sent again
        cursor.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-fail', 'fail@client.com', 'Hall B', 'approved', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        approved_draft_id = cursor.lastrowid

        # Case 2: Draft that will fail during send
        cursor.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thd-fail', 'fail@client.com', 'Hall B', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        failing_draft_id = cursor.lastrowid
    conn.close()

    # Case 1: Already approved draft fails
    res_app = client.post(f"/api/drafts/{approved_draft_id}/send")
    assert res_app.status_code == 400
    assert "already approved" in res_app.json()["detail"].lower()

    # Case 2: Failure transitions status to 'failed'
    def mock_failing_send(*args, **kwargs):
        return email_sender.SendResult(success=False, error="SMTP 550 Mailbox does not exist or delivery rejected")

    monkeypatch.setattr(fake_sender, "send_email", mock_failing_send)

    res_fail = client.post(f"/api/drafts/{failing_draft_id}/send")
    assert res_fail.status_code == 500

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, reason FROM drafts WHERE id = ?", (failing_draft_id,))
    row = cursor.fetchone()
    assert row["status"] == "failed"
    assert "SMTP 550" in row["reason"]
    conn.close()


def test_needs_review_draft_requires_edit(clean_test_env):
    """A needs_review draft can only be sent after body is edited from original and not empty."""
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('review@client.com', 'Reviewer', 'sent', ?)", (now_str,))
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-rev', 'thd-rev', 'review@client.com', 'incoming', 'Refunds', 'Can I get a refund?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-rev'")
        reply_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body)
            VALUES (?, 'thd-rev', 'review@client.com', 'Refund policy inquiry', 'needs_review', 'do_not_answer: refunds', ?, ?, 'Refund policy inquiry')
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    # 1. Attempt to send unedited -> 400
    res_unedited = client.post(f"/api/drafts/{draft_id}/send")
    assert res_unedited.status_code == 400
    assert "edited" in res_unedited.json()["detail"].lower()

    # 2. Attempt to send empty -> 400
    client.patch(f"/api/drafts/{draft_id}", json={"body": "   "})
    res_empty = client.post(f"/api/drafts/{draft_id}/send")
    assert res_empty.status_code == 400

    # 3. Edit text to a valid personalized response -> send succeeds
    patch_ok = client.patch(f"/api/drafts/{draft_id}", json={"body": "Hello, our team has processed your full refund to your original payment method."})
    assert patch_ok.status_code == 200

    res_ok = client.post(f"/api/drafts/{draft_id}/send")
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "sent"


def test_reply_headers_and_outgoing_record(clean_test_env):
    """Sent reply must include Re: subject, threadId, In-Reply-To, References, and record outgoing message."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('headers@client.com', 'Header Test', 'sent', ?)", (now_str,))
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('gmail-msg-999', 'thread-abc-123', 'headers@client.com', 'incoming', 'Speaker Slides', 'Where are the slides?', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'gmail-msg-999'")
        reply_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thread-abc-123', 'headers@client.com', 'Slides will be posted on the website.', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 200

    # Verify FakeEmailSender captured all reply headers
    sent = fake_sender.sent_emails[0]
    assert sent["subject"] == "Re: Speaker Slides"
    assert sent["thread_id"] == "thread-abc-123"
    assert sent["in_reply_to"] == "gmail-msg-999"
    assert sent["references"] == "gmail-msg-999"

    # Verify saved in messages table with direction = 'outgoing'
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE direction = 'outgoing' AND thread_id = 'thread-abc-123'")
    out_row = cursor.fetchone()
    assert out_row is not None
    assert out_row["contact_email"] == "headers@client.com"
    assert out_row["subject"] == "Re: Speaker Slides"
    assert out_row["category"] == "reply"
    assert out_row["processed"] == 1
    conn.close()


def test_per_thread_reply_limit_at_send_time(clean_test_env):
    """At send time, re-check the per-thread reply limit and block sending if already 3 sent replies."""
    fake_sender = clean_test_env
    client = TestClient(main.app)

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('limit@client.com', 'Limit Test', 'sent', ?)", (now_str,))
        # Pre-seed 3 outgoing replies on thread 'thread-limit-test'
        for i in range(1, 4):
            conn.execute(
                """
                INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
                VALUES (?, 'thread-limit-test', 'limit@client.com', 'outgoing', 'Re: Chat', 'Prior reply', ?, 'reply', 1)
                """,
                (f"out-limit-{i}", now_str),
            )

        # Incoming reply
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-in-limit', 'thread-limit-test', 'limit@client.com', 'incoming', 'Chat', 'Still more questions', ?, 'reply', 0)
            """,
            (now_str,),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = 'msg-in-limit'")
        reply_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at)
            VALUES (?, 'thread-limit-test', 'limit@client.com', '4th reply attempt', 'pending_approval', '', ?, ?)
            """,
            (reply_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    # Sending 4th reply on this thread is blocked
    res = client.post(f"/api/drafts/{draft_id}/send")
    assert res.status_code == 400
    assert "limit" in res.json()["detail"].lower()
    assert len(fake_sender.sent_emails) == 0

