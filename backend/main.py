#!/usr/bin/env python3
"""FastAPI Backend for AI Email Assistant - Phase 8."""

from contextlib import asynccontextmanager
import csv
import io
import json
import sqlite3
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
import time
import secrets
import logging
import urllib.parse

from fastapi import FastAPI, File, HTTPException, UploadFile, Query, Response, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
import db
import queue_worker
import sender
import watcher
import classifier
import responder
import templating
import email_sender
import ai_client
import autopilot
import auth
import limits

logger = logging.getLogger("mail_agent.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run database recovery, load stored settings, and start background reply watcher on startup."""
    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        for r in cursor.fetchall():
            k, v = r["key"], r["value"]
            if k == "sender_name": config.SENDER_NAME = v
            elif k == "tone": config.TONE = v
            elif k == "test_mode": config.TEST_MODE = v.lower() in ("true", "1", "yes")
            elif k == "test_email": config.TEST_EMAIL = v
            elif k == "daily_cap":
                val = int(v)
                config.DAILY_CAP = val
                if config.PROVIDER.lower() == "gmail": config.GMAIL_DAILY_CAP = val
                else: config.SMTP_DAILY_CAP = val
            elif k == "pause_seconds": config.PAUSE_SECONDS = int(v)
    finally:
        conn.close()

    recovered = queue_worker.recover_stranded_sending()
    rec_count = recovered.get("stranded_recipients", 0) + recovered.get("stranded_drafts", 0)
    if rec_count > 0:
        print(f"[RECOVERY] Found {rec_count} stranded item(s). Marked for manual review.")

    # Safety check test mode configuration at startup
    if config.TEST_MODE and not config.is_test_email_valid():
        print("[SAFETY ALERT] Test mode is ON but TEST_EMAIL is empty or invalid. All sending is blocked until configured in Settings.")

    # Safety check SESSION_SECRET configuration
    if config.is_session_secret_default_or_missing():
        print(
            "\n" + "=" * 70 + "\n"
            "[SECURITY ALERT] SESSION_SECRET is missing or using default placeholder!\n"
            "Please configure a secure SESSION_SECRET in your .env file.\n"
            + "=" * 70 + "\n"
        )
        logger.warning(
            "[SECURITY ALERT] SESSION_SECRET is missing or using default placeholder. "
            "Please configure a secure SESSION_SECRET in your .env file."
        )

    # Start the reply watcher thread and autopilot scheduler
    if not config.IS_VERCEL:
        watcher.start_watcher()
        autopilot.start_autopilot()
    yield
    # Stop background workers on application shutdown
    if not config.IS_VERCEL:
        autopilot.stop_autopilot()
        watcher.stop_watcher()


app = FastAPI(
    title="AI Email Assistant API",
    description="Backend API for managing email campaigns, tracking replies, and AI response drafting.",
    version="3.0.0",
    lifespan=lifespan,
)

# Enable CORS for local Vite development and deployed frontend
cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://bulkmail-frontend-cyan.vercel.app",
]
if config.FRONTEND_URL and config.FRONTEND_URL not in cors_origins:
    cors_origins.append(config.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Root status and navigation endpoint."""
    return {
        "status": "online",
        "service": "BulkMail API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


def get_session_cookie_params(request: Request) -> Dict[str, Any]:
    """
    Return appropriate SameSite and Secure flags.
    Cross-site HTTPS requests (e.g. frontend and backend on different Vercel domains)
    require SameSite=None and Secure=True.
    Local HTTP requests require SameSite=Lax and Secure=False.
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
    is_secure = proto == "https" or config.IS_VERCEL
    if is_secure:
        return {"samesite": "none", "secure": True}
    return {"samesite": "lax", "secure": False}


# Pydantic Schemas
class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    mode: str = Field(..., pattern="^(same|fields|per_person)$")
    template: str = Field(...)
    provider: str = Field(default="gmail", pattern="^(gmail|smtp)$")
    group_tag: Optional[str] = None


class TestSendRequest(BaseModel):
    test_email: str = Field(..., min_length=3)


class DraftUpdate(BaseModel):
    body: str = Field(...)


class SettingsUpdate(BaseModel):
    sender_name: Optional[str] = None
    tone: Optional[str] = None
    test_mode: Optional[bool] = None
    test_email: Optional[str] = None
    daily_cap: Optional[int] = None
    pause_seconds: Optional[int] = None
    warmup_enabled: Optional[bool] = None


# --- Authentication & Session Security Dependencies ---

def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    """Return authenticated user dictionary from signed session cookie or test header."""
    # 0. Explicit unauthenticated header for test suites
    if request.headers.get("X-Test-No-Auth") or request.headers.get("X-Unauthenticated"):
        return None

    # 1. Allow automated tests to specify user ID directly
    test_user_id = request.headers.get("X-Test-User-Id")
    conn = db.get_db_connection()
    try:
        if test_user_id:
            try:
                uid = int(test_user_id)
                u = db.get_user_by_id(conn, uid)
                if u:
                    return dict(u)
            except Exception:
                pass

        # 2. Verify signed session token from Authorization header or cookie
        auth_header = request.headers.get("Authorization", "").strip()
        session_token = None
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:].strip()
        elif request.headers.get("X-Session-Token"):
            session_token = request.headers.get("X-Session-Token", "").strip()
        if not session_token:
            session_token = request.cookies.get("app_session")

        if session_token:
            payload = auth.verify_token(session_token)
            if payload and ("uid" in payload or "email" in payload):
                uid = payload.get("uid")
                email = payload.get("email")
                user_row = db.get_user_by_id(conn, uid) if uid is not None else None
                if not user_row and email:
                    # Self-heal across serverless containers: recover or recreate user record
                    user_row = db.get_user_by_email(conn, email)
                    if not user_row:
                        user_row, _ = db.get_or_create_user(
                            conn=conn,
                            email=email,
                            name=payload.get("name") or email.split("@")[0],
                            picture_url=payload.get("picture"),
                            user_id=uid,
                        )

                # Self-heal Google OAuth tokens in current container if missing
                if uid and "tokens_enc" in payload:
                    token_file = config.TOKENS_DIR / f"{uid}.json"
                    if not token_file.exists():
                        try:
                            dec_str = auth.decrypt_data(payload["tokens_enc"])
                            if dec_str:
                                token_dict = json.loads(dec_str)
                                auth.save_user_tokens(uid, token_dict)
                        except Exception:
                            pass

                if user_row:
                    return dict(user_row)

        # 3. Legacy test suite compatibility fixture
        if getattr(request.app.state, "legacy_test_user_enabled", False):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY id ASC LIMIT 1")
            first_user = cursor.fetchone()
            if not first_user:
                first_user, _ = db.get_or_create_user(conn, "test.user@example.com", "Test User")
            return dict(first_user)

        return None
    finally:
        conn.close()


def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency enforcing that an authenticated user session is active. Returns 401 otherwise."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in with your Google account.",
        )
    return user


# --- Auth Endpoints (Phase 11) ---

@app.get("/login", include_in_schema=False)
@app.get("/api/login", include_in_schema=False)
def login_fallback(request: Request) -> Any:
    """Fallback handler redirecting direct backend /login hits to frontend login page."""
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return {"status": "ok", "login_url": f"{config.FRONTEND_URL}/login"}
    return RedirectResponse(url=f"{config.FRONTEND_URL}/login", status_code=303)


@app.get("/app", include_in_schema=False)
@app.get("/api/app", include_in_schema=False)
def app_fallback(request: Request) -> Any:
    """Fallback handler redirecting direct backend /app hits to frontend app page."""
    return RedirectResponse(url=f"{config.FRONTEND_URL}/app", status_code=303)


@app.get("/auth/login", include_in_schema=False)
def auth_login_alias(request: Request) -> Any:
    """Fallback alias handling /auth/login if called without /api prefix."""
    return auth_login(request)


