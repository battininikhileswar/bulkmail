"""Unit and integration tests for Phase 10: Quick Start and Autopilot."""

from datetime import datetime, timedelta
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

import ai_client
import autopilot
import config
import db
import email_sender
import main
import queue_worker


@pytest.fixture(autouse=True)
def clean_test_env(tmp_path, monkeypatch):
    """Isolate SQLite database to a temporary file and mock email sender."""
    test_db = tmp_path / "test_phase10.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    conn = db.get_db_connection()
    conn.close()

    fake_sender = email_sender.FakeEmailSender(daily_cap=50)
    email_sender.set_email_sender_override(fake_sender)

    # Reset in-memory global pause switch
    queue_worker.set_global_sending_paused(False)
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "test@example.com")

    yield fake_sender

    email_sender.set_email_sender_override(None)
    ai_client.set_client_override(None)


def test_quick_start_sample_data_and_template_fallback():
    """Verify Load Sample Contacts and AI template fallback when AI fails."""
    client = TestClient(main.app)

    # 1. Load sample contacts
    res = client.post("/api/contacts/load-sample")
    assert res.status_code == 200
    data = res.json()
    assert data["added"] == 5

    # 2. Mock AI failure to test safe fallback template
    class FailingAiClient:
        class messages:
            @staticmethod
            def create(*args, **kwargs):
                raise RuntimeError("API quota exceeded")

    ai_client.set_client_override(FailingAiClient())

    # Call quick-template
    res = client.post(
        "/api/ai/quick-template",
        json={
            "goal": "Announce / invite",
            "prompt": "Announce our keynote speaker Alice",
            "placeholders": ["name", "company"],
        },
    )
    assert res.status_code == 200
    t_data = res.json()
    assert t_data["fallback"] is True
    assert "{name}" in t_data["template"]
    assert "Alice" in t_data["template"]

    # 3. Create draft campaign from Quick Start
    camp_res = client.post(
        "/api/campaigns",
        json={
            "name": "Quick Launch Event",
            "subject": t_data["subject"],
            "mode": "same",
            "template": t_data["template"],
            "provider": "gmail",
        },
    )
    assert camp_res.status_code == 200
    camp = camp_res.json()
    assert camp["status"] == "draft"


