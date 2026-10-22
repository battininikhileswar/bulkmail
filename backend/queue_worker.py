"""Sending queue worker, pause/resume/stop lifecycle, crash recovery, and test-send logic."""

from datetime import datetime, date, timedelta
import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import config
import db
from email_sender import BaseEmailSender, get_sender
from templating import render_email_body


class CampaignControl:
    """Thread control flags for a running campaign."""
    def __init__(self):
        self.pause_event = threading.Event()
        self.pause_event.set()  # Unpaused initially
        self.stop_event = threading.Event()
        self.is_running = True


# In-memory registry for active campaign workers
ACTIVE_CONTROLS: Dict[int, CampaignControl] = {}
ACTIVE_THREADS: Dict[int, threading.Thread] = {}
REGISTRY_LOCK = threading.Lock()

# Global sending pause switch
_GLOBAL_SENDING_PAUSED = False
_GLOBAL_PAUSE_LOCK = threading.Lock()

# Gmail authorization status
_GMAIL_AUTH_EXPIRED = False
_GMAIL_AUTH_LOCK = threading.Lock()


def is_global_sending_paused() -> bool:
    """Return whether all sending (campaigns and reply drafts) is globally paused."""
    with _GLOBAL_PAUSE_LOCK:
        return _GLOBAL_SENDING_PAUSED


def set_global_sending_paused(paused: bool) -> None:
    """Set the global sending pause switch."""
    global _GLOBAL_SENDING_PAUSED
    with _GLOBAL_PAUSE_LOCK:
        _GLOBAL_SENDING_PAUSED = paused


def is_gmail_auth_expired() -> bool:
    """Return whether Gmail authentication has expired or was revoked."""
    with _GMAIL_AUTH_LOCK:
        return _GMAIL_AUTH_EXPIRED


def set_gmail_auth_expired(expired: bool) -> None:
    """Flag Gmail authorization as expired/revoked."""
    global _GMAIL_AUTH_EXPIRED
    with _GMAIL_AUTH_LOCK:
        _GMAIL_AUTH_EXPIRED = expired


def is_gmail_auth_error(error_message: str) -> bool:
    """Detect if an error signifies expired or revoked Gmail OAuth authorization."""
    if not error_message:
        return False
    lowered = error_message.lower()
    return any(term in lowered for term in [
        "invalid_grant", "token has been expired or revoked", "token.json",
        "gmail.readonly", "unauthorized_client", "credentials are missing",
        "deleted client", "token expired"
    ])


def is_uncertain_error(error_message: str) -> bool:
    """
    Detect errors where the send request may have reached Gmail/SMTP before the connection timed out or dropped.
    These must NEVER be auto-retried to avoid duplicate emails.
    """
    if not error_message:
        return False
    err = error_message.lower()
    uncertain_indicators = [
        "timeout", "timed out", "read timeout", "readtimedout", "socket timeout",
        "connection reset", "connection aborted", "connection dropped", "connection closed",
        "remotely closed", "broken pipe", "uncertain", "server disconnected", "reset by peer",
        "delivery unknown"
    ]
    return any(ind in err for ind in uncertain_indicators)


def is_temporary_error(error_message: str) -> bool:
    """
    Classify whether an email delivery error is temporary (pre-send network, rate limit, server errors)
    or permanent (invalid address, blocked, auth failure, unsubscribed).
    Uncertain sends (timeouts, dropped connections in flight) are strictly excluded from auto-retries.
    """
    if not error_message:
        return False
    err = error_message.lower()

    # Uncertain sends must NEVER be auto-retried
    if is_uncertain_error(err):
        return False

    # Permanent errors - NEVER retry automatically
    permanent_indicators = [
        "invalid address", "invalid recipient", "does not exist", "recipient rejected",
        "no such user", "user unknown", "mailbox unavailable", "unsubscribed",
        "auth", "authentication", "credentials", "unauthorized", "permission denied",
        "blocked", "blacklist", "spam", "policy violation", "disabled"
    ]
    for ind in permanent_indicators:
        if ind in err:
            return False

    # Temporary errors that clearly occurred BEFORE the request reached the mail server
    pre_send_indicators = [
        "refused", "connection refused", "dns", "resolution", "name resolution",
        "getaddrinfo", "nodename nor servname", "rate limit", "too many requests",
        "429", "500", "502", "503", "504", "temporary", "quota", "overloaded",
        "busy", "try again", "service unavailable", "gateway"
    ]
    for ind in pre_send_indicators:
        if ind in err:
            return True

    return False


