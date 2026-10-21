"""OAuth 2.0 authentication, PKCE, signed session cookies, and multi-user token storage."""

import base64
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, Optional, Tuple

import requests
import config

logger = logging.getLogger("mail_agent.auth")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://openidconnect.googleapis.com/v1/userinfo"


def generate_pkce_pair() -> Tuple[str, str]:
    """Generate high-entropy code_verifier and S256 code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def sign_token(payload: Dict[str, Any]) -> str:
    """Create a tamper-proof HMAC-SHA256 signed token."""
    raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_data = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    sig = hmac.new(config.SESSION_SECRET.encode("utf-8"), b64_data.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"


def verify_token(signed_token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Verify HMAC-SHA256 signature and return decoded payload if valid and unexpired."""
    if not signed_token or "." not in signed_token:
        return None
    try:
        b64_data, sig = signed_token.rsplit(".", 1)
        expected_sig = hmac.new(
            config.SESSION_SECRET.encode("utf-8"),
            b64_data.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # Restore padding
        padding = "=" * (-len(b64_data) % 4)
        raw_json = base64.urlsafe_b64decode(b64_data + padding).decode("utf-8")
        payload = json.loads(raw_json)

        exp = payload.get("exp")
        if exp and exp < time.time():
            return None
        return payload
    except Exception:
        return None


def create_session_cookie(user_id: int, email: str, days: int = 14) -> str:
    """Generate a signed session cookie value for the authenticated user."""
    payload = {
        "uid": user_id,
        "email": email,
        "exp": int(time.time() + (days * 86400)),
    }
    return sign_token(payload)


def find_google_credentials_file() -> Optional[Path]:
    """Locate Google OAuth credentials.json in backend or project root."""
    candidates = [
        config.BASE_DIR / "credentials.json",
        config.BASE_DIR.parent / "credentials.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def get_oauth_client_config() -> Dict[str, Any]:
    """
    Extract client_id, client_secret, auth_uri, and token_uri from credentials.json
    or environment variables.
    """
    cred_file = find_google_credentials_file()
    if cred_file:
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            web = data.get("web") or data.get("installed")
            if web:
                return {
                    "client_id": web.get("client_id", "").strip(),
                    "client_secret": web.get("client_secret", "").strip(),
                    "auth_uri": web.get("auth_uri", AUTH_URI),
                    "token_uri": web.get("token_uri", TOKEN_URI),
                    "type": "web" if "web" in data else "installed",
                }
        except Exception as e:
            logger.warning(f"Error reading credentials file {cred_file}: {e}")

    # Fallback to environment variables
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "type": "env",
        }

    return {
        "client_id": "",
        "client_secret": "",
        "auth_uri": AUTH_URI,
        "token_uri": TOKEN_URI,
        "type": "missing",
    }


def build_authorization_url(state: str, code_challenge: str) -> str:
    """Build the Google OAuth 2.0 authorization URL with PKCE and state."""
    cfg = get_oauth_client_config()
    if not cfg["client_id"]:
        raise ValueError(
            "Google credentials not configured. Please place a 'Web application' credentials.json in backend/ "
            "with Authorized redirect URI: http://localhost:8000/api/auth/callback."
        )

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": config.OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    encoded_params = requests.compat.urlencode(params)
    return f"{cfg['auth_uri']}?{encoded_params}"


def exchange_code_for_tokens(code: str, code_verifier: str) -> Dict[str, Any]:
    """Exchange authorization code and PKCE verifier for Google tokens."""
    cfg = get_oauth_client_config()
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": config.OAUTH_REDIRECT_URI,
    }
    res = requests.post(cfg["token_uri"], data=data, timeout=15)
    if not res.ok:
        logger.error("Token exchange failed: %s %s", res.status_code, res.text)
        raise RuntimeError(f"Google token exchange failed ({res.status_code})")
    return res.json()


def fetch_google_user_info(access_token: str) -> Dict[str, Any]:
    """Fetch user profile details (id, email, name, picture) using OAuth access token."""
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get(USERINFO_URI, headers=headers, timeout=10)
    if not res.ok:
        raise RuntimeError(f"Failed to fetch user info from Google ({res.status_code})")
    return res.json()


def save_user_tokens(user_id: int, token_dict: Dict[str, Any]) -> None:
    """Securely store tokens in database and disk cache. Never log token contents."""
    cfg = get_oauth_client_config()
    token_dict["client_id"] = cfg["client_id"]
    token_dict["client_secret"] = cfg["client_secret"]
    token_dict["token_uri"] = cfg["token_uri"]

    # 1. Dual persistence: Save into SQLite user_tokens table
    try:
        import db
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tokens_json FROM user_tokens WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and "refresh_token" not in token_dict:
            try:
                existing_db = json.loads(row[0])
                if "refresh_token" in existing_db:
                    token_dict["refresh_token"] = existing_db["refresh_token"]
            except Exception:
                pass

        now_str = datetime.utcnow().isoformat()
        with conn:
            conn.execute(
                """
                INSERT INTO user_tokens (user_id, tokens_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    tokens_json = excluded.tokens_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(token_dict), now_str),
            )
        conn.close()
    except Exception as e:
        logger.warning(f"Could not persist tokens to database for user {user_id}: {e}")

    # 2. Dual persistence: Write to disk cache if directory is writable
    try:
        config.ensure_tokens_dir()
        token_file = config.TOKENS_DIR / f"{user_id}.json"
        if token_file.exists() and "refresh_token" not in token_dict:
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    existing_file = json.load(f)
                if "refresh_token" in existing_file:
                    token_dict["refresh_token"] = existing_file["refresh_token"]
            except Exception:
                pass

        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(token_dict, f)

        # Restrict permissions on POSIX
        try:
            os.chmod(token_file, 0o600)
        except Exception:
            pass
    except OSError as e:
        logger.warning(f"Could not write token file for user {user_id}: {e}")


def get_user_credentials(user_id: int) -> Optional[Any]:
    """Load Google OAuth credentials for user, automatically refreshing expired tokens."""
    token_dict: Optional[Dict[str, Any]] = None
    token_file = config.TOKENS_DIR / f"{user_id}.json"

    # Try disk cache first
    if token_file.exists():
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                token_dict = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read token file for user {user_id}: {e}")

    # Fallback to database user_tokens table
    if not token_dict:
        try:
            import db
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT tokens_json FROM user_tokens WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                token_dict = json.loads(row[0])
        except Exception as e:
            logger.warning(f"Failed to load tokens from DB for user {user_id}: {e}")

    if not token_dict:
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_info(token_dict, SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                updated_dict = json.loads(creds.to_json())
                save_user_tokens(user_id, updated_dict)
            else:
                return None
        return creds
    except Exception as e:
        logger.warning(f"Failed to load or refresh credentials for user {user_id}: {e}")
        return None