def test_followup_skips_replied_unsubscribed_bounced_and_manual_review(clean_test_env):
    """Confirm Autopilot follow-up strictly skips replied, unsubscribed, bounced, or manual_review contacts."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    now_str = (datetime.utcnow() - timedelta(days=5)).isoformat()

    # Create campaign
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Camp 1', 'Welcome', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid

        # Contact 1: Valid eligible recipient (sent 5 days ago, no reply, no bounce)
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('User 1', 'user1@example.com', 'sent', ?)", (now_str,))
        c1_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-1', 'msg-1', ?, ?, 0)",
            (camp_id, c1_id, now_str, now_str),
        )

        # Contact 2: Contact who replied (incoming reply exists)
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('User 2', 'user2@example.com', 'sent', ?)", (now_str,))
        c2_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-2', 'msg-2', ?, ?, 0)",
            (camp_id, c2_id, now_str, now_str),
        )
        cursor.execute(
            "INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed) VALUES ('msg-in-2', 'thd-2', 'user2@example.com', 'incoming', 'Thanks', 'Got it', ?, 'reply', 1)",
            (now_str,),
        )

        # Contact 3: Unsubscribed contact
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('User 3', 'user3@example.com', 'unsubscribed', ?)", (now_str,))
        c3_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-3', 'msg-3', ?, ?, 0)",
            (camp_id, c3_id, now_str, now_str),
        )

        # Contact 4: Bounced message recipient
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('User 4', 'user4@example.com', 'sent', ?)", (now_str,))
        c4_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'failed', 'thd-4', 'msg-4', ?, ?, 0)",
            (camp_id, c4_id, now_str, now_str),
        )

        # Contact 5: Manual review / uncertain recipient
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('User 5', 'user5@example.com', 'sent', ?)", (now_str,))
        c5_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, error, created_at, followup_count) VALUES (?, ?, 'manual_review', 'thd-5', 'msg-5', ?, 'Delivery unknown. Check your Gmail Sent folder before sending again.', ?, 0)",
            (camp_id, c5_id, now_str, now_str),
        )

    conn.close()

    # Create automation rule
    create_res = client.post(
        "/api/automations",
        json={
            "campaign_id": camp_id,
            "type": "followup",
            "delay_days": 3,
            "max_followups": 1,
            "template": "Hi {name}, just following up on our invitation.",
        },
    )
    assert create_res.status_code == 200
    auto = create_res.json()
    auto_id = auto["id"]

    # Preview checks
    preview_res = client.get(f"/api/automations/{auto_id}/preview")
    assert preview_res.status_code == 200
    preview = preview_res.json()

    assert preview["total_eligible"] == 1
    assert preview["eligible"][0]["email"] == "user1@example.com"

    skipped_emails = {s["email"] for s in preview["skipped"]}
    assert "user2@example.com" in skipped_emails  # Replied
    assert "user3@example.com" in skipped_emails  # Unsubscribed
    assert "user4@example.com" in skipped_emails  # Bounced / failed
    assert "user5@example.com" in skipped_emails  # Manual review


def test_followup_never_exceeds_max_followups_and_respects_quiet_hours(clean_test_env):
    """Verify follow-up hard ceiling (max 2) and quiet hours window suppression."""
    conn = db.get_db_connection()
    now_str = (datetime.utcnow() - timedelta(days=10)).isoformat()

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Camp 2', 'Hello', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid

        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Max User', 'max@example.com', 'sent', ?)", (now_str,))
        cid = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-m', 'msg-m', ?, ?, 2)",
            (camp_id, cid, now_str, now_str),
        )
    conn.close()

    auto = autopilot.create_automation({
        "campaign_id": camp_id,
        "type": "followup",
        "delay_days": 1,
        "max_followups": 2,
        "template": "Followup body",
    })
    auto_id = auto["id"]

    # Check preview: max followups reached
    preview = autopilot.preview_automation(auto_id)
    assert preview["total_eligible"] == 0
    assert "Max follow-ups reached" in preview["skipped"][0]["reason"]

    # Check quiet hours suppression
    outside_cycle = autopilot.run_autopilot_cycle(send_window_override=False)
    assert outside_cycle["processed"] == 0


def test_daily_cap_pause_switch_and_invalid_test_email_block_automations(clean_test_env, monkeypatch):
    """Confirm daily cap, pause switch, and invalid TEST_EMAIL safely halt automations."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    now_str = (datetime.utcnow() - timedelta(days=5)).isoformat()

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Camp 3', 'Hello', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid

        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Bob', 'bob@example.com', 'sent', ?)", (now_str,))
        cid = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-b', 'msg-b', ?, ?, 0)",
            (camp_id, cid, now_str, now_str),
        )
    conn.close()

    auto = autopilot.create_automation({
        "campaign_id": camp_id,
        "type": "followup",
        "delay_days": 1,
        "max_followups": 1,
        "template": "Followup to {name}",
    })
    auto_id = auto["id"]
    autopilot.enable_automation(auto_id, consent=True)

    # 1. Invalid TEST_EMAIL blocks
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "")
    res = autopilot.run_autopilot_cycle(send_window_override=True)
    assert res["status"] == "blocked"

    # Restore valid TEST_EMAIL
    monkeypatch.setattr(config, "TEST_EMAIL", "test@example.com")

    # 2. Pause switch blocks
    queue_worker.set_global_sending_paused(True)
    res_paused = autopilot.run_autopilot_cycle(send_window_override=True)
    assert res_paused["status"] == "paused"
    queue_worker.set_global_sending_paused(False)

    # 3. Daily cap blocks
    monkeypatch.setattr(config, "TEST_MODE", False)  # Live mode checks daily cap
    conn = db.get_db_connection()
    with conn:
        conn.execute("INSERT OR REPLACE INTO daily_sends (provider, send_date, count) VALUES ('gmail', ?, 400)", (datetime.utcnow().strftime("%Y-%m-%d"),))
    conn.close()
    res_cap = autopilot.run_autopilot_cycle(send_window_override=True)
    assert res_cap["status"] == "daily_cap_reached"


def test_test_mode_sends_only_to_test_address_and_restart_safety(clean_test_env, monkeypatch):
    """Verify test mode diversion and crash restart safety prevents double sends."""
    fake_sender = clean_test_env
    conn = db.get_db_connection()
    now_str = (datetime.utcnow() - timedelta(days=5)).isoformat()

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Camp 4', 'Announcement', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid

        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Sam User', 'sam@example.com', 'sent', ?)", (now_str,))
        cid = cursor.lastrowid
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-s', 'msg-s', ?, ?, 0)",
            (camp_id, cid, now_str, now_str),
        )
    conn.close()

    auto = autopilot.create_automation({
        "campaign_id": camp_id,
        "type": "followup",
        "delay_days": 1,
        "max_followups": 1,
        "template": "Checking in with {name}",
    })
    auto_id = auto["id"]
    autopilot.enable_automation(auto_id, consent=True)

    # Execute cycle in test mode
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "test-override@example.com")
    cycle_res = autopilot.run_autopilot_cycle(send_window_override=True)
    assert cycle_res["processed"] == 1

    # Verify FakeEmailSender sent ONLY to test address
    assert len(fake_sender.sent_emails) == 1
    sent_msg = fake_sender.sent_emails[0]
    assert sent_msg["to_email"] == "test-override@example.com"
    assert "[TEST]" in sent_msg["subject"]

    # Verify recipient followup_count updated in DB
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT followup_count, status FROM campaign_recipients WHERE campaign_id = ?", (camp_id,))
    row = cursor.fetchone()
    assert row["followup_count"] == 1
    assert row["status"] == "sent"

    # Simulate server crash recovery / restart: ensure follow-up is NEVER sent a second time
    recovered = queue_worker.recover_stranded_sending()
    cycle_res_2 = autopilot.run_autopilot_cycle(send_window_override=True)
    assert cycle_res_2["processed"] == 0
    assert len(fake_sender.sent_emails) == 1  # No second send
    conn.close()


