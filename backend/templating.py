"""Plain-code personalization, template rendering, and mandatory footer appending."""

import re
from typing import Any, Dict, Optional, Tuple

import config

PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def append_footer(body: str, sender_name: Optional[str] = None, unsubscribe_line: Optional[str] = None) -> str:
    """Ensure outgoing email body ends with sender name and mandatory unsubscribe line."""
    name = sender_name or config.SENDER_NAME
    unsub = unsubscribe_line or config.UNSUBSCRIBE_LINE

    trimmed = body.rstrip()

    # Check if footer components are already present
    has_sender = name.lower() in trimmed.lower()
    has_unsub = "unsubscribe" in trimmed.lower()

    footer_parts = []
    if not has_sender:
        footer_parts.append(f"Best regards,\n{name}")

    if not has_unsub:
        footer_parts.append(f"---\n{unsub}")

    if footer_parts:
        return f"{trimmed}\n\n" + "\n\n".join(footer_parts)
    return trimmed


def render_email_body(
    mode: str,
    template: str,
    contact_name: str,
    contact_extra: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Renders email body according to one of the 3 campaign modes:
    - 'same': replaces {name} with contact_name.
    - 'fields': replaces any {column_name} using CSV columns. Skips if any placeholder is missing or blank.
    - 'per_person': uses contact's own 'body' value from CSV extra data. Skips if missing.

    Returns:
        (rendered_body_with_footer, None) on success.
        (None, skip_reason) on failure/skip.
    """
    extra = contact_extra or {}
    mode = (mode or "").lower()

    if mode == "same":
        # Replace only {name} (case-insensitive)
        body = re.sub(r"\{name\}", contact_name, template, flags=re.IGNORECASE)
        # Check if any remaining unfilled placeholders exist
        return append_footer(body), None

    elif mode == "fields":
        # Build normalized case-insensitive dictionary
        lookup: Dict[str, str] = {"name": contact_name}
        for k, v in extra.items():
            if v is not None:
                lookup[k.strip().lower()] = str(v).strip()

        # Find all placeholders in template
        matches = PLACEHOLDER_REGEX.findall(template)
        rendered = template

        for key in matches:
            norm_key = key.lower()
            val = lookup.get(norm_key)
            if val is None or val == "":
                return None, f"Missing placeholder: {{{key}}}"

            rendered = re.sub(rf"\{{{re.escape(key)}\}}", val, rendered)

        return append_footer(rendered), None

    elif mode == "per_person":
        # Look for 'body' in extra dictionary (case-insensitive)
        body_val = None
        for k, v in extra.items():
            if k.strip().lower() == "body":
                body_val = v
                break

        if not body_val or not str(body_val).strip():
            return None, "Missing personal body in CSV"

        body_str = str(body_val).strip()
        # Optionally replace {name} if contact included it in their custom body
        body_str = re.sub(r"\{name\}", contact_name, body_str, flags=re.IGNORECASE)
        return append_footer(body_str), None

    else:
        return None, f"Unknown campaign mode: '{mode}'"