# Retry backoff delays: 30s, 2min, 10min
RETRY_DELAYS_SECONDS = [30, 120, 600]


class RecoverySummary(int):
    """Integer total of recovered items that also provides dictionary-like access."""
    def __new__(cls, recipients: int, drafts: int):
        obj = super().__new__(cls, recipients + drafts)
        obj.stranded_recipients = recipients
        obj.stranded_drafts = drafts
        return obj

    def get(self, key, default=None):
        if key == "stranded_recipients": return self.stranded_recipients
        if key == "stranded_drafts": return self.stranded_drafts
        return default

    def __getitem__(self, key):
        if key == "stranded_recipients": return self.stranded_recipients
        if key == "stranded_drafts": return self.stranded_drafts
        raise KeyError(key)


def recover_stranded_sending() -> RecoverySummary:
    """
    On server startup, identify contacts left in 'sending' and drafts in 'approved'/'sending'
    due to an unexpected crash or restart, and mark them for manual review so they are
    never automatically re-sent.
    """
    conn = db.get_db_connection()
    cursor = conn.cursor()
    with conn:
        cursor.execute(
            """
            UPDATE campaign_recipients
            SET status = 'manual_review',
                error = 'Interrupted: Server crashed or restarted while sending. Flagged for manual review.'
            WHERE status = 'sending'
            """
        )
        recipients_count = cursor.rowcount

        cursor.execute(
            """
            UPDATE drafts
            SET status = 'needs_review',
                reason = 'Interrupted: Server crashed or restarted while approved. Flagged for review.'
            WHERE status IN ('approved', 'sending')
            """
        )
        drafts_count = cursor.rowcount

        if recipients_count > 0 or drafts_count > 0:
            db.log_activity(
                conn,
                action="crash_recovery_processed",
                details=f"Crash recovery: Marked {recipients_count} recipient(s) and {drafts_count} draft(s) for manual review.",
            )

    conn.close()
    return RecoverySummary(recipients_count, drafts_count)


def get_stranded_items(user_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieve all contacts and drafts currently in manual review from crash recovery."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute(
            """
            SELECT cr.id, cr.campaign_id, cr.error, c.name, c.email
            FROM campaign_recipients cr
            JOIN contacts c ON cr.contact_id = c.id
            WHERE cr.status = 'manual_review' AND c.user_id = ?
            ORDER BY cr.id DESC
            """,
            (user_id,),
        )
        recipients = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT d.id, d.thread_id, d.contact_email, d.reason, d.created_at
            FROM drafts d
            WHERE d.status = 'needs_review' AND (d.reason LIKE 'Interrupted%' OR d.reason LIKE '%Delivery unknown%')
              AND d.user_id = ?
            ORDER BY d.id DESC
            """,
            (user_id,),
        )
        drafts = [dict(r) for r in cursor.fetchall()]
    else:
        cursor.execute(
            """
            SELECT cr.id, cr.campaign_id, cr.error, c.name, c.email
            FROM campaign_recipients cr
            JOIN contacts c ON cr.contact_id = c.id
            WHERE cr.status = 'manual_review'
            ORDER BY cr.id DESC
            """
        )
        recipients = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT d.id, d.thread_id, d.contact_email, d.reason, d.created_at
            FROM drafts d
            WHERE d.status = 'needs_review' AND (d.reason LIKE 'Interrupted%' OR d.reason LIKE '%Delivery unknown%')
            ORDER BY d.id DESC
            """
        )
        drafts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "stranded_recipients": recipients,
        "stranded_drafts": drafts,
        "total_stranded": len(recipients) + len(drafts),
    }


