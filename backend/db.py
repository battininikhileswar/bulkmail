"""Database initialization, migration, and connection utilities."""

from datetime import datetime
import sqlite3
from typing import Optional, Set, Tuple, List, Dict, Any
import config


def get_db_connection() -> sqlite3.Connection:
    """Establish connection to SQLite database with foreign keys and WAL enabled."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    init_db(conn)
    return conn


def log_activity(
    conn: sqlite3.Connection,
    action: str,
    contact_email: Optional[str] = None,
    details: str = "",
    user_id: Optional[int] = None,
) -> None:
    """Record an audit trail event in activity_log."""
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO activity_log (timestamp, action, contact_email, details, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now_str, action, contact_email, details, user_id),
        )


def log_ai_usage(
    conn: sqlite3.Connection,
    purpose: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Record token consumption in ai_usage."""
    now_str = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO ai_usage (timestamp, purpose, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?)
            """,
            (now_str, purpose, input_tokens, output_tokens),
        )


def init_db(conn: sqlite3.Connection) -> None:
    """Safely migrate and initialize tables without modifying existing records."""
    with conn:
        # Base contacts table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                extra_data TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                sent_at TEXT,
                message_id TEXT,
                thread_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # Inspect existing columns in contacts table
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(contacts)")
        existing_cols: Set[str] = {row[1].lower() for row in cursor.fetchall()}

        if "group_tag" not in existing_cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN group_tag TEXT")

        if "extra" not in existing_cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN extra TEXT")

        if "user_id" not in existing_cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN user_id INTEGER")

        # Upgrade contacts table constraint from global email UNIQUE to UNIQUE(email, user_id)
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='contacts'")
        tbl_sql_row = cursor.fetchone()
        if tbl_sql_row and "email TEXT UNIQUE" in tbl_sql_row[0]:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL,
                    extra_data TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    sent_at TEXT,
                    message_id TEXT,
                    thread_id TEXT,
                    created_at TEXT NOT NULL,
                    group_tag TEXT,
                    extra TEXT,
                    user_id INTEGER,
                    UNIQUE(email, user_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO contacts_temp (id, email, name, extra_data, status, sent_at, message_id, thread_id, created_at, group_tag, extra, user_id)
                SELECT id, email, name, extra_data, status, sent_at, message_id, thread_id, created_at, group_tag, extra, user_id FROM contacts
            """)
            conn.execute("DROP TABLE contacts")
            conn.execute("ALTER TABLE contacts_temp RENAME TO contacts")
            conn.execute("PRAGMA foreign_keys = ON")

        # Campaigns table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                mode TEXT NOT NULL,
                template TEXT NOT NULL,
                provider TEXT NOT NULL,
                group_tag TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL
            )
            """
        )

        # Campaign recipients (per-campaign tracking)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS campaign_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                thread_id TEXT,
                message_id TEXT,
                sent_at TEXT,
                error TEXT,
                rendered_body TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(campaign_id, contact_id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE,
                FOREIGN KEY (contact_id) REFERENCES contacts (id) ON DELETE CASCADE
            )
            """
        )

        # Daily provider send counts (for daily cap enforcement)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_sends (
                provider TEXT NOT NULL,
                send_date TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                count INTEGER NOT NULL DEFAULT 0,
                campaign_count INTEGER NOT NULL DEFAULT 0,
                reply_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (provider, send_date, user_id)
            )
            """
        )

        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='daily_sends'")
        ds_sql_row = cursor.fetchone()
        if ds_sql_row and "PRIMARY KEY (provider, send_date)" in ds_sql_row[0]:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_sends_temp (
                    provider TEXT NOT NULL,
                    send_date TEXT NOT NULL,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    count INTEGER NOT NULL DEFAULT 0,
                    campaign_count INTEGER NOT NULL DEFAULT 0,
                    reply_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, send_date, user_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO daily_sends_temp (provider, send_date, user_id, count, campaign_count, reply_count)
                SELECT provider, send_date, COALESCE(user_id, 0), count, COALESCE(campaign_count, 0), COALESCE(reply_count, 0) FROM daily_sends
            """)
            conn.execute("DROP TABLE daily_sends")
            conn.execute("ALTER TABLE daily_sends_temp RENAME TO daily_sends")

        # Messages table (for reply tracking)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_message_id TEXT UNIQUE NOT NULL,
                thread_id TEXT NOT NULL,
                contact_email TEXT,
                direction TEXT NOT NULL,
                subject TEXT,
                body_text TEXT,
                received_at TEXT NOT NULL,
                category TEXT NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0,
                flagged_reason TEXT,
                intent TEXT,
                summary TEXT
            )
            """
        )

        cursor.execute("PRAGMA table_info(messages)")
        msg_cols: Set[str] = {row[1].lower() for row in cursor.fetchall()}
        if "intent" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN intent TEXT")
        if "summary" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN summary TEXT")

        # AI usage tracking table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                purpose TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        # Drafts table (for AI generated responses)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reply_id INTEGER NOT NULL,
                thread_id TEXT NOT NULL,
                contact_email TEXT,
                body TEXT,
                status TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                original_body TEXT,
                FOREIGN KEY (reply_id) REFERENCES messages (id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute("PRAGMA table_info(drafts)")
        draft_cols: Set[str] = {row[1].lower() for row in cursor.fetchall()}
        if "original_body" not in draft_cols:
            conn.execute("ALTER TABLE drafts ADD COLUMN original_body TEXT")

        # Activity log table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                contact_email TEXT,
                details TEXT
            )
            """
        )

        # Settings table for runtime configuration overrides
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        # Migrate campaign_recipients for retry mechanism and autopilot followups
        cursor.execute("PRAGMA table_info(campaign_recipients)")
        cr_cols: Set[str] = {row[1].lower() for row in cursor.fetchall()}
        if "retry_count" not in cr_cols:
            conn.execute("ALTER TABLE campaign_recipients ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
        if "next_retry_at" not in cr_cols:
            conn.execute("ALTER TABLE campaign_recipients ADD COLUMN next_retry_at TEXT")
        if "followup_count" not in cr_cols:
            conn.execute("ALTER TABLE campaign_recipients ADD COLUMN followup_count INTEGER NOT NULL DEFAULT 0")
        if "last_followup_at" not in cr_cols:
            conn.execute("ALTER TABLE campaign_recipients ADD COLUMN last_followup_at TEXT")

        # Automations table (Phase 10: Autopilot)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS automations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                delay_days INTEGER NOT NULL DEFAULT 3,
                max_followups INTEGER NOT NULL DEFAULT 1,
                send_window_start TEXT NOT NULL DEFAULT '09:00',
                send_window_end TEXT NOT NULL DEFAULT '18:00',
                subject TEXT,
                template TEXT NOT NULL,
                scheduled_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE
            )
            """
        )

        # Users table (Phase 11: Multi-user auth & limits)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                picture_url TEXT,
                created_at TEXT NOT NULL,
                warmup_enabled INTEGER NOT NULL DEFAULT 1,
                warmup_day INTEGER NOT NULL DEFAULT 1,
                last_warmup_date TEXT,
                daily_cap INTEGER NOT NULL DEFAULT 400,
                quota_exhausted_until TEXT,
                gmail_auth_expired INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        # Multi-user tokens persistence table for serverless & database backups
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tokens (
                user_id INTEGER PRIMARY KEY,
                tokens_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )

        # Migrate user_id into all resource tables for strict data separation
        for table_name in ["contacts", "campaigns", "messages", "drafts", "automations", "activity_log", "settings"]:
            cursor.execute(f"PRAGMA table_info({table_name})")
            cols = {row[1].lower() for row in cursor.fetchall()}
            if "user_id" not in cols:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER")

        # Migrate daily_sends table for per-user tracking and reserve breakdowns
        cursor.execute("PRAGMA table_info(daily_sends)")
        ds_cols = {row[1].lower() for row in cursor.fetchall()}
        if "user_id" not in ds_cols:
            conn.execute("ALTER TABLE daily_sends ADD COLUMN user_id INTEGER")
        if "campaign_count" not in ds_cols:
            conn.execute("ALTER TABLE daily_sends ADD COLUMN campaign_count INTEGER NOT NULL DEFAULT 0")
        if "reply_count" not in ds_cols:
            conn.execute("ALTER TABLE daily_sends ADD COLUMN reply_count INTEGER NOT NULL DEFAULT 0")

        # Unique index on daily_sends for ON CONFLICT per user
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_sends_user ON daily_sends(provider, send_date, user_id)")


def migrate_unassigned_data_to_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Migrate unowned existing records (where user_id IS NULL) to the first signed-in user."""
    with conn:
        for tbl in ["contacts", "campaigns", "messages", "drafts", "automations", "activity_log", "settings", "daily_sends"]:
            try:
                conn.execute(f"UPDATE {tbl} SET user_id = ? WHERE user_id IS NULL", (user_id,))
            except Exception:
                pass


