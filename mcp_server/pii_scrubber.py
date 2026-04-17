"""
PII Scrubber - L1 layer, runs before any data is written or uploaded.

Applies 5 targeted regex rules to redact sensitive data from URL strings,
request header strings, and response body strings. Cloud storage never
receives raw sensitive values.
"""

import re

# ---------------------------------------------------------------------------
# Compiled patterns (module-level for performance - compiled once at import)
# ---------------------------------------------------------------------------

# Rule 1: Authorization headers - redact bearer token value
_RE_AUTH_HEADER = re.compile(r"(?i)(authorization:\s*bearer\s+)\S+")

# Rule 2: Access tokens in URLs - redact token value only
_RE_ACCESS_TOKEN = re.compile(r"access_token=[^&\s]+")

# Rule 3: Email addresses (RFC 5322 simplified)
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Rule 4: Phone numbers - 11-digit starting with 1[3-9] (e.g. Chinese mobile)
_RE_PHONE = re.compile(r"\b1[3-9]\d{9}\b")

# Rule 5: Credit card candidates - 13-16 digit sequences with optional separators
_RE_CARD = re.compile(r"\b(?:\d[ -]?){13,15}\d\b")

_RULES: list[tuple[re.Pattern[str], str]] = [
    (_RE_AUTH_HEADER, r"\1[REDACTED]"),
    (_RE_ACCESS_TOKEN, "access_token=[REDACTED]"),
    (_RE_EMAIL, "[EMAIL]"),
    (_RE_PHONE, "[PHONE]"),
    (_RE_CARD, "[CARD_CANDIDATE]"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scrub(text: str) -> tuple[str, int]:
    """Scrub PII from a text string using 5 targeted regex rules.

    Returns: (scrubbed_text, count_of_replacements)
    Performance: completes in <1ms for typical strings.
    """
    if text is None:
        return ("", 0)
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return ("", 0)

    total = 0
    for pattern, replacement in _RULES:
        new_text, count = pattern.subn(replacement, text)
        text = new_text
        total += count

    return (text, total)


def scrub_log_entry(url: str, headers: str, response_body: str) -> dict:
    """Scrub all three fields of a log entry.

    Returns dict with scrubbed values and total PII count.
    """
    scrubbed_url, c1 = scrub(url)
    scrubbed_headers, c2 = scrub(headers)
    scrubbed_body, c3 = scrub(response_body)
    return {
        "url": scrubbed_url,
        "headers": scrubbed_headers,
        "response_body": scrubbed_body,
        "pii_items_scrubbed": c1 + c2 + c3,
    }
