"""Unit tests for small fixes: uncertain send handling and test mode safety (fake sender only, no real email)."""

from datetime import datetime
import pytest
from fastapi.testclient import TestClient

import config
import db
import email_sender
import main
import queue_worker


class TimeoutFakeSender(email_sender.BaseEmailSender):
    """Fake sender that simulates an in-flight socket / read timeout."""

    def __init__(self, error_msg: str = "ReadTimeout: The read operation timed out"):
        self.error_msg = error_msg
        self.call_count = 0

    def send_email(self, to_email: str, subject: str, body: str, thread_id=None, in_reply_to=None):
        self.call_count += 1
        return email_sender.SendResult(success=False, error=self.error_msg)

    def get_daily_cap(self) -> int:
        return 100


class PreSendErrorFakeSender(email_sender.BaseEmailSender):
    """Fake sender that simulates a pre-send connection refused error."""

    def __init__(self, error_msg: str = "ConnectionRefusedError: [Errno 111] Connection refused"):
        self.error_msg = error_msg
        self.call_count = 0

    def send_email(self, to_email: str, subject: str, body: str, thread_id=None, in_reply_to=None):
        self.call_count += 1
        return email_sender.SendResult(success=False, error=self.error_msg)

    def get_daily_cap(self) -> int:
        return 100


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Isolate database and inject default valid test email."""
    test_db = tmp_path / "test_small_fixes.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(config, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "test.tester@example.com")
    conn = db.get_db_connection()
    conn.close()
    yield
    email_sender.set_email_sender_override(None)


def test_simulated_timeout_marks_campaign_contact_uncertain_and_never_auto_retried():
    """If send times out, contact is marked manual_review with delivery unknown note and never auto-retried."""
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contacts (email, name, status, created_at) VALUES ('timeout.lead@example.com', 'Timeout Lead', 'pending', ?)",
            (now_str,),
        )
        cid = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Timeout Camp', 'Hi {name}', 'same', 'Hello!', 'gmail', 'draft', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid
    conn.close()

    timeout_sender = TimeoutFakeSender("ReadTimeout: HTTPSConnectionPool: Read timed out")
    email_sender.set_email_sender_override(timeout_sender)

    # Dispatch campaign
    queue_worker.start_campaign_queue(camp_id, sender_override=timeout_sender)
    import time
    time.sleep(0.5)

    # Check recipient record in DB
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT cr.id, cr.status, cr.error, cr.retry_count, cr.next_retry_at FROM campaign_recipients cr WHERE cr.campaign_id = ?",
        (camp_id,),
    )
    rcpt = cursor.fetchone()
    assert rcpt is not None
    rcpt_id = rcpt["id"]

    # 1. Must be marked 'manual_review', NOT 'failed'
    assert rcpt["status"] == "manual_review"
    assert "Delivery unknown. Check your Gmail Sent folder before sending again." in rcpt["error"]

    # 2. Must NOT be scheduled for auto-retry
    assert rcpt["next_retry_at"] is None

    # 3. 'Retry failed' button/worker MUST NOT touch uncertain items
    requeued = queue_worker.retry_failed_recipients(camp_id)
    assert requeued["requeued_count"] == 0

    cursor.execute("SELECT status FROM campaign_recipients WHERE id = ?", (rcpt_id,))
    assert cursor.fetchone()["status"] == "manual_review"

    # 4. Appears on Dashboard / stranded items as Needs Review
    stranded = queue_worker.get_stranded_items()
    assert stranded["total_stranded"] >= 1
    assert any(r["id"] == rcpt_id for r in stranded["stranded_recipients"])

    # 5. Manual confirmation endpoint re-queues the uncertain recipient safely
    client = TestClient(main.app)
    conf_res = client.post(f"/api/recipients/{rcpt_id}/confirm-resend")
    assert conf_res.status_code == 200
    assert conf_res.json()["status"] == "pending"

    cursor.execute("SELECT status, retry_count FROM campaign_recipients WHERE id = ?", (rcpt_id,))
    row_conf = cursor.fetchone()
    assert row_conf["status"] == "pending"
    assert row_conf["retry_count"] == 0
    conn.close()


def test_simulated_timeout_marks_draft_needs_review():
    """If reply draft send times out, draft is marked needs_review with delivery unknown warning."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contacts (email, name, status, thread_id, created_at) VALUES ('reply.timeout@example.com', 'Reply Timeout', 'pending', 'thd-timeout-1', ?)",
            (now_str,),
        )
        cursor.execute(
            "INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed, intent) VALUES ('msg-timeout-1', 'thd-timeout-1', 'reply.timeout@example.com', 'incoming', 'Inquiry', 'Hello', ?, 'reply', 0, 'question')",
            (now_str,),
        )
        msg_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body) VALUES (?, 'thd-timeout-1', 'reply.timeout@example.com', 'Draft reply text', 'pending_approval', '', ?, ?, 'Draft reply text')",
            (msg_id, now_str, now_str),
        )
        draft_id = cursor.lastrowid
    conn.close()

    timeout_sender = TimeoutFakeSender("SocketTimeout: connection timed out after 30s")
    email_sender.set_email_sender_override(timeout_sender)

    # Attempt to send draft
    send_res = client.post(f"/api/drafts/{draft_id}/approve-and-send")
    assert send_res.status_code == 500
    assert "Delivery unknown" in send_res.json()["detail"]

    # Verify draft status in database: must be 'needs_review', NOT 'failed'
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, reason FROM drafts WHERE id = ?", (draft_id,))
    d_row = cursor.fetchone()
    conn.close()

    assert d_row["status"] == "needs_review"
    assert "Delivery unknown. Check your Gmail Sent folder before sending again." in d_row["reason"]

    # Check dashboard stranded count includes this uncertain draft
    stranded = queue_worker.get_stranded_items()
    assert any(d["id"] == draft_id for d in stranded["stranded_drafts"])


