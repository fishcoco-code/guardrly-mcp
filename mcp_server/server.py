"""
Guardrly MCP Server entry point.

Registers the MCP tools that AI Agents use to make HTTP requests.
All requests are transparently intercepted, PII-scrubbed, and logged
before being forwarded to the target API.

Transport: stdio (standard MCP pattern for local servers).
"""

import asyncio
import logging
import os
import uuid
from typing import Any, Literal

import anyio
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server import interceptor, local_queue, log_shipper

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv(override=False)  # don't override env vars already set in the environment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# One session ID per server process - shared by all requests in this session.
SESSION_ID: str = str(uuid.uuid4())

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("guardrly")

# ---------------------------------------------------------------------------
# Tool: make_http_request
# ---------------------------------------------------------------------------


@mcp.tool()
async def make_http_request(
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"],
    url: str,
    headers: dict[str, str] | None = None,
    body: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an HTTP request to any external API.

    Guardrly will intercept and log this request for monitoring and compliance.

    Args:
        method:  HTTP verb - GET, POST, PUT, DELETE, or PATCH.
        url:     Full URL including scheme (https://...).
        headers: Optional request headers dict.
        body:    Optional request body - either a JSON-serialisable dict or
                 a raw string.  Values are never stored; only field names are
                 captured in the operation log.

    Returns:
        dict with keys:
            status_code (int)  - HTTP response status code.
            body        (str)  - Response body text.
    """
    response, log_entry = await interceptor.intercept(
        method=method,
        url=url,
        headers=headers or {},
        body=body,
        session_id=SESSION_ID,
    )

    try:
        await local_queue.enqueue(log_entry)
    except Exception as exc:  # noqa: BLE001
        # Never let queue failures block the Agent.
        logger.warning("Failed to write log entry to local queue: %s", exc)

    return {
        "status_code": response.status_code,
        "body": response.text,
    }


# ---------------------------------------------------------------------------
# Tool: agentwatch_log_reasoning  (P1 feature - stub registered now)
# ---------------------------------------------------------------------------


@mcp.tool()
async def agentwatch_log_reasoning(
    reason: str,
    action_type: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Log the reasoning behind an API action for audit purposes.

    Call this before any high-risk operation to record why you are taking
    this action.  The reasoning is stored alongside the operation log so
    users can review the Agent's decision-making in the Guardrly dashboard.

    Args:
        reason:      Human-readable explanation (max 2000 chars).
        action_type: Optional category label (e.g. "product_update").
        confidence:  Optional confidence score between 0.0 and 1.0.

    Returns:
        {"logged": true}
    """
    # Full implementation ships in Phase 1 (P1 feature).
    return {"logged": True}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run_server() -> None:
    """Async entry point: init, cleanup, then run MCP + shipper concurrently."""
    api_key = os.getenv("GUARDRLY_API_KEY")
    if not api_key:
        logger.warning(
            "GUARDRLY_API_KEY is not set - log shipping to the cloud will be "
            "disabled until the key is configured in .env."
        )

    await local_queue.init_db()
    await log_shipper.run_startup_cleanup()
    logger.info("Guardrly MCP Server started. Session: %s", SESSION_ID)

    # Run MCP server and background shipper concurrently inside the same
    # event loop. When run_stdio_async() returns (e.g. stdin closes), the
    # cancel_scope stops the shipping loop cleanly.
    async with anyio.create_task_group() as tg:
        tg.start_soon(log_shipper.start_shipping_loop, 30)
        await mcp.run_stdio_async()
        tg.cancel_scope.cancel()  # stop shipper when MCP server exits


def main() -> None:
    """Start the Guardrly MCP Server with stdio transport."""
    anyio.run(_run_server)


if __name__ == "__main__":
    main()
