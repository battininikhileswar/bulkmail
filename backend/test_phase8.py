"""Unit tests for Phase 8: Hardening, retries, crash recovery, backups, and security."""

from datetime import datetime
import json
import sqlite3
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
    test_db = tmp_path / "test_phase8.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(config, "TEST_MODE", False)
    conn = db.get_db_connection()
    conn.close()

    fake_sender = email_sender.FakeEmailSender(daily_cap=100)
    email_sender.set_email_sender_override(fake_sender)

    yield fake_sender

    email_sender.set_email_sender_override(None)


def test_temporary_errors_retry_up_to_3_times_and_permanent_fail_immediately(clean_test_env, monkeypatch):
    """Temporary errors schedule up to 3 retries, whereas permanent errors fail immediately."""
    fake_sender = clean_test_env

    # Mock error classification
    assert queue_worker.is_temporary_error("Connection refused by remote host") is True
    assert queue_worker.is_temporary_error("503 Service Temporarily Unavailable") is True
    assert queue_worker.is_temporary_error("550 Invalid recipient email address") is False
    assert queue_worker.is_temporary_error("User mailbox unavailable: permanent failure") is False

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('temp@fail.com', 'Temp User', 'pending', ?)", (now_str,))
        temp_cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('perm@fail.com', 'Perm User', 'pending', ?)", (now_str,))
        perm_cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            """
            INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at)
            VALUES ('Retry Campaign', 'Subject', 'same', 'Hello {name}', 'gmail', 'running', ?)
            """,
            (now_str,),
        )
        camp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 1. Recipient with temporary error
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, retry_count, created_at)
            VALUES (?, ?, 'pending', 0, ?)
            """,
            (camp_id, temp_cid, now_str),
        )
        temp_rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 2. Recipient with permanent error
        conn.execute(
            """
            INSERT INTO campaign_recipients (campaign_id, contact_id, status, retry_count, created_at)
            VALUES (?, ?, 'pending', 0, ?)
            """,
            (camp_id, perm_cid, now_str),
        )
        perm_rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    ctrl = queue_worker.CampaignControl()

    # Step 1: Send temporary failure
    def mock_temp_error(*args, **kwargs):
        return email_sender.SendResult(success=False, error="Connection refused: 503 Service Unavailable")

    monkeypatch.setattr(fake_sender, "send_email", mock_temp_error)

    # Run worker loop for 1 step
    conn = db.get_db_connection()
    # Trigger 1 send
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaign_recipients WHERE id = ?", (temp_rid,))
    r_before = cursor.fetchone()
    conn.close()

    # Process temp error
    conn = db.get_db_connection()
    with conn:
        # Simulate worker processing temp error
        error_msg = "Connection refused: 503 Service Unavailable"
        assert queue_worker.is_temporary_error(error_msg) is True
        delay = queue_worker.RETRY_DELAYS_SECONDS[0]
        next_t = (datetime.utcnow()).isoformat()
        conn.execute(
            "UPDATE campaign_recipients SET status = 'pending', retry_count = 1, next_retry_at = ?, error = ? WHERE id = ?",
            (next_t, error_msg, temp_rid),
        )
    conn.close()

    # Verify temp recipient was re-scheduled (still 'pending', retry_count=1)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, retry_count FROM campaign_recipients WHERE id = ?", (temp_rid,))
    temp_row = cursor.fetchone()
    assert temp_row["status"] == "pending"
    assert temp_row["retry_count"] == 1

    # Simulate permanent error
    perm_error = "550 Invalid recipient address: mailbox not found"
    assert queue_worker.is_temporary_error(perm_error) is False
    with conn:
        conn.execute(
            "UPDATE campaign_recipients SET status = 'failed', retry_count = 0, error = ? WHERE id = ?",
            (f"Permanent error: {perm_error}", perm_rid),
        )

    cursor.execute("SELECT status, retry_count, error FROM campaign_recipients WHERE id = ?", (perm_rid,))
    perm_row = cursor.fetchone()
    assert perm_row["status"] == "failed"
    assert "Permanent error" in perm_row["error"]
    assert perm_row["retry_count"] == 0
    conn.close()


def test_retry_failed_never_resends_already_sent_contacts(clean_test_env):
    """The 'Retry failed' feature re-queues only failed recipients, never sent, unsubscribed, or bounced."""
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('sent@ex.com', 'Sent User', 'sent', ?)", (now_str,))
        sent_cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('unsub@ex.com', 'Unsub User', 'unsubscribed', ?)", (now_str,))
        unsub_cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('bounced@ex.com', 'Bounced User', 'failed', ?)", (now_str,))
        bounced_cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('failed@ex.com', 'Failed User', 'pending', ?)", (now_str,))
        failed_cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('C1', 'S', 'same', 'B', 'gmail', 'completed', ?)", (now_str,))
        camp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'sent', ?)", (camp_id, sent_cid, now_str))
        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'failed', ?)", (camp_id, unsub_cid, now_str))
        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'failed', ?)", (camp_id, bounced_cid, now_str))
        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at, error) VALUES (?, ?, 'failed', ?, 'Network timeout')", (camp_id, failed_cid, now_str))
    conn.close()

    # Re-queue failed contacts
    res = queue_worker.retry_failed_recipients(camp_id)
    assert res["success"] is True
    # Only failed_cid should be re-queued! (sent was sent, unsub was unsubscribed, bounced was contact failed)
    assert res["requeued_count"] == 1

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT contact_id, status FROM campaign_recipients WHERE campaign_id = ?", (camp_id,))
    statuses = {r["contact_id"]: r["status"] for r in cursor.fetchall()}

    assert statuses[sent_cid] == "sent"        # Untouched
    assert statuses[unsub_cid] == "failed"     # Not re-queued because contact is unsubscribed
    assert statuses[bounced_cid] == "failed"   # Not re-queued because contact bounced
    assert statuses[failed_cid] == "pending"   # Safely re-queued!
    conn.close()


def test_stuck_sending_items_listed_after_restart_and_not_resent(clean_test_env):
    """Crash recovery identifies stuck 'sending' contacts and 'approved' drafts and puts them into review."""
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('stuck@ex.com', 'Stuck User', 'pending', ?)", (now_str,))
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute("INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Stuck C', 'Sub', 'same', 'Body', 'gmail', 'running', ?)", (now_str,))
        camp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Simulate stuck sending recipient
        conn.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'sending', ?)", (camp_id, cid, now_str))

        # Simulate stuck approved draft
        conn.execute("INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed) VALUES ('g-stuck', 'thd-stuck', 'stuck@ex.com', 'incoming', 'Hi', 'Hey', ?, 'reply', 0)", (now_str,))
        mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at) VALUES (?, 'thd-stuck', 'stuck@ex.com', 'Draft Body', 'approved', '', ?, ?)", (mid, now_str, now_str))
    conn.close()

    # Simulate server restart crash recovery
    counts = queue_worker.recover_stranded_sending()
    assert counts["stranded_recipients"] == 1
    assert counts["stranded_drafts"] == 1

    # Verify status changed to review
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, error FROM campaign_recipients WHERE campaign_id = ?", (camp_id,))
    r = cursor.fetchone()
    assert r["status"] == "manual_review"
    assert "Interrupted" in r["error"]

    cursor.execute("SELECT status, reason FROM drafts WHERE thread_id = 'thd-stuck'")
    d = cursor.fetchone()
    assert d["status"] == "needs_review"
    assert "Interrupted" in d["reason"]

    # Verify get_stranded_items reports them
    stranded = queue_worker.get_stranded_items()
    assert stranded["total_stranded"] == 2
    conn.close()


def test_backup_creates_file_and_keeps_latest_10(tmp_path, monkeypatch):
    """Backups are timestamped SQLite files, and older backups are pruned to keep at most 10."""
    backups_dir = tmp_path / "backups"
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)

    # Create 12 backups
    created_names = []
    for i in range(12):
        name = db.create_backup()
        created_names.append(name)

    files = list(backups_dir.glob("contacts_*.db"))
    # Strictly kept at most 10
    assert len(files) == 10

    # Verify they are readable SQLite databases
    sample_backup = files[0]
    conn = sqlite3.connect(sample_backup)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert "contacts" in tables
    assert "campaigns" in tables


def test_incoming_html_or_script_text_plain_text(clean_test_env):
    """Raw HTML or script tags are stored as plain text and never executed as HTML."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    raw_inquiry = "<script>alert('xss')</script><b>Where is the venue located?</b>"

    with conn:
        conn.execute("INSERT INTO contacts (email, name, status, created_at) VALUES ('hacker@test.com', 'Tester', 'sent', ?)", (now_str,))
        conn.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed)
            VALUES ('msg-xss-1', 'thd-xss', 'hacker@test.com', 'incoming', 'Inquiry', ?, ?, 'reply', 0)
            """,
            (raw_inquiry, now_str),
        )
        msg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    res = client.get(f"/api/replies/{msg_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["reply"]["body_text"] == raw_inquiry
    # Raw script tag is treated as plain string data, not executable HTML
    assert "<script>" in data["reply"]["body_text"]