def test_presend_error_is_classified_as_temporary():
    """Errors that clearly occur before sending (e.g. connection refused) are retried temporarily."""
    assert queue_worker.is_uncertain_error("ReadTimeout: The read operation timed out") is True
    assert queue_worker.is_temporary_error("ReadTimeout: The read operation timed out") is False

    assert queue_worker.is_uncertain_error("ConnectionRefusedError: Connection refused") is False
    assert queue_worker.is_temporary_error("ConnectionRefusedError: Connection refused") is True

    assert queue_worker.is_temporary_error("RateLimitError: 429 Too Many Requests") is True
    assert queue_worker.is_temporary_error("Invalid Address: user does not exist") is False


def test_empty_test_email_blocks_sending(monkeypatch):
    """When test mode is on and TEST_EMAIL is empty or invalid, all sending is blocked with clear message."""
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "")

    client = TestClient(main.app)

    # 1. Block Campaign start
    conn = db.get_db_connection()
    user_row, _ = db.get_or_create_user(conn, "test.user@example.com", "Test User")
    uid = user_row["id"]
    now_str = datetime.utcnow().isoformat()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at, user_id) VALUES ('Camp No Test Email', 'Subj', 'same', 'Body', 'gmail', 'draft', ?, ?)",
            (now_str, uid),
        )
        camp_id = cursor.lastrowid
    conn.close()

    res_camp = client.post(f"/api/campaigns/{camp_id}/start")
    assert res_camp.status_code == 400
    assert "TEST_EMAIL is not configured" in res_camp.json()["detail"]

    # 2. Block Test send
    res_test_send = client.post(f"/api/campaigns/{camp_id}/test-send", json={"test_email": "test@example.com"})
    assert res_test_send.status_code == 400
    assert "TEST_EMAIL is not configured" in res_test_send.json()["detail"]

    # 3. Block Reply draft send
    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed, user_id) VALUES ('msg-no-test-1', 'thd-no-test-1', 'client@example.com', 'incoming', 'Hi', 'Text', ?, 'reply', 0, ?)",
            (now_str, uid),
        )
        mid = cursor.lastrowid
        cursor.execute(
            "INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body, user_id) VALUES (?, 'thd-no-test-1', 'client@example.com', 'Reply', 'pending_approval', '', ?, ?, 'Reply', ?)",
            (mid, now_str, now_str, uid),
        )
        did = cursor.lastrowid
    conn.close()

    res_draft = client.post(f"/api/drafts/{did}/approve-and-send")
    assert res_draft.status_code == 400
    assert "TEST_EMAIL is not configured" in res_draft.json()["detail"]

    # 4. Settings update rejects empty test email when test mode is active
    res_set = client.post("/api/settings", json={"test_mode": True, "test_email": ""})
    assert res_set.status_code == 400
    assert "TEST_EMAIL" in res_set.json()["detail"]

    # 5. Settings update rejects invalid test email
    res_inv = client.post("/api/settings", json={"test_mode": True, "test_email": "not-an-email"})
    assert res_inv.status_code == 400
    assert "valid email" in res_inv.json()["detail"].lower()
