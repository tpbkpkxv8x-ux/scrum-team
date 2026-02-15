# Backlog API Guide

SQLite-backed Product Backlog for parallel agent teams. Supports concurrent read/write by multiple agents using WAL mode and thread-local connections.

## Quick Start

```python
from backlog_db import get_backlog_db

bl = get_backlog_db(agent="Paula")  # identify yourself once

# Create items
epic = bl.add("User login", description="OAuth2 flow", item_type="story",
              priority=10, sprint="sprint-1")
subtask = bl.add("Token refresh", parent=epic.id, item_type="task", priority=5)

# Assign it
epic.assign("Barry")

# Move it through the workflow
epic.update_status("ready")
epic.update_status("in_progress")
epic.update_status("review")
epic.update_status("merged")
epic.update_status("done", result="Deployed to prod")

# Refine it
epic.update_title("User login via OAuth2")
epic.update_description("Full OAuth2 flow with Google provider")

# Add a comment
epic.comment("Blocked on API key")

# Delete an item created by mistake
bad = bl.add("Oops", item_type="task")
bad.delete()

# Query the backlog
ready = bl.list_items(status="ready")
mine = bl.list_items(assigned_to="Barry")
sprint = bl.list_items(sprint="sprint-1")
bugs = bl.list_items(item_type="bug", status="backlog")
children = bl.list_items(parent=epic.id)
top_level = bl.list_items(top_level_only=True)

# Get just the comments on an item
comments = epic.get_comments()

# Check an item's full audit trail
events = epic.get_history()

# Reload from DB to pick up changes made by other agents
epic.refresh()
```

## `BacklogItem` Attributes

Every method that creates or returns items gives you a `BacklogItem` with these fields:

| Attribute | Type | Description |
|---|---|---|
| `id` | `int` | Unique auto-incrementing ID. |
| `title` | `str` | Short summary. Must not be empty. |
| `description` | `str` or `None` | Detailed requirements or acceptance criteria. |
| `item_type` | `str` | One of: `story`, `bug`, `task`, `spike`. |
| `status` | `str` | One of: `backlog`, `ready`, `in_progress`, `review`, `merged`, `done`, `parked`. |
| `priority` | `int` | Higher = more important. Must be an integer. |
| `sprint` | `str` or `None` | Sprint name, or `None` if unscheduled. |
| `assigned_to` | `str` or `None` | Agent name, or `None` if unassigned. |
| `created_by` | `str` or `None` | Full agent identity of whoever created the item (set automatically). |
| `result` | `str` or `None` | Outcome text, typically set when moving to `done`. |
| `parent` | `int` or `None` | ID of the parent item, or `None` for top-level items. |
| `created_at` | `str` | ISO 8601 timestamp with millisecond precision (`2025-01-15T10:30:45.123Z`). |
| `updated_at` | `str` | ISO 8601 timestamp, updated on every mutation. |

## Status Flow

```
backlog <--> ready <--> in_progress <--> review --> merged --> done
                                    \                  |
                                     `<--- (rework) <--'

Any status (except done) --> parked --> backlog
```

`review` can also transition directly to `done` (skipping `merged`).
`merged` can go back to `in_progress` if rework is needed after merge.
`done` is terminal — no transitions out of it.
`parked` takes an item out of active flow. The only way back is through `backlog`.

## Item Types

`story`, `bug`, `task`, `spike`

## Agent Identity

Set your agent name once when you open the backlog:

```python
bl = get_backlog_db(agent="Barry")
```

Every write operation automatically records a full agent identity in the audit trail:

```
Barry/pid=1234/MainThread
```

This includes the short name you provided, the process ID, and the thread name. You never need to pass your name to individual methods — it's always taken from the stored identity.

If you don't set an agent name, audit trail entries will have `None` as the agent.

## Calling Convention

Most operations can be called two ways — on the database object or directly on an item:

```python
# These do the same thing:
bl.assign(item.id, "Barry")   # on the database, passing the item ID
item.assign("Barry")          # on the item directly (no ID needed)
```

The item-level calls are shortcuts. They call the database method internally and update the item's local fields (`status`, `assigned_to`, `updated_at`, etc.) so you don't need to call `refresh()` afterwards.

The database-level calls are useful when you only have an item ID (e.g. from a query) and don't want to fetch the full item first.

The reference below documents each method once, showing both calling conventions where applicable.

---

## Getting a Database Instance

### `get_backlog_db(db_path=DEFAULT_DB_PATH, *, agent=None)`

Returns a `ProductBacklog` instance. Thread-safe singleton — one instance per `(db_path, agent)` pair. Different agents sharing the same DB file get separate instances (each recording their own identity in the audit trail).

```python
from backlog_db import get_backlog_db