def retry_failed_recipients(campaign_id: int) -> Dict[str, Any]:
    """
    Re-queue failed contacts for a campaign safely.
    Strictly excludes contacts that are already sent, unsubscribed, or marked failed in contacts table (bounces).
    """
    conn = db.get_db_connection()
    cursor = conn.cursor()
    with conn:
        cursor.execute(
            """
            SELECT cr.id, cr.contact_id, c.email, c.status as contact_status
            FROM campaign_recipients cr
            JOIN contacts c ON cr.contact_id = c.id
            WHERE cr.campaign_id = ?
              AND cr.status = 'failed'
              AND c.status NOT IN ('unsubscribed', 'bounced', 'failed')
            """,
            (campaign_id,),
        )
        eligible = cursor.fetchall()
        requeued_ids = [r["id"] for r in eligible]

        if requeued_ids:
            placeholders = ",".join("?" for _ in requeued_ids)
            cursor.execute(
                f"""
                UPDATE campaign_recipients
                SET status = 'pending', retry_count = 0, next_retry_at = NULL, error = NULL
                WHERE id IN ({placeholders})
                """,
                requeued_ids,
            )
            # If campaign was completed or stopped, reset to paused so user can resume/start
            cursor.execute(
                "UPDATE campaigns SET status = 'paused' WHERE id = ? AND status IN ('completed', 'stopped')",
                (campaign_id,),
            )
            db.log_activity(
                conn,
                action="campaign_retry_failed",
                details=f"Campaign #{campaign_id}: Re-queued {len(requeued_ids)} failed recipient(s).",
            )

    conn.close()
    return {"success": True, "requeued_count": len(requeued_ids)}


def get_daily_send_count(conn: sqlite3.Connection, provider: str, user_id: Optional[int] = None) -> int:
    """Get total emails sent today for a given provider and optional user."""
    today_str = date.today().isoformat()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute(
            "SELECT count FROM daily_sends WHERE provider = ? AND send_date = ? AND user_id = ?",
            (provider.lower(), today_str, user_id),
        )
    else:
        cursor.execute(
            "SELECT SUM(count) FROM daily_sends WHERE provider = ? AND send_date = ?",
            (provider.lower(), today_str),
        )
    row = cursor.fetchone()
    return (row[0] or 0) if row else 0


def increment_daily_send_count(
    conn: sqlite3.Connection,
    provider: str,
    user_id: Optional[int] = None,
    send_type: str = "campaign",
) -> None:
    """Increment today's send count for a given provider and user."""
    if user_id is None:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
        u = cursor.fetchone()
        if u:
            user_id = u[0]
    import limits
    limits.record_send(conn, provider, user_id, send_type)


def populate_campaign_recipients(campaign_id: int) -> int:
    """
    Populate campaign_recipients with eligible contacts.
    Applies group_tag filter if the campaign specified one, and restricts to campaign's user_id.
    """
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT group_tag, user_id FROM campaigns WHERE id = ?", (campaign_id,))
    camp_row = cursor.fetchone()
    if not camp_row:
        conn.close()
        return 0

    group_tag = camp_row["group_tag"]
    user_id = camp_row["user_id"] if "user_id" in camp_row.keys() else None
    now_str = datetime.utcnow().isoformat()

    query = "SELECT id FROM contacts WHERE 1=1"
    params = []
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if group_tag:
        query += " AND group_tag = ?"
        params.append(group_tag)

    cursor.execute(query, tuple(params))
    contact_ids = [row["id"] for row in cursor.fetchall()]

    added = 0
    with conn:
        for cid in contact_ids:
            try:
                conn.execute(
                    """
                    INSERT INTO campaign_recipients (campaign_id, contact_id, status, created_at)
                    VALUES (?, ?, 'pending', ?)
                    """,
                    (campaign_id, cid, now_str),
                )
                added += 1
            except sqlite3.IntegrityError:
                pass  # Already queued

    conn.close()
    return added


