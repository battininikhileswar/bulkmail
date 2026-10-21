"""Autopilot engine: scheduled follow-ups and event reminders with strict safety guardrails."""

from datetime import datetime, date, time as dt_time
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import config
import db
import email_sender
import queue_worker
import templating

logger = logging.getLogger("mail_agent.autopilot")

_AUTOPILOT_THREAD: Optional[threading.Thread] = None
_AUTOPILOT_STOP_EVENT = threading.Event()
_AUTOPILOT_LOCK = threading.Lock()


def is_inside_send_window(
    window_start: str = "09:00",
    window_end: str = "18:00",
    current_time_override: Optional[datetime] = None,
) -> bool:
    """Verify whether local time falls within [window_start, window_end]."""
    ref_time = current_time_override or datetime.now()
    cur_t = ref_time.time()
    try:
        sh, sm = map(int, window_start.split(":"))
        eh, em = map(int, window_end.split(":"))
        st = dt_time(sh, sm, 0)
        et = dt_time(eh, em, 59)
        if st <= et:
            return st <= cur_t <= et
        else:  # Overnight window
            return cur_t >= st or cur_t <= et
    except Exception:
        return True


def get_automations(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List all automations with associated campaign metadata."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute(
            """
            SELECT a.*, c.name as campaign_name, c.status as campaign_status
            FROM automations a
            JOIN campaigns c ON a.campaign_id = c.id
            WHERE a.user_id = ?
            ORDER BY a.id DESC
            """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT a.*, c.name as campaign_name, c.status as campaign_status
            FROM automations a
            JOIN campaigns c ON a.campaign_id = c.id
            ORDER BY a.id DESC
            """
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_automation(automation_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single automation by ID."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.*, c.name as campaign_name, c.subject as campaign_subject, c.provider as campaign_provider
        FROM automations a
        JOIN campaigns c ON a.campaign_id = c.id
        WHERE a.id = ?
        """,
        (automation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_automation(data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Create a new automation rule (OFF by default)."""
    campaign_id = data.get("campaign_id")
    auto_type = data.get("type", "followup")
    if auto_type not in ("followup", "event_reminder"):
        raise ValueError("Automation type must be 'followup' or 'event_reminder'.")

    delay_days = max(0, int(data.get("delay_days", 3)))
    # Hard ceiling of 2 for max_followups
    max_followups = min(2, max(1, int(data.get("max_followups", 1))))
    send_window_start = data.get("send_window_start", "09:00")
    send_window_end = data.get("send_window_end", "18:00")
    subject = data.get("subject", "")
    template = data.get("template", "")
    if not template:
        raise ValueError("Automation template is required.")
    scheduled_at = data.get("scheduled_at")
    created_at = datetime.utcnow().isoformat()

    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO automations (
                campaign_id, type, enabled, delay_days, max_followups,
                send_window_start, send_window_end, subject, template,
                scheduled_at, created_at, user_id
            )
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                auto_type,
                delay_days,
                max_followups,
                send_window_start,
                send_window_end,
                subject,
                template,
                scheduled_at,
                created_at,
                user_id,
            ),
        )
        auto_id = cursor.lastrowid
        db.log_activity(
            conn,
            "automation_created",
            details=f"Created {auto_type} automation #{auto_id} for campaign #{campaign_id} (disabled by default)",
            user_id=user_id,
        )
    conn.close()
    return get_automation(auto_id) or {}


def enable_automation(automation_id: int, consent: bool = False) -> Dict[str, Any]:
    """Enable automation upon explicit user consent confirmation."""
    if not consent:
        raise ValueError("Explicit consent confirmation is required to enable an automation.")

    conn = db.get_db_connection()
    with conn:
        conn.execute("UPDATE automations SET enabled = 1 WHERE id = ?", (automation_id,))
        db.log_activity(conn, "automation_enabled", details=f"Enabled automation #{automation_id}")
    conn.close()
    return get_automation(automation_id) or {}


def disable_automation(automation_id: int) -> Dict[str, Any]:
    """Disable an active automation rule."""
    conn = db.get_db_connection()
    with conn:
        conn.execute("UPDATE automations SET enabled = 0 WHERE id = ?", (automation_id,))
        db.log_activity(conn, "automation_disabled", details=f"Disabled automation #{automation_id}")
    conn.close()
    return get_automation(automation_id) or {}


def preview_automation(
    automation_id: int,
    now_override: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Evaluate recipients for an automation and return:
    - eligible: contacts who qualify to be emailed now
    - skipped: contacts who are skipped along with exact reasons
    """
    auto = get_automation(automation_id)
    if not auto:
        raise ValueError(f"Automation {automation_id} not found.")

    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT cr.id as recipient_id, cr.campaign_id, cr.contact_id, cr.status as recipient_status,
               cr.thread_id, cr.message_id, cr.sent_at, cr.error, cr.followup_count, cr.last_followup_at,
               c.name as contact_name, c.email as contact_email, c.status as contact_status,
               c.extra_data
        FROM campaign_recipients cr
        JOIN contacts c ON cr.contact_id = c.id
        WHERE cr.campaign_id = ?
        ORDER BY cr.id ASC
        """,
        (auto["campaign_id"],),
    )
    recipients = [dict(r) for r in cursor.fetchall()]

    # Fetch all incoming messages for thread/email checking
    cursor.execute("SELECT thread_id, contact_email, category FROM messages WHERE direction = 'incoming'")
    incoming_msgs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    replied_threads = {m["thread_id"] for m in incoming_msgs if m.get("thread_id")}
    replied_emails = {m["contact_email"].lower() for m in incoming_msgs if m.get("contact_email")}

    bounced_threads = {
        m["thread_id"] for m in incoming_msgs if m.get("thread_id") and m.get("category") == "bounce"
    }
    bounced_emails = {
        m["contact_email"].lower() for m in incoming_msgs if m.get("contact_email") and m.get("category") == "bounce"
    }

    now = now_override or datetime.utcnow()
    eligible: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    max_allowed_followups = min(2, max(1, auto.get("max_followups", 1)))
    delay_days = auto.get("delay_days", 3)

    for r in recipients:
        email = r["contact_email"]
        recip_info = {
            "recipient_id": r["recipient_id"],
            "contact_id": r["contact_id"],
            "name": r["contact_name"],
            "email": email,
            "followup_count": r.get("followup_count", 0),
            "sent_at": r.get("sent_at"),
            "extra_data": r.get("extra_data"),
        }

        # 1. Must be sent initial mail
        if r["recipient_status"] != "sent":
            skipped.append({**recip_info, "reason": f"Initial campaign email not sent (status: {r['recipient_status']})"})
            continue

        # 2. Unsubscribed check
        if r["contact_status"] == "unsubscribed":
            skipped.append({**recip_info, "reason": "Contact unsubscribed"})
            continue

        # 3. Bounce check
        if r["thread_id"] in bounced_threads or email.lower() in bounced_emails:
            skipped.append({**recip_info, "reason": "Message bounced"})
            continue

        # 4. Manual review / uncertain check
        if r["recipient_status"] == "manual_review" or (r.get("error") and "Delivery unknown" in r["error"]):
            skipped.append({**recip_info, "reason": "In manual review / uncertain delivery"})
            continue

        # 5. Replied check (both follow-up and reminder skip contacts who replied)
        if r["thread_id"] in replied_threads or email.lower() in replied_emails:
            skipped.append({**recip_info, "reason": "Contact already replied"})
            continue

        # 6. Type-specific checks
        if auto["type"] == "followup":
            # Hard ceiling max_followups
            cur_followups = r.get("followup_count", 0)
            if cur_followups >= max_allowed_followups:
                skipped.append({**recip_info, "reason": f"Max follow-ups reached ({cur_followups}/{max_allowed_followups})"})
                continue

            # Delay days check
            base_time_str = r.get("last_followup_at") or r.get("sent_at")
            if delay_days > 0 and base_time_str:
                try:
                    clean_ts = base_time_str.replace("Z", "+00:00")
                    base_dt = datetime.fromisoformat(clean_ts).replace(tzinfo=None)
                    elapsed_secs = (now - base_dt).total_seconds()
                    required_secs = delay_days * 86400
                    if elapsed_secs < required_secs:
                        hours_left = max(0, round((required_secs - elapsed_secs) / 3600, 1))
                        skipped.append({
                            **recip_info,
                            "reason": f"Delay of {delay_days} day(s) not elapsed ({hours_left}h remaining)",
                        })
                        continue
                except Exception:
                    pass

            eligible.append(recip_info)

        elif auto["type"] == "event_reminder":
            # Reminder only once
            cur_followups = r.get("followup_count", 0)
            if cur_followups >= 1:
                skipped.append({**recip_info, "reason": "Reminder already sent"})
                continue

            # Scheduled time check
            sched_str = auto.get("scheduled_at")
            if sched_str:
                try:
                    clean_sched = sched_str.replace("Z", "+00:00")
                    sched_dt = datetime.fromisoformat(clean_sched).replace(tzinfo=None)
                    if now < sched_dt:
                        skipped.append({
                            **recip_info,
                            "reason": f"Scheduled for {sched_str}",
                        })
                        continue
                except Exception:
                    pass

            eligible.append(recip_info)

    return {
        "automation_id": automation_id,
        "eligible": eligible,
        "skipped": skipped,
        "total_eligible": len(eligible),
        "total_skipped": len(skipped),
    }


def resume_multi_day_campaigns(
    now_override: Optional[datetime] = None,
    send_window_override: Optional[bool] = None,
) -> List[int]:
    """
    Check for paused multi-day campaigns with scheduled_next_day contacts.
    If local time falls within the send window and user daily limit allows, resumes automatically.
    Recipients already sent are preserved and never double-sent.
    """
    if queue_worker.is_global_sending_paused():
        return []

    now = now_override or datetime.now()
    in_window = (
        send_window_override
        if send_window_override is not None
        else is_inside_send_window("09:00", "18:00", current_time_override=now)
    )
    if not in_window:
        return []

    conn = db.get_db_connection()
    resumed = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT c.id, c.user_id, c.name
            FROM campaigns c
            JOIN campaign_recipients cr ON c.id = cr.campaign_id
            WHERE c.status = 'paused' AND cr.status = 'scheduled_next_day'
            """
        )
        candidates = cursor.fetchall()
        import limits
        for row in candidates:
            camp_id = row["id"]
            user_id = row["user_id"] if "user_id" in row.keys() else None
            user_row = None
            if user_id:
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user_row = cursor.fetchone()

            if user_row:
                limits_status = limits.get_user_limits_status(conn, user_row)
                if limits_status["quota_exhausted"] or limits_status["remaining_campaign"] <= 0:
                    continue  # Limit still exhausted for today

            # Resume campaign
            queue_worker.start_campaign_queue(camp_id)
            resumed.append(camp_id)
            db.log_activity(
                conn,
                action="campaign_auto_resumed_next_window",
                details=f"Multi-day campaign #{camp_id} ({row['name']}) resumed automatically at send window.",
                user_id=user_id,
            )
    finally:
        conn.close()

    return resumed


def run_autopilot_cycle(
    now_override: Optional[datetime] = None,
    send_window_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Execute one evaluation and dispatch cycle across enabled automations.
    Enforces quiet hours, daily cap, pause switch, and test mode.
    """
    # 1. Global sending pause switch
    if queue_worker.is_global_sending_paused():
        logger.info("Autopilot skipped: global sending is paused.")
        return {"processed": 0, "status": "paused", "reason": "Global sending is paused."}

    # 2. Test mode safety check
    if config.TEST_MODE and not config.is_test_email_valid():
        logger.warning("Autopilot skipped: test mode is ON but TEST_EMAIL is invalid.")
        return {"processed": 0, "status": "blocked", "reason": "Test mode enabled but TEST_EMAIL is invalid."}

    now = now_override or datetime.utcnow()

    # Check and resume multi-day campaigns at send window
    try:
        resume_multi_day_campaigns(now_override=now, send_window_override=send_window_override)
    except Exception as e:
        logger.error(f"Error checking multi-day campaigns: {e}")

    automations = get_automations()
    active_automations = [a for a in automations if a.get("enabled") == 1]

    if not active_automations:
        return {"processed": 0, "status": "idle", "reason": "No active automations."}

    total_sent = 0
    conn = db.get_db_connection()

    try:
        for a in active_automations:
            auto_id = a["id"]
            # 3. Quiet hours send window check
            in_window = (
                send_window_override
                if send_window_override is not None
                else is_inside_send_window(
                    a.get("send_window_start", "09:00"),
                    a.get("send_window_end", "18:00"),
                    current_time_override=now,
                )
            )

            if not in_window:
                logger.info(f"Autopilot #{auto_id} skipped: outside send window (quiet hours).")
                continue

            preview = preview_automation(auto_id, now_override=now)
            eligible = preview["eligible"]
            if not eligible:
                continue

            # Load campaign details
            cursor = conn.cursor()
            cursor.execute("SELECT name, subject, provider, user_id FROM campaigns WHERE id = ?", (a["campaign_id"],))
            camp = cursor.fetchone()
            if not camp:
                continue

            provider = camp["provider"]
            camp_uid = camp["user_id"] if "user_id" in camp.keys() else None
            user_id = a.get("user_id") or camp_uid
            sender_email = None
            user_row = None
            if user_id:
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row:
                    sender_email = user_row["email"]

            sender_instance = email_sender.get_sender(
                provider=provider,
                test_mode=config.TEST_MODE,
                user_id=user_id,
                sender_email=sender_email,
            )

            for recip in eligible:
                # 4. Daily cap check
                if not config.TEST_MODE:
                    import limits
                    if user_row:
                        l_status = limits.get_user_limits_status(conn, user_row)
                        if l_status["quota_exhausted"] or l_status["remaining_campaign"] <= 0:
                            logger.warning(f"Autopilot user #{user_id} reached campaign daily cap.")
                            db.log_activity(
                                conn,
                                "autopilot_daily_cap_reached",
                                details=f"Automation #{auto_id} stopped: user daily campaign cap reached.",
                                user_id=user_id,
                            )
                            return {"processed": total_sent, "status": "daily_cap_reached"}
                    else:
                        current_count = queue_worker.get_daily_send_count(conn, provider)
                        if current_count >= config.DAILY_CAP:
                            logger.warning(f"Autopilot reached daily cap ({config.DAILY_CAP}) for {provider}.")
                            db.log_activity(
                                conn,
                                "autopilot_daily_cap_reached",
                                details=f"Automation #{auto_id} stopped: daily cap reached.",
                            )
                            return {"processed": total_sent, "status": "daily_cap_reached"}

                # 5. Mark sending first (crash-safe)
                r_id = recip["recipient_id"]
                with conn:
                    conn.execute("UPDATE campaign_recipients SET status = 'sending' WHERE id = ?", (r_id,))

                # 6. Format email
                target_email = config.TEST_EMAIL if config.TEST_MODE else recip["email"]
                raw_subject = a.get("subject") or (
                    f"Re: {camp['subject']}" if a["type"] == "followup" else camp["subject"]
                )
                subject = f"[TEST] {raw_subject}" if config.TEST_MODE and not raw_subject.startswith("[TEST]") else raw_subject

                # Render template variables
                extra_dict = {}
                if recip.get("extra_data"):
                    try:
                        extra_dict = json.loads(recip["extra_data"])
                    except Exception:
                        pass

                raw_body = a["template"].replace("{name}", recip["name"] or "there")
                for k, v in extra_dict.items():
                    raw_body = raw_body.replace(f"{{{k}}}", str(v))

                final_body = templating.append_footer(raw_body)

                # Fetch thread/message IDs for reply headers
                cursor.execute(
                    "SELECT thread_id, message_id FROM campaign_recipients WHERE id = ?",
                    (r_id,),
                )
                header_row = cursor.fetchone()
                thread_id = header_row["thread_id"] if header_row else None
                in_reply_to = header_row["message_id"] if header_row else None

                # 7. Dispatch
                try:
                    result = sender_instance.send_email(
                        to_email=target_email,
                        subject=subject,
                        body=final_body,
                        thread_id=thread_id,
                        in_reply_to=in_reply_to,
                    )

                    now_str = now.isoformat()
                    with conn:
                        conn.execute(
                            """
                            UPDATE campaign_recipients
                            SET status = 'sent',
                                followup_count = followup_count + 1,
                                last_followup_at = ?
                            WHERE id = ?
                            """,
                            (now_str, r_id),
                        )
                        if not config.TEST_MODE:
                            queue_worker.increment_daily_send_count(conn, provider, user_id=user_id, send_type="campaign")

                        # Record outgoing message in messages table
                        msg_id = result.get("message_id") if isinstance(result, dict) else f"auto-{r_id}-{now_str}"
                        conn.execute(
                            """
                            INSERT INTO messages (
                                gmail_message_id, thread_id, contact_email, direction,
                                subject, body_text, received_at, category, processed, user_id
                            )
                            VALUES (?, ?, ?, 'outgoing', ?, ?, ?, 'automation', 1, ?)
                            """,
                            (
                                msg_id or f"auto-{r_id}-{now_str}",
                                thread_id or f"thd-{r_id}",
                                recip["email"],
                                subject,
                                final_body,
                                now_str,
                                user_id,
                            ),
                        )

                        db.log_activity(
                            conn,
                            "autopilot_sent",
                            contact_email=recip["email"],
                            details=f"Automation #{auto_id} ({a['type']}) sent to {target_email} ({'TEST MODE' if config.TEST_MODE else 'live'}).",
                            user_id=user_id,
                        )

                    total_sent += 1

                except Exception as send_err:
                    err_msg = str(send_err)
                    now_str = now.isoformat()

                    with conn:
                        if queue_worker.is_uncertain_error(err_msg):
                            # Mark uncertain as manual_review (NEVER auto-retry)
                            conn.execute(
                                """
                                UPDATE campaign_recipients
                                SET status = 'manual_review',
                                    error = 'Delivery unknown. Check your Gmail Sent folder before sending again.'
                                WHERE id = ?
                                """,
                                (r_id,),
                            )
                            db.log_activity(
                                conn,
                                "autopilot_send_uncertain",
                                contact_email=recip["email"],
                                details=f"Automation #{auto_id} send timed out/uncertain: {err_msg}",
                            )
                        else:
                            conn.execute(
                                """
                                UPDATE campaign_recipients
                                SET status = 'failed',
                                    error = ?
                                WHERE id = ?
                                """,
                                (err_msg, r_id),
                            )
                            db.log_activity(
                                conn,
                                "autopilot_send_failed",
                                contact_email=recip["email"],
                                details=f"Automation #{auto_id} failed: {err_msg}",
                            )

    finally:
        conn.close()

    return {"processed": total_sent, "status": "completed"}


def _autopilot_worker_loop() -> None:
    """Background worker daemon executing autopilot cycles every 60 seconds."""
    logger.info("Autopilot background worker loop started.")
    while not _AUTOPILOT_STOP_EVENT.is_set():
        try:
            run_autopilot_cycle()
        except Exception as e:
            logger.error(f"Unexpected error in autopilot cycle (recovered): {e}")
        # Sleep for 60 seconds or until stopped
        _AUTOPILOT_STOP_EVENT.wait(60.0)
    logger.info("Autopilot background worker loop stopped.")


def start_autopilot() -> None:
    """Start background scheduler thread."""
    global _AUTOPILOT_THREAD
    with _AUTOPILOT_LOCK:
        if _AUTOPILOT_THREAD and _AUTOPILOT_THREAD.is_alive():
            return
        _AUTOPILOT_STOP_EVENT.clear()
        _AUTOPILOT_THREAD = threading.Thread(
            target=_autopilot_worker_loop,
            daemon=True,
            name="AutopilotWorkerThread",
        )
        _AUTOPILOT_THREAD.start()


def stop_autopilot() -> None:
    """Stop background scheduler thread cleanly."""
    global _AUTOPILOT_THREAD
    with _AUTOPILOT_LOCK:
        if _AUTOPILOT_THREAD and _AUTOPILOT_THREAD.is_alive():
            _AUTOPILOT_STOP_EVENT.set()
            _AUTOPILOT_THREAD.join(timeout=3.0)
            _AUTOPILOT_THREAD = None


def is_autopilot_running() -> bool:
    """Check if scheduler thread is running."""
    with _AUTOPILOT_LOCK:
        return _AUTOPILOT_THREAD is not None and _AUTOPILOT_THREAD.is_alive()
