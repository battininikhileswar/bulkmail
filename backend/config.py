import os
import re
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if available
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

# Project settings
SENDER_NAME = os.getenv("SENDER_NAME", "Event Coordinator")
TONE = os.getenv("TONE", "friendly and professional")
PAUSE_SECONDS = int(os.getenv("PAUSE_SECONDS", 5))
PROVIDER = os.getenv("EMAIL_PROVIDER", "gmail")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() in ("true", "1", "yes")
TEST_EMAIL = os.getenv("TEST_EMAIL", "").strip()


def is_valid_email(email: str) -> bool:
    """Validate standard email address syntax."""
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def is_test_email_valid() -> bool:
    """Return True if TEST_EMAIL is a valid address when TEST_MODE is active."""
    if not TEST_MODE:
        return True
    return is_valid_email(TEST_EMAIL)

# Provider daily caps
GMAIL_DAILY_CAP = int(os.getenv("GMAIL_DAILY_CAP", 400))
SMTP_DAILY_CAP = int(os.getenv("SMTP_DAILY_CAP", 2000))
DAILY_CAP = GMAIL_DAILY_CAP if PROVIDER.lower() == "gmail" else SMTP_DAILY_CAP

# SMTP Settings
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

# Standard Unsubscribe line
UNSUBSCRIBE_LINE = os.getenv("UNSUBSCRIBE_LINE", "To unsubscribe from these communications, reply with 'UNSUBSCRIBE'.")

# Watcher settings
WATCHER_POLL_INTERVAL_SECONDS = int(os.getenv("WATCHER_POLL_INTERVAL", 10))

# AI Provider settings
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").strip().lower()

# AI Provider API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# AI Model configurations per provider
ANTHROPIC_CLASSIFIER_MODEL = os.getenv("ANTHROPIC_CLASSIFIER_MODEL", "claude-haiku-5-5")
ANTHROPIC_RESPONDER_MODEL = os.getenv("ANTHROPIC_RESPONDER_MODEL", "claude-sonnet-5-5")

GEMINI_CLASSIFIER_MODEL = os.getenv("GEMINI_CLASSIFIER_MODEL", "gemini-1.5-flash")
GEMINI_RESPONDER_MODEL = os.getenv("GEMINI_RESPONDER_MODEL", "gemini-1.5-flash")

GROQ_CLASSIFIER_MODEL = os.getenv("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")
GROQ_RESPONDER_MODEL = os.getenv("GROQ_RESPONDER_MODEL", "llama-3.3-70b-versatile")

# Backward compatibility model aliases
AI_MODEL = ANTHROPIC_CLASSIFIER_MODEL
RESPONDER_MODEL = ANTHROPIC_RESPONDER_MODEL


def get_ai_model(provider: str = "", purpose: str = "classifier") -> str:
    """Return configured model for provider and purpose."""
    prov = (provider or AI_PROVIDER).strip().lower()
    is_responder = "responder" in purpose.lower() or "draft" in purpose.lower()
    if prov == "gemini":
        return GEMINI_RESPONDER_MODEL if is_responder else GEMINI_CLASSIFIER_MODEL
    elif prov == "groq":
        return GROQ_RESPONDER_MODEL if is_responder else GROQ_CLASSIFIER_MODEL
    else:
        return ANTHROPIC_RESPONDER_MODEL if is_responder else ANTHROPIC_CLASSIFIER_MODEL


# Database & Facts settings
DB_PATH = BASE_DIR / "contacts.db"
FACTS_PATH = BASE_DIR / "facts.json"

# Auth & Session Settings (Phase 11)
DEFAULT_SESSION_SECRET = "super-secret-mail-assistant-session-key-change-in-env"
SESSION_SECRET = os.getenv("SESSION_SECRET", DEFAULT_SESSION_SECRET)
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
TOKENS_DIR = BASE_DIR / "tokens"
TOKENS_DIR.mkdir(parents=True, exist_ok=True)


def is_session_secret_default_or_missing() -> bool:
    """Return True if SESSION_SECRET is not set in .env or is using the default placeholder."""
    sec = os.getenv("SESSION_SECRET", "").strip()
    return not sec or sec == DEFAULT_SESSION_SECRET