def get_campaign_multi_day_plan(campaign_id: int) -> Dict[str, Any]:
    """Calculate multi-day sending plan for a campaign based on user's sending limits."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM campaigns WHERE id = ?", (campaign_id,))
    camp_row = cursor.fetchone()
    if not camp_row:
        conn.close()
        return {"days_needed": 0, "finish_date": date.today().isoformat(), "is_multi_day": False}

    user_id = camp_row["user_id"] if "user_id" in camp_row.keys() else None
    cursor.execute(
        "SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'pending'",
        (campaign_id,),
    )
    pending_count = cursor.fetchone()[0]

    import limits
    user_row = None
    if user_id:
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()

    if not user_row:
        user_row = {"daily_cap": 400, "warmup_enabled": 1, "warmup_day": 1, "email": "user@gmail.com"}

    limits_status = limits.get_user_limits_status(conn, user_row)
    plan = limits.calculate_multi_day_plan(
        remaining_recipients=pending_count,
        campaign_cap_per_day=limits_status["campaign_cap"],
        remaining_campaign_today=limits_status["remaining_campaign"],
    )
    plan["pending_count"] = pending_count
    plan["limits_status"] = limits_status
    conn.close()
    return plan


def preview_campaign(campaign_id: int, limit: int = 5) -> Dict[str, Any]:
    """
    Render preview of the first N mails and report skipped contacts with reasons.
    Does not modify database records.
    """
    populate_campaign_recipients(campaign_id)
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT subject, mode, template FROM campaigns WHERE id = ?", (campaign_id,))
    camp = cursor.fetchone()
    if not camp:
        conn.close()
        raise ValueError(f"Campaign {campaign_id} not found.")

    cursor.execute(
        """
        SELECT cr.id as recipient_id, c.id as contact_id, c.email, c.name, c.extra, c.status as contact_status
        FROM campaign_recipients cr
        JOIN contacts c ON cr.contact_id = c.id
        WHERE cr.campaign_id = ?
        ORDER BY cr.id ASC
        """,
        (campaign_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    rendered_list = []
    skipped_list = []

    for r in rows:
        cid = r["contact_id"]
        cname = r["name"]
        cemail = r["email"]
        cstatus = r["contact_status"]
        extra = json.loads(r["extra"]) if r["extra"] else {}

        if cstatus == "unsubscribed":
            skipped_list.append({"contact_id": cid, "name": cname, "email": cemail, "reason": "Contact is unsubscribed"})
            continue

        body, reason = render_email_body(camp["mode"], camp["template"], cname, extra)
        if reason:
            skipped_list.append({"contact_id": cid, "name": cname, "email": cemail, "reason": reason})
        else:
            if len(rendered_list) < limit:
                rendered_list.append({
                    "contact_id": cid,
                    "name": cname,
                    "email": cemail,
                    "subject": camp["subject"],
                    "body": body,
                })

    return {
        "campaign_id": campaign_id,
        "total_contacts": len(rows),
        "rendered": rendered_list,
        "skipped": skipped_list,
        "skipped_count": len(skipped_list),
        "eligible_preview_count": len(rendered_list),
    }


def send_test_email(
    campaign_id: int,
    test_email: str,
    sender_override: Optional[BaseEmailSender] = None,
    user_id: Optional[int] = None,
    sender_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send up to 3 sample personalized mails to test_email without changing contact statuses.
    """
    if not config.is_valid_email(test_email):
        raise ValueError("Provided test email address is invalid.")
    if config.TEST_MODE and not config.is_test_email_valid():
        raise ValueError("Test mode is enabled but TEST_EMAIL is not configured with a valid email address. Configure a valid test email in Settings before sending.")

    populate_campaign_recipients(campaign_id)
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT subject, mode, template, provider, user_id FROM campaigns WHERE id = ?", (campaign_id,))
    camp = cursor.fetchone()
    if not camp:
        conn.close()
        raise ValueError(f"Campaign {campaign_id} not found.")

    eff_user_id = user_id or (camp["user_id"] if "user_id" in camp.keys() else None)
    if not sender_email and eff_user_id:
        cursor.execute("SELECT email FROM users WHERE id = ?", (eff_user_id,))
        u = cursor.fetchone()
        if u:
            sender_email = u["email"]

    cursor.execute(
        """
        SELECT c.id as contact_id, c.email, c.name, c.extra, c.status as contact_status
        FROM campaign_recipients cr
        JOIN contacts c ON cr.contact_id = c.id
        WHERE cr.campaign_id = ? AND c.status != 'unsubscribed'
        ORDER BY cr.id ASC
        LIMIT 3
        """,
        (campaign_id,),
    )
    sample_rows = cursor.fetchall()
    conn.close()

    if not sample_rows:
        # Fallback to test_email as sample recipient so test-send always works even before uploading CSV
        sample_rows = [{
            "contact_id": 0,
            "email": test_email,
            "name": test_email.split("@")[0].replace(".", " ").title(),
            "extra": json.dumps({"company": "Sample Corp", "role": "Preview Tester"}),
            "contact_status": "pending",
        }]

    sender = sender_override or get_sender(camp["provider"], test_mode=True, user_id=eff_user_id, sender_email=sender_email)
    results = []

    for r in sample_rows:
        extra = json.loads(r["extra"]) if r["extra"] else {}
        body, reason = render_email_body(camp["mode"], camp["template"], r["name"], extra)
        if reason:
            continue

        subject = f"[TEST SAMPLE for {r['name']}] {camp['subject']}"
        res = sender.send_email(test_email, subject, body)
        results.append({
            "for_contact": r["name"],
            "original_email": r["email"],
            "sent_to": test_email,
            "success": res.success,
            "error": res.error,
        })

    success_count = sum(1 for s in results if s["success"])
    all_failed = len(results) > 0 and success_count == 0
    first_error = next((s["error"] for s in results if s.get("error")), "Failed to dispatch test email.")

    return {
        "success": not all_failed and len(results) > 0,
        "sent_count": success_count,
        "test_email": test_email,
        "samples": results,
        "message": first_error if all_failed else f"Dispatched {success_count} sample(s) to {test_email}",
    }