def get_or_create_user(
    conn: sqlite3.Connection,
    email: str,
    name: str,
    picture_url: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Tuple[sqlite3.Row, bool]:
    """Look up user by email or create new. If this is the first user ever, migrates existing data to them."""
    clean_email = email.strip().lower()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (clean_email,))
    existing = cursor.fetchone()
    if existing:
        with conn:
            conn.execute(
                "UPDATE users SET name = ?, picture_url = COALESCE(?, picture_url) WHERE id = ?",
                (name, picture_url, existing["id"]),
            )
        cursor.execute("SELECT * FROM users WHERE id = ?", (existing["id"],))
        return cursor.fetchone(), False

    # Check if first user
    cursor.execute("SELECT COUNT(*) FROM users")
    count_before = cursor.fetchone()[0]
    is_first = (count_before == 0)

    # Determine default cap based on domain (400 for personal Gmail, 1500 for Google Workspace)
    from limits import get_default_daily_cap
    default_cap = get_default_daily_cap(clean_email)
    now_str = datetime.utcnow().isoformat()

    with conn:
        if user_id is not None:
            cursor.execute(
                """
                INSERT INTO users (id, email, name, picture_url, created_at, warmup_enabled, warmup_day, daily_cap)
                VALUES (?, ?, ?, ?, ?, 1, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    email = excluded.email,
                    name = excluded.name,
                    picture_url = COALESCE(excluded.picture_url, users.picture_url)
                """,
                (user_id, clean_email, name, picture_url, now_str, default_cap),
            )
            new_id = user_id
        else:
            cursor.execute(
                """
                INSERT INTO users (email, name, picture_url, created_at, warmup_enabled, warmup_day, daily_cap)
                VALUES (?, ?, ?, ?, 1, 1, ?)
                """,
                (clean_email, name, picture_url, now_str, default_cap),
            )
            new_id = cursor.lastrowid

    if is_first:
        migrate_unassigned_data_to_user(conn, new_id)

    cursor.execute("SELECT * FROM users WHERE id = ?", (new_id,))
    return cursor.fetchone(), is_first


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    """Retrieve user row by primary ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()


def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    """Retrieve user row by email."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
    return cursor.fetchone()


def get_all_active_users(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """List all registered users."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY id ASC")
    return cursor.fetchall()



def create_backup() -> str:
    """
    Perform a safe live backup of the SQLite database using sqlite3.Connection.backup.
    Saves to backups/contacts_YYYYMMDD_HHMMSS_ffffff.db and prunes older backups to keep the latest 10.
    """
    target_base = config.DATA_DIR if config.IS_VERCEL else config.BASE_DIR
    backups_dir = target_base / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    backup_file = backups_dir / f"contacts_{now_str}.db"

    src_conn = get_db_connection()
    dest_conn = sqlite3.connect(str(backup_file))
    try:
        with dest_conn:
            src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    # Retain strictly the latest 10 backup files
    all_backups = sorted(backups_dir.glob("contacts_*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    for old_file in all_backups[10:]:
        try:
            old_file.unlink()
        except OSError:
            pass

    return backup_file.name


def list_backups():
    """List all available backup files sorted newest first."""
    target_base = config.DATA_DIR if config.IS_VERCEL else config.BASE_DIR
    backups_dir = target_base / "backups"
    if not backups_dir.exists():
        return []
    files = sorted(backups_dir.glob("contacts_*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    results = []
    for f in files:
        results.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.utcfromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return results
