"""Email sender adapters for Gmail API, SMTP service, and Fake test recording."""

import base64
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from pathlib import Path
import smtplib
import time
from typing import Any, Dict, List, Optional
import uuid

import config

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

_CACHED_GMAIL_SERVICE = None


@dataclass
class SendResult:
    """Outcome of an email dispatch operation."""
    success: bool
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    error: Optional[str] = None
    is_quota_error: bool = False


class BaseEmailSender:
    """Abstract interface for email dispatch providers."""

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> SendResult:
        raise NotImplementedError

    def get_daily_cap(self) -> int:
        raise NotImplementedError


class FakeEmailSender(BaseEmailSender):
    """Test recorder sender that stores dispatched emails in memory without sending network requests."""

    def __init__(self, daily_cap: int = 2000, should_fail: bool = False):
        self.daily_cap = daily_cap
        self.should_fail = should_fail
        self.sent_emails: List[Dict[str, Any]] = []

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> SendResult:
        if self.should_fail:
            return SendResult(success=False, error="Simulated network failure")

        msg_id = f"fake-msg-{uuid.uuid4().hex[:12]}"
        thd_id = thread_id or f"fake-thd-{uuid.uuid4().hex[:12]}"
        self.sent_emails.append(
            {
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "message_id": msg_id,
                "thread_id": thd_id,
                "in_reply_to": in_reply_to,
                "references": in_reply_to,
                "timestamp": time.time(),
            }
        )
        return SendResult(success=True, message_id=msg_id, thread_id=thd_id)

    def get_daily_cap(self) -> int:
        return self.daily_cap


class SMTPEmailSender(BaseEmailSender):
    """Dispatches outgoing messages through a standard SMTP relay (e.g. Brevo, SendGrid, Amazon SES)."""

    def __init__(self, sender_email: Optional[str] = None):
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.user = config.SMTP_USER
        self.password = config.SMTP_PASSWORD
        self.use_tls = config.SMTP_USE_TLS
        self.sender_name = config.SENDER_NAME
        self.sender_email = sender_email

    def get_daily_cap(self) -> int:
        return config.SMTP_DAILY_CAP

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> SendResult:
        if not self.host:
            return SendResult(success=False, error="SMTP_HOST is not configured in environment or .env.")

        # SMTP provider is only allowed when sender's From address is on a custom domain (non-@gmail.com)
        from limits import can_use_smtp
        sender_addr = self.sender_email or self.user or "noreply@event.local"
        if sender_addr and not can_use_smtp(sender_addr):
            return SendResult(
                success=False,
                error="SMTP sending is only permitted for custom domain addresses (non-@gmail.com) to ensure proper SPF/DKIM delivery.",
            )

        msg = MIMEMultipart()
        msg["From"] = f"{self.sender_name} <{sender_addr}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg_id = f"<{uuid.uuid4()}@{self.host or 'mail-agent.local'}>"
        msg["Message-ID"] = msg_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            if self.port == 465:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=15)

            with server:
                if self.use_tls and self.port != 465:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)

            return SendResult(success=True, message_id=msg_id, thread_id=thread_id or msg_id)
        except Exception as e:
            return SendResult(success=False, error=f"SMTP Error: {str(e)}")


def get_gmail_service(user_id: Optional[int] = None, force_refresh: bool = False):
    """
    Build an authenticated Google Gmail API service client.
    If user_id is provided, loads the per-user credentials from tokens/{user_id}.json.
    Otherwise falls back to token.json for backward compatibility.
    """
    global _CACHED_GMAIL_SERVICE
    if user_id is None and _CACHED_GMAIL_SERVICE is not None and not force_refresh:
        return _CACHED_GMAIL_SERVICE

    from googleapiclient.discovery import build

    if user_id is not None:
        import auth
        creds = auth.get_user_credentials(user_id)
        if not creds:
            raise RuntimeError(
                f"Google OAuth credentials missing or expired for user {user_id}. Please re-authenticate."
            )
        return build("gmail", "v1", credentials=creds)

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    token_file = config.BASE_DIR / "token.json"
    credentials_file = config.BASE_DIR / "credentials.json"
    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
        # Verify read scope
        if creds.scopes and not set(GMAIL_SCOPES).issubset(set(creds.scopes)):
            raise RuntimeError(
                "Stored Gmail credentials in token.json are missing read permissions ('gmail.readonly'). "
                "Please delete backend/token.json and authenticate again to grant read access."
            )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif credentials_file.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            # Check if any user token exists in tokens/
            token_files = list(config.TOKENS_DIR.glob("*.json"))
            if token_files:
                try:
                    uid = int(token_files[0].stem)
                    import auth
                    creds = auth.get_user_credentials(uid)
                except Exception:
                    creds = None
            if not creds:
                raise FileNotFoundError(
                    "Gmail API credentials.json or token.json not found in backend directory. "
                    "Sign in with Google to enable Gmail provider."
                )

        if token_file.parent.exists() and creds:
            try:
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
            except Exception:
                pass

    service = build("gmail", "v1", credentials=creds)
    if user_id is None:
        _CACHED_GMAIL_SERVICE = service
    return service


class GmailEmailSender(BaseEmailSender):
    """Dispatches outgoing messages via Google Gmail API."""

    def __init__(self, user_id: Optional[int] = None, sender_email: Optional[str] = None):
        self.user_id = user_id
        self.sender_email = sender_email
        self.sender_name = config.SENDER_NAME

    def get_daily_cap(self) -> int:
        return config.GMAIL_DAILY_CAP

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> SendResult:
        try:
            service = get_gmail_service(user_id=self.user_id)
            msg = MIMEMultipart()
            msg["to"] = to_email
            msg["subject"] = subject
            if self.sender_email:
                msg["from"] = f"{self.sender_name} <{self.sender_email}>" if self.sender_name else self.sender_email
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                msg["References"] = in_reply_to
            msg.attach(MIMEText(body, "plain", "utf-8"))

            raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            body_dict = {"raw": raw_msg}
            if thread_id:
                body_dict["threadId"] = thread_id

            sent = service.users().messages().send(userId="me", body=body_dict).execute()

            return SendResult(
                success=True,
                message_id=sent.get("id"),
                thread_id=sent.get("threadId"),
            )
        except Exception as e:
            err_str = str(e)
            is_quota = any(term in err_str.lower() for term in [
                "ratelimit", "rate_limit", "user_rate_limit", "quota", "dailylimit", "429"
            ])
            return SendResult(success=False, error=f"Gmail API Error: {err_str}", is_quota_error=is_quota)


_EMAIL_SENDER_OVERRIDE: Optional[BaseEmailSender] = None


def set_email_sender_override(sender: Optional[BaseEmailSender]) -> None:
    """Allow test suites to inject a mock email sender globally."""
    global _EMAIL_SENDER_OVERRIDE
    _EMAIL_SENDER_OVERRIDE = sender


def get_sender(
    provider: str = "",
    test_mode: bool = False,
    fake_instance: Optional[BaseEmailSender] = None,
    user_id: Optional[int] = None,
    sender_email: Optional[str] = None,
) -> BaseEmailSender:
    """Return appropriate email sender adapter based on configuration."""
    if _EMAIL_SENDER_OVERRIDE is not None:
        return _EMAIL_SENDER_OVERRIDE
    if fake_instance is not None:
        return fake_instance

    prov = (provider or config.PROVIDER).lower()
    if prov == "smtp":
        return SMTPEmailSender(sender_email=sender_email)
    return GmailEmailSender(user_id=user_id, sender_email=sender_email)
