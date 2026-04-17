"""
Local SQLite async write queue - L1 layer.

Buffers operation log entries on the user's machine before they are batched
and uploaded to the Guardrly API.  PII scrubbing always runs before enqueue()
is called, so this layer only ever stores already-scrubbed data.

Storage: ~/.guardrly/cache.db  (override _DB_PATH in tests via monkeypatch)
Performance: enqueue() target <1ms per call (WAL journal mode, async I/O).
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration - override _DB_PATH in tests via monkeypatch
# ---------------------------------------------------------------------------

_DB_PATH: Path = Path.home() / ".guardrly" / "cache.db"

_LOW_DISK_BYTES: int = 100 * 1024 * 1024  # 100 MB
_MAX_PENDING: int = 100_000
_EVICT_COUNT: int = 10_000

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL_TABLE = """
CREATE TABLE IF NOT EXISTS log_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    uploaded    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    uploaded_at TEXT
);
"""

_DDL_IDX_UPLOADED = (
    "CREATE INDEX IF NOT EXISTS idx_uploaded ON log_queue(uploaded);"
)
_DDL_IDX_CREATED = (
    "CREATE INDEX IF NOT EXISTS idx_created_at ON log_queue(created_at);"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create ~/.guardrly/ and the database schema if not already present.

    Must be called once at MCP Server startup before any enqueue() calls.
    """
    db_dir = _DB_PATH.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute(_DDL_TABLE)
        await db.execute(_DDL_IDX_UPLOADED)
        await db.execute(_DDL_IDX_CREATED)
        await db.commit()

    logger.info("Local queue initialized at %s", _DB_PATH)


async def enqueue(log_entry: dict[str, Any]) -> int:
    """Serialize and insert a log entry into the local queue.

    Returns the new row id on success, or -1 if the write was skipped
    (disk full, or any other write error).  The Agent is never blocked
    by queue failures.
    """
    # --- Disk space check ---
    try:
        usage = shutil.disk_usage(_DB_PATH.parent)
        if usage.free < _LOW_DISK_BYTES:
            logger.warning("Disk space low (<100MB free). Skipping log entry.")
            await cleanup_old_entries(days=3)
            return -1
    except OSError as exc:
        logger.error("Could not check disk space: %s", exc)

    # --- Capacity check: evict uploaded entries when pending >= 100k ---
    stats = await get_queue_stats()
    if stats["pending"] >= _MAX_PENDING:
        logger.warning(
            "Queue at capacity. Evicting oldest %d entries.", _EVICT_COUNT
        )
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                """
                DELETE FROM log_queue
                WHERE id IN (
                    SELECT id FROM log_queue
                    WHERE uploaded = 1
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (_EVICT_COUNT,),
            )
            await db.commit()

    # --- Write entry ---
    try:
        payload = json.dumps(log_entry)
        async with aiosqlite.connect(_DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO log_queue (session_id, payload) VALUES (?, ?)",
                (log_entry.get("session_id", ""), payload),
            )
            await db.commit()
            row_id: int = cursor.lastrowid  # type: ignore[assignment]
            return row_id
    except Exception as exc:
        logger.error("Failed to write log entry to queue: %s", exc)
        return -1


async def get_pending(limit: int = 500) -> list[dict[str, Any]]:
    """Return up to `limit` pending (not-yet-uploaded) entries in FIFO order.

    Each item includes: id, session_id, payload (parsed dict), created_at.
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, session_id, payload, created_at
            FROM log_queue
            WHERE uploaded = 0
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "session_id": row[1],
            "payload": json.loads(row[2]),
            "created_at": row[3],
        }
        for row in rows
    ]


async def mark_uploaded(ids: list[int]) -> None:
    """Set uploaded=1 and uploaded_at=now for the given row ids.

    Uses a single UPDATE with an IN clause for efficiency.
    """
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            f"UPDATE log_queue SET uploaded=1, uploaded_at=datetime('now') "
            f"WHERE id IN ({placeholders})",
            ids,
        )
        await db.commit()


async def get_queue_stats() -> dict[str, int]:
    """Return counts of pending/uploaded/total entries and the DB file size."""
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM log_queue WHERE uploaded=0"
        ) as cur:
            pending: int = (await cur.fetchone())[0]  # type: ignore[index]
        async with db.execute(
            "SELECT COUNT(*) FROM log_queue WHERE uploaded=1"
        ) as cur:
            uploaded: int = (await cur.fetchone())[0]  # type: ignore[index]
        async with db.execute("SELECT COUNT(*) FROM log_queue") as cur:
            total: int = (await cur.fetchone())[0]  # type: ignore[index]

    try:
        db_size = os.path.getsize(_DB_PATH)
    except OSError:
        db_size = 0

    return {
        "pending": pending,
        "uploaded": uploaded,
        "total": total,
        "db_size_bytes": db_size,
    }


async def cleanup_old_entries(days: int = 7) -> int:
    """Delete uploaded entries older than `days` days.

    Returns the count of deleted rows.
    Called by the log shipper on startup to prevent unbounded DB growth.
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM log_queue WHERE uploaded=1 AND created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
        return cursor.rowcount