def test_event_reminder_skips_replied_unsubscribed_and_manual_review(clean_test_env):
    """Verify event_reminder automation skips anyone who replied, unsubscribed, or in manual_review."""
    conn = db.get_db_connection()
    now_str = (datetime.utcnow() - timedelta(days=2)).isoformat()
    past_sched = (datetime.utcnow() - timedelta(hours=1)).isoformat()

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Camp Reminder', 'Event Soon', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid

        # Contact 1: Valid eligible
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Alice', 'alice@example.com', 'sent', ?)", (now_str,))
        c1 = cursor.lastrowid
        cursor.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-r1', 'msg-r1', ?, ?, 0)", (camp_id, c1, now_str, now_str))

        # Contact 2: Replied
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Bob', 'bob@example.com', 'sent', ?)", (now_str,))
        c2 = cursor.lastrowid
        cursor.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-r2', 'msg-r2', ?, ?, 0)", (camp_id, c2, now_str, now_str))
        cursor.execute("INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed) VALUES ('msg-in-r2', 'thd-r2', 'bob@example.com', 'incoming', 'Re: Event Soon', 'See you there', ?, 'reply', 1)", (now_str,))

        # Contact 3: In manual review
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Carol', 'carol@example.com', 'sent', ?)", (now_str,))
        c3 = cursor.lastrowid
        cursor.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, error, created_at, followup_count) VALUES (?, ?, 'manual_review', 'thd-r3', 'msg-r3', ?, 'Delivery unknown. Check your Gmail Sent folder before sending again.', ?, 0)", (camp_id, c3, now_str, now_str))
    conn.close()

    auto = autopilot.create_automation({
        "campaign_id": camp_id,
        "type": "event_reminder",
        "template": "Reminder: Event starts soon!",
        "scheduled_at": past_sched,
    })
    preview = autopilot.preview_automation(auto["id"])
    assert preview["total_eligible"] == 1
    assert preview["eligible"][0]["email"] == "alice@example.com"
    skipped = {s["email"] for s in preview["skipped"]}
    assert "bob@example.com" in skipped
    assert "carol@example.com" in skipped


def test_timeout_creates_uncertain_item_never_auto_retried(clean_test_env, monkeypatch):
    """Simulated timeout during automation send creates uncertain item (manual_review) and is never auto-retried."""
    conn = db.get_db_connection()
    now_str = (datetime.utcnow() - timedelta(days=5)).isoformat()

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Camp Timeout', 'Notice', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid
        cursor.execute("INSERT INTO contacts (name, email, status, created_at) VALUES ('Dave', 'dave@example.com', 'sent', ?)", (now_str,))
        cid = cursor.lastrowid
        cursor.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, thread_id, message_id, sent_at, created_at, followup_count) VALUES (?, ?, 'sent', 'thd-to', 'msg-to', ?, ?, 0)", (camp_id, cid, now_str, now_str))
    conn.close()

    auto = autopilot.create_automation({
        "campaign_id": camp_id,
        "type": "followup",
        "delay_days": 1,
        "max_followups": 1,
        "template": "Followup for {name}",
    })
    autopilot.enable_automation(auto["id"], consent=True)

    # Mock timeout error
    class TimeoutSender(email_sender.BaseEmailSender):
        def send_email(self, *args, **kwargs):
            raise TimeoutError("Read timeout while contacting mail server")

    email_sender.set_email_sender_override(TimeoutSender())

    # Run cycle
    res = autopilot.run_autopilot_cycle(send_window_override=True)
    assert res["processed"] == 0

    # Verify recipient transitioned to manual_review with Delivery unknown note
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, error FROM campaign_recipients WHERE campaign_id = ?", (camp_id,))
    row = cursor.fetchone()
    assert row["status"] == "manual_review"
    assert "Delivery unknown" in row["error"]

    # Verify subsequent cycle strictly ignores it
    email_sender.set_email_sender_override(clean_test_env)
    res_2 = autopilot.run_autopilot_cycle(send_window_override=True)
    assert res_2["processed"] == 0
    conn.close()


def test_enabling_requires_consent_tick_and_defaults_to_off():
    """Verify that an automation defaults to OFF and enabling requires consent=True."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Consent Camp', 'Test', 'same', 'Hi', 'gmail', 'running', ?)", (datetime.utcnow().isoformat(),))
        camp_id = cursor.lastrowid
    conn.close()

    # 1. Create automation: defaults to OFF
    res = client.post("/api/automations", json={"campaign_id": camp_id, "type": "followup", "template": "Hi"})
    assert res.status_code == 200
    auto = res.json()
    assert auto["enabled"] == 0

    # 2. Enable without consent: rejected with 400
    fail_res = client.post(f"/api/automations/{auto['id']}/enable", json={"consent": False})
    assert fail_res.status_code == 400

    # 3. Enable with consent: succeeds
    ok_res = client.post(f"/api/automations/{auto['id']}/enable", json={"consent": True})
    assert ok_res.status_code == 200
    assert ok_res.json()["enabled"] == 1

