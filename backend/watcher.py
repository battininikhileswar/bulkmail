"""Reply watcher module: polls Gmail for thread replies, categorizes them, handles unsubscribes and bounces."""

import base64
from datetime import datetime
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import config
import db
import email_sender
import classifier
import responder
import queue_worker

logger = logging.getLogger("mail_agent.watcher")

UNSUB_PATTERNS = ["unsubscribe", "stop emailing", "remove me", "do not email", "opt out"]

# Watcher thread state
_WATCHER_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()
_WATCHER_LOCK = threading.Lock()

_WATCHER_STATUS = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "messages_seen": 0,
}

_GMAIL_CLIENT_OVERRIDE = None


def set_gmail_client_override(client: Any) -> None:
    """Allow test suites to inject a mock Gmail client."""
    global _GMAIL_CLIENT_OVERRIDE
    _GMAIL_CLIENT_OVERRIDE = client


def get_watcher_status() -> Dict[str, Any]:
    """Return live status of the reply watcher."""
    return dict(_WATCHER_STATUS)


def extract_email(from_header: str) -> str:
    """Extract clean lowercase email address from a 'From' header string."""
    if not from_header:
        return ""
    bracket_match = re.search(r"<([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>", from_header)
    if bracket_match:
        return bracket_match.group(1).lower().strip()
    raw_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", from_header)
    if raw_match:
        return raw_match.group(1).lower().strip()
    return from_header.lower().strip()


def strip_quoted_text(body: str) -> str:
    """Remove quoted reply lines, 'On ... wrote:' headers, and signatures."""
    if not body:
        return ""
    lines = body.splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        # Stop at 'On <date>, <someone> wrote:' or '---------- Forwarded message ---------'
        if re.match(r"^On\s+.*,\s+.*wrote:", stripped, re.IGNORECASE):
            break
        if re.match(r"^-+\s*Original Message\s*-+", stripped, re.IGNORECASE):
            break
        if re.match(r"^From:\s+.*", stripped, re.IGNORECASE):
            break
        # Skip lines starting with quote symbol >
        if stripped.startswith(">"):
            continue
        clean_lines.append(line)

    text = "\n".join(clean_lines).strip()
    # Remove standard signature separator
    sig_split = re.split(r"\n--\s*\n", text)
    if sig_split:
        text = sig_split[0].strip()
    return text


def parse_message_payload(payload: Dict[str, Any]) -> str:
    """Recursively extract plain-text body from a Gmail message payload (with HTML fallback)."""
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    # Case 1: Direct text/plain body
    if mime_type == "text/plain" and "data" in payload.get("body", {}):
        raw = payload["body"]["data"]
        return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")

    # Case 2: Inspect parts
    plain_text = ""
    html_text = ""

    if parts:
        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain" and "data" in part.get("body", {}):
                raw = part["body"]["data"]
                return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")
            elif part_mime == "text/html" and "data" in part.get("body", {}):
                raw = part["body"]["data"]
                html_text = base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")
            elif "parts" in part:
                nested = parse_message_payload(part)
                if nested:
                    return nested

    if html_text:
        # Strip HTML tags
        clean_html = re.sub(r"<[^>]+>", " ", html_text)
        return re.sub(r"\s+", " ", clean_html).strip()

    # Fallback to direct payload body data
    if "data" in payload.get("body", {}):
        raw = payload["body"]["data"]
        decoded = base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", decoded).strip()

    return ""


def is_auto_reply(headers: Dict[str, str], subject: str) -> bool:
    """Detect automated out-of-office and machine replies."""
    auto_sub = headers.get("auto-submitted", "").lower()
    if auto_sub and auto_sub != "no":
        return True
    prec = headers.get("precedence", "").lower()
    if any(p in prec for p in ["bulk", "auto_reply", "junk"]):
        return True
    if "x-autoreply" in headers or "x-auto-response-suppress" in headers:
        return True
    subj = subject.lower().strip()
    if subj.startswith(("automatic reply", "out of office", "auto:")):
        return True
    return False


def is_bounce(sender_email: str, subject: str) -> bool:
    """Detect non-delivery reports and mailer daemon bounces."""
    sender_clean = sender_email.lower()
    if "mailer-daemon" in sender_clean or "postmaster" in sender_clean:
        return True
    subj = subject.lower()
    if any(b in subj for b in ["delivery status notification", "undeliverable", "mail delivery failed"]):
        return True
    return False