def _worker_loop(campaign_id: int, sender: BaseEmailSender, ctrl: CampaignControl) -> None:
    """Internal thread loop processing queued recipients one by one."""
    conn = db.get_db_connection()

    try:
        # Load campaign details
        cursor = conn.cursor()
        cursor.execute("SELECT subject, mode, template, provider, user_id FROM campaigns WHERE id = ?", (campaign_id,))
        camp = cursor.fetchone()
        if not camp:
            return

        subject = camp["subject"]
        mode = camp["mode"]
        template = camp["template"]
        provider = camp["provider"]
        user_id = camp["user_id"] if "user_id" in camp.keys() else None
        daily_cap = sender.get_daily_cap()

        import limits
        user_row = None
        if user_id:
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user_row = cursor.fetchone()

        while not ctrl.stop_event.is_set():
            # Respect campaign pause
            ctrl.pause_event.wait()
            if ctrl.stop_event.is_set():
                break

            # Respect global sending pause
            while is_global_sending_paused() and not ctrl.stop_event.is_set():
                time.sleep(0.5)

            if ctrl.stop_event.is_set():
                break

            # Check daily sending cap & limit-aware multi-day rules
            if user_row:
                limits_status = limits.get_user_limits_status(conn, user_row)
                if limits_status["quota_exhausted"] or limits_status["remaining_campaign"] <= 0:
                    with conn:
                        conn.execute(
                            "UPDATE campaign_recipients SET status = 'scheduled_next_day' WHERE campaign_id = ? AND status = 'pending'",
                            (campaign_id,),
                        )
                        conn.execute(
                            "UPDATE campaigns SET status = 'paused' WHERE id = ?",
                            (campaign_id,),
                        )
                    db.log_activity(
                        conn,
                        action="campaign_paused_limit_reached",
                        details=f"Campaign #{campaign_id} paused: daily campaign cap reached. Remaining {limits_status['remaining_reply']} sends reserved for replies. Resumes at next send window.",
                        user_id=user_id,
                    )
                    break
            else:
                sent_today = get_daily_send_count(conn, provider)
                if sent_today >= daily_cap:
                    with conn:
                        conn.execute(
                            "UPDATE campaign_recipients SET status = 'scheduled_next_day' WHERE campaign_id = ? AND status = 'pending'",
                            (campaign_id,),
                        )
                        conn.execute(
                            "UPDATE campaigns SET status = 'paused' WHERE id = ?",
                            (campaign_id,),
                        )
                    break

            # Fetch next pending recipient ready for delivery
            now_iso = datetime.utcnow().isoformat()
            cursor.execute(
                """
                SELECT cr.id as recipient_id, cr.retry_count, c.id as contact_id, c.email, c.name, c.extra, c.status as contact_status
                FROM campaign_recipients cr
                JOIN contacts c ON cr.contact_id = c.id
                WHERE cr.campaign_id = ?
                  AND cr.status = 'pending'
                  AND (cr.next_retry_at IS NULL OR cr.next_retry_at <= ?)
                ORDER BY cr.id ASC
                LIMIT 1
                """,
                (campaign_id, now_iso),
            )
            item = cursor.fetchone()

            if not item:
                # Check if there are recipients still waiting on future retry timers
                cursor.execute(
                    "SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ? AND status = 'pending'",
                    (campaign_id,),
                )
                pending_waiting = cursor.fetchone()[0]
                if pending_waiting > 0:
                    time.sleep(1.0)
                    continue

                # All recipients processed!
                with conn:
                    conn.execute("UPDATE campaigns SET status = 'completed' WHERE id = ?", (campaign_id,))
                break

            recipient_id = item["recipient_id"]
            retry_count = item["retry_count"] or 0
            contact_name = item["name"]
            contact_email = item["email"]
            contact_status = item["contact_status"]
            extra = json.loads(item["extra"]) if item["extra"] else {}
            now_str = datetime.utcnow().isoformat()

            # Rule: Always skip unsubscribed contacts
            if contact_status == "unsubscribed":
                with conn:
                    conn.execute(
                        """
                        UPDATE campaign_recipients
                        SET status = 'skipped', error = 'Contact is unsubscribed'
                        WHERE id = ?
                        """,
                        (recipient_id,),
                    )
                continue

            # Render template
            body, skip_reason = render_email_body(mode, template, contact_name, extra)
            if skip_reason:
                with conn:
                    conn.execute(
                        """
                        UPDATE campaign_recipients
                        SET status = 'skipped', error = ?
                        WHERE id = ?
                        """,
                        (skip_reason, recipient_id),
                    )
                continue

            # RULE: Mark recipient 'sending' BEFORE dispatching
            with conn:
                conn.execute(
                    "UPDATE campaign_recipients SET status = 'sending' WHERE id = ?",
                    (recipient_id,),
                )

            # Dispatch mail
            result = sender.send_email(contact_email, subject, body)

            if result.success:
                with conn:
                    conn.execute(
                        """
                        UPDATE campaign_recipients
                        SET status = 'sent', sent_at = ?, message_id = ?, thread_id = ?, rendered_body = ?
                        WHERE id = ?
                        """,
                        (now_str, result.message_id, result.thread_id, body, recipient_id),
                    )
                    db.log_activity(
                        conn,
                        action="campaign_mail_sent",
                        contact_email=contact_email,
                        details=f"Campaign #{campaign_id} sent email to {contact_email}. Subject: '{subject}'",
                        user_id=user_id,
                    )
                increment_daily_send_count(conn, provider, user_id=user_id, send_type="campaign")
            else:
                error_str = result.error or "Unknown delivery error"

                # If Gmail returns quota / rate-limit error: stop for today, keep remaining contacts pending
                if getattr(result, "is_quota_error", False):
                    tomorrow_iso = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
                    if user_id:
                        with conn:
                            conn.execute("UPDATE users SET quota_exhausted_until = ? WHERE id = ?", (tomorrow_iso, user_id))
                    # Reset current recipient back to pending so it is not marked failed
                    with conn:
                        conn.execute("UPDATE campaign_recipients SET status = 'pending' WHERE id = ?", (recipient_id,))
                        conn.execute("UPDATE campaigns SET status = 'paused' WHERE id = ?", (campaign_id,))
                    db.log_activity(
                        conn,
                        action="gmail_quota_exceeded",
                        contact_email=contact_email,
                        details=f"Campaign #{campaign_id}: Gmail daily sending quota or rate limit reached ({error_str}). Pausing campaign until next send window. Recipients remain pending.",
                        user_id=user_id,
                    )
                    break

                # Check if Gmail authorization expired or was revoked
                if is_gmail_auth_error(error_str):
                    if user_id:
                        with conn:
                            conn.execute("UPDATE users SET gmail_auth_expired = 1 WHERE id = ?", (user_id,))
                    set_gmail_auth_expired(True)
                    set_global_sending_paused(True)
                    db.log_activity(
                        conn,
                        action="gmail_auth_expired",
                        details="Gmail authorization expired or revoked during campaign dispatch. Paused all sending.",
                        user_id=user_id,
                    )

                # Retry up to 3 times ONLY for temporary errors
                if is_uncertain_error(error_str):
                    uncertain_note = "Delivery unknown. Check your Gmail Sent folder before sending again."
                    reason = f"{error_str}. {uncertain_note}" if "Delivery unknown" not in error_str else error_str
                    with conn:
                        conn.execute(
                            """
                            UPDATE campaign_recipients
                            SET status = 'manual_review', error = ?, next_retry_at = NULL
                            WHERE id = ?
                            """,
                            (reason, recipient_id),
                        )
                        db.log_activity(
                            conn,
                            action="campaign_mail_uncertain",
                            contact_email=contact_email,
                            details=f"Campaign #{campaign_id}: Delivery uncertain for {contact_email} ({error_str}). Flagged for manual review.",
                            user_id=user_id,
                        )
                elif is_temporary_error(error_str) and retry_count < 3:
                    delay_sec = RETRY_DELAYS_SECONDS[retry_count]
                    next_retry = (datetime.utcnow() + timedelta(seconds=delay_sec)).isoformat()
                    new_retry_count = retry_count + 1
                    with conn:
                        conn.execute(
                            """
                            UPDATE campaign_recipients
                            SET status = 'pending', retry_count = ?, next_retry_at = ?, error = ?
                            WHERE id = ?
                            """,
                            (new_retry_count, next_retry, f"Temporary error: {error_str}", recipient_id),
                        )
                        db.log_activity(
                            conn,
                            action="campaign_mail_retry_scheduled",
                            contact_email=contact_email,
                            details=f"Campaign #{campaign_id}: Temporary error for {contact_email} ({error_str}). Scheduled retry #{new_retry_count} at {next_retry}.",
                        )
                else:
                    # Permanent error or retry cap exceeded
                    final_reason = f"Permanent error: {error_str}" if not is_temporary_error(error_str) else f"Exceeded {retry_count} retries: {error_str}"
                    with conn:
                        conn.execute(
                            """
                            UPDATE campaign_recipients
                            SET status = 'failed', error = ?
                            WHERE id = ?
                            """,
                            (final_reason, recipient_id),
                        )
                        db.log_activity(
                            conn,
                            action="campaign_mail_failed",
                            contact_email=contact_email,
                            details=f"Campaign #{campaign_id} failed sending to {contact_email}: {final_reason}",
                        )

            # Throttle delay between sends
            pause_time = config.PAUSE_SECONDS
            while pause_time > 0 and not ctrl.stop_event.is_set():
                sleep_chunk = min(0.5, pause_time)
                time.sleep(sleep_chunk)
                pause_time -= sleep_chunk

    finally:
        conn.close()
        with REGISTRY_LOCK:
            ACTIVE_CONTROLS.pop(campaign_id, None)
            ACTIVE_THREADS.pop(campaign_id, None)


