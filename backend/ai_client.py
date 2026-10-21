"""Unified AI Client supporting Anthropic, Google Gemini, and Groq providers."""

import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import anthropic
import requests

import config
import db

logger = logging.getLogger("mail_agent.ai_client")

# Overrides for testing
_CLIENT_OVERRIDE = None
_HTTP_SESSION_OVERRIDE = None

# Retry delays in seconds (attempt 1, attempt 2)
RETRY_DELAYS = [0.05, 0.1]


class RateLimitError(Exception):
    """Raised when an AI provider returns 429 rate limit error."""
    pass


class TemporaryAPIError(Exception):
    """Raised when an AI provider returns temporary 5xx error or connection drop."""
    pass


def set_client_override(client: Any) -> None:
    """Inject mock client for Anthropic testing."""
    global _CLIENT_OVERRIDE
    _CLIENT_OVERRIDE = client


def set_http_session_override(session: Any) -> None:
    """Inject mock HTTP session for Gemini/Groq testing."""
    global _HTTP_SESSION_OVERRIDE
    _HTTP_SESSION_OVERRIDE = session


def _call_anthropic(
    system_prompt: str,
    user_text: str,
    max_tokens: int,
    model: str,
    client_override: Any = None,
) -> Tuple[str, int, int]:
    """Execute Anthropic API call."""
    if client_override is not None:
        client = client_override
    elif _CLIENT_OVERRIDE is not None:
        client = _CLIENT_OVERRIDE
    else:
        api_key = config.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")
        client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_text}],
    )

    raw_text = ""
    if hasattr(response, "content") and response.content:
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text
            elif isinstance(block, dict) and "text" in block:
                raw_text += block["text"]

    input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0) or 0
    output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0) or 0
    return raw_text, input_tokens, output_tokens


def _call_gemini(
    system_prompt: str,
    user_text: str,
    max_tokens: int,
    model: str,
) -> Tuple[str, int, int]:
    """Execute Google Gemini API call via REST."""
    api_key = config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_text}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}],
        },
        "generationConfig": {
            "maxOutputTokens": max_tokens,
        },
    }

    http = _HTTP_SESSION_OVERRIDE or requests
    resp = http.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    if resp.status_code == 429:
        raise RateLimitError(f"Gemini API rate limit exceeded (HTTP 429): {resp.text}")
    elif resp.status_code >= 500:
        raise TemporaryAPIError(f"Gemini API server error (HTTP {resp.status_code}): {resp.text}")
    elif resp.status_code >= 400:
        raise RuntimeError(f"Gemini API error (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    candidates = data.get("candidates", [])
    raw_text = ""
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        for p in parts:
            if isinstance(p, dict) and "text" in p:
                raw_text += p["text"]

    usage = data.get("usageMetadata", {})
    input_tokens = usage.get("promptTokenCount", 0) or 0
    output_tokens = usage.get("candidatesTokenCount", 0) or 0
    return raw_text, input_tokens, output_tokens


def _call_groq(
    system_prompt: str,
    user_text: str,
    max_tokens: int,
    model: str,
) -> Tuple[str, int, int]:
    """Execute Groq API call via OpenAI-compatible REST endpoint."""
    api_key = config.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured.")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "max_tokens": max_tokens,
    }

    http = _HTTP_SESSION_OVERRIDE or requests
    resp = http.post(
        url,
        json=payload,
        headers=headers,
        timeout=30,
    )

    if resp.status_code == 429:
        raise RateLimitError(f"Groq API rate limit exceeded (HTTP 429): {resp.text}")
    elif resp.status_code >= 500:
        raise TemporaryAPIError(f"Groq API server error (HTTP {resp.status_code}): {resp.text}")
    elif resp.status_code >= 400:
        raise RuntimeError(f"Groq API error (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    choices = data.get("choices", [])
    raw_text = ""
    if choices:
        msg = choices[0].get("message", {})
        raw_text = msg.get("content", "")

    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0) or 0
    output_tokens = usage.get("completion_tokens", 0) or 0
    return raw_text, input_tokens, output_tokens


def complete(
    system_prompt: str,
    user_text: str,
    max_tokens: int = 350,
    purpose: str = "ai_call",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    client_override: Any = None,
) -> str:
    """
    Unified completion function across configured AI providers (anthropic, gemini, groq).
    Retries up to 2 times on rate limits or temporary errors.
    Logs usage into the ai_usage table.
    """
    active_provider = (provider or getattr(config, "AI_PROVIDER", "anthropic")).strip().lower()

    # Determine model if not specified
    if not model:
        model = config.get_ai_model(active_provider, purpose=purpose)

    max_retries = 2
    last_err: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            if active_provider == "gemini":
                text, in_tok, out_tok = _call_gemini(
                    system_prompt=system_prompt,
                    user_text=user_text,
                    max_tokens=max_tokens,
                    model=model,
                )
            elif active_provider == "groq":
                text, in_tok, out_tok = _call_groq(
                    system_prompt=system_prompt,
                    user_text=user_text,
                    max_tokens=max_tokens,
                    model=model,
                )
            else:  # anthropic default
                text, in_tok, out_tok = _call_anthropic(
                    system_prompt=system_prompt,
                    user_text=user_text,
                    max_tokens=max_tokens,
                    model=model,
                    client_override=client_override,
                )

            # Log usage in database (either tokens or call count only)
            try:
                conn = db.get_db_connection()
                db.log_ai_usage(
                    conn,
                    purpose=purpose,
                    input_tokens=in_tok if in_tok > 0 else 0,
                    output_tokens=out_tok if out_tok > 0 else 0,
                )
                conn.close()
            except Exception as log_err:
                logger.warning(f"Could not record AI usage in ai_usage table: {log_err}")

            return text

        except (RateLimitError, TemporaryAPIError, requests.RequestException) as err:
            last_err = err
            logger.warning(f"Temporary AI error (provider={active_provider}, attempt {attempt+1}/{max_retries+1}): {err}")
            if attempt < max_retries:
                delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else 0.1
                time.sleep(delay)
                continue
            raise RateLimitError(f"{active_provider.capitalize()} API rate limit / temporary failure after {max_retries} retries: {err}") from err

        except Exception as err:
            # Check for Anthropic SDK rate limit exception or status 429
            err_str = str(err).lower()
            if "rate" in err_str and "limit" in err_str or "429" in err_str or "503" in err_str:
                last_err = err
                logger.warning(f"Temporary AI error (provider={active_provider}, attempt {attempt+1}/{max_retries+1}): {err}")
                if attempt < max_retries:
                    delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else 0.1
                    time.sleep(delay)
                    continue
                raise RateLimitError(f"{active_provider.capitalize()} API rate limit / temporary failure after {max_retries} retries: {err}") from err

            # Non-retryable error (e.g., missing API key, invalid request)
            raise err

    if last_err:
        raise last_err
    return ""