bl = get_backlog_db(agent="Barry")               # default DB (scrimmage/backlog.db), agent identified
bl2 = get_backlog_db("/tmp/other.db", agent="Sam")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `db_path` | `str` or `Path` | `scrimmage/backlog.db` | Path to the SQLite database file. Defaults to `backlog.db` next to the module (i.e. `scrimmage/backlog.db`). Created automatically if it doesn't exist. |
| `agent` | `str` or `None` | `None` | Short agent name. Used as a prefix for the full agent identity in all audit-trail events. |

**Returns:** `ProductBacklog`

**Property:** `bl.agent_name` returns the full identity string (e.g. `"Barry/pid=1234/MainThread"`) or `None`.

---

## Method Reference

### `add(title, *, description, item_type, priority, sprint, parent)`

Create a new backlog item. Starts in `backlog` status. The calling agent's identity is recorded as `created_by`.

```python
item = bl.add(
    "As a user, I want to reset my password",
    description="Send email with reset link, expire after 24h",
    item_type="story",
    priority=10,
    sprint="sprint-1",
)

# Create a child item
subtask = bl.add("Write reset email template", parent=item.id, item_type="task")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | *required* | Short summary of the item. Must not be empty. |
| `description` | `str` or `None` | `None` | Detailed requirements or acceptance criteria. |
| `item_type` | `str` | `"story"` | One of: `story`, `bug`, `task`, `spike`. |
| `priority` | `int` | `0` | Higher number = higher priority. Used for ordering in `list_items()`. |
| `sprint` | `str` or `None` | `None` | Sprint name (e.g. `"sprint-1"`). `None` means unscheduled. |
| `parent` | `int` or `None` | `None` | ID of a parent backlog item. `None` for top-level items. |

**Returns:** `BacklogItem`

**Raises:**
- `ValueError` if `title` is empty or whitespace-only.
- `ValueError` if `item_type` is not valid.
- `TypeError` if `priority` is not an integer.
- `LookupError` if `parent` ID doesn't exist.

**Events:** Records a `created` event.

---

### `assign(agent_name)`

Assign an item to an agent, or unassign by passing `None`.

```python
# On the item:
item.assign("Barry")
item.assign(None)       # unassign

# On the database (equivalent, but takes item_id):
bl.assign(item.id, "Barry")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_name` | `str` or `None` | *required* | Agent to assign to, or `None` to unassign. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:** `LookupError` if the item doesn't exist.

**Events:** Records an `assigned` event with `old_value` (previous assignee), `new_value` (new assignee), and `agent_id` (who did it — the stored agent identity).

---

### `update_status(new_status, *, result)`

Transition an item to a new status. The transition must be valid (see Status Flow above).

```python
# On the item:
item.update_status("ready")
item.update_status("done", result="Deployed to prod")

# On the database:
bl.update_status(item.id, "ready")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `new_status` | `str` | *required* | Target status. Must be a valid transition from the current status. |
| `result` | `str` or `None` | *(omit)* | Outcome text. Pass a string to set, `None` to clear, or omit to leave unchanged. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:**
- `LookupError` if the item doesn't exist.
- `ValueError` if `new_status` is not a valid status.
- `ValueError` if the transition is not allowed (e.g. `backlog` to `done`).
- `TypeError` if `result` is not a string or `None`.

**Events:** Records a `status_change` event with `old_value` and `new_value`.