@app.get("/api/auth/login")
def auth_login(request: Request) -> Any:
    """Initiate Google OAuth 2.0 authorization code flow with PKCE and state."""
    verifier, challenge = auth.generate_pkce_pair()
    nonce = secrets.token_urlsafe(32)
    redirect_uri = config.OAUTH_REDIRECT_URI

    # Store state & code_verifier in signed temporary token (10 minute expiry)
    state_token = auth.sign_token({
        "state": nonce,
        "verifier": verifier,
        "redirect_uri": redirect_uri,
        "exp": int(time.time() + 600),
    })

    try:
        # Use signed state_token as the state parameter so Google returns it in the callback query param.
        # This guarantees reliable PKCE exchange even if browser cookies are blocked cross-site.
        auth_url = auth.build_authorization_url(state=state_token, code_challenge=challenge, redirect_uri=redirect_uri)
        resp = RedirectResponse(url=auth_url, status_code=303)
        c_params = get_session_cookie_params(request)
        resp.set_cookie(
            key="oauth_state",
            value=state_token,
            httponly=True,
            samesite=c_params["samesite"],
            secure=c_params["secure"],
            max_age=600,
            path="/",
        )
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/auth/callback")
def auth_callback(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> Any:
    """Handle Google OAuth callback, exchange code, retrieve profile, and set session cookie."""
    frontend_base = config.FRONTEND_URL.rstrip("/")
    if error:
        return RedirectResponse(url=f"{frontend_base}/login?auth_error=" + urllib.parse.quote_plus(error))
    if not code or not state:
        return RedirectResponse(url=f"{frontend_base}/login?auth_error=missing_code_or_state")

    # 1. Verify state directly from Google query param (signed token)
    verified_state = None
    if state and "." in state:
        verified_state = auth.verify_token(state)

    # 2. Fallback to oauth_state cookie
    if not verified_state:
        state_cookie = request.cookies.get("oauth_state")
        if state_cookie:
            verified_state = auth.verify_token(state_cookie)
            if verified_state and verified_state.get("state") != state and state_cookie != state:
                verified_state = None

    if not verified_state:
        return RedirectResponse(url=f"{frontend_base}/login?auth_error=invalid_oauth_state")

    code_verifier = verified_state.get("verifier", "")
    redirect_uri = verified_state.get("redirect_uri", config.OAUTH_REDIRECT_URI)
    try:
        tokens = auth.exchange_code_for_tokens(code, code_verifier, redirect_uri=redirect_uri)
        user_info = auth.fetch_google_user_info(tokens["access_token"])
        email = user_info.get("email", "").lower().strip()
        name = user_info.get("name") or email.split("@")[0]
        picture = user_info.get("picture")

        conn = db.get_db_connection()
        try:
            user_row, is_first = db.get_or_create_user(conn, email, name, picture)
            uid = user_row["id"]
            auth.save_user_tokens(uid, tokens)
            db.log_activity(
                conn,
                action="user_signed_in",
                contact_email=email,
                details=f"User {email} authenticated via Google OAuth.",
                user_id=uid,
            )
        finally:
            conn.close()

        session_token = auth.create_session_cookie(uid, email, name=name, picture=picture, tokens=tokens)
        c_params = get_session_cookie_params(request)
        redirect_resp = RedirectResponse(url=f"{frontend_base}/app#session={session_token}", status_code=303)
        redirect_resp.set_cookie(
            key="app_session",
            value=session_token,
            httponly=True,
            samesite=c_params["samesite"],
            secure=c_params["secure"],
            max_age=14 * 86400,
            path="/",
        )
        redirect_resp.delete_cookie(
            key="oauth_state",
            path="/",
            samesite=c_params["samesite"],
            secure=c_params["secure"],
        )
        return redirect_resp
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return RedirectResponse(url=f"{frontend_base}/login?auth_error=" + urllib.parse.quote_plus(str(e)))


@app.get("/auth/callback", include_in_schema=False)
def auth_callback_alias(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> Any:
    """Fallback alias handling /auth/callback if called without /api prefix."""
    return auth_callback(request=request, response=response, code=code, state=state, error=error)


@app.get("/api/auth/me")
def auth_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return identity and sending limits for the authenticated user."""
    conn = db.get_db_connection()
    try:
        limits_status = limits.get_user_limits_status(conn, user)
        return {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "picture_url": user.get("picture_url"),
            "created_at": user["created_at"],
            "gmail_auth_expired": bool(user.get("gmail_auth_expired")),
            "limits": limits_status,
        }
    finally:
        conn.close()


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> Dict[str, Any]:
    """Clear session cookie and log user out."""
    c_params = get_session_cookie_params(request)
    response.delete_cookie(
        key="app_session",
        path="/",
        samesite=c_params["samesite"],
        secure=c_params["secure"],
    )
    return {"success": True, "message": "Signed out successfully."}


@app.post("/api/auth/test-login")
def auth_test_login(email: str, name: str = "Test User", response: Response = None) -> Dict[str, Any]:
    """Helper endpoint allowing test suites to set up session tokens without browser interaction."""
    conn = db.get_db_connection()
    try:
        user_row, is_first = db.get_or_create_user(conn, email, name)
        uid = user_row["id"]
    finally:
        conn.close()
    token = auth.create_session_cookie(uid, email, name=name)
    if response:
        response.set_cookie(key="app_session", value=token, httponly=True, samesite="lax", path="/")
    return {"user_id": uid, "email": email, "token": token}


# --- Core Endpoints ---

@app.get("/api/health")
def get_health(request: Request) -> Dict[str, Any]:
    """Health check endpoint confirming backend readiness and live configuration."""
    user = get_current_user_optional(request)
    stranded_data = queue_worker.get_stranded_items()
    resp = {
        "status": "ok",
        "authenticated": user is not None,
        "provider": config.PROVIDER,
        "daily_cap": user.get("daily_cap", config.DAILY_CAP) if user else config.DAILY_CAP,
        "gmail_daily_cap": config.GMAIL_DAILY_CAP,
        "smtp_daily_cap": config.SMTP_DAILY_CAP,
        "test_mode": config.TEST_MODE,
        "test_email": config.TEST_EMAIL,
        "global_sending_paused": queue_worker.is_global_sending_paused(),
        "gmail_auth_expired": bool(user.get("gmail_auth_expired")) if user else queue_worker.is_gmail_auth_expired(),
        "sender_name": config.SENDER_NAME,
        "tone": config.TONE,
        "pause_seconds": config.PAUSE_SECONDS,
        "watcher_interval": config.WATCHER_POLL_INTERVAL_SECONDS,
        "stranded_count": stranded_data["total_stranded"],
        "ai_provider": getattr(config, "AI_PROVIDER", "anthropic"),
        "test_email_valid": config.is_test_email_valid(),
        "storage": {
            "data_dir": str(config.DATA_DIR),
            "is_vercel": config.IS_VERCEL,
            "oauth_redirect_uri": config.OAUTH_REDIRECT_URI,
            "frontend_url": config.FRONTEND_URL,
        },
    }
    if user:
        resp["sending_as"] = user["email"]
        resp["user_name"] = user["name"]
        resp["user_picture"] = user.get("picture_url")
    return resp


@app.get("/api/stranded")
def get_stranded_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve items flagged for manual review during startup recovery."""
    return queue_worker.get_stranded_items(user_id=user["id"])


@app.post("/api/sending/pause")
def pause_sending(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Globally pause all email sending (campaigns and reply drafts)."""
    queue_worker.set_global_sending_paused(True)
    return {"paused": True, "message": "All sending is paused globally."}


@app.post("/api/sending/resume")
def resume_sending(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Globally resume email sending."""
    queue_worker.set_global_sending_paused(False)
    return {"paused": False, "message": "All sending has resumed."}


@app.get("/api/sending/status")
@app.get("/api/sending")
def get_sending_status(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Get global sending pause status."""
    return {"paused": queue_worker.is_global_sending_paused()}


@app.get("/api/stats")
def get_stats(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, int]:
    """Return overall counts of contacts, replies, drafts, and review items for the user."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    uid = user["id"]

    cursor.execute("SELECT COUNT(*) FROM contacts WHERE user_id = ?", (uid,))
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT status, COUNT(*) FROM contacts WHERE user_id = ? GROUP BY status",
        (uid,),
    )
    breakdown = dict(cursor.fetchall())

    # Count unhandled replies
    cursor.execute(
        "SELECT COUNT(*) FROM messages WHERE category = 'reply' AND processed = 0 AND user_id = ?",
        (uid,),
    )
    unhandled_replies = cursor.fetchone()[0]

    # Count pending drafts
    cursor.execute(
        "SELECT COUNT(*) FROM drafts WHERE status = 'pending_approval' AND user_id = ?",
        (uid,),
    )
    pending_drafts = cursor.fetchone()[0]

    stranded_data = queue_worker.get_stranded_items(user_id=uid)

    conn.close()

    return {
        "total": total,
        "pending": breakdown.get("pending", 0),
        "sent": breakdown.get("sent", 0),
        "failed": breakdown.get("failed", 0),
        "unsubscribed": breakdown.get("unsubscribed", 0),
        "unhandled_replies": unhandled_replies,
        "pending_drafts": pending_drafts,
        "stranded": stranded_data["total_stranded"],
    }


@app.get("/api/dashboard/summary")
def get_dashboard_summary(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Read-only dashboard summary returning 14-day send trends, intent breakdown, and KPI totals."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    uid = user["id"]

    # 1. 14-day send trends
    today = date.today()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    placeholders = ",".join(["?"] * len(day_list))
    cursor.execute(
        f"""
        SELECT send_date, SUM(count) as total_sends, SUM(campaign_count) as camp_sends, SUM(reply_count) as rep_sends
        FROM daily_sends
        WHERE user_id = ? AND send_date IN ({placeholders})
        GROUP BY send_date
        """,
        [uid] + day_list,
    )
    sends_map = {row["send_date"]: row["total_sends"] or 0 for row in cursor.fetchall()}
    daily_trends = [{"date": d, "sends": sends_map.get(d, 0)} for d in day_list]

    # 2. Intent breakdown from incoming replies
    cursor.execute(
        """
        SELECT COALESCE(NULLIF(intent, ''), 'other') as intent_name, COUNT(*) as count
        FROM messages
        WHERE user_id = ? AND direction = 'incoming'
        GROUP BY intent_name
        ORDER BY count DESC
        """,
        (uid,),
    )
    intent_rows = cursor.fetchall()
    intent_breakdown = [{"intent": r["intent_name"], "count": r["count"]} for r in intent_rows]

    # 3. Quick KPI numbers
    cursor.execute("SELECT COUNT(*) FROM contacts WHERE user_id = ?", (uid,))
    total_contacts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND status = 'sent'", (uid,))
    sent_contacts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM messages WHERE user_id = ? AND direction = 'incoming'", (uid,))
    incoming_replies = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM drafts WHERE user_id = ? AND status IN ('pending_approval', 'needs_review')", (uid,))
    pending_drafts = cursor.fetchone()[0]

    reply_rate = round((incoming_replies / sent_contacts * 100), 1) if sent_contacts > 0 else 0.0

    conn.close()

    return {
        "daily_trends": daily_trends,
        "intent_breakdown": intent_breakdown,
        "total_contacts": total_contacts,
        "sent_contacts": sent_contacts,
        "incoming_replies": incoming_replies,
        "reply_rate": reply_rate,
        "pending_drafts": pending_drafts,
    }


@app.get("/api/contacts")
def get_contacts(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Return all contacts for the current user ordered by creation recency."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, email, name, group_tag, extra, extra_data, status, sent_at, created_at
        FROM contacts
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user["id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    contacts = []
    for row in rows:
        extra_val = row["extra"] or row["extra_data"]
        contacts.append(
            {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "group_tag": row["group_tag"],
                "extra": json.loads(extra_val) if extra_val else {},
                "status": row["status"],
                "sent_at": row["sent_at"],
                "created_at": row["created_at"],
            }
        )
    return contacts


@app.get("/api/contacts/placeholders")
def get_placeholders(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return all available CSV placeholder keys discovered across the user's contacts."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT extra, extra_data, group_tag FROM contacts WHERE user_id = ?",
        (user["id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    keys = {"name"}
    groups = set()

    for row in rows:
        if row["group_tag"]:
            groups.add(row["group_tag"])
        extra_val = row["extra"] or row["extra_data"]
        if extra_val:
            try:
                data = json.loads(extra_val)
                for k in data.keys():
                    keys.add(k)
            except Exception:
                pass

    return {
        "placeholders": sorted(list(keys)),
        "groups": sorted(list(groups)),
    }


@app.post("/api/contacts/upload")
async def upload_contacts(file: UploadFile = File(...), user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, int]:
    """Accept and validate a CSV contact file, saving extra columns and group_tag for the user."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1")

    csv_stream = io.StringIO(content)
    reader = csv.DictReader(csv_stream)

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file must include a header row.")

    field_map = {col.strip().lower(): col for col in reader.fieldnames}
    if "email" not in field_map or "name" not in field_map:
        raise HTTPException(
            status_code=400,
            detail="CSV file must contain both 'name' and 'email' header columns.",
        )

    email_key = field_map["email"]
    name_key = field_map["name"]
    group_key = field_map.get("group") or field_map.get("group_tag")

    conn = db.get_db_connection()
    added_count = 0
    duplicate_count = 0
    invalid_count = 0
    now_str = datetime.utcnow().isoformat()
    uid = user["id"]

    for row in reader:
        email = row.get(email_key, "").strip()
        name = row.get(name_key, "").strip()

        if not email or "@" not in email or not name:
            invalid_count += 1
            continue

        group_val = row[group_key].strip() if group_key and row.get(group_key) else None

        excluded_keys = {email_key, name_key}
        if group_key:
            excluded_keys.add(group_key)

        extra = {k: v for k, v in row.items() if k not in excluded_keys}
        extra_json = json.dumps(extra) if extra else None

        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO contacts (email, name, extra_data, extra, group_tag, status, created_at, user_id)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (email, name, extra_json, extra_json, group_val, now_str, uid),
                )
            added_count += 1
        except sqlite3.IntegrityError:
            duplicate_count += 1

    conn.close()

    return {
        "added": added_count,
        "duplicates": duplicate_count,
        "invalid": invalid_count,
        "total_processed": added_count + duplicate_count + invalid_count,
    }


@app.post("/api/contacts/load-sample")
def load_sample_contacts(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, int]:
    """Load 5 fake sample contacts (example.com addresses) into contacts table for current user."""
    samples = [
        {"name": "Alice Smith", "email": "alice.smith@example.com", "group": "Attendees", "extra": {"role": "Designer", "company": "Acme Inc"}},
        {"name": "Bob Jones", "email": "bob.jones@example.com", "group": "Attendees", "extra": {"role": "Engineer", "company": "Tech Corp"}},
        {"name": "Carol White", "email": "carol.white@example.com", "group": "VIP", "extra": {"role": "Director", "company": "Global Media"}},
        {"name": "David Brown", "email": "david.brown@example.com", "group": "Speakers", "extra": {"role": "Keynote Speaker", "company": "Innovate"}},
        {"name": "Emma Davis", "email": "emma.davis@example.com", "group": "Attendees", "extra": {"role": "Manager", "company": "Apex Co"}},
    ]
    conn = db.get_db_connection()
    added = 0
    duplicates = 0
    now_str = datetime.utcnow().isoformat()
    uid = user["id"]
    for s in samples:
        extra_json = json.dumps(s["extra"])
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO contacts (email, name, extra_data, extra, group_tag, status, created_at, user_id)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (s["email"], s["name"], extra_json, extra_json, s["group"], now_str, uid),
                )
            added += 1
        except sqlite3.IntegrityError:
            duplicates += 1
    conn.close()
    return {"added": added, "duplicates": duplicates, "invalid": 0, "total_processed": len(samples)}


class QuickTemplateRequest(BaseModel):
    goal: str = Field(..., description="Announce / invite, Reminder, or Follow-up")
    prompt: str = Field(..., description="Details of what the email should say")
    placeholders: Optional[List[str]] = Field(default_factory=list)


@app.post("/api/ai/quick-template")
def generate_quick_template(req: QuickTemplateRequest, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Generate email subject and body template using AI client.
    Strictly uses user details, never invents facts, appends no signature.
    Falls back gracefully to default template if AI fails or key is missing.
    """
    goal_norm = req.goal.strip().lower()
    default_templates = {
        "announce / invite": {
            "subject": "Invitation: Join us for our upcoming update",
            "body": "Hi {name},\n\nWe would love to invite you to join us! We look forward to connecting with you.",
        },
        "reminder": {
            "subject": "Reminder: Upcoming event details",
            "body": "Hi {name},\n\nThis is a friendly reminder about our upcoming schedule. Please let us know if you have any questions.",
        },
        "follow-up": {
            "subject": "Following up on our recent note",
            "body": "Hi {name},\n\nI wanted to follow up with you regarding our recent update. Let us know if you need any additional information.",
        },
    }

    fallback_choice = default_templates["announce / invite"]
    for key, val in default_templates.items():
        if key in goal_norm or goal_norm in key:
            fallback_choice = val
            break

    if req.prompt.strip():
        user_lines = req.prompt.strip()
        fallback_choice = {
            "subject": fallback_choice["subject"],
            "body": f"Hi {{name}},\n\n{user_lines}",
        }

    placeholders_str = ", ".join([f"{{{p}}}" for p in req.placeholders or []]) if req.placeholders else "{name}"
    system_prompt = (
        "You are an email copywriting assistant. Write an email subject and body based strictly on the user's provided details.\n"
        "Rules:\n"
        "- Use ONLY the details provided by the user. Never invent dates, prices, links, venues, or promises.\n"
        "- Keep the message short, clear, and friendly.\n"
        "- Do NOT include a signature, sign-off name, or unsubscribe line (the system automatically appends the sender name and unsubscribe link).\n"
        "- Use {name} as the greeting placeholder (e.g. 'Hi {name},').\n"
        f"- Available placeholders: {placeholders_str}.\n"
        "- Output MUST be valid JSON in this exact structure with no extra text:\n"
        "{\"subject\": \"...\", \"body\": \"...\"}"
    )

    user_text = (
        f"Goal: {req.goal}\n"
        f"What the email should say: {req.prompt}\n"
        f"Available placeholders: {req.placeholders}"
    )

    try:
        raw_res = ai_client.complete(
            system_prompt=system_prompt,
            user_text=user_text,
            max_tokens=250,
            purpose="quick_start_copy",
        )
        cleaned = raw_res.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

        data = json.loads(cleaned)
        subj = (data.get("subject") or "").strip()
        bdy = (data.get("body") or "").strip()
        if subj and bdy:
            return {"subject": subj, "template": bdy, "fallback": False}
    except Exception as e:
        print(f"[Quick Start AI Error] {e}; using safe fallback template.")

    return {
        "subject": fallback_choice["subject"],
        "template": fallback_choice["body"],
        "fallback": True,
    }


@app.post("/api/contacts/{email}/unsubscribe")
def unsubscribe_contact(email: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Mark a contact as unsubscribed in SQLite so they are never sent messages."""
    conn = db.get_db_connection()
    uid = user["id"]
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE contacts SET status = 'unsubscribed' WHERE LOWER(email) = LOWER(?) AND user_id = ?",
            (email.strip(), uid),
        )
        updated = cursor.rowcount
        if updated > 0:
            db.log_activity(
                conn,
                action="manual_unsubscribe",
                contact_email=email,
                details=f"Contact {email} unsubscribed manually via API.",
                user_id=uid,
            )
    conn.close()

    if updated == 0:
        raise HTTPException(status_code=404, detail=f"Contact '{email}' not found.")

    return {"success": True, "email": email, "status": "unsubscribed"}


# --- Campaign Endpoints ---

@app.post("/api/campaigns")
def create_campaign(data: CampaignCreate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Create a new campaign and queue its recipient snapshot."""
    if data.provider.lower() == "smtp" and not limits.can_use_smtp(user["email"]):
        raise HTTPException(
            status_code=400,
            detail="SMTP is only permitted when sending from a custom domain (non-@gmail.com). Please use Gmail for @gmail.com accounts.",
        )

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    uid = user["id"]

    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO campaigns (name, subject, mode, template, provider, group_tag, status, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)
            """,
            (
                data.name.strip(),
                data.subject.strip(),
                data.mode.lower(),
                data.template,
                data.provider.lower(),
                data.group_tag.strip() if data.group_tag else None,
                now_str,
                uid,
            ),
        )
        campaign_id = cursor.lastrowid

    conn.close()
    queue_worker.populate_campaign_recipients(campaign_id)

    return {
        "id": campaign_id,
        "name": data.name,
        "subject": data.subject,
        "mode": data.mode,
        "provider": data.provider,
        "status": "draft",
        "created_at": now_str,
    }


@app.get("/api/campaigns")
def list_campaigns(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """List all campaigns for current user with summary counts."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE user_id = ? ORDER BY id DESC", (user["id"],))
    rows = cursor.fetchall()

    campaigns = []
    for r in rows:
        cid = r["id"]
        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM campaign_recipients
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (cid,),
        )
        counts = dict(cursor.fetchall())
        cursor.execute("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id = ?", (cid,))
        total = cursor.fetchone()[0]

        campaigns.append({
            "id": r["id"],
            "name": r["name"],
            "subject": r["subject"],
            "mode": r["mode"],
            "template": r["template"],
            "provider": r["provider"],
            "group_tag": r["group_tag"],
            "status": r["status"],
            "created_at": r["created_at"],
            "total_recipients": total,
            "counts": counts,
        })

    conn.close()
    return campaigns


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve full details of a specific campaign."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE id = ? AND user_id = ?", (campaign_id, user["id"]))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    progress = queue_worker.get_campaign_progress(campaign_id)

    return {
        "id": row["id"],
        "name": row["name"],
        "subject": row["subject"],
        "mode": row["mode"],
        "template": row["template"],
        "provider": row["provider"],
        "group_tag": row["group_tag"],
        "status": row["status"],
        "created_at": row["created_at"],
        "progress": progress,
    }


def _check_campaign_access(conn: sqlite3.Connection, campaign_id: int, user_id: int) -> sqlite3.Row:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE id = ? AND user_id = ?", (campaign_id, user_id))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return row


@app.get("/api/campaigns/{campaign_id}/plan")
def get_campaign_plan_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return multi-day dispatch plan for campaign based on user daily limits."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    return queue_worker.get_campaign_multi_day_plan(campaign_id)


@app.post("/api/campaigns/{campaign_id}/preview")
def preview_campaign_endpoint(campaign_id: int, limit: int = 5, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Generate preview of first N rendered mails and list skipped contacts with reasons."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    try:
        return queue_worker.preview_campaign(campaign_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/campaigns/{campaign_id}/test-send")
def test_send_endpoint(campaign_id: int, req: TestSendRequest, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Send up to 3 personalized sample emails to test_email without changing contact statuses."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    if not config.is_valid_email(req.test_email):
        raise HTTPException(status_code=400, detail="Provided test email address is invalid.")
    if config.TEST_MODE and not config.is_test_email_valid():
        raise HTTPException(
            status_code=400,
            detail="Test mode is enabled but TEST_EMAIL is not configured with a valid email address. Configure a valid test email in Settings before sending.",
        )
    try:
        return queue_worker.send_test_email(campaign_id, req.test_email, user_id=user["id"], sender_email=user["email"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Test send unexpected error: {e}", exc_info=True)
        return {
            "success": False,
            "sent_count": 0,
            "test_email": req.test_email,
            "samples": [],
            "message": f"Dispatch error: {str(e)}",
        }


@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Start campaign dispatch in background worker."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
        status = limits.get_user_limits_status(conn, user)
    finally:
        conn.close()

    if config.TEST_MODE and not config.is_test_email_valid():
        raise HTTPException(
            status_code=400,
            detail="Test mode is enabled but TEST_EMAIL is not configured with a valid email address. Configure a valid test email in Settings before sending.",
        )

    if not config.TEST_MODE and status["remaining_campaign"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Daily campaign sending cap of {status['campaign_cap']} reached for today (10% reserved for replies).",
        )

    try:
        success = queue_worker.start_campaign_queue(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    conn = db.get_db_connection()
    db.log_activity(conn, action="campaign_started", details=f"Campaign #{campaign_id} started.", user_id=user["id"])
    conn.close()
    return {"success": True, "campaign_id": campaign_id, "status": "running"}


@app.post("/api/campaigns/{campaign_id}/pause")
def pause_campaign_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Pause campaign sending worker."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    queue_worker.pause_campaign_queue(campaign_id)
    conn = db.get_db_connection()
    db.log_activity(conn, action="campaign_paused", details=f"Campaign #{campaign_id} paused.", user_id=user["id"])
    conn.close()
    return {"success": True, "campaign_id": campaign_id, "status": "paused"}


@app.post("/api/campaigns/{campaign_id}/resume")
def resume_campaign_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Resume paused campaign queue."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    queue_worker.resume_campaign_queue(campaign_id)
    conn = db.get_db_connection()
    db.log_activity(conn, action="campaign_resumed", details=f"Campaign #{campaign_id} resumed.", user_id=user["id"])
    conn.close()
    return {"success": True, "campaign_id": campaign_id, "status": "running"}


@app.post("/api/campaigns/{campaign_id}/stop")
def stop_campaign_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Stop campaign queue completely."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    queue_worker.stop_campaign_queue(campaign_id)
    conn = db.get_db_connection()
    db.log_activity(conn, action="campaign_stopped", details=f"Campaign #{campaign_id} stopped.", user_id=user["id"])
    conn.close()
    return {"success": True, "campaign_id": campaign_id, "status": "stopped"}


@app.post("/api/campaigns/{campaign_id}/retry-failed")
def retry_failed_campaign_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Safely re-queue failed contacts for a campaign (never sent, unsubscribed, or bounced)."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    return queue_worker.retry_failed_recipients(campaign_id)


@app.get("/api/campaigns/{campaign_id}/progress")
def get_campaign_progress_endpoint(campaign_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve live dispatch counts and latest 20 recipient results."""
    conn = db.get_db_connection()
    try:
        _check_campaign_access(conn, campaign_id, user["id"])
    finally:
        conn.close()
    try:
        return queue_worker.get_campaign_progress(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Phase 3: Watcher, Replies & Activity Log Endpoints ---

@app.post("/api/watcher/start")
def start_watcher_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Start the background reply watcher."""
    watcher.start_watcher()
    return {"success": True, "status": watcher.get_watcher_status()}


@app.post("/api/watcher/stop")
def stop_watcher_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Stop the background reply watcher."""
    watcher.stop_watcher()
    return {"success": True, "status": watcher.get_watcher_status()}


@app.get("/api/watcher/status")
def get_watcher_status_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve live status, last poll timestamp, messages count, and errors of the watcher."""
    return watcher.get_watcher_status()


@app.get("/api/replies")
def get_replies(
    category: Optional[str] = Query(None, description="Filter category: reply, auto_reply, bounce, unsubscribe_request"),
    contact_email: Optional[str] = Query(None, description="Filter by sender email"),
    unprocessed_only: bool = Query(False, description="Filter by unprocessed state"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve categorized incoming replies for current user ordered newest first."""
    conn = db.get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT m.id, m.gmail_message_id, m.thread_id, m.contact_email, m.direction,
               m.subject, m.body_text, m.received_at, m.category, m.processed, m.flagged_reason,
               m.intent, m.summary,
               c.name as contact_name
        FROM messages m
        LEFT JOIN contacts c ON LOWER(m.contact_email) = LOWER(c.email) AND c.user_id = m.user_id
        WHERE m.user_id = ?
    """
    params: List[Any] = [user["id"]]

    if category and category.lower() != "all":
        query += " AND m.category = ?"
        params.append(category.lower())

    if contact_email:
        query += " AND LOWER(m.contact_email) = LOWER(?)"
        params.append(contact_email.strip())

    if unprocessed_only:
        query += " AND m.processed = 0"

    query += " ORDER BY m.received_at DESC, m.id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]


@app.get("/api/replies/{reply_id}")
def get_reply_detail(reply_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve reply details along with original sent email and full thread conversation history."""
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT m.*, c.name as contact_name
        FROM messages m
        LEFT JOIN contacts c ON LOWER(m.contact_email) = LOWER(c.email) AND c.user_id = m.user_id
        WHERE m.id = ? AND m.user_id = ?
        """,
        (reply_id, user["id"]),
    )
    reply_row = cursor.fetchone()
    if not reply_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Reply message not found.")

    thread_id = reply_row["thread_id"]
    contact_email = reply_row["contact_email"]

    # 1. Fetch original outgoing mail sent to this contact
    cursor.execute(
        """
        SELECT cr.sent_at, cr.rendered_body, camp.name as campaign_name, camp.subject
        FROM campaign_recipients cr
        JOIN campaigns camp ON cr.campaign_id = camp.id
        JOIN contacts c ON cr.contact_id = c.id
        WHERE (cr.thread_id = ? OR LOWER(c.email) = LOWER(?))
          AND camp.user_id = ?
        ORDER BY cr.sent_at ASC
        LIMIT 1
        """,
        (thread_id, contact_email or "", user["id"]),
    )
    orig_mail = cursor.fetchone()

    # 2. Fetch full conversation messages in this thread
    cursor.execute(
        """
        SELECT m.*, c.name as contact_name
        FROM messages m
        LEFT JOIN contacts c ON LOWER(m.contact_email) = LOWER(c.email) AND c.user_id = m.user_id
        WHERE m.thread_id = ? AND m.user_id = ?
        ORDER BY m.received_at ASC, m.id ASC
        """,
        (thread_id, user["id"]),
    )
    thread_msgs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "reply": dict(reply_row),
        "original_sent_mail": dict(orig_mail) if orig_mail else None,
        "thread_history": thread_msgs,
    }


@app.post("/api/replies/{reply_id}/mark-handled")
def mark_reply_handled(reply_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Mark a reply message as handled."""
    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET processed = 1 WHERE id = ? AND user_id = ?", (reply_id, user["id"]))
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Reply message not found.")

        cursor.execute("SELECT contact_email, subject FROM messages WHERE id = ?", (reply_id,))
        m = cursor.fetchone()
        email = m["contact_email"] if m else None
        db.log_activity(
            conn,
            action="reply_marked_handled",
            contact_email=email,
            details=f"Reply #{reply_id} marked as handled.",
            user_id=user["id"],
        )

    conn.close()
    return {"success": True, "reply_id": reply_id, "processed": 1}


@app.post("/api/replies/{reply_id}/classify")
def classify_reply_endpoint(reply_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Re-run AI classification for a specific reply."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE id = ? AND user_id = ?", (reply_id, user["id"]))
    msg_row = cursor.fetchone()
    if not msg_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Reply not found.")

    reply_dict = dict(msg_row)
    orig_text = watcher.get_original_email_text(conn, reply_dict["thread_id"], reply_dict["contact_email"])

    try:
        result = classifier.classify(reply_dict["body_text"] or "", orig_text)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}")

    intent = result.get("intent", "other")
    summary = result.get("summary", "")

    with conn:
        conn.execute(
            "UPDATE messages SET intent = ?, summary = ? WHERE id = ?",
            (intent, summary, reply_id),
        )
        if intent == "unsubscribe" and reply_dict["contact_email"]:
            conn.execute(
                "UPDATE contacts SET status = 'unsubscribed' WHERE LOWER(email) = LOWER(?) AND user_id = ?",
                (reply_dict["contact_email"].strip(), user["id"]),
            )
            db.log_activity(
                conn,
                action="ai_unsubscribe_processed",
                contact_email=reply_dict["contact_email"],
                details=f"AI classified reply #{reply_id} as unsubscribe ({summary}). Marked contact unsubscribed.",
                user_id=user["id"],
            )

        if intent in ("question", "interested"):
            try:
                responder.generate_draft_for_reply(conn, reply_id)
            except Exception as draft_err:
                pass

    conn.close()
    return {
        "success": True,
        "reply_id": reply_id,
        "intent": intent,
        "summary": summary,
    }


@app.get("/api/ai/usage")
def get_ai_usage(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Return total AI invocations and token consumption."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
        FROM ai_usage
        """
    )
    row = cursor.fetchone()
    total_calls = row[0]
    input_tokens = row[1]
    output_tokens = row[2]
    conn.close()

    return {
        "total_calls": total_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


# --- Phase 5: Drafts Endpoints ---

@app.get("/api/drafts")
def list_drafts(
    status: Optional[str] = Query(None, description="Filter by status: pending_approval, needs_review, approved, rejected, sent"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve all AI generated response drafts for the current user, optionally filtered by status."""
    conn = db.get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT d.id, d.reply_id, d.thread_id, d.contact_email, d.body, d.status, d.reason,
               d.created_at, d.updated_at, d.original_body,
               m.subject as reply_subject, m.body_text as reply_body, m.received_at as reply_received_at,
               c.name as contact_name
        FROM drafts d
        LEFT JOIN messages m ON d.reply_id = m.id
        LEFT JOIN contacts c ON LOWER(d.contact_email) = LOWER(c.email) AND c.user_id = d.user_id
        WHERE d.user_id = ?
    """
    params: List[Any] = [user["id"]]
    if status and status.lower() != "all":
        query += " AND LOWER(d.status) = LOWER(?)"
        params.append(status.strip())

    query += " ORDER BY d.id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve full details of a specific response draft for the current user."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.id, d.reply_id, d.thread_id, d.contact_email, d.body, d.status, d.reason,
               d.created_at, d.updated_at, d.original_body,
               m.subject as reply_subject, m.body_text as reply_body, m.received_at as reply_received_at,
               c.name as contact_name
        FROM drafts d
        LEFT JOIN messages m ON d.reply_id = m.id
        LEFT JOIN contacts c ON LOWER(d.contact_email) = LOWER(c.email) AND c.user_id = d.user_id
        WHERE d.id = ? AND d.user_id = ?
        """,
        (draft_id, user["id"]),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return dict(row)


@app.post("/api/drafts/{draft_id}/regenerate")
def regenerate_draft(draft_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Regenerate an AI response draft, counting toward the thread limit."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user["id"]))
    draft_row = cursor.fetchone()
    if not draft_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Draft not found.")

    draft = dict(draft_row)
    thread_id = draft["thread_id"]
    reply_id = draft["reply_id"]
    contact_email = draft["contact_email"]
    now_str = datetime.utcnow().isoformat()
    uid = user["id"]

    # Check thread draft count (hard limit: 3)
    cursor.execute("SELECT COUNT(*) FROM drafts WHERE thread_id = ?", (thread_id,))
    draft_count = cursor.fetchone()[0]

    if draft_count >= 3:
        with conn:
            cursor.execute(
                """
                INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body, user_id)
                VALUES (?, ?, ?, '', 'needs_review', 'reply limit reached', ?, ?, '', ?)
                """,
                (reply_id, thread_id, contact_email, now_str, now_str, uid),
            )
            new_id = cursor.lastrowid
            db.log_activity(
                conn,
                action="ai_draft_limit_reached",
                contact_email=contact_email,
                details=f"Thread {thread_id} reached 3 draft limit. Draft #{new_id} marked needs_review.",
                user_id=uid,
            )
        cursor.execute(
            """
            SELECT d.*, m.subject as reply_subject, m.body_text as reply_body, c.name as contact_name
            FROM drafts d
            LEFT JOIN messages m ON d.reply_id = m.id
            LEFT JOIN contacts c ON LOWER(d.contact_email) = LOWER(c.email)
            WHERE d.id = ?
            """,
            (new_id,),
        )
        created_row = cursor.fetchone()
        conn.close()
        return dict(created_row)

    # Fetch thread conversation
    cursor.execute(
        """
        SELECT direction, contact_email, body_text, received_at
        FROM messages
        WHERE thread_id = ?
        ORDER BY received_at ASC, id ASC
        """,
        (thread_id,),
    )
    thread_messages = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT body_text FROM messages WHERE id = ?", (reply_id,))
    msg_row = cursor.fetchone()
    new_reply_text = msg_row["body_text"] if msg_row else ""

    try:
        facts = responder.load_facts()
        result = responder.draft_reply(
            thread_messages=thread_messages,
            new_reply=new_reply_text,
            facts=facts,
            tone=config.TONE,
        )
        db_status = "pending_approval" if result["status"] == "draft" else "needs_review"
        body = result.get("body", "")
        reason = result.get("reason", "")

        with conn:
            cursor.execute(
                """
                INSERT INTO drafts (reply_id, thread_id, contact_email, body, status, reason, created_at, updated_at, original_body, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (reply_id, thread_id, contact_email, body, db_status, reason, now_str, now_str, body, uid),
            )
            new_id = cursor.lastrowid
            db.log_activity(
                conn,
                action="ai_draft_regenerated",
                contact_email=contact_email,
                details=f"Draft #{new_id} regenerated ({db_status}) for reply #{reply_id}.",
                user_id=uid,
            )

        cursor.execute(
            """
            SELECT d.*, m.subject as reply_subject, m.body_text as reply_body, c.name as contact_name
            FROM drafts d
            LEFT JOIN messages m ON d.reply_id = m.id
            LEFT JOIN contacts c ON LOWER(d.contact_email) = LOWER(c.email)
            WHERE d.id = ?
            """,
            (new_id,),
        )
        created_row = cursor.fetchone()
        conn.close()
        return dict(created_row)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {e}")


@app.patch("/api/drafts/{draft_id}")
def update_draft(draft_id: int, req: DraftUpdate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Edit draft response body text."""
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE drafts SET body = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (req.body, now_str, draft_id, user["id"]),
        )
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Draft not found.")

        cursor.execute(
            """
            SELECT d.*, m.subject as reply_subject, m.body_text as reply_body, c.name as contact_name
            FROM drafts d
            LEFT JOIN messages m ON d.reply_id = m.id
            LEFT JOIN contacts c ON LOWER(d.contact_email) = LOWER(c.email)
            WHERE d.id = ?
            """,
            (draft_id,),
        )
        updated = cursor.fetchone()

    conn.close()
    return dict(updated)


@app.post("/api/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Reject a response draft."""
    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE drafts SET status = 'rejected', updated_at = ? WHERE id = ? AND user_id = ?",
            (now_str, draft_id, user["id"]),
        )
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Draft not found.")

        cursor.execute("SELECT contact_email FROM drafts WHERE id = ?", (draft_id,))
        row = cursor.fetchone()
        email = row["contact_email"] if row else None
        db.log_activity(
            conn,
            action="draft_rejected",
            contact_email=email,
            details=f"Draft #{draft_id} marked as rejected.",
            user_id=user["id"],
        )

    conn.close()
    return {"success": True, "draft_id": draft_id, "status": "rejected"}


@app.post("/api/drafts/{draft_id}/send")
@app.post("/api/drafts/{draft_id}/approve-and-send")
def send_approved_draft(draft_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Approve and dispatch a drafted response email as the logged-in user."""
    # 1. Global pause switch check
    if queue_worker.is_global_sending_paused():
        raise HTTPException(status_code=400, detail="All sending is currently paused globally.")

    conn = db.get_db_connection()
    now_str = datetime.utcnow().isoformat()
    cursor = conn.cursor()

    # 2. Fetch draft
    cursor.execute("SELECT * FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user["id"]))
    draft_row = cursor.fetchone()
    if not draft_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Draft not found.")

    # Check test mode safety before proceeding
    if config.TEST_MODE and not config.is_test_email_valid():
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Test mode is enabled but TEST_EMAIL is not configured with a valid email address. Configure a valid test email in Settings before sending.",
        )

    draft = dict(draft_row)
    contact_email = (draft.get("contact_email") or "").strip()
    thread_id = draft.get("thread_id")
    reply_id = draft.get("reply_id")
    body_text = draft.get("body") or ""

    if not body_text.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot send an empty draft response.")

    # 3. Check draft status (double-send protection)
    if draft["status"] == "approved":
        conn.close()
        raise HTTPException(status_code=400, detail="Draft is already approved / sending.")
    if draft["status"] == "sent":
        conn.close()
        raise HTTPException(status_code=400, detail="Draft has already been sent.")
    if draft["status"] == "rejected":
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot send a rejected draft.")

    # 4. Check needs_review edit rule
    if draft["status"] == "needs_review":
        orig_body = (draft.get("original_body") or "").strip()
        current_body = body_text.strip()
        reason_text = (draft.get("reason") or "").lower()
        is_uncertain_draft = "delivery unknown" in reason_text or "uncertain" in reason_text
        if not current_body or (current_body == orig_body and not is_uncertain_draft):
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="A draft flagged as needs_review can only be sent after you have edited the text.",
            )

    # 5. Check contact status (must not be unsubscribed)
    if contact_email:
        cursor.execute("SELECT status FROM contacts WHERE LOWER(email) = LOWER(?) AND user_id = ?", (contact_email, user["id"]))
        c_row = cursor.fetchone()
        if c_row and c_row["status"] == "unsubscribed":
            conn.close()
            raise HTTPException(status_code=400, detail=f"Contact '{contact_email}' is unsubscribed. Outgoing send blocked.")

    # 6. Re-check per-thread reply limit (at send time)
    cursor.execute(
        "SELECT COUNT(*) FROM messages WHERE thread_id = ? AND direction = 'outgoing'",
        (thread_id,),
    )
    sent_replies_count = cursor.fetchone()[0]
    if sent_replies_count >= 3:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Per-thread reply limit reached (maximum 3 replies per thread).",
        )

    # 7. Check user's daily reply limit (live sends only)
    provider = config.PROVIDER.lower()
    if not config.TEST_MODE:
        user_limits = limits.get_user_limits_status(conn, user)
        if user_limits["remaining_reply"] <= 0:
            conn.close()
            raise HTTPException(
                status_code=429,
                detail=f"Daily send cap / sending limit reached for user {user['email']} (0 reply sends remaining today).",
            )

    # 8. Fetch incoming reply message to get Subject and message_id for headers
    cursor.execute("SELECT gmail_message_id, subject FROM messages WHERE id = ?", (reply_id,))
    msg_row = cursor.fetchone()
    in_reply_to_msg_id = msg_row["gmail_message_id"] if msg_row else None
    orig_subject = msg_row["subject"] if msg_row else "Inquiry"
    reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

    # 9. Append mandatory footer (sender name + unsubscribe line)
    final_body = templating.append_footer(body_text)

    # 10. Mark draft 'approved' BEFORE sending (double-send protection)
    with conn:
        conn.execute(
            "UPDATE drafts SET status = 'approved', updated_at = ? WHERE id = ?",
            (now_str, draft_id),
        )

    # 11. Test mode handling
    target_email = config.TEST_EMAIL if config.TEST_MODE else contact_email
    send_subject = f"[TEST] {reply_subject}" if config.TEST_MODE and not reply_subject.startswith("[TEST]") else reply_subject

    # 12. Dispatch via email sender with logged-in user credentials
    sender_instance = email_sender.get_sender(
        provider=provider,
        test_mode=config.TEST_MODE,
        user_id=user["id"],
        sender_email=user["email"],
    )
    try:
        result = sender_instance.send_email(
            to_email=target_email,
            subject=send_subject,
            body=final_body,
            thread_id=thread_id,
            in_reply_to=in_reply_to_msg_id,
        )
    except Exception as e:
        err_str = str(e)
        if queue_worker.is_uncertain_error(err_str):
            reason_msg = "Delivery unknown. Check your Gmail Sent folder before sending again."
            with conn:
                conn.execute(
                    "UPDATE drafts SET status = 'needs_review', reason = ?, updated_at = ? WHERE id = ?",
                    (reason_msg, datetime.utcnow().isoformat(), draft_id),
                )
            conn.close()
            raise HTTPException(status_code=500, detail=f"Delivery uncertain: {err_str}. {reason_msg}")
        else:
            with conn:
                conn.execute(
                    "UPDATE drafts SET status = 'failed', reason = ?, updated_at = ? WHERE id = ?",
                    (err_str, datetime.utcnow().isoformat(), draft_id),
                )
            conn.close()
            raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")

    if not result.success:
        err_msg = result.error or "Send failed"
        if queue_worker.is_uncertain_error(err_msg):
            reason_msg = "Delivery unknown. Check your Gmail Sent folder before sending again."
            with conn:
                conn.execute(
                    "UPDATE drafts SET status = 'needs_review', reason = ?, updated_at = ? WHERE id = ?",
                    (reason_msg, datetime.utcnow().isoformat(), draft_id),
                )
            conn.close()
            raise HTTPException(status_code=500, detail=f"Delivery uncertain: {err_msg}. {reason_msg}")
        else:
            with conn:
                conn.execute(
                    "UPDATE drafts SET status = 'failed', reason = ?, updated_at = ? WHERE id = ?",
                    (err_msg, datetime.utcnow().isoformat(), draft_id),
                )
            conn.close()
            raise HTTPException(status_code=500, detail=f"Failed to send email: {err_msg}")

    # 13. Record success: update daily count (if not test mode), draft status, messages, activity log
    out_msg_id = result.message_id or f"out-{datetime.utcnow().timestamp()}"
    if not config.TEST_MODE:
        limits.record_send(conn, provider=provider, user_id=user["id"], send_type="reply")

    with conn:
        # Mark draft sent
        conn.execute(
            "UPDATE drafts SET status = 'sent', updated_at = ? WHERE id = ?",
            (now_str, draft_id),
        )
        # Mark original incoming reply as handled
        if reply_id:
            conn.execute(
                "UPDATE messages SET processed = 1 WHERE id = ?",
                (reply_id,),
            )
        # Record outgoing message
        conn.execute(
            """
            INSERT INTO messages (
                gmail_message_id, thread_id, contact_email, direction,
                subject, body_text, received_at, category, processed, user_id
            ) VALUES (?, ?, ?, 'outgoing', ?, ?, ?, 'reply', 1, ?)
            """,
            (
                out_msg_id,
                thread_id,
                contact_email,
                reply_subject,
                final_body,
                now_str,
                user["id"],
            ),
        )
        db.log_activity(
            conn,
            action="draft_approved_and_sent",
            contact_email=contact_email,
            details=f"Draft #{draft_id} sent to {target_email} ({'TEST MODE' if config.TEST_MODE else 'live'}). Subject: '{send_subject}'",
            user_id=user["id"],
        )

    conn.close()
    return {
        "success": True,
        "draft_id": draft_id,
        "status": "sent",
        "sent_at": now_str,
        "message_id": out_msg_id,
        "thread_id": thread_id,
    }


@app.get("/api/activity")
def get_activity_log(
    limit: int = Query(200, description="Max entries to return"),
    contact_email: Optional[str] = Query(None, description="Filter by contact email"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve the latest entries from the activity log audit trail for the current user."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    query = "SELECT id, timestamp, action, contact_email, details FROM activity_log WHERE user_id = ?"
    params: List[Any] = [user["id"]]
    if contact_email and contact_email.strip():
        query += " AND LOWER(contact_email) LIKE ?"
        params.append(f"%{contact_email.strip().lower()}%")
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/activity/export")
def export_activity_csv(
    contact_email: Optional[str] = Query(None, description="Filter by contact email"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Response:
    """Download activity log entries for the current user as a CSV file."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    query = "SELECT id, timestamp, action, contact_email, details FROM activity_log WHERE user_id = ?"
    params: List[Any] = [user["id"]]
    if contact_email and contact_email.strip():
        query += " AND LOWER(contact_email) LIKE ?"
        params.append(f"%{contact_email.strip().lower()}%")
    query += " ORDER BY id DESC LIMIT 5000"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "action", "contact_email", "details"])
    for r in rows:
        writer.writerow([r["id"], r["timestamp"], r["action"], r["contact_email"] or "", r["details"] or ""])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=activity_log.csv"},
    )


# --- Backups and Export Endpoints ---

@app.post("/api/backups/create")
def create_backup_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Perform an immediate live database backup to backups/ and prune older files."""
    try:
        filename = db.create_backup()
        conn = db.get_db_connection()
        db.log_activity(conn, action="database_backup_created", details=f"Database backup saved to {filename}", user_id=user["id"])
        conn.close()
        return {"success": True, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")


@app.get("/api/backups")
def list_backups_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """List recent database backups."""
    return db.list_backups()


@app.get("/api/contacts/export")
def export_contacts_csv(user: Dict[str, Any] = Depends(get_current_user)) -> Response:
    """Download full contacts list for current user as a CSV file."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, email, group_tag, status, sent_at, created_at
        FROM contacts
        WHERE user_id = ?
        ORDER BY id ASC
        """,
        (user["id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email", "group_tag", "status", "sent_at", "created_at"])
    for r in rows:
        writer.writerow([r["id"], r["name"], r["email"], r["group_tag"] or "", r["status"], r["sent_at"] or "", r["created_at"]])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts_export.csv"},
    )


@app.post("/api/recipients/{recipient_id}/confirm-resend")
def confirm_resend_recipient(recipient_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Manually confirm and re-queue an uncertain/manual_review campaign recipient."""
    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cr.*, c.email
            FROM campaign_recipients cr
            JOIN contacts c ON cr.contact_id = c.id
            WHERE cr.id = ? AND c.user_id = ?
            """,
            (recipient_id, user["id"]),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Recipient record not found.")

        cursor.execute(
            """
            UPDATE campaign_recipients
            SET status = 'pending', retry_count = 0, next_retry_at = NULL, error = NULL
            WHERE id = ?
            """,
            (recipient_id,),
        )
        db.log_activity(
            conn,
            action="campaign_mail_manual_confirmed",
            contact_email=row["email"],
            details=f"Recipient #{recipient_id} ({row['email']}) manually confirmed for re-send after delivery unknown warning.",
            user_id=user["id"],
        )
    conn.close()
    return {"success": True, "recipient_id": recipient_id, "status": "pending"}


# --- Settings Endpoints ---

@app.get("/api/settings")
def get_settings(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve current system and user settings, sending limits, and footer preview."""
    example_body = "Hi there,\n\nThank you for registering. We look forward to connecting!"
    preview = templating.append_footer(example_body)

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    u = cursor.fetchone()
    user_dict = dict(u) if u else user
    limits_status = limits.get_user_limits_status(conn, user_dict)
    conn.close()

    return {
        "sender_name": config.SENDER_NAME,
        "tone": config.TONE,
        "test_mode": config.TEST_MODE,
        "test_email": config.TEST_EMAIL,
        "daily_cap": user_dict.get("daily_cap", config.DAILY_CAP),
        "default_cap": limits.get_default_daily_cap(user["email"]),
        "effective_cap": limits_status["effective_cap"],
        "warmup_enabled": bool(user_dict.get("warmup_enabled", 1)),
        "warmup_day": user_dict.get("warmup_day", 1),
        "can_use_smtp": limits.can_use_smtp(user["email"]),
        "sending_as": user["email"],
        "pause_seconds": config.PAUSE_SECONDS,
        "unsubscribe_line": config.UNSUBSCRIBE_LINE,
        "footer_preview": preview,
        "ai_provider": getattr(config, "AI_PROVIDER", "anthropic"),
    }


@app.post("/api/settings")
@app.patch("/api/settings")
def update_settings(req: SettingsUpdate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Update runtime configuration settings and persist in database for current user."""
    # Validate test mode and test email combination
    target_test_mode = config.TEST_MODE if req.test_mode is None else bool(req.test_mode)
    target_test_email = (config.TEST_EMAIL if req.test_email is None else req.test_email).strip()
    if target_test_mode and not config.is_valid_email(target_test_email):
        raise HTTPException(
            status_code=400,
            detail="Test mode is enabled but TEST_EMAIL is empty or not a valid email address. Provide a valid email (e.g. user@example.com).",
        )

    conn = db.get_db_connection()
    changes = []
    with conn:
        cursor = conn.cursor()
        if req.sender_name is not None and req.sender_name.strip():
            config.SENDER_NAME = req.sender_name.strip()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value, user_id) VALUES ('sender_name', ?, ?)", (config.SENDER_NAME, user["id"]))
            changes.append(f"sender_name={config.SENDER_NAME}")

        if req.tone is not None and req.tone.strip():
            config.TONE = req.tone.strip()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value, user_id) VALUES ('tone', ?, ?)", (config.TONE, user["id"]))
            changes.append(f"tone={config.TONE}")

        if req.test_mode is not None:
            config.TEST_MODE = bool(req.test_mode)
            cursor.execute("INSERT OR REPLACE INTO settings (key, value, user_id) VALUES ('test_mode', ?, ?)", ("true" if config.TEST_MODE else "false", user["id"]))
            changes.append(f"test_mode={config.TEST_MODE}")

        if req.test_email is not None and req.test_email.strip():
            config.TEST_EMAIL = req.test_email.strip()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value, user_id) VALUES ('test_email', ?, ?)", (config.TEST_EMAIL, user["id"]))
            changes.append(f"test_email={config.TEST_EMAIL}")

        if req.daily_cap is not None and req.daily_cap > 0:
            default_cap = limits.get_default_daily_cap(user["email"])
            if req.daily_cap > default_cap:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail=f"Daily cap cannot exceed the default limit of {default_cap} for domain '{user['email']}'.",
                )
            cursor.execute("UPDATE users SET daily_cap = ? WHERE id = ?", (int(req.daily_cap), user["id"]))
            config.DAILY_CAP = int(req.daily_cap)
            changes.append(f"daily_cap={config.DAILY_CAP}")

        if req.warmup_enabled is not None:
            cursor.execute("UPDATE users SET warmup_enabled = ? WHERE id = ?", (1 if req.warmup_enabled else 0, user["id"]))
            changes.append(f"warmup_enabled={req.warmup_enabled}")

        if req.pause_seconds is not None and req.pause_seconds >= 0:
            config.PAUSE_SECONDS = int(req.pause_seconds)
            cursor.execute("INSERT OR REPLACE INTO settings (key, value, user_id) VALUES ('pause_seconds', ?, ?)", (str(config.PAUSE_SECONDS), user["id"]))
            changes.append(f"pause_seconds={config.PAUSE_SECONDS}")

        if changes:
            db.log_activity(
                conn,
                action="settings_updated",
                details=f"Settings updated: {', '.join(changes)}",
                user_id=user["id"],
            )

    conn.close()
    return get_settings(user)


# ==========================================
# PHASE 10: AUTOPILOT ENDPOINTS
# ==========================================

class AutomationCreateRequest(BaseModel):
    campaign_id: int
    type: str = "followup"
    delay_days: int = 3
    max_followups: int = 1
    send_window_start: str = "09:00"
    send_window_end: str = "18:00"
    subject: Optional[str] = ""
    template: str
    scheduled_at: Optional[str] = None


class AutomationConsentRequest(BaseModel):
    consent: bool = False


@app.get("/api/automations")
def list_automations(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """List all configured automations for current user with campaign metadata."""
    return autopilot.get_automations(user_id=user["id"])


@app.post("/api/automations")
def create_automation_endpoint(req: AutomationCreateRequest, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Create a new automation rule (disabled by default) for current user."""
    try:
        return autopilot.create_automation(req.model_dump(), user_id=user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/automations/{automation_id}/enable")
def enable_automation_endpoint(automation_id: int, req: AutomationConsentRequest, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Enable an automation rule (requires explicit consent confirmation)."""
    if not req.consent:
        raise HTTPException(
            status_code=400,
            detail="Consent confirmation is required to enable an automation rule.",
        )
    try:
        return autopilot.enable_automation(automation_id, consent=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/automations/{automation_id}/disable")
def disable_automation_endpoint(automation_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Disable an active automation rule."""
    return autopilot.disable_automation(automation_id)


@app.get("/api/automations/{automation_id}/preview")
def preview_automation_endpoint(automation_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Preview which contacts qualify now and which are skipped with detailed reasons."""
    try:
        return autopilot.preview_automation(automation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/automations/run-cycle")
def run_automation_cycle_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Manually invoke an autopilot evaluation and send cycle."""
    return autopilot.run_autopilot_cycle()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