def start_campaign_queue(
    campaign_id: int,
    sender_override: Optional[BaseEmailSender] = None,
) -> bool:
    """Start background queue worker for the specified campaign."""
    if config.TEST_MODE and not config.is_test_email_valid():
        raise ValueError("Test mode is enabled but TEST_EMAIL is not configured with a valid email address. Configure a valid test email in Settings before sending.")

    populate_campaign_recipients(campaign_id)

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, provider, user_id FROM campaigns WHERE id = ?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    provider = row["provider"]
    user_id = row["user_id"] if "user_id" in row.keys() else None
    sender_email = None
    if user_id:
        cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
        u = cursor.fetchone()
        if u:
            sender_email = u["email"]

    sender = sender_override or get_sender(provider=provider, user_id=user_id, sender_email=sender_email)

    with conn:
        conn.execute("UPDATE campaign_recipients SET status = 'pending' WHERE campaign_id = ? AND status = 'scheduled_next_day'", (campaign_id,))
        conn.execute("UPDATE campaigns SET status = 'running' WHERE id = ?", (campaign_id,))
    conn.close()

    with REGISTRY_LOCK:
        if campaign_id in ACTIVE_THREADS and ACTIVE_THREADS[campaign_id].is_alive():
            return True  # Already running

        ctrl = CampaignControl()
        ACTIVE_CONTROLS[campaign_id] = ctrl
        thread = threading.Thread(
            target=_worker_loop,
            args=(campaign_id, sender, ctrl),
            daemon=True,
            name=f"campaign-worker-{campaign_id}",
        )
        ACTIVE_THREADS[campaign_id] = thread
        thread.start()

    return True