**Concurrency:** Uses `BEGIN IMMEDIATE` transactions. If two agents race to claim the same item, exactly one succeeds and the other gets a `ValueError` (the transition is no longer valid).

---

### `update_priority(priority)`

Change an item's priority.

```python
# On the item:
item.update_priority(99)

# On the database:
bl.update_priority(item.id, 99)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `priority` | `int` | *required* | New priority value. Higher = more important. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:**
- `LookupError` if the item doesn't exist.
- `TypeError` if `priority` is not an integer.

**Events:** Records a `priority_change` event with `old_value` and `new_value` (as strings).

---

### `update_sprint(sprint)`

Change which sprint an item belongs to, or remove it from a sprint by passing `None`.

```python
# On the item:
item.update_sprint("sprint-2")
item.update_sprint(None)       # remove from sprint

# On the database:
bl.update_sprint(item.id, "sprint-2")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sprint` | `str` or `None` | *required* | Sprint name, or `None` to unschedule. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:** `LookupError` if the item doesn't exist.

**Events:** Records a `sprint_change` event with `old_value` and `new_value`.

---

### `update_parent(parent)`

Change an item's parent, or make it top-level by passing `None`. Self-references and circular hierarchies are rejected.

```python
# On the item:
item.update_parent(epic.id)
item.update_parent(None)       # make top-level

# On the database:
bl.update_parent(item.id, epic.id)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `parent` | `int` or `None` | *required* | ID of the new parent item, or `None` for top-level. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:**
- `LookupError` if the item doesn't exist.
- `LookupError` if the parent ID doesn't exist.
- `ValueError` if the item would become its own parent (self-reference).
- `ValueError` if the change would create a circular parent chain.

**Events:** Records a `parent_change` event with `old_value` and `new_value` (as stringified IDs, or `None`).

---

### `update_title(title)`

Change an item's title.

```python
# On the item:
item.update_title("Better title")

# On the database:
bl.update_title(item.id, "Better title")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | *required* | New title. Must not be empty. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:**
- `LookupError` if the item doesn't exist.
- `ValueError` if `title` is empty or whitespace-only.

**Events:** Records a `title_change` event with `old_value` and `new_value`.

---

### `update_description(description)`

Change an item's description, or clear it by passing `None`.

```python
# On the item:
item.update_description("Updated acceptance criteria")
item.update_description(None)  # clear

# On the database:
bl.update_description(item.id, "Updated acceptance criteria")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `description` | `str` or `None` | *required* | New description, or `None` to clear. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:** `LookupError` if the item doesn't exist.

**Events:** Records a `description_change` event with `old_value` and `new_value`.

---

### `comment(text)`

Add a comment to an item's event log. The calling agent's identity is recorded automatically.

```python
# On the item:
item.comment("Blocked on API key from the cloud team")

# On the database:
bl.comment(item.id, "Blocked on API key from the cloud team")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | *required* | The comment text. Must not be empty. |

**Returns:** Database call returns `BacklogItem`. Item call returns `None` (updates the item in place).

**Raises:**
- `LookupError` if the item doesn't exist.
- `ValueError` if `text` is empty or whitespace-only.

**Events:** Records a `comment` event with `agent_id` and `comment` fields.

---

### `delete()`

Delete an item. Any children of the deleted item are unparented (become top-level), with `parent_change` events recorded for each child. The item's audit trail is preserved — a `deleted` event is recorded with the item's final state serialized as JSON in `old_value`. You can still call `get_history(item_id)` after deletion to see the full audit log.

```python
# On the item:
item.delete()
# item is now unbound — calling any method on it raises RuntimeError

# On the database:
bl.delete(item.id)

# Audit trail is still accessible:
events = bl.get_history(item.id)
# Last event has event_type="deleted" and old_value=JSON of final state
```

**Returns:** `None`

**Raises:** `LookupError` if the item doesn't exist.

---

### `get_item(item_id)`

Fetch a single item by ID.

```python
item = bl.get_item(42)
if item is None:
    print("Not found")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `item_id` | `int` | *required* | The item's ID. |

