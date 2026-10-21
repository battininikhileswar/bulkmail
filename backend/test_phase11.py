"""Unit and integration tests for Phase 11: Multi-user OAuth, data separation, and limit-aware sending."""

from datetime import datetime, timedelta, date
import sqlite3
import pytest
from fastapi.testclient import TestClient

import main
import db
import auth
import limits
import config
import email_sender
import queue_worker


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Ensure all Phase 11 tests run against an isolated temporary database and token directory."""
    test_db = tmp_path / "test_phase11.db"
    test_tokens = tmp_path / "tokens"
    test_tokens.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(config, "TOKENS_DIR", test_tokens)
    monkeypatch.setattr(config, "PAUSE_SECONDS", 0)
    conn = db.get_db_connection()
    conn.close()
    yield test_db


def test_unauthenticated_requests_return_401():
    """All protected API routes return 401 when not signed in."""
    client = TestClient(main.app)
    unauth_headers = {"X-Test-No-Auth": "1"}

    # Contacts
    assert client.get("/api/contacts", headers=unauth_headers).status_code == 401
    assert client.post("/api/contacts/load-sample", headers=unauth_headers).status_code == 401
    assert client.get("/api/contacts/placeholders", headers=unauth_headers).status_code == 401
    # Campaigns
    assert client.get("/api/campaigns", headers=unauth_headers).status_code == 401
    assert client.post("/api/campaigns", json={"name": "C", "subject": "S", "mode": "same", "template": "T"}, headers=unauth_headers).status_code == 401
    assert client.get("/api/campaigns/1/plan", headers=unauth_headers).status_code == 401
    assert client.get("/api/campaigns/1/progress", headers=unauth_headers).status_code == 401
    # Drafts
    assert client.get("/api/drafts", headers=unauth_headers).status_code == 401
    # Replies
    assert client.get("/api/replies", headers=unauth_headers).status_code == 401
    # Settings
    assert client.get("/api/settings", headers=unauth_headers).status_code == 401
    # Activity
    assert client.get("/api/activity", headers=unauth_headers).status_code == 401
    # Automations
    assert client.get("/api/automations", headers=unauth_headers).status_code == 401
    # Stats & Stranded
    assert client.get("/api/stats", headers=unauth_headers).status_code == 401
    assert client.get("/api/stranded", headers=unauth_headers).status_code == 401


def test_user_data_isolation():
    """User A and User B never see or send for each other's contacts, campaigns, or drafts."""
    client = TestClient(main.app)
    conn = db.get_db_connection()

    # Create User A and User B
    user_a, _ = db.get_or_create_user(conn, "alice@gmail.com", "Alice")
    user_b, _ = db.get_or_create_user(conn, "bob@gmail.com", "Bob")
    ua_id = user_a["id"]
    ub_id = user_b["id"]
    conn.close()

    headers_a = {"X-Test-User-Id": str(ua_id)}
    headers_b = {"X-Test-User-Id": str(ub_id)}

    # 1. Contacts isolation
    res_a_sample = client.post("/api/contacts/load-sample", headers=headers_a)
    assert res_a_sample.status_code == 200

    contacts_a = client.get("/api/contacts", headers=headers_a).json()
    contacts_b = client.get("/api/contacts", headers=headers_b).json()

    assert len(contacts_a) >= 5
    assert len(contacts_b) == 0  # Bob cannot see Alice's contacts

    # 2. Campaign isolation
    res_camp_a = client.post(
        "/api/campaigns",
        json={"name": "Alice's Secret Campaign", "subject": "Special", "mode": "same", "template": "Hi {name}", "provider": "gmail"},
        headers=headers_a,
    )
    assert res_camp_a.status_code == 200
    camp_a_id = res_camp_a.json()["id"]

    campaigns_b = client.get("/api/campaigns", headers=headers_b).json()
    assert all(c["id"] != camp_a_id for c in campaigns_b)

    # Bob cannot access or control Alice's campaign directly
    assert client.get(f"/api/campaigns/{camp_a_id}", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a_id}/start", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a_id}/preview", headers=headers_b).status_code == 404
    assert client.get(f"/api/campaigns/{camp_a_id}/plan", headers=headers_b).status_code == 404
    assert client.get(f"/api/campaigns/{camp_a_id}/progress", headers=headers_b).status_code == 404

    # 3. Draft isolation
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    uniq = str(int(datetime.utcnow().timestamp() * 1000))
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed, user_id)
            VALUES (?, ?, 'contact@example.com', 'incoming', 'Inquiry', 'Hello Alice', ?, 'reply', 0, ?)
            """,
            (f"msg-a-{uniq}", f"thd-a-{uniq}", now_str, ua_id),
        )
        mid = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body, user_id)
            VALUES (?, ?, 'contact@example.com', 'Alice Draft Body', 'pending_approval', '', ?, ?, 'Alice Draft Body', ?)
            """,
            (mid, f"thd-a-{uniq}", now_str, now_str, ua_id),
        )
        draft_a_id = cursor.lastrowid
    conn.close()

    drafts_b = client.get("/api/drafts", headers=headers_b).json()
    assert all(d["id"] != draft_a_id for d in drafts_b)
    assert client.get(f"/api/drafts/{draft_a_id}", headers=headers_b).status_code == 404


