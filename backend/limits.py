"""Limit-aware sending, per-user daily caps, warm-up schedules, reply reserves, and multi-day planning."""

from datetime import date, datetime, timedelta
import math
import sqlite3
from typing import Dict, Any, Optional
import config

WARMUP_SCHEDULE = [50, 100, 200]  # Day 1: 50, Day 2: 100, Day 3: 200, Day 4+: full daily cap


def is_personal_gmail(email: str) -> bool:
    """Return True if email address belongs to standard personal Gmail / Googlemail."""
    if not email or "@" not in email:
        return True
    domain = email.split("@")[1].strip().lower()
    return domain in ("gmail.com", "googlemail.com")


def can_use_smtp(email: str) -> bool:
    """
    SMTP provider option is allowed only when sender's From address is on a custom domain
    (non-@gmail.com, e.g. company domain or domain matching SMTP host) to guarantee proper SPF/DKIM delivery.
    """
    return not is_personal_gmail(email)


def get_default_daily_cap(email: str) -> int:
    """Return default daily sending cap: 400 for personal Gmail, 1500 for Google Workspace / custom domains."""
    return 400 if is_personal_gmail(email) else 1500


def get_user_effective_cap(user_row: Any) -> int:
    """Calculate today's maximum outgoing limit considering warm-up ramp."""
    u_dict = dict(user_row) if user_row else {}
    global_cap = getattr(config, "DAILY_CAP", 400)
    user_cap = u_dict.get("daily_cap") or get_default_daily_cap(u_dict.get("email", ""))
    configured_cap = min(user_cap, global_cap)
    warmup_enabled = bool(u_dict.get("warmup_enabled", 1))
    warmup_day = u_dict.get("warmup_day", 1) or 1

    if warmup_enabled and warmup_day <= len(WARMUP_SCHEDULE):
        warmup_cap = WARMUP_SCHEDULE[warmup_day - 1]
        return min(warmup_cap, configured_cap)
    return configured_cap


def get_user_send_stats_today(conn: sqlite3.Connection, user_id: Optional[int]) -> Dict[str, int]:
    """Return total sends, campaign sends, and reply sends for today."""
    today_str = date.today().isoformat()
    cursor = conn.cursor()

    # In single-user databases (or legacy tests), attribute unassigned sends (0 or NULL) to the primary user
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_id is not None:
        cursor.execute(
            """
            SELECT SUM(count), SUM(campaign_count), SUM(reply_count)
            FROM daily_sends
            WHERE user_id = ? AND send_date = ?
            """,
            (user_id, today_str),
        )
    else:
        cursor.execute(
            """
            SELECT SUM(count), SUM(campaign_count), SUM(reply_count)
            FROM daily_sends
            WHERE send_date = ?
            """,
            (today_str,),
        )
    row = cursor.fetchone()
    total = row[0] or 0 if row else 0
    campaign = row[1] or 0 if row else 0
    reply = row[2] or 0 if row else 0
    return {"total": total, "campaign": campaign, "reply": reply}


def get_user_limits_status(conn: sqlite3.Connection, user_row: Any) -> Dict[str, Any]:
    """Calculate all limits, reserves, and remaining allowances for a user."""
    u_dict = dict(user_row) if user_row else {}
    effective_cap = get_user_effective_cap(u_dict)
    stats = get_user_send_stats_today(conn, u_dict.get("id"))

    # Reserve 10% of daily cap for replies (at least 1, up to 10%)
    reply_reserve = max(1, int(math.ceil(effective_cap * 0.10)))
    campaign_cap = max(0, effective_cap - reply_reserve)

    remaining_total = max(0, effective_cap - stats["total"])
    remaining_campaign = max(0, campaign_cap - stats["campaign"])
    remaining_reply = remaining_total

    today_str = date.today().isoformat()
    quota_exhausted_until = u_dict.get("quota_exhausted_until")
    is_quota_exhausted = bool(quota_exhausted_until and quota_exhausted_until >= today_str)

    return {
        "daily_cap": u_dict.get("daily_cap", 400),
        "effective_cap": effective_cap,
        "warmup_enabled": bool(u_dict.get("warmup_enabled", 1)),
        "warmup_day": u_dict.get("warmup_day", 1),
        "reply_reserve": reply_reserve,
        "campaign_cap": campaign_cap,
        "sent_today": stats["total"],
        "campaign_sent_today": stats["campaign"],
        "reply_sent_today": stats["reply"],
        "remaining_today": remaining_total,
        "remaining_campaign": remaining_campaign,
        "remaining_reply": remaining_reply,
        "is_workspace": not is_personal_gmail(u_dict.get("email", "")),
        "can_use_smtp": can_use_smtp(u_dict.get("email", "")),
        "quota_exhausted": is_quota_exhausted,
    }


