"""
Log Shipper - L2 layer.

Batches pending SQLite queue entries and uploads them to the Guardrly API
backend. Runs as a background asyncio task inside the MCP Server process.

Security: every upload request is signed with HMAC-SHA256.
Resilience: network errors trigger exponential backoff; the MCP Server is
never blocked or crashed by shipper failures.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import httpx

from mcp_server import local_queue

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [1, 4, 16]  # seconds - exponential backoff, max 3 retries


def _get_api_url() -> str:
    return os.getenv("GUARDRLY_API_URL", "https://api.guardrly.com").rstrip("/")


def _get_api_key() -> str:
    return os.getenv("GUARDRLY_API_KEY", "")


def _get_hmac_secret() -> str:
    return os.getenv("HMAC_SECRET", "")


def _sign_request(method: str, path: str, body_bytes: bytes) -> tuple[str, str]:
    """Return (timestamp_str, hmac_hex) for the given request."""
    timestamp = str(int(time.time() * 1000))
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    message = f"{method}{path}{timestamp}{body_hash}".encode()
    secret = _get_hmac_secret()
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return timestamp, signature


async def ship_pending_logs() -> dict[str, int]:
    """
    Fetch pending logs from local SQLite queue and upload to API.
    Returns: {shipped: int, failed: int, skipped: int}
    Never raises - all errors are caught and logged.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("GUARDRLY_API_KEY not set - skipping log upload.")
        return {"shipped": 0, "failed": 0, "skipped": 1}

    pending = await local_queue.get_pending(limit=500)
    if not pending:
        return {"shipped": 0, "failed": 0, "skipped": 0}

    log_dicts: list[dict[str, Any]] = [entry["payload"] for entry in pending]
    ids: list[int] = [entry["id"] for entry in pending]

    path = "/api/v1/ingest"
    body_bytes = json.dumps({"logs": log_dicts}, ensure_ascii=True).encode()

    url = f"{_get_api_url()}{path}"
    last_exc: Exception | None = None

    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            timestamp, signature = _sign_request("POST", path, body_bytes)
            headers = {
                "X-API-Key": api_key,
                "X-Timestamp": timestamp,
                "X-Signature": signature,
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(verify=True, timeout=30.0) as client:
                response = await client.post(url, content=body_bytes, headers=headers)

            if response.status_code < 300:
                await local_queue.mark_uploaded(ids)
                logger.info("Shipped %d logs to Guardrly API.", len(ids))
                return {"shipped": len(ids), "failed": 0, "skipped": 0}

            if response.status_code == 401:
                logger.error("Invalid API key - stopping log shipping.")
                return {"shipped": 0, "failed": len(ids), "skipped": 0}

            if response.status_code == 429:
                logger.warning("Rate limited by Guardrly API. Will retry after 60s.")
                return {"shipped": 0, "failed": 0, "skipped": len(ids)}

            if response.status_code >= 500:
                logger.warning(
                    "Guardrly API returned %d (attempt %d/%d). Retrying in %ds.",
                    response.status_code,
                    attempt + 1,
                    len(_RETRY_DELAYS),
                    delay,
                )
                if attempt < len(_RETRY_DELAYS) - 1:
                    await asyncio.sleep(delay)
                continue

            logger.error("Guardrly API returned unexpected status %d.", response.status_code)
            return {"shipped": 0, "failed": len(ids), "skipped": 0}

        except httpx.ConnectError as exc:
            last_exc = exc
            logger.warning(
                "Network error shipping logs (attempt %d/%d): %s.",
                attempt + 1,
                len(_RETRY_DELAYS),
                exc,
            )
            if attempt < len(_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)

        except Exception as exc:
            logger.error("Unexpected error in ship_pending_logs: %s", exc)
            return {"shipped": 0, "failed": len(ids), "skipped": 0}

    logger.error("All retries exhausted. Last error: %s", last_exc)
    return {"shipped": 0, "failed": len(ids), "skipped": 0}


async def start_shipping_loop(interval_seconds: int = 30) -> None:
    """
    Run ship_pending_logs() every interval_seconds.
    Runs forever until cancelled. Never crashes the MCP Server.
    """
    api_url = _get_api_url()
    api_key = _get_api_key()
    logger.info("API URL: %s", api_url)
    logger.info("API Key set: %s", bool(api_key))
    logger.info("Log shipping loop started (interval=%ds).", interval_seconds)
    while True:
        try:
            await ship_pending_logs()
        except Exception as exc:  # noqa: BLE001
            logger.error("Unhandled error in shipping loop: %s", exc)
        await asyncio.sleep(interval_seconds)


async def run_startup_cleanup() -> None:
    """
    Called once on MCP Server start.
    Deletes uploaded entries older than 7 days to prevent unbounded DB growth.
    """
    deleted = await local_queue.cleanup_old_entries(days=7)
    logger.info("Startup cleanup: deleted %d old queue entries.", deleted)