def test_smtp_restriction_for_gmail_accounts():
    """SMTP is forbidden for personal @gmail.com accounts and permitted for custom domains."""
    client = TestClient(main.app)
    conn = db.get_db_connection()

    gmail_user, _ = db.get_or_create_user(conn, "testuser@gmail.com", "Gmail User")
    corp_user, _ = db.get_or_create_user(conn, "founder@mycompany.org", "Corporate User")
    conn.close()

    # Attempt SMTP with @gmail.com -> Blocked
    res_gmail = client.post(
        "/api/campaigns",
        json={"name": "SMTP Camp", "subject": "Test", "mode": "same", "template": "Hi", "provider": "smtp"},
        headers={"X-Test-User-Id": str(gmail_user["id"])},
    )
    assert res_gmail.status_code == 400
    assert "SMTP is only permitted when sending from a custom domain" in res_gmail.json()["detail"]

    # Attempt SMTP with custom domain -> Allowed
    res_corp = client.post(
        "/api/campaigns",
        json={"name": "SMTP Corp Camp", "subject": "Test", "mode": "same", "template": "Hi", "provider": "smtp"},
        headers={"X-Test-User-Id": str(corp_user["id"])},
    )
    assert res_corp.status_code == 200
    assert res_corp.json()["provider"] == "smtp"


def test_limits_calculation_and_reply_reserve():
    """Verify 10% reserve for replies and multi-day planning calculation."""
    conn = db.get_db_connection()
    user, _ = db.get_or_create_user(conn, "limits_test@gmail.com", "Limits Tester")
    uid = user["id"]

    # Turn off warmup so effective cap is the full daily cap (400 for personal gmail)
    with conn:
        conn.execute("UPDATE users SET warmup_enabled = 0, daily_cap = 400 WHERE id = ?", (uid,))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))
    user_row = dict(cursor.fetchone())

    status = limits.get_user_limits_status(conn, user_row)
    # Effective cap: 400. 10% reply reserve = 40. Campaign cap = 360.
    assert status["effective_cap"] == 400
    assert status["reply_reserve"] == 40
    assert status["campaign_cap"] == 360
    assert status["remaining_campaign"] == 360
    assert status["remaining_reply"] == 400

    # Test multi-day planning: 1000 contacts at 360 per day = 3 days
    plan = limits.calculate_multi_day_plan(
        remaining_recipients=1000,
        campaign_cap_per_day=360,
        remaining_campaign_today=360,
    )
    assert plan["is_multi_day"] is True
    assert plan["days_needed"] == 3
    assert plan["batches"] == [360, 360, 280]
    expected_finish = (date.today() + timedelta(days=2)).isoformat()
    assert plan["finish_date"] == expected_finish
    conn.close()


