"""Unit and integration tests for Phase 2: Template modes, crash recovery, unsubscribe, and daily cap."""

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
import pytest

import config
import db
from email_sender import FakeEmailSender
import queue_worker
from templating import render_email_body, append_footer


# --- Test 1: Template filling for all 3 modes ---

def test_template_mode_same():
    template = "Hello {name}, welcome to our conference!"
    rendered, skip = render_email_body("same", template, "Alice", {"company": "Acme"})
    assert skip is None
    assert "Hello Alice, welcome to our conference!" in rendered
    assert config.SENDER_NAME in rendered
    assert "unsubscribe" in rendered.lower()


def test_template_mode_fields_success():
    template = "Hi {name}, your company is {company} and your seat is {seat_no}."
    rendered, skip = render_email_body("fields", template, "Bob", {"company": "Tech Corp", "seat_no": "42A"})
    assert skip is None
    assert "Hi Bob, your company is Tech Corp and your seat is 42A." in rendered
    assert config.SENDER_NAME in rendered
    assert "unsubscribe" in rendered.lower()


def test_template_mode_fields_missing_placeholder():
    template = "Hi {name}, your company is {company} and your seat is {seat_no}."
    # Missing seat_no
    rendered, skip = render_email_body("fields", template, "Carol", {"company": "Initech"})
    assert rendered is None
    assert skip == "Missing placeholder: {seat_no}"


def test_template_mode_fields_empty_placeholder():
    template = "Hi {name}, your ticket code is {ticket}."
    # Empty ticket code
    rendered, skip = render_email_body("fields", template, "David", {"ticket": "   "})
    assert rendered is None
    assert skip == "Missing placeholder: {ticket}"


def test_template_mode_per_person_success():
    template = "Ignored fallback"
    custom_body = "Hey Eve, thank you for your custom keynote session proposal."
    rendered, skip = render_email_body("per_person", template, "Eve", {"body": custom_body})
    assert skip is None
    assert custom_body in rendered
    assert config.SENDER_NAME in rendered
    assert "unsubscribe" in rendered.lower()


def test_template_mode_per_person_missing_body():
    template = "Fallback template"
    rendered, skip = render_email_body("per_person", template, "Frank", {"other_info": "123"})
    assert rendered is None
    assert "Missing personal body" in skip


# --- Database Fixtures for Queue Tests ---

@pytest.fixture
def test_db(monkeypatch, tmp_path):
    """Set up an isolated SQLite database for testing."""
    test_db_path = tmp_path / "test_contacts.db"
    monkeypatch.setattr(config, "DB_PATH", test_db_path)
    monkeypatch.setattr(config, "PAUSE_SECONDS", 0)  # Zero pause for fast tests

    conn = db.get_db_connection()
    conn.close()
    return test_db_path


# --- Test 2: Crash recovery & Duplicate-send protection ---

def test_crash_recovery_prevents_duplicate_send(test_db):
    conn = db.get_db_connection()
    now_str = "2026-10-17T12:00:00"

    with conn:
        # Insert contact
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contacts (email, name, status, created_at) VALUES ('crash.user@example.com', 'Crash User', 'pending', ?)",
            (now_str,),
        )
        cid = cursor.lastrowid

        # Insert campaign
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Crash Test', 'Crash Subject', 'same', 'Hi {name}', 'gmail', 'running', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid

        # Simulate contact was left in 'sending' state when a crash occurred
        cursor.execute(
            "INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'sending', ?)",
            (camp_id, cid, now_str),
        )
    conn.close()

    # Run crash recovery
    recovered = queue_worker.recover_stranded_sending()
    assert recovered == 1

    # Verify status changed to manual_review and not re-sent
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, error FROM campaign_recipients WHERE campaign_id = ?", (camp_id,))
    row = cursor.fetchone()
    conn.close()

    assert row["status"] == "manual_review"
    assert "Flagged for manual review" in row["error"]

    # Now run queue worker with FakeEmailSender - should NOT send to this contact
    fake_sender = FakeEmailSender()
    queue_worker.start_campaign_queue(camp_id, sender_override=fake_sender)
    time.sleep(0.3)

    assert len(fake_sender.sent_emails) == 0


# --- Test 3: Unsubscribed contacts are never sent ---

def test_unsubscribed_contacts_are_skipped(test_db):
    conn = db.get_db_connection()
    now_str = "2026-10-17T12:00:00"

    with conn:
        cursor = conn.cursor()
        # Insert 1 active contact and 1 unsubscribed contact
        cursor.execute(
            "INSERT INTO contacts (email, name, status, created_at) VALUES ('active@example.com', 'Active Person', 'pending', ?)",
            (now_str,),
        )
        active_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO contacts (email, name, status, created_at) VALUES ('unsub@example.com', 'Unsubscribed Person', 'unsubscribed', ?)",
            (now_str,),
        )
        unsub_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Unsub Test', 'Subject', 'same', 'Hi {name}', 'gmail', 'draft', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid
    conn.close()

    fake_sender = FakeEmailSender()
    queue_worker.start_campaign_queue(camp_id, sender_override=fake_sender)
    time.sleep(0.5)

    # Fake sender should ONLY have sent to active person
    assert len(fake_sender.sent_emails) == 1
    assert fake_sender.sent_emails[0]["to_email"] == "active@example.com"

    # Verify DB status of unsubscribed recipient
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, error FROM campaign_recipients WHERE campaign_id = ? AND contact_id = ?", (camp_id, unsub_id))
    unsub_row = cursor.fetchone()
    conn.close()

    assert unsub_row["status"] == "skipped"
    assert "unsubscribed" in unsub_row["error"].lower()


# --- Test 4: Daily cap stops the queue ---

def test_daily_cap_stops_queue(test_db):
    conn = db.get_db_connection()
    now_str = "2026-10-17T12:00:00"

    with conn:
        cursor = conn.cursor()
        # Insert 5 contacts
        for i in range(1, 6):
            cursor.execute(
                "INSERT INTO contacts (email, name, status, created_at) VALUES (?, ?, 'pending', ?)",
                (f"user{i}@example.com", f"User {i}", now_str),
            )

        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at) VALUES ('Cap Test', 'Subject', 'same', 'Hi {name}', 'smtp', 'draft', ?)",
            (now_str,),
        )
        camp_id = cursor.lastrowid
    conn.close()

    # Fake sender with daily_cap = 2
    fake_sender = FakeEmailSender(daily_cap=2)
    queue_worker.start_campaign_queue(camp_id, sender_override=fake_sender)
    time.sleep(0.6)

    # Exactly 2 emails should have been sent before cap stopped the queue
    assert len(fake_sender.sent_emails) == 2

    # Check progress
    progress = queue_worker.get_campaign_progress(camp_id)
    assert progress["sent"] == 2
    assert progress["pending"] == 3
    assert progress["campaign_status"] == "paused"