def record_send(
    conn: sqlite3.Connection,
    provider: Any = "gmail",
    user_id: Optional[int] = None,
    send_type: str = "campaign",
    is_campaign: Optional[bool] = None,
    **kwargs: Any,
) -> None:
    """Record an outgoing send for a user and increment warm-up day if advancing to a new day."""
    if isinstance(provider, int):
        user_id = provider
        provider = kwargs.get("provider", "gmail")
    elif not isinstance(provider, str):
        provider = "gmail"

    if is_campaign is not None:
        send_type = "campaign" if is_campaign else "reply"

    today_str = date.today().isoformat()
    is_camp = 1 if send_type == "campaign" else 0
    is_rep = 1 if send_type == "reply" else 0

    eff_user_id = user_id if user_id is not None else 0
    with conn:
        conn.execute(
            """
            INSERT INTO daily_sends (provider, send_date, user_id, count, campaign_count, reply_count)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(provider, send_date, user_id) DO UPDATE SET
                count = count + 1,
                campaign_count = campaign_count + excluded.campaign_count,
                reply_count = reply_count + excluded.reply_count
            """,
            (provider.lower(), today_str, eff_user_id, is_camp, is_rep),
        )

        # Update warm-up progress if new day
        if user_id is not None:
            cursor = conn.cursor()
            cursor.execute("SELECT warmup_enabled, warmup_day, last_warmup_date FROM users WHERE id = ?", (user_id,))
            u = cursor.fetchone()
            if u and u["warmup_enabled"]:
                last_date = u["last_warmup_date"]
                if last_date != today_str:
                    new_day = (u["warmup_day"] or 1) + (1 if last_date else 0)
                    conn.execute(
                        "UPDATE users SET warmup_day = ?, last_warmup_date = ? WHERE id = ?",
                        (new_day, today_str, user_id),
                    )


def calculate_multi_day_plan(
    remaining_recipients: int,
    campaign_cap_per_day: int,
    remaining_campaign_today: int,
    window_start: str = "09:00",
) -> Dict[str, Any]:
    """Plan campaign dispatch across days based on sending limit."""
    if remaining_recipients <= 0:
        return {
            "days_needed": 0,
            "finish_date": date.today().isoformat(),
            "is_multi_day": False,
            "can_send_today": 0,
            "contacts_per_day": campaign_cap_per_day,
            "batches": [],
            "summary_text": "No pending contacts to send.",
        }

    if campaign_cap_per_day <= 0:
        campaign_cap_per_day = 360  # standard fallback

    can_send_today = min(remaining_recipients, max(0, remaining_campaign_today))
    leftover = remaining_recipients - can_send_today

    batches = []
    if can_send_today > 0:
        batches.append(can_send_today)
    elif leftover > 0:
        batches.append(0)

    rem = leftover
    while rem > 0:
        b = min(rem, campaign_cap_per_day)
        batches.append(b)
        rem -= b

    total_days = len(batches) if batches else 1
    additional_days = max(0, total_days - 1)
    finish_date = (date.today() + timedelta(days=additional_days)).isoformat()
    is_multi_day = total_days > 1

    batch_parts = [f"Day {i+1}: {b}" for i, b in enumerate(batches)]
    batch_str = ", ".join(batch_parts)
    summary_text = (
        f"Campaign has {remaining_recipients} contacts. With today's remaining limit ({can_send_today}), "
        f"it will take {total_days} days: {batch_str}. Next batch sends tomorrow at {window_start}."
    ) if is_multi_day else f"All {remaining_recipients} contacts can be sent today within your daily limit ({campaign_cap_per_day}/day)."

    return {
        "days_needed": total_days,
        "finish_date": finish_date,
        "is_multi_day": is_multi_day,
        "can_send_today": can_send_today,
        "leftover_after_today": leftover,
        "contacts_per_day": campaign_cap_per_day,
        "batches": batches,
        "summary_text": summary_text,
    }