def test_warmup_schedule_progression():
    """Warm-up caps scale: 50 -> 100 -> 200 -> full daily cap."""
    conn = db.get_db_connection()
    user, _ = db.get_or_create_user(conn, "warmup@gmail.com", "Warmup Tester")
    uid = user["id"]

    with conn:
        conn.execute("UPDATE users SET warmup_enabled = 1, warmup_day = 1, daily_cap = 400 WHERE id = ?", (uid,))
    u1 = dict(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    assert limits.get_user_effective_cap(u1) == 50

    with conn:
        conn.execute("UPDATE users SET warmup_day = 2 WHERE id = ?", (uid,))
    u2 = dict(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    assert limits.get_user_effective_cap(u2) == 100

    with conn:
        conn.execute("UPDATE users SET warmup_day = 3 WHERE id = ?", (uid,))
    u3 = dict(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    assert limits.get_user_effective_cap(u3) == 200

    with conn:
        conn.execute("UPDATE users SET warmup_day = 4 WHERE id = ?", (uid,))
    u4 = dict(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    assert limits.get_user_effective_cap(u4) == 400
    conn.close()


def test_quota_error_pauses_campaign_without_marking_recipients_failed():
    """Quota/rate limit errors safely pause campaigns while leaving recipients in 'pending'."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    user, _ = db.get_or_create_user(conn, "quota_test@gmail.com", "Quota User")
    uid = user["id"]

    now_str = datetime.utcnow().isoformat()
    uniq = str(int(datetime.utcnow().timestamp() * 1000))
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at, user_id) VALUES ('Quota Camp', 'Subject', 'same', 'Hi {name}', 'gmail', 'running', ?, ?)",
            (now_str, uid),
        )
        camp_id = cursor.lastrowid
        cursor.execute("INSERT INTO contacts (name, email, status, created_at, user_id) VALUES ('Alice', ?, 'pending', ?, ?)", (f"alice-{uniq}@test.com", now_str, uid))
        c1 = cursor.lastrowid
        cursor.execute("INSERT INTO contacts (name, email, status, created_at, user_id) VALUES ('Bob', ?, 'pending', ?, ?)", (f"bob-{uniq}@test.com", now_str, uid))
        c2 = cursor.lastrowid
        cursor.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'pending', ?)", (camp_id, c1, now_str))
        cursor.execute("INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'pending', ?)", (camp_id, c2, now_str))
    conn.close()

    # Simulate Gmail quota exhausted error
    class QuotaFailSender(email_sender.BaseEmailSender):
        def get_daily_cap(self) -> int:
            return 400

        def send_email(self, *args, **kwargs):
            return email_sender.SendResult(
                success=False,
                error="Rate limit exceeded: 429 User-rate limit exceeded. Retry later.",
                is_quota_error=True,
            )

    email_sender.set_email_sender_override(QuotaFailSender())

    # Dispatch via worker queue
    ctrl = queue_worker.CampaignControl()
    queue_worker._worker_loop(camp_id, sender=QuotaFailSender(), ctrl=ctrl)

    # Check recipient and campaign statuses
    conn = db.get_db_connection()
    c_status = conn.execute("SELECT status FROM campaigns WHERE id = ?", (camp_id,)).fetchone()["status"]
    assert c_status == "paused"

    # Recipients must NOT be marked failed! They must remain 'pending' for next day resumption
    pending_recs = conn.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'pending'", (camp_id,)).fetchone()[0]
    failed_recs = conn.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'failed'", (camp_id,)).fetchone()[0]
    assert pending_recs == 2
    assert failed_recs == 0

    # User's quota_exhausted_until flag must be set
    u = conn.execute("SELECT quota_exhausted_until FROM users WHERE id = ?", (uid,)).fetchone()
    assert u["quota_exhausted_until"] >= date.today().isoformat()
    conn.close()
    email_sender.set_email_sender_override(None)


def test_multi_day_campaign_resumes_at_next_window_without_double_send():
    """Multi-day campaign pauses when daily cap is reached, resumes at next window, and never double-sends."""
    import autopilot
    conn = db.get_db_connection()
    user, _ = db.get_or_create_user(conn, "multiday@gmail.com", "Multi User")
    uid = user["id"]

    now_str = datetime.utcnow().isoformat()
    uniq = str(int(datetime.utcnow().timestamp() * 1000))
    with conn:
        cursor = conn.cursor()
        # Cap set to 2 so user can only send 1 or 2 before daily limit is hit
        conn.execute("UPDATE users SET warmup_enabled = 0, daily_cap = 2 WHERE id = ?", (uid,))
        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at, user_id) VALUES ('MD Camp', 'Subject', 'same', 'Hi {name}', 'gmail', 'running', ?, ?)",
            (now_str, uid),
        )
        camp_id = cursor.lastrowid
        for i in range(5):
            cursor.execute(
                "INSERT INTO contacts (name, email, status, created_at, user_id) VALUES (?, ?, 'pending', ?, ?)",
                (f"User {i}", f"user{i}_{uniq}@test.com", now_str, uid),
            )
            cid = cursor.lastrowid
            cursor.execute(
                "INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at) VALUES (?, ?, 'pending', ?)",
                (camp_id, cid, now_str),
            )
    conn.close()

    fake_sender = email_sender.FakeEmailSender(daily_cap=100)
    email_sender.set_email_sender_override(fake_sender)

    # Day 1: Run queue worker with small cap
    ctrl = queue_worker.CampaignControl()
    queue_worker._worker_loop(camp_id, sender=fake_sender, ctrl=ctrl)

    # Check Day 1 status: campaign paused, some sent, remainder scheduled_next_day
    conn = db.get_db_connection()
    camp_st = conn.execute("SELECT status FROM campaigns WHERE id = ?", (camp_id,)).fetchone()["status"]
    assert camp_st == "paused"

    sent_day1 = conn.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'sent'", (camp_id,)).fetchone()[0]
    next_day1 = conn.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'scheduled_next_day'", (camp_id,)).fetchone()[0]
    assert sent_day1 > 0
    assert sent_day1 + next_day1 == 5
    assert next_day1 > 0
    conn.close()

    # Day 2: Advance to new day with limit available
    conn = db.get_db_connection()
    with conn:
        conn.execute("UPDATE users SET daily_cap = 100 WHERE id = ?", (uid,))
        conn.execute("DELETE FROM daily_sends WHERE user_id = ?", (uid,))
    conn.close()

    # Automatic resumption via autopilot check
    resumed = autopilot.resume_multi_day_campaigns(send_window_override=True)
    assert camp_id in resumed

    # Run queue worker to complete remaining batch
    queue_worker._worker_loop(camp_id, sender=fake_sender, ctrl=queue_worker.CampaignControl())

    # Verify all 5 contacts sent and 0 pending/scheduled
    conn = db.get_db_connection()
    final_sent = conn.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'sent'", (camp_id,)).fetchone()[0]
    final_pending = conn.execute(
        "SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status IN ('pending', 'scheduled_next_day')",
        (camp_id,),
    ).fetchone()[0]
    assert final_sent == 5
    assert final_pending == 0
    conn.close()
    email_sender.set_email_sender_override(None)


def test_ownerless_rows_never_returned_to_any_user():
    """Verify that records with user_id = NULL (owner-less rows) are never returned to any user."""
    client = TestClient(main.app)
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()

    # Create two distinct users
    user_a, _ = db.get_or_create_user(conn, "alice_iso@example.com", "Alice Iso")
    user_b, _ = db.get_or_create_user(conn, "bob_iso@example.com", "Bob Iso")
    ua_id = user_a["id"]
    ub_id = user_b["id"]

    # Directly insert owner-less (user_id = NULL) rows across tables
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contacts (email, name, status, created_at, user_id) VALUES ('orphan@example.com', 'Orphan Contact', 'pending', ?, NULL)",
            (now_str,),
        )
        orphan_cid = cursor.lastrowid

        cursor.execute(
            "INSERT INTO campaigns (name, subject, mode, template, provider, status, created_at, user_id) VALUES ('Orphan Campaign', 'Subject', 'same', 'Body', 'gmail', 'draft', ?, NULL)",
            (now_str,),
        )
        orphan_camp_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO messages (gmail_message_id, thread_id, contact_email, direction, subject, body_text, received_at, category, processed, user_id) VALUES ('orphan-msg-1', 'thd-orphan', 'orphan@example.com', 'incoming', 'Hi', 'Text', ?, 'reply', 0, NULL)",
            (now_str,),
        )
        orphan_mid = cursor.lastrowid

        cursor.execute(
            "INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body, user_id) VALUES (?, 'thd-orphan', 'orphan@example.com', 'Orphan Draft', 'pending_approval', '', ?, ?, 'Orphan Draft', NULL)",
            (orphan_mid, now_str, now_str),
        )
        orphan_did = cursor.lastrowid

        cursor.execute(
            "INSERT INTO activity_log (timestamp, action, contact_email, details, user_id) VALUES (?, 'orphan_event', 'orphan@example.com', 'Orphan details', NULL)",
            (now_str,),
        )
        orphan_aid = cursor.lastrowid
    conn.close()

    for user_header in [{"X-Test-User-Id": str(ua_id)}, {"X-Test-User-Id": str(ub_id)}]:
        # 1. Contacts
        contacts = client.get("/api/contacts", headers=user_header).json()
        assert not any(c["id"] == orphan_cid or c["email"] == "orphan@example.com" for c in contacts)

        # 2. Campaigns
        campaigns = client.get("/api/campaigns", headers=user_header).json()
        assert not any(c["id"] == orphan_camp_id for c in campaigns)
        assert client.get(f"/api/campaigns/{orphan_camp_id}", headers=user_header).status_code == 404

        # 3. Drafts
        drafts = client.get("/api/drafts", headers=user_header).json()
        assert not any(d["id"] == orphan_did for d in drafts)
        assert client.post(f"/api/drafts/{orphan_did}/approve-and-send", headers=user_header).status_code == 404

        # 4. Replies
        replies = client.get("/api/replies", headers=user_header).json()
        assert not any(r["id"] == orphan_mid for r in replies)

        # 5. Activity log
        activity = client.get("/api/activity", headers=user_header).json()
        assert not any(a["id"] == orphan_aid for a in activity)


def test_serverless_self_healing_authentication():
    """A valid signed session token automatically self-heals across serverless cold-start containers."""
    client = TestClient(main.app)

    # User does NOT exist in the database yet (simulating cold lambda container)
    conn = db.get_db_connection()
    assert db.get_user_by_id(conn, 88) is None
    assert db.get_user_by_email(conn, "serverless.user@example.com") is None
    conn.close()

    # Create signed session token for non-existent user
    token = auth.create_session_cookie(user_id=88, email="serverless.user@example.com", name="Serverless User")
    headers = {"Authorization": f"Bearer {token}"}

    # Protected endpoints should self-heal and return 200, NOT 401
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["id"] == 88
    assert me_data["email"] == "serverless.user@example.com"
    assert me_data["name"] == "Serverless User"

    stats_res = client.get("/api/stats", headers=headers)
    assert stats_res.status_code == 200
    assert "total" in stats_res.json()

    campaigns_res = client.get("/api/campaigns", headers=headers)
    assert campaigns_res.status_code == 200
    assert isinstance(campaigns_res.json(), list)

    drafts_res = client.get("/api/drafts", headers=headers)
    assert drafts_res.status_code == 200

    watcher_res = client.get("/api/watcher/status", headers=headers)
    assert watcher_res.status_code == 200

    activity_res = client.get("/api/activity", headers=headers)
    assert activity_res.status_code == 200

    # Verify user record was persisted with identical user ID
    conn = db.get_db_connection()
    persisted = db.get_user_by_id(conn, 88)
    assert persisted is not None
    assert persisted["email"] == "serverless.user@example.com"
    conn.close()


def test_login_and_app_fallback_routes():
    """Direct requests to /login and /app on backend return 303 Redirect to frontend instead of 404."""
    client = TestClient(main.app)

    # Test /login and /api/login
    res_login = client.get("/login", follow_redirects=False)
    assert res_login.status_code == 303
    assert f"{config.FRONTEND_URL}/login" in res_login.headers.get("location", "")

    res_api_login = client.get("/api/login", follow_redirects=False)
    assert res_api_login.status_code == 303
    assert f"{config.FRONTEND_URL}/login" in res_api_login.headers.get("location", "")

    # Test JSON accept header for /login
    json_login = client.get("/login", headers={"Accept": "application/json"})
    assert json_login.status_code == 200
    assert "login_url" in json_login.json()

    # Test /app and /api/app
    res_app = client.get("/app", follow_redirects=False)
    assert res_app.status_code == 303
    assert f"{config.FRONTEND_URL}/app" in res_app.headers.get("location", "")

    res_api_app = client.get("/api/app", follow_redirects=False)
    assert res_api_app.status_code == 303
    assert f"{config.FRONTEND_URL}/app" in res_api_app.headers.get("location", "")