def pause_campaign_queue(campaign_id: int) -> bool:
    """Pause sending worker for the specified campaign."""
    with REGISTRY_LOCK:
        ctrl = ACTIVE_CONTROLS.get(campaign_id)
        if ctrl:
            ctrl.pause_event.clear()

    conn = db.get_db_connection()
    with conn:
        conn.execute("UPDATE campaigns SET status = 'paused' WHERE id = ?", (campaign_id,))
    conn.close()
    return True


def resume_campaign_queue(
    campaign_id: int,
    sender_override: Optional[BaseEmailSender] = None,
) -> bool:
    """Resume a paused campaign queue worker."""
    with REGISTRY_LOCK:
        ctrl = ACTIVE_CONTROLS.get(campaign_id)
        if ctrl and ACTIVE_THREADS.get(campaign_id, None) and ACTIVE_THREADS[campaign_id].is_alive():
            ctrl.pause_event.set()
            conn = db.get_db_connection()
            with conn:
                conn.execute("UPDATE campaigns SET status = 'running' WHERE id = ?", (campaign_id,))
            conn.close()
            return True

    # Thread ended or not active, re-start
    return start_campaign_queue(campaign_id, sender_override)


def stop_campaign_queue(campaign_id: int) -> bool:
    """Stop sending worker for the specified campaign."""
    with REGISTRY_LOCK:
        ctrl = ACTIVE_CONTROLS.get(campaign_id)
        if ctrl:
            ctrl.stop_event.set()
            ctrl.pause_event.set()

    conn = db.get_db_connection()
    with conn:
        conn.execute("UPDATE campaigns SET status = 'stopped' WHERE id = ?", (campaign_id,))
    conn.close()
    return True


