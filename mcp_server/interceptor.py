"""
HTTP Interceptor - L1 layer.

Proxies every outbound HTTP request made by the AI Agent, captures metadata
for the operation log, and runs the PII scrubber before anything is written
to local storage or uploaded to the cloud.

Performance requirement: overhead added by interception must be <5ms (P99).
"""

import logging
import re
import ssl
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from mcp_server import pii_scrubber

logger = logging.getLogger(__name__)

# Matches a path segment that is entirely numeric (a resource ID).
_NUMERIC_ID_RE = re.compile(r"(?<=/)\d+(?=/|$)")

# Ordered list of (hostname-fragment, platform-key) pairs.
_PLATFORM_RULES: list[tuple[str, str]] = [
    ("myshopify.com", "shopify"),
    ("graph.facebook.com", "meta"),
    ("api.facebook.com", "meta"),
    ("business.facebook.com", "meta"),
    ("api.stripe.com", "stripe"),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_platform(url: str) -> str:
    """Return the platform key for the given URL hostname."""
    hostname = urlparse(url).netloc.lower()
    for fragment, platform in _PLATFORM_RULES:
        if fragment in hostname:
            return platform
    return "generic"


def _normalize_endpoint(url: str) -> str:
    """Replace every numeric path segment with the {id} placeholder.

    Example:
        /admin/api/2024-01/products/123456/variants/789
        -> /admin/api/2024-01/products/{id}/variants/{id}
    """
    path = urlparse(url).path
    return _NUMERIC_ID_RE.sub("{id}", path)


def _extract_params_schema(body: Any) -> dict[str, None] | None:
    """Return a dict of body field names mapped to None (values are never stored).

    Returns None for non-dict bodies (raw strings, None, etc.).
    """
    if not isinstance(body, dict):
        return None
    return {key: None for key in body}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def intercept(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | dict[str, Any] | None = None,
    session_id: str = "",
) -> tuple[httpx.Response, dict[str, Any]]:
    """Proxy an HTTP request and return the response together with a log entry.

    Steps performed (in order):
    1. PII-scrub url, headers string (before any write).
    2. Extract endpoint_pattern, params_schema, platform.
    3. Forward request via httpx.AsyncClient (timeout=30s, SSL verified).
    4. Measure response time, PII-scrub response body.
    5. Build and return the log entry dict.

    On error: populate log_entry with an appropriate response_status, then
    re-raise the original exception so the Agent always sees the failure.

    Returns:
        (httpx.Response, log_entry dict)
    """
    if headers is None:
        headers = {}

    # --- Metadata extraction ---
    platform = _detect_platform(url)
    endpoint_pattern = _normalize_endpoint(url)
    params_schema = _extract_params_schema(body)

    # --- Build the log entry skeleton (status and PII-scrubbed fields filled in below) ---
    log_entry: dict[str, Any] = {
        "session_id": session_id,
        "platform": platform,
        "method": method.upper(),
        "endpoint_pattern": endpoint_pattern,
        "params_schema": params_schema,
        "response_status": 0,
        "response_time_ms": 0,
        "raw_url": url,
    }

    # --- Build request kwargs ---
    request_kwargs: dict[str, Any] = {
        "headers": headers,
        "follow_redirects": True,
    }
    if isinstance(body, dict):
        request_kwargs["json"] = body
    elif isinstance(body, str) and body:
        request_kwargs["content"] = body.encode()

    # --- Forward the request ---
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
            response = await client.request(method.upper(), url, **request_kwargs)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # PII-scrub url, headers, and response body before writing to log.
        scrubbed = pii_scrubber.scrub_log_entry(url, str(headers), response.text)
        log_entry["raw_url"] = scrubbed["url"]
        log_entry["response_body"] = scrubbed["response_body"]
        log_entry["pii_items_scrubbed"] = scrubbed["pii_items_scrubbed"]

        log_entry["response_status"] = response.status_code
        log_entry["response_time_ms"] = max(elapsed_ms, 1)

        return response, log_entry

    except httpx.TimeoutException:
        log_entry["response_status"] = 408
        log_entry["response_time_ms"] = int((time.monotonic() - start) * 1000)
        logger.warning("Request timed out: %s %s", method, url)
        raise

    except httpx.ConnectError as exc:
        # Distinguish SSL handshake failures from generic connection errors.
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, ssl.SSLError):
            log_entry["response_status"] = 495
            logger.warning("SSL error for %s %s: %s", method, url, exc)
        else:
            log_entry["response_status"] = 503
            logger.warning("Connection error: %s %s - %s", method, url, exc)
        log_entry["response_time_ms"] = int((time.monotonic() - start) * 1000)
        raise

    except Exception as exc:
        log_entry["response_status"] = 0
        log_entry["response_time_ms"] = int((time.monotonic() - start) * 1000)
        logger.error("Unexpected interceptor error: %s %s - %s", method, url, exc)
        raise
