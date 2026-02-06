"""
Product Backlog — SQLite-backed scrum backlog for parallel agent teams.

Designed for concurrent read/write by multiple agents. Uses WAL mode,
busy_timeout, and thread-local connections for safe multi-agent access.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ITEM_TYPES = {"story", "bug", "task", "spike"}
VALID_STATUSES = {"backlog", "ready", "in_progress", "review", "done"}
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"ready"},
    "ready": {"in_progress", "backlog"},
    "in_progress": {"review", "ready"},
    "review": {"done", "in_progress"},
    "done": set(),
}

DEFAULT_DB_PATH = Path("backlog.db")

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class BacklogItem:
    """A single Product Backlog item with convenience methods."""

    id: int
    title: str
    description: str | None
    item_type: str
    status: str
    priority: int
    sprint: str | None
    assigned_to: str | None
    created_by: str | None
    result: str | None
    created_at: str
    updated_at: str

    # Bound after construction by ProductBacklog
    _backlog: ProductBacklog | None = field(default=None, repr=False, compare=False)

    # -- convenience methods (delegate to backlog) --

    def assign(self, agent_name: str | None, *, agent: str | None = None) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.assign(self.id, agent_name, agent=agent)
        self.assigned_to = updated.assigned_to
        self.updated_at = updated.updated_at

    def update_status(
        self, new_status: str, *, agent: str | None = None, result: str | None = None,
    ) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_status(self.id, new_status, agent=agent, result=result)
        self.status = updated.status
        self.updated_at = updated.updated_at
        if result is not None:
            self.result = updated.result

    def comment(self, agent_name: str, text: str) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        self._backlog.comment(self.id, agent_name, text)

    def refresh(self) -> Self:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        fresh = self._backlog.get_item(self.id)
        if fresh is None:
            raise LookupError(f"Backlog item {self.id} no longer exists")
        self.__dict__.update(fresh.__dict__)
        return self

    def get_history(self) -> list[dict[str, Any]]:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        return self._backlog.get_history(self.id)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_instances: dict[str, ProductBacklog] = {}
_instance_lock = threading.Lock()


def get_backlog_db(db_path: str | Path = DEFAULT_DB_PATH) -> ProductBacklog:
    """Thread-safe singleton — one ProductBacklog per database path."""
    key = str(Path(db_path).resolve())
    if key not in _instances:
        with _instance_lock:
            if key not in _instances:
                _instances[key] = ProductBacklog(db_path)
    return _instances[key]


class ProductBacklog:
    """SQLite-backed Product Backlog with WAL mode for concurrent agent access."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_schema()

    # -- connection management --

    @property
    def _conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        """Transaction context manager — commits on success, rolls back on error."""
        conn = self._conn
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # -- schema --

    def _init_schema(self) -> None:
        conn = self._conn
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS backlog_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                item_type   TEXT NOT NULL DEFAULT 'story',
                status      TEXT NOT NULL DEFAULT 'backlog',
                priority    INTEGER NOT NULL DEFAULT 0,
                sprint      TEXT,
                assigned_to TEXT,
                created_by  TEXT,
                result      TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS backlog_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id     INTEGER NOT NULL REFERENCES backlog_items(id),
                event_type  TEXT NOT NULL,
                old_value   TEXT,
                new_value   TEXT,
                agent_id    TEXT,
                comment     TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE INDEX IF NOT EXISTS idx_items_status ON backlog_items(status);
            CREATE INDEX IF NOT EXISTS idx_items_sprint ON backlog_items(sprint);
            CREATE INDEX IF NOT EXISTS idx_items_assigned ON backlog_items(assigned_to);
            CREATE INDEX IF NOT EXISTS idx_events_item ON backlog_events(item_id);
            """
        )

    # -- helpers --

    def _row_to_item(self, row: sqlite3.Row) -> BacklogItem:
        item = BacklogItem(**dict(row))
        item._backlog = self
        return item

    @staticmethod
    def _now() -> str:
        # Millisecond precision to match SQLite's strftime('%Y-%m-%dT%H:%M:%fZ')
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"

    # -- public API --

    def add(
        self,
        title: str,
        *,
        description: str | None = None,
        item_type: str = "story",
        priority: int = 0,
        sprint: str | None = None,
        created_by: str | None = None,
    ) -> BacklogItem:
        if item_type not in VALID_ITEM_TYPES:
            raise ValueError(f"Invalid item_type {item_type!r}; must be one of {VALID_ITEM_TYPES}")
        with self._tx() as cur:
            cur.execute(
                """
                INSERT INTO backlog_items (title, description, item_type, priority, sprint, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                (title, description, item_type, priority, sprint, created_by),
            )
            row = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, new_value, agent_id) VALUES (?, 'created', ?, ?)",
                (row["id"], title, created_by),
            )
        return self._row_to_item(row)

    def assign(self, item_id: int, agent_name: str | None, *, agent: str | None = None) -> BacklogItem:
        with self._tx() as cur:
            cur.execute("SELECT assigned_to FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            old = row["assigned_to"]
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET assigned_to = ?, updated_at = ? WHERE id = ? RETURNING *",
                (agent_name, now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'assigned', ?, ?, ?)",
                (item_id, old, agent_name, agent),
            )
        return self._row_to_item(updated)

    def update_status(
        self,
        item_id: int,
        new_status: str,
        *,
        agent: str | None = None,
        result: str | None = None,
    ) -> BacklogItem:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status {new_status!r}; must be one of {VALID_STATUSES}")
        with self._tx() as cur:
            cur.execute("SELECT status FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            old_status = row["status"]
            if new_status not in STATUS_TRANSITIONS.get(old_status, set()):
                raise ValueError(
                    f"Cannot transition from {old_status!r} to {new_status!r}. "
                    f"Allowed: {STATUS_TRANSITIONS.get(old_status, set())}"
                )
            now = self._now()
            params: list[Any] = [new_status, now]
            result_clause = ""
            if result is not None:
                result_clause = ", result = ?"
                params.append(result)
            params.append(item_id)
            cur.execute(
                f"UPDATE backlog_items SET status = ?, updated_at = ?{result_clause} WHERE id = ? RETURNING *",
                params,
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'status_change', ?, ?, ?)",
                (item_id, old_status, new_status, agent),
            )
        return self._row_to_item(updated)

    def update_priority(self, item_id: int, priority: int, *, agent: str | None = None) -> BacklogItem:
        with self._tx() as cur:
            cur.execute("SELECT priority FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            old_priority = row["priority"]
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET priority = ?, updated_at = ? WHERE id = ? RETURNING *",
                (priority, now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'priority_change', ?, ?, ?)",
                (item_id, str(old_priority), str(priority), agent),
            )
        return self._row_to_item(updated)

    def comment(self, item_id: int, agent_name: str, text: str) -> None:
        with self._tx() as cur:
            cur.execute("SELECT id FROM backlog_items WHERE id = ?", (item_id,))
            if cur.fetchone() is None:
                raise LookupError(f"Backlog item {item_id} not found")
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, agent_id, comment) VALUES (?, 'comment', ?, ?)",
                (item_id, agent_name, text),
            )

    def get_item(self, item_id: int) -> BacklogItem | None:
        row = self._conn.execute("SELECT * FROM backlog_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def get_sprint(self, sprint_name: str, *, status: str | None = None) -> list[BacklogItem]:
        sql = "SELECT * FROM backlog_items WHERE sprint = ?"
        params: list[Any] = [sprint_name]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY priority DESC, id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def list_items(
        self,
        *,
        status: str | None = None,
        assigned_to: str | None = None,
        item_type: str | None = None,
        sprint: str | None = None,
    ) -> list[BacklogItem]:
        sql = "SELECT * FROM backlog_items WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if assigned_to is not None:
            sql += " AND assigned_to = ?"
            params.append(assigned_to)
        if item_type is not None:
            sql += " AND item_type = ?"
            params.append(item_type)
        if sprint is not None:
            sql += " AND sprint = ?"
            params.append(sprint)
        sql += " ORDER BY priority DESC, id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_history(self, item_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM backlog_events WHERE item_id = ? ORDER BY id",
            (item_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        # Remove from singleton cache so get_backlog_db() creates a fresh instance
        key = str(self.db_path.resolve())
        with _instance_lock:
            _instances.pop(key, None)