def get_campaign_progress(campaign_id: int) -> Dict[str, Any]:
    """Retrieve counts by status and the 20 most recent recipient records."""
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT status, provider FROM campaigns WHERE id = ?", (campaign_id,))
    camp = cursor.fetchone()
    if not camp:
        conn.close()
        raise ValueError(f"Campaign {campaign_id} not found.")

    # Status counts
    cursor.execute(
        """
        SELECT status, COUNT(*)
        FROM campaign_recipients
        WHERE campaign_id = ?
        GROUP BY status
        """,
        (campaign_id,),
    )
    counts = dict(cursor.fetchall())

    # Total recipients
    cursor.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ?", (campaign_id,))
    total = cursor.fetchone()[0]

    # Latest 20 results
    cursor.execute(
        """
        SELECT cr.id, cr.status, cr.sent_at, cr.error, cr.message_id, c.name, c.email
        FROM campaign_recipients cr
        JOIN contacts c ON cr.contact_id = c.id
        WHERE cr.campaign_id = ?
        ORDER BY cr.id DESC
        LIMIT 20
        """,
        (campaign_id,),
    )
    recent = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "campaign_id": campaign_id,
        "campaign_status": camp["status"],
        "provider": camp["provider"],
        "total": total,
        "pending": counts.get("pending", 0) + counts.get("scheduled_next_day", 0),
        "scheduled_next_day": counts.get("scheduled_next_day", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "manual_review": counts.get("manual_review", 0),
        "recent_results": recent,
    }