def classify_unsubscribe_intent(body_text: str) -> Tuple[bool, bool]:
    """
    Conservative plain-code unsubscribe detection:
    Returns (is_unsub_request, is_ambiguous_review).
    """
    cleaned = body_text.lower().strip()
    words = cleaned.split()
    is_short = len(cleaned) <= 150 or len(words) <= 20

    has_clear_phrase = any(phrase in cleaned for phrase in UNSUB_PATTERNS)

    if has_clear_phrase:
        if is_short:
            return True, False
        else:
            return False, True

    if "stop" in words:
        if is_short:
            return True, False
        else:
            return False, True

    return False, False


def get_tracked_thread_ids(conn, user_id: Optional[int] = None) -> Set[str]:
    """Get all thread IDs from sent campaign messages for tracking replies."""
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute(
            """
            SELECT cr.thread_id
            FROM campaign_recipients cr
            JOIN campaigns c ON cr.campaign_id = c.id
            WHERE cr.thread_id IS NOT NULL AND cr.status = 'sent' AND c.user_id = ?
            UNION
            SELECT thread_id FROM contacts WHERE thread_id IS NOT NULL AND user_id = ?
            """,
            (user_id, user_id),
        )
    else:
        cursor.execute(
            """
            SELECT thread_id FROM campaign_recipients WHERE thread_id IS NOT NULL AND status = 'sent'
            UNION
            SELECT thread_id FROM contacts WHERE thread_id IS NOT NULL
            """
        )
    return {row[0] for row in cursor.fetchall() if row[0]}


def get_original_email_text(conn, thread_id: str, contact_email: Optional[str] = None) -> str:
    """Retrieve rendered body or template of original outgoing email for a thread/contact."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cr.rendered_body, camp.template
        FROM campaign_recipients cr
        JOIN campaigns camp ON cr.campaign_id = camp.id
        LEFT JOIN contacts c ON cr.contact_id = c.id
        WHERE cr.thread_id = ? OR (c.email IS NOT NULL AND LOWER(c.email) = LOWER(?))
        ORDER BY cr.sent_at ASC
        LIMIT 1
        """,
        (thread_id, contact_email or ""),
    )
    row = cursor.fetchone()
    if row:
        return row[0] or row[1] or ""
    return ""