**Returns:** `BacklogItem` or `None`

---

### `list_items(*, status, assigned_to, item_type, sprint, parent, top_level_only)`

Query the backlog with optional filters. All filters are combined with AND. Results are ordered by priority (descending), then by ID (ascending) as a tiebreak.

```python
bl.list_items()                                  # everything
bl.list_items(status="ready")                    # ready items
bl.list_items(assigned_to="Barry")               # Barry's items
bl.list_items(sprint="sprint-1", status="done")  # done items in sprint 1
bl.list_items(item_type="bug")                   # all bugs
bl.list_items(parent=epic.id)                    # children of an epic
bl.list_items(top_level_only=True)               # top-level items only
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | `str` or `None` | `None` | Filter by status. `None` = no filter. |
| `assigned_to` | `str` or `None` | `None` | Filter by assignee. `None` = no filter. |
| `item_type` | `str` or `None` | `None` | Filter by item type. `None` = no filter. |
| `sprint` | `str` or `None` | `None` | Filter by sprint name. `None` = no filter. |
| `parent` | `int` | *(omit)* | Filter by parent ID. Pass an item ID to get its children. |
| `top_level_only` | `bool` | `False` | If `True`, return only items with no parent. |

**Note:** `parent=None` also returns top-level items (for backward compatibility), but `top_level_only=True` is the preferred, clearer way to express this. Passing both `top_level_only=True` and `parent` raises `ValueError`.

**Returns:** `list[BacklogItem]` (empty list if no matches)

---

### `get_comments()`

Get only the comment events for an item, ordered chronologically. This is a convenience method that filters the event log to return just comments, without status changes, assignments, etc.

```python
# On the item:
comments = item.get_comments()

# On the database:
comments = bl.get_comments(item.id)

for c in comments:
    print(c["agent_id"], c["comment"], c["created_at"])
```

**Returns:** `list[dict]` — each dict has keys: `id`, `item_id`, `event_type`, `old_value`, `new_value`, `agent_id`, `comment`, `created_at`. The `event_type` is always `"comment"`.

**Raises:** `LookupError` if the item has never existed (items that were deleted still return their comments).

---

### `get_history()`

Get an item's full event log including comments, ordered chronologically.

```python
# On the item:
events = item.get_history()

# On the database:
events = bl.get_history(item.id)

for e in events:
    print(e["event_type"], e["agent_id"], e["created_at"])
```

**Returns:** `list[dict]` — each dict has keys: `id`, `item_id`, `event_type`, `old_value`, `new_value`, `agent_id`, `comment`, `created_at`.

**Raises:** `LookupError` if the item doesn't exist.

Event types: `created`, `status_change`, `assigned`, `comment`, `priority_change`, `sprint_change`, `parent_change`, `title_change`, `description_change`, `deleted`.

---

### `refresh()`

Reload all fields from the database. Use this when other agents may have modified the item since you last read it. Only available on the item.

```python
item.refresh()
print(item.status)  # guaranteed fresh
```

**Returns:** `self` (for chaining)

**Raises:** `LookupError` if the item no longer exists.

---

### `close()`

Close all database connections (across all threads) and remove the instance from the singleton cache. The next call to `get_backlog_db()` with the same path and agent will create a fresh instance. Any threads that still hold a reference to this instance will get fresh connections on their next operation.

```python
bl.close()
```

## Input Validation Summary

| Input | Validation |
|---|---|
| `title` | Must be a non-empty, non-whitespace string. |
| `priority` | Must be an integer (`TypeError` if not). |
| `item_type` | Must be one of: `story`, `bug`, `task`, `spike`. |
| `result` | Must be `str` or `None` (`TypeError` if e.g. a dict). |
| `comment text` | Must be a non-empty, non-whitespace string. |
| `parent` | Must reference an existing item. Self-references and cycles are rejected. |
| `status transitions` | Must follow the valid status flow. `done` is terminal. Any status except `done` can transition to `parked`; `parked` can only return to `backlog`. |
