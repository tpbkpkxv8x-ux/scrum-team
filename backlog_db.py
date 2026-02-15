#!/usr/bin/python3
"""
Product Backlog — SQLite-backed scrimmage backlog for parallel agent teams.

Designed for concurrent read/write by multiple agents. Uses WAL mode,
busy_timeout, and thread-local connections for safe multi-agent access.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ITEM_TYPES = {"story", "bug", "task", "spike"}
VALID_STATUSES = {"backlog", "ready", "in_progress", "review", "merged", "done", "parked"}
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"ready", "parked"},
    "ready": {"in_progress", "backlog", "parked"},
    "in_progress": {"review", "ready", "parked"},
    "review": {"merged", "done", "in_progress", "parked"},
    "merged": {"done", "in_progress", "parked"},
    "done": set(),
    "parked": {"backlog"},
}

_DB_FILENAME = "backlog.db"

# Resolve default path relative to this module's location (repo root),
# not the caller's CWD.  This prevents agents in worktrees or other
# directories from silently creating an empty DB.
_MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = _MODULE_DIR / _DB_FILENAME

_UNSET = object()  # sentinel for "parameter not passed"

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
    parent: int | None
    created_at: str
    updated_at: str

    # Bound after construction by ProductBacklog
    _backlog: ProductBacklog | None = field(default=None, repr=False, compare=False)

    # -- convenience methods (delegate to backlog) --

    def assign(self, agent_name: str | None) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.assign(self.id, agent_name)
        self.assigned_to = updated.assigned_to
        self.updated_at = updated.updated_at

    def update_status(self, new_status: str, *, result: object = _UNSET) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_status(self.id, new_status, result=result)
        self.status = updated.status
        self.updated_at = updated.updated_at
        if result is not _UNSET:
            self.result = updated.result

    def update_priority(self, priority: int) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_priority(self.id, priority)
        self.priority = updated.priority
        self.updated_at = updated.updated_at

    def update_sprint(self, sprint: str | None) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_sprint(self.id, sprint)
        self.sprint = updated.sprint
        self.updated_at = updated.updated_at

    def update_parent(self, parent: int | None) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_parent(self.id, parent)
        self.parent = updated.parent
        self.updated_at = updated.updated_at

    def update_title(self, title: str) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_title(self.id, title)
        self.title = updated.title
        self.updated_at = updated.updated_at

    def update_description(self, description: str | None) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.update_description(self.id, description)
        self.description = updated.description
        self.updated_at = updated.updated_at

    def comment(self, text: str) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        updated = self._backlog.comment(self.id, text)
        self.updated_at = updated.updated_at

    def delete(self) -> None:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        self._backlog.delete(self.id)
        self._backlog = None

    def refresh(self) -> Self:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        fresh = self._backlog.get_item(self.id)
        if fresh is None:
            raise LookupError(f"Backlog item {self.id} no longer exists")
        self.__dict__.update(fresh.__dict__)
        return self

    def get_comments(self) -> list[dict[str, Any]]:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        return self._backlog.get_comments(self.id)

    def get_history(self) -> list[dict[str, Any]]:
        if self._backlog is None:
            raise RuntimeError("BacklogItem is not bound to a ProductBacklog")
        return self._backlog.get_history(self.id)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_instances: dict[str, ProductBacklog] = {}
_instance_lock = threading.Lock()


def get_backlog_db(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    agent: str | None = None,
) -> ProductBacklog:
    """Thread-safe singleton — one ProductBacklog per database path and agent.

    Parameters
    ----------
    db_path : path to the SQLite database file.  Defaults to
        ``backlog.db`` next to this module (the repo root), so it works
        from any CWD.
    agent : short agent name (e.g. "Barry"). Used as a prefix for the
        full agent identity recorded in all audit-trail events.
    """
    key = f"{Path(db_path).resolve()}::{agent or ''}"
    with _instance_lock:
        if key not in _instances:
            _instances[key] = ProductBacklog(db_path, agent=agent)
        return _instances[key]


class ProductBacklog:
    """SQLite-backed Product Backlog with WAL mode for concurrent agent access."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH, *, agent: str | None = None) -> None:
        self.db_path = Path(db_path)
        self._agent_prefix = agent
        self._local = threading.local()
        self._all_conns: set[sqlite3.Connection] = set()
        self._conn_lock = threading.Lock()
        self._closed = False
        self._init_schema()

    @property
    def agent_name(self) -> str | None:
        """Full agent identity: ``"Barry/pid=1234/MainThread"``."""
        if self._agent_prefix is None:
            return None
        return f"{self._agent_prefix}/pid={os.getpid()}/{threading.current_thread().name}"

    # -- connection management --

    @property
    def _conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        # Detect stale reference from a previous close() call
        if conn is not None:
            with self._conn_lock:
                if conn not in self._all_conns:
                    conn = None
                    self._local.conn = None
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            with self._conn_lock:
                self._all_conns.add(conn)
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
        conn.execute(
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
                parent      INTEGER REFERENCES backlog_items(id),
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backlog_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id     INTEGER NOT NULL,
                event_type  TEXT NOT NULL,
                old_value   TEXT,
                new_value   TEXT,
                agent_id    TEXT,
                comment     TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_status ON backlog_items(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_sprint ON backlog_items(sprint)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_assigned ON backlog_items(assigned_to)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_parent ON backlog_items(parent)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_item ON backlog_events(item_id)")
        conn.commit()

    # -- helpers --

    _ITEM_FIELDS: set[str] = {f.name for f in fields(BacklogItem) if f.name != "_backlog"}

    def _row_to_item(self, row: sqlite3.Row) -> BacklogItem:
        data = {k: v for k, v in dict(row).items() if k in self._ITEM_FIELDS}
        item = BacklogItem(**data)
        item._backlog = self
        return item

    @staticmethod
    def _now() -> str:
        # Millisecond precision to match SQLite's strftime('%Y-%m-%dT%H:%M:%fZ')
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"

    def _validate_parent(self, cur: sqlite3.Cursor, parent: int | None, item_id: int | None = None) -> None:
        """Validate that a parent reference is safe.

        Checks:
        1. Parent exists in the database.
        2. Item is not its own parent (self-reference).
        3. Setting this parent would not create a cycle.
        """
        if parent is None:
            return
        if item_id is not None and parent == item_id:
            raise ValueError(f"Item {item_id} cannot be its own parent")
        cur.execute("SELECT id FROM backlog_items WHERE id = ?", (parent,))
        if cur.fetchone() is None:
            raise LookupError(f"Parent item {parent} not found")
        if item_id is not None:
            # Walk the parent chain from `parent` upward; if we reach `item_id`, it's a cycle.
            current = parent
            visited: set[int] = {item_id}
            while current is not None:
                if current in visited:
                    raise ValueError(
                        f"Circular parent reference: setting parent of item {item_id} "
                        f"to {parent} would create a cycle"
                    )
                visited.add(current)
                cur.execute("SELECT parent FROM backlog_items WHERE id = ?", (current,))
                row = cur.fetchone()
                if row is None:
                    break
                current = row["parent"]

    # -- public API --

    def add(
        self,
        title: str,
        *,
        description: str | None = None,
        item_type: str = "story",
        priority: int = 0,
        sprint: str | None = None,
        parent: int | None = None,
    ) -> BacklogItem:
        if not title or not title.strip():
            raise ValueError("Title must not be empty")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise TypeError(f"Priority must be an integer, got {type(priority).__name__}")
        if item_type not in VALID_ITEM_TYPES:
            raise ValueError(f"Invalid item_type {item_type!r}; must be one of {VALID_ITEM_TYPES}")
        agent_id = self.agent_name
        now = self._now()
        with self._tx() as cur:
            self._validate_parent(cur, parent)
            cur.execute(
                """
                INSERT INTO backlog_items
                    (title, description, item_type, priority, sprint,
                     created_by, parent, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                (title, description, item_type, priority, sprint,
                 agent_id, parent, now, now),
            )
            row = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, new_value, agent_id) VALUES (?, 'created', ?, ?)",
                (row["id"], title, agent_id),
            )
        return self._row_to_item(row)

    def assign(self, item_id: int, agent_name: str | None) -> BacklogItem:
        agent_id = self.agent_name
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
                (item_id, old, agent_name, agent_id),
            )
        return self._row_to_item(updated)

    def update_status(
        self,
        item_id: int,
        new_status: str,
        *,
        result: object = _UNSET,
    ) -> BacklogItem:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status {new_status!r}; must be one of {VALID_STATUSES}")
        if result is not _UNSET and result is not None and not isinstance(result, str):
            raise TypeError(f"Result must be a string or None, got {type(result).__name__}")
        agent_id = self.agent_name
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
            if result is not _UNSET:
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
                (item_id, old_status, new_status, agent_id),
            )
        return self._row_to_item(updated)

    def update_priority(self, item_id: int, priority: int) -> BacklogItem:
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise TypeError(f"Priority must be an integer, got {type(priority).__name__}")
        agent_id = self.agent_name
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
                (item_id, str(old_priority), str(priority), agent_id),
            )
        return self._row_to_item(updated)

    def update_sprint(self, item_id: int, sprint: str | None) -> BacklogItem:
        agent_id = self.agent_name
        with self._tx() as cur:
            cur.execute("SELECT sprint FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            old_sprint = row["sprint"]
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET sprint = ?, updated_at = ? WHERE id = ? RETURNING *",
                (sprint, now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'sprint_change', ?, ?, ?)",
                (item_id, old_sprint, sprint, agent_id),
            )
        return self._row_to_item(updated)

    def update_parent(self, item_id: int, parent: int | None) -> BacklogItem:
        agent_id = self.agent_name
        with self._tx() as cur:
            cur.execute("SELECT parent FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            self._validate_parent(cur, parent, item_id)
            old_parent = row["parent"]
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET parent = ?, updated_at = ? WHERE id = ? RETURNING *",
                (parent, now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'parent_change', ?, ?, ?)",
                (item_id, str(old_parent) if old_parent is not None else None,
                 str(parent) if parent is not None else None, agent_id),
            )
        return self._row_to_item(updated)

    def update_title(self, item_id: int, title: str) -> BacklogItem:
        if not title or not title.strip():
            raise ValueError("Title must not be empty")
        agent_id = self.agent_name
        with self._tx() as cur:
            cur.execute("SELECT title FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            old_title = row["title"]
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET title = ?, updated_at = ? WHERE id = ? RETURNING *",
                (title, now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'title_change', ?, ?, ?)",
                (item_id, old_title, title, agent_id),
            )
        return self._row_to_item(updated)

    def update_description(self, item_id: int, description: str | None) -> BacklogItem:
        agent_id = self.agent_name
        with self._tx() as cur:
            cur.execute("SELECT description FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            old_desc = row["description"]
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET description = ?, updated_at = ? WHERE id = ? RETURNING *",
                (description, now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id)"
                " VALUES (?, 'description_change', ?, ?, ?)",
                (item_id, old_desc, description, agent_id),
            )
        return self._row_to_item(updated)

    def delete(self, item_id: int) -> None:
        import json

        agent_id = self.agent_name
        with self._tx() as cur:
            cur.execute("SELECT * FROM backlog_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"Backlog item {item_id} not found")
            # Serialize the item's final state for the audit log
            final_state = json.dumps(dict(row), default=str)
            # Unparent children and record audit events for each
            cur.execute("SELECT id FROM backlog_items WHERE parent = ?", (item_id,))
            children = cur.fetchall()
            if children:
                now = self._now()
                for child_row in children:
                    cur.execute(
                        "INSERT INTO backlog_events (item_id, event_type, old_value, new_value, agent_id, comment)"
                        " VALUES (?, 'parent_change', ?, NULL, ?, ?)",
                        (child_row["id"], str(item_id), agent_id, f"Parent item {item_id} was deleted"),
                    )
                cur.execute(
                    "UPDATE backlog_items SET parent = NULL, updated_at = ? WHERE parent = ?",
                    (now, item_id),
                )
            # Record the deletion event with the final state
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, old_value, agent_id)"
                " VALUES (?, 'deleted', ?, ?)",
                (item_id, final_state, agent_id),
            )
            cur.execute("DELETE FROM backlog_items WHERE id = ?", (item_id,))

    def comment(self, item_id: int, text: str) -> BacklogItem:
        if not text or not text.strip():
            raise ValueError("Comment text must not be empty")
        agent_id = self.agent_name
        with self._tx() as cur:
            cur.execute("SELECT id FROM backlog_items WHERE id = ?", (item_id,))
            if cur.fetchone() is None:
                raise LookupError(f"Backlog item {item_id} not found")
            now = self._now()
            cur.execute(
                "UPDATE backlog_items SET updated_at = ? WHERE id = ? RETURNING *",
                (now, item_id),
            )
            updated = cur.fetchone()
            cur.execute(
                "INSERT INTO backlog_events (item_id, event_type, agent_id, comment) VALUES (?, 'comment', ?, ?)",
                (item_id, agent_id, text),
            )
        return self._row_to_item(updated)

    def get_item(self, item_id: int) -> BacklogItem | None:
        row = self._conn.execute("SELECT * FROM backlog_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def list_items(
        self,
        *,
        status: str | None = None,
        assigned_to: str | None = None,
        item_type: str | None = None,
        sprint: str | None = None,
        parent: object = _UNSET,
        top_level_only: bool = False,
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
        if top_level_only and parent is not _UNSET:
            raise ValueError("Cannot specify both top_level_only=True and parent")
        if top_level_only:
            sql += " AND parent IS NULL"
        elif parent is not _UNSET:
            if parent is None:
                sql += " AND parent IS NULL"
            else:
                sql += " AND parent = ?"
                params.append(parent)
        sql += " ORDER BY priority DESC, id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_comments(self, item_id: int) -> list[dict[str, Any]]:
        """Return comment events for a backlog item, ordered chronologically."""
        rows = self._conn.execute(
            "SELECT * FROM backlog_events WHERE item_id = ? AND event_type = 'comment' ORDER BY id",
            (item_id,),
        ).fetchall()
        if not rows:
            # No comments — check whether the item exists at all.
            if self._conn.execute(
                "SELECT id FROM backlog_items WHERE id = ?", (item_id,)
            ).fetchone() is None:
                # Not in items table; check if it was deleted (events still exist)
                if not self._conn.execute(
                    "SELECT id FROM backlog_events WHERE item_id = ?", (item_id,)
                ).fetchone():
                    raise LookupError(f"Backlog item {item_id} not found")
        return [dict(r) for r in rows]

    def get_history(self, item_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM backlog_events WHERE item_id = ? ORDER BY id",
            (item_id,),
        ).fetchall()
        # If no events and item doesn't exist, it never existed
        if not rows and self._conn.execute(
            "SELECT id FROM backlog_items WHERE id = ?", (item_id,)
        ).fetchone() is None:
            raise LookupError(f"Backlog item {item_id} not found")
        return [dict(r) for r in rows]

    def close(self) -> None:
        # Close all thread-local connections; stale refs are detected by _conn
        with self._conn_lock:
            for ref_conn in self._all_conns:
                with suppress(Exception):
                    ref_conn.close()
            self._all_conns.clear()
        self._local.conn = None
        self._closed = True
        # Remove from singleton cache so get_backlog_db() creates a fresh instance
        key = f"{self.db_path.resolve()}::{self._agent_prefix or ''}"
        with _instance_lock:
            _instances.pop(key, None)