def classify_reply_message(
    conn,
    message_id: int,
    body_text: str,
    thread_id: str,
    contact_email: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Classify a reply message with AI and update database records.
    Catches all errors (missing API key, rate limits) to never crash the watcher.
    """
    try:
        orig_text = get_original_email_text(conn, thread_id, contact_email)
        result = classifier.classify(body_text or "", orig_text)
        intent = result.get("intent", "other")
        summary = result.get("summary", "")

        with conn:
            conn.execute(
                "UPDATE messages SET intent = ?, summary = ? WHERE id = ?",
                (intent, summary, message_id),
            )

            if intent == "unsubscribe" and contact_email:
                conn.execute(
                    "UPDATE contacts SET status = 'unsubscribed' WHERE LOWER(email) = LOWER(?)",
                    (contact_email.strip(),),
                )
                db.log_activity(
                    conn,
                    action="ai_unsubscribe_processed",
                    contact_email=contact_email,
                    details=f"AI classified reply #{message_id} as unsubscribe ({summary}). Marked contact unsubscribed.",
                )

        if intent in ("question", "interested"):
            try:
                responder.generate_draft_for_reply(conn, message_id)
            except Exception as draft_err:
                logger.warning(f"Draft generation failed for message #{message_id}: {draft_err}")

        return result
    except Exception as e:
        logger.warning(f"AI classification failed for message #{message_id}: {e}")
        # Failure must never crash watcher. Leave intent empty.
        return None


def classify_unclassified_replies(conn) -> int:
    """Run AI classification on any pending incoming replies without an intent."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, body_text, thread_id, contact_email
        FROM messages
        WHERE category = 'reply' AND (intent IS NULL OR intent = '')
        """
    )
    unclassified = cursor.fetchall()
    count = 0
    for row in unclassified:
        res = classify_reply_message(
            conn,
            message_id=row["id"],
            body_text=row["body_text"],
            thread_id=row["thread_id"],
            contact_email=row["contact_email"],
        )
        if res is not None:
            count += 1
    return count


def poll_user_inbox(service: Any, conn: Any, user_id: Optional[int] = None) -> int:
    """Process incoming replies from Gmail for a specific user."""
    newly_recorded = 0
    tracked_threads = get_tracked_thread_ids(conn, user_id=user_id)

    # If no campaigns have sent tracked emails yet, nothing to match
    if not tracked_threads:
        return 0

    # Query recent inbox messages
    response = service.users().messages().list(
        userId="me",
        q="in:inbox -from:me newer_than:7d",
        maxResults=50,
    ).execute()

    messages_list = response.get("messages", [])

    for msg_meta in messages_list:
        msg_id = msg_meta["id"]
        thread_id = msg_meta.get("threadId")

        # 1. Skip if already recorded in messages table
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages WHERE gmail_message_id = ?", (msg_id,))
        if cursor.fetchone():
            continue

        # 2. Check if threadId matches a sent campaign mail
        if thread_id not in tracked_threads:
            # Not related to our campaigns; ignore
            continue

        # 3. Fetch full message details
        full_msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()

        # Extract headers
        payload = full_msg.get("payload", {})
        header_list = payload.get("headers", [])
        headers = {h["name"].lower(): h["value"] for h in header_list}

        from_header = headers.get("from", "")
        subject = headers.get("subject", "No Subject")
        sender_email = extract_email(from_header)

        # Extract received timestamp
        internal_date_ms = int(full_msg.get("internalDate", time.time() * 1000))
        received_at = datetime.utcfromtimestamp(internal_date_ms / 1000.0).isoformat()

        # Extract and clean body
        raw_body = parse_message_payload(payload)
        body_clean = strip_quoted_text(raw_body)

        # Match sender to contacts
        if user_id is not None:
            cursor.execute("SELECT id, name, status FROM contacts WHERE LOWER(email) = LOWER(?) AND user_id = ?", (sender_email, user_id))
        else:
            cursor.execute("SELECT id, name, status FROM contacts WHERE LOWER(email) = LOWER(?)", (sender_email,))
        contact_row = cursor.fetchone()

        flagged_reason = None
        if not contact_row:
            flagged_reason = "unknown sender"

        # 4. Classify category
        if is_bounce(sender_email, subject):
            category = "bounce"
            if contact_row:
                with conn:
                    conn.execute(
                        "UPDATE contacts SET status = 'failed' WHERE id = ?",
                        (contact_row["id"],),
                    )
                    conn.execute(
                        """
                        UPDATE campaign_recipients
                        SET status = 'failed', error = 'Bounced: Mail delivery failed or rejected'
                        WHERE contact_id = ?
                        """,
                        (contact_row["id"],),
                    )
            db.log_activity(
                conn,
                action="bounce_recorded",
                contact_email=sender_email,
                details=f"Mail bounce detected from {sender_email}. Subject: '{subject}'",
                user_id=user_id,
            )

        elif is_auto_reply(headers, subject):
            category = "auto_reply"
            db.log_activity(
                conn,
                action="auto_reply_filtered",
                contact_email=sender_email,
                details=f"Auto-reply filtered for {sender_email}. Subject: '{subject}'",
                user_id=user_id,
            )

        else:
            is_unsub, is_ambiguous = classify_unsubscribe_intent(body_clean)
            if is_unsub:
                category = "unsubscribe_request"
                if contact_row:
                    with conn:
                        conn.execute(
                            "UPDATE contacts SET status = 'unsubscribed' WHERE id = ?",
                            (contact_row["id"],),
                        )
                db.log_activity(
                    conn,
                    action="unsubscribe_processed",
                    contact_email=sender_email,
                    details=f"Unsubscribe requested by {sender_email}. Marked contact unsubscribed.",
                    user_id=user_id,
                )
            else:
                category = "reply"
                if is_ambiguous:
                    flagged_reason = "possible unsubscribe, review"
                    db.log_activity(
                        conn,
                        action="possible_unsubscribe_flagged",
                        contact_email=sender_email,
                        details=f"Reply from {sender_email} contains stop/unsub wording in long message. Flagged for review.",
                        user_id=user_id,
                    )
                else:
                    db.log_activity(
                        conn,
                        action="reply_received",
                        contact_email=sender_email,
                        details=f"Incoming reply from {sender_email}. Subject: '{subject}'",
                        user_id=user_id,
                    )

        # 5. Save message to DB
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (
                    gmail_message_id, thread_id, contact_email, direction,
                    subject, body_text, received_at, category, processed, flagged_reason, user_id
                )
                VALUES (?, ?, ?, 'incoming', ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    msg_id,
                    thread_id,
                    sender_email,
                    subject,
                    body_clean,
                    received_at,
                    category,
                    flagged_reason,
                    user_id,
                ),
            )
            new_msg_id = cursor.lastrowid

        if category == "reply":
            classify_reply_message(
                conn,
                message_id=new_msg_id,
                body_text=body_clean,
                thread_id=thread_id,
                contact_email=sender_email,
            )

        newly_recorded += 1

    return newly_recorded


def poll_gmail_inbox() -> int:
    """
    Fetch and process new incoming replies from Gmail per connected user.
    Returns the count of newly recorded messages.
    """
    conn = db.get_db_connection()
    newly_recorded = 0

    try:
        active_users = db.get_all_active_users(conn)
        if active_users and _GMAIL_CLIENT_OVERRIDE is None:
            for u in active_users:
                uid = u["id"]
                try:
                    service = email_sender.get_gmail_service(user_id=uid)
                    if u["gmail_auth_expired"]:
                        with conn:
                            conn.execute("UPDATE users SET gmail_auth_expired = 0 WHERE id = ?", (uid,))
                    newly_recorded += poll_user_inbox(service, conn, user_id=uid)
                except Exception as ue:
                    err_str = str(ue)
                    if queue_worker.is_gmail_auth_error(err_str) or "credentials missing" in err_str.lower():
                        with conn:
                            conn.execute("UPDATE users SET gmail_auth_expired = 1 WHERE id = ?", (uid,))
                        logger.warning(f"Gmail token missing or expired for user {u['email']}. Pausing sending for this user.")
                    else:
                        logger.warning(f"Error polling inbox for user {u['email']}: {ue}")
        else:
            service = _GMAIL_CLIENT_OVERRIDE or email_sender.get_gmail_service()
            newly_recorded = poll_user_inbox(service, conn, user_id=None)

        # Check for any unclassified replies
        classify_unclassified_replies(conn)

        _WATCHER_STATUS["last_check_time"] = datetime.utcnow().isoformat()
        _WATCHER_STATUS["messages_seen"] += newly_recorded
        _WATCHER_STATUS["last_error"] = None

    except Exception as e:
        err_msg = str(e)
        logger.error(f"Watcher poll error: {err_msg}")
        _WATCHER_STATUS["last_error"] = err_msg
        _WATCHER_STATUS["last_check_time"] = datetime.utcnow().isoformat()

    finally:
        conn.close()

    return newly_recorded


def _watcher_worker_loop():
    """Background polling loop."""
    logger.info("Reply watcher thread started.")
    _WATCHER_STATUS["running"] = True

    while not _STOP_EVENT.is_set():
        try:
            poll_gmail_inbox()
        except Exception as e:
            logger.error(f"Unexpected watcher loop error: {e}")
            _WATCHER_STATUS["last_error"] = str(e)

        # Sleep in small slices for fast stopping
        sleep_time = config.WATCHER_POLL_INTERVAL_SECONDS
        while sleep_time > 0 and not _STOP_EVENT.is_set():
            time.sleep(min(0.5, sleep_time))
            sleep_time -= 0.5

    _WATCHER_STATUS["running"] = False
    logger.info("Reply watcher thread stopped.")


def start_watcher() -> bool:
    """Start background watcher thread."""
    global _WATCHER_THREAD
    with _WATCHER_LOCK:
        if _WATCHER_THREAD and _WATCHER_THREAD.is_alive():
            return True

        _STOP_EVENT.clear()
        _WATCHER_THREAD = threading.Thread(
            target=_watcher_worker_loop,
            daemon=True,
            name="reply-watcher",
        )
        _WATCHER_THREAD.start()
        _WATCHER_STATUS["running"] = True
    return True


def stop_watcher() -> bool:
    """Signal background watcher thread to stop."""
    global _WATCHER_THREAD
    with _WATCHER_LOCK:
        _STOP_EVENT.set()
        if _WATCHER_THREAD and _WATCHER_THREAD.is_alive():
            _WATCHER_THREAD.join(timeout=3.0)
        _WATCHER_STATUS["running"] = False
        _WATCHER_THREAD = None
    return True
