"""Tests for backlog_db.py — Product Backlog."""

from __future__ import annotations

import threading
from collections.abc import Generator
from pathlib import Path

import pytest

from backlog_db import ProductBacklog, _instances, get_backlog_db


@pytest.fixture()
def db(tmp_path: Path) -> Generator[ProductBacklog]:
    """Fresh backlog database in a temp directory."""
    db_path = tmp_path / "test_backlog.db"
    backlog = ProductBacklog(db_path)
    yield backlog
    backlog.close()
    # Clean up WAL/SHM files
    for suffix in ("", "-wal", "-shm"):
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            p.unlink()


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestAdd:
    def test_add_minimal(self, db: ProductBacklog) -> None:
        item = db.add("As a user, I want to log in")
        assert item.id == 1
        assert item.title == "As a user, I want to log in"
        assert item.item_type == "story"
        assert item.status == "backlog"
        assert item.priority == 0
        assert item.sprint is None
        assert item.assigned_to is None

    def test_add_full(self, db: ProductBacklog) -> None:
        item = db.add(
            "Fix login crash",
            description="App crashes on empty password",
            item_type="bug",
            priority=10,
            sprint="sprint-1",
            created_by="Paula",
        )
        assert item.item_type == "bug"
        assert item.priority == 10
        assert item.sprint == "sprint-1"
        assert item.created_by == "Paula"
        assert item.description == "App crashes on empty password"

    def test_add_all_item_types(self, db: ProductBacklog) -> None:
        for item_type in ("story", "bug", "task", "spike"):
            item = db.add(f"A {item_type}", item_type=item_type)
            assert item.item_type == item_type

    def test_add_invalid_type(self, db: ProductBacklog) -> None:
        with pytest.raises(ValueError, match="Invalid item_type"):
            db.add("Bad item", item_type="epic")

    def test_add_creates_event(self, db: ProductBacklog) -> None:
        item = db.add("Story one", created_by="Paula")
        events = db.get_history(item.id)
        assert len(events) == 1
        assert events[0]["event_type"] == "created"
        assert events[0]["agent_id"] == "Paula"


# ---------------------------------------------------------------------------
# assign
# ---------------------------------------------------------------------------


class TestAssign:
    def test_assign(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        updated = db.assign(item.id, "Barry")
        assert updated.assigned_to == "Barry"

    def test_reassign(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.assign(item.id, "Barry")
        updated = db.assign(item.id, "Bonnie")
        assert updated.assigned_to == "Bonnie"
        events = db.get_history(item.id)
        assign_events = [e for e in events if e["event_type"] == "assigned"]
        assert len(assign_events) == 2
        assert assign_events[1]["old_value"] == "Barry"
        assert assign_events[1]["new_value"] == "Bonnie"

    def test_assign_records_who_assigned(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.assign(item.id, "Barry", agent="Sam")
        events = db.get_history(item.id)
        assign_events = [e for e in events if e["event_type"] == "assigned"]
        assert assign_events[0]["new_value"] == "Barry"
        assert assign_events[0]["agent_id"] == "Sam"

    def test_unassign(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.assign(item.id, "Barry")
        updated = db.assign(item.id, None)
        assert updated.assigned_to is None

    def test_assign_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.assign(999, "Barry")


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    def test_happy_path(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item = db.update_status(item.id, "ready", agent="Sam")
        assert item.status == "ready"
        item = db.update_status(item.id, "in_progress", agent="Barry")
        assert item.status == "in_progress"
        item = db.update_status(item.id, "review", agent="Barry")
        assert item.status == "review"
        item = db.update_status(item.id, "done", agent="Sam")
        assert item.status == "done"

    def test_invalid_transition(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(ValueError, match="Cannot transition"):
            db.update_status(item.id, "done")

    def test_invalid_status(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(ValueError, match="Invalid status"):
            db.update_status(item.id, "cancelled")

    def test_backward_transition_ready_to_backlog(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        updated = db.update_status(item.id, "backlog")
        assert updated.status == "backlog"

    def test_backward_transition_in_progress_to_ready(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        updated = db.update_status(item.id, "ready")
        assert updated.status == "ready"

    def test_backward_transition_review_to_in_progress(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        updated = db.update_status(item.id, "in_progress")
        assert updated.status == "in_progress"

    def test_done_is_terminal(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        db.update_status(item.id, "done")
        for status in ("backlog", "ready", "in_progress", "review"):
            with pytest.raises(ValueError, match="Cannot transition"):
                db.update_status(item.id, status)

    def test_updated_at_changes(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        updated = db.update_status(item.id, "ready")
        assert updated.updated_at >= original

    def test_status_with_result(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        updated = db.update_status(item.id, "done", result="Deployed to prod")
        assert updated.result == "Deployed to prod"

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_status(999, "ready")

    def test_status_events(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready", agent="Sam")
        events = db.get_history(item.id)
        status_events = [e for e in events if e["event_type"] == "status_change"]
        assert len(status_events) == 1
        assert status_events[0]["old_value"] == "backlog"
        assert status_events[0]["new_value"] == "ready"
        assert status_events[0]["agent_id"] == "Sam"


# ---------------------------------------------------------------------------
# update_priority
# ---------------------------------------------------------------------------


class TestUpdatePriority:
    def test_update_priority(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=5)
        updated = db.update_priority(item.id, 20, agent="Sam")
        assert updated.priority == 20

    def test_priority_event(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=5)
        db.update_priority(item.id, 20, agent="Sam")
        events = db.get_history(item.id)
        prio_events = [e for e in events if e["event_type"] == "priority_change"]
        assert len(prio_events) == 1
        assert prio_events[0]["old_value"] == "5"
        assert prio_events[0]["new_value"] == "20"

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_priority(999, 10)


# ---------------------------------------------------------------------------
# comment
# ---------------------------------------------------------------------------


class TestComment:
    def test_comment(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "Barry", "Started working on this")
        events = db.get_history(item.id)
        comments = [e for e in events if e["event_type"] == "comment"]
        assert len(comments) == 1
        assert comments[0]["agent_id"] == "Barry"
        assert comments[0]["comment"] == "Started working on this"

    def test_multiple_comments(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "Barry", "First comment")
        db.comment(item.id, "Bonnie", "Second comment")
        db.comment(item.id, "Barry", "Third comment")
        events = db.get_history(item.id)
        comments = [e for e in events if e["event_type"] == "comment"]
        assert len(comments) == 3
        assert comments[0]["comment"] == "First comment"
        assert comments[1]["agent_id"] == "Bonnie"
        assert comments[2]["comment"] == "Third comment"

    def test_comment_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.comment(999, "Barry", "text")


# ---------------------------------------------------------------------------
# get / query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_get_item(self, db: ProductBacklog) -> None:
        created = db.add("Story")
        fetched = db.get_item(created.id)
        assert fetched is not None
        assert fetched.title == "Story"

    def test_get_item_not_found(self, db: ProductBacklog) -> None:
        assert db.get_item(999) is None

    def test_list_items_all(self, db: ProductBacklog) -> None:
        db.add("A", priority=1)
        db.add("B", priority=10)
        db.add("C", priority=5)
        items = db.list_items()
        assert len(items) == 3
        # Should be ordered by priority DESC
        assert items[0].title == "B"
        assert items[1].title == "C"
        assert items[2].title == "A"

    def test_list_items_filtered(self, db: ProductBacklog) -> None:
        db.add("S1", item_type="story")
        db.add("B1", item_type="bug")
        db.add("S2", item_type="story")
        stories = db.list_items(item_type="story")
        assert len(stories) == 2
        bugs = db.list_items(item_type="bug")
        assert len(bugs) == 1

    def test_list_items_by_status(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        backlog_items = db.list_items(status="backlog")
        ready_items = db.list_items(status="ready")
        assert len(backlog_items) == 0
        assert len(ready_items) == 1

    def test_list_items_by_assigned(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.assign(item.id, "Barry")
        db.add("Unassigned story")
        barry_items = db.list_items(assigned_to="Barry")
        assert len(barry_items) == 1
        assert barry_items[0].title == "Story"

    def test_list_items_by_sprint(self, db: ProductBacklog) -> None:
        db.add("S1", sprint="sprint-1")
        db.add("S2", sprint="sprint-2")
        db.add("S3", sprint="sprint-1")
        sprint1 = db.list_items(sprint="sprint-1")
        assert len(sprint1) == 2
        assert all(i.sprint == "sprint-1" for i in sprint1)

    def test_list_items_combined_filters(self, db: ProductBacklog) -> None:
        db.add("S1", item_type="story", sprint="sprint-1")
        db.add("B1", item_type="bug", sprint="sprint-1")
        db.add("S2", item_type="story", sprint="sprint-2")
        item = db.add("S3", item_type="story", sprint="sprint-1")
        db.assign(item.id, "Barry")
        results = db.list_items(item_type="story", sprint="sprint-1", assigned_to="Barry")
        assert len(results) == 1
        assert results[0].title == "S3"

    def test_list_items_empty(self, db: ProductBacklog) -> None:
        assert db.list_items() == []
        assert db.list_items(status="done") == []

    def test_list_items_priority_tiebreak_by_id(self, db: ProductBacklog) -> None:
        a = db.add("First", priority=5)
        b = db.add("Second", priority=5)
        c = db.add("Third", priority=5)
        items = db.list_items()
        assert [i.id for i in items] == [a.id, b.id, c.id]

    def test_get_history_nonexistent_item(self, db: ProductBacklog) -> None:
        assert db.get_history(999) == []

    def test_get_sprint(self, db: ProductBacklog) -> None:
        db.add("S1", sprint="sprint-1", priority=1)
        db.add("S2", sprint="sprint-1", priority=10)
        db.add("S3", sprint="sprint-2")
        sprint1 = db.get_sprint("sprint-1")
        assert len(sprint1) == 2
        assert sprint1[0].title == "S2"  # higher priority first

    def test_get_sprint_with_status(self, db: ProductBacklog) -> None:
        item = db.add("S1", sprint="sprint-1")
        db.update_status(item.id, "ready")
        db.add("S2", sprint="sprint-1")
        ready = db.get_sprint("sprint-1", status="ready")
        assert len(ready) == 1


# ---------------------------------------------------------------------------
# BacklogItem bound methods
# ---------------------------------------------------------------------------


class TestBacklogItemMethods:
    def test_assign_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.assign("Barry")
        assert item.assigned_to == "Barry"
        item.refresh()
        assert item.assigned_to == "Barry"

    def test_unassign_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.assign("Barry")
        assert item.assigned_to == "Barry"
        item.assign(None)
        assert item.assigned_to is None
        item.refresh()
        assert item.assigned_to is None

    def test_update_status_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.update_status("ready", agent="Sam")
        assert item.status == "ready"

    def test_update_status_method_with_result(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.update_status("ready", agent="Sam")
        item.update_status("in_progress", agent="Barry")
        item.update_status("review", agent="Barry")
        item.update_status("done", agent="Sam", result="Shipped!")
        assert item.status == "done"
        assert item.result == "Shipped!"
        item.refresh()
        assert item.result == "Shipped!"

    def test_assign_method_with_agent(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.assign("Barry", agent="Sam")
        events = item.get_history()
        assign_events = [e for e in events if e["event_type"] == "assigned"]
        assert assign_events[0]["agent_id"] == "Sam"
        assert assign_events[0]["new_value"] == "Barry"

    def test_bound_methods_sync_updated_at(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        item.update_status("ready", agent="Sam")
        assert item.updated_at >= original
        after_status = item.updated_at
        item.assign("Barry", agent="Sam")
        assert item.updated_at >= after_status

    def test_comment_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.comment("Barry", "Looks good")
        history = item.get_history()
        comments = [e for e in history if e["event_type"] == "comment"]
        assert len(comments) == 1

    def test_refresh(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=0)
        db.update_priority(item.id, 50)
        assert item.priority == 0  # stale
        item.refresh()
        assert item.priority == 50  # fresh


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_adds(self, db: ProductBacklog) -> None:
        errors: list[Exception] = []

        def add_items(start: int) -> None:
            try:
                for i in range(10):
                    db.add(f"Item {start + i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_items, args=(i * 10,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        items = db.list_items()
        assert len(items) == 50

    def test_concurrent_status_updates(self, db: ProductBacklog) -> None:
        """Multiple agents updating different items concurrently."""
        items = [db.add(f"Item {i}") for i in range(10)]
        for item in items:
            db.update_status(item.id, "ready")
        errors: list[Exception] = []

        def transition(item_id: int) -> None:
            try:
                db.update_status(item_id, "in_progress")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=transition, args=(item.id,)) for item in items]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        in_progress = db.list_items(status="in_progress")
        assert len(in_progress) == 10

    def test_concurrent_same_item_status_race(self, db: ProductBacklog) -> None:
        """Two agents try to move the same item from ready to in_progress."""
        item = db.add("Contested")
        db.update_status(item.id, "ready")
        results: list[str] = []

        def try_claim(agent: str) -> None:
            try:
                db.update_status(item.id, "in_progress", agent=agent)
                results.append(f"{agent}:ok")
            except ValueError:
                results.append(f"{agent}:rejected")

        t1 = threading.Thread(target=try_claim, args=("Barry",))
        t2 = threading.Thread(target=try_claim, args=("Bonnie",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        # Exactly one should succeed, one should fail (already in_progress)
        ok = [r for r in results if r.endswith(":ok")]
        rejected = [r for r in results if r.endswith(":rejected")]
        assert len(ok) == 1
        assert len(rejected) == 1
        refreshed = db.get_item(item.id)
        assert refreshed is not None
        assert refreshed.status == "in_progress"

    def test_concurrent_comments_same_item(self, db: ProductBacklog) -> None:
        """Multiple agents commenting on the same item concurrently."""
        item = db.add("Contested item")
        errors: list[Exception] = []

        def add_comments(agent: str) -> None:
            try:
                for i in range(10):
                    db.comment(item.id, agent, f"{agent} comment {i}")
            except Exception as e:
                errors.append(e)

        agents = ["Barry", "Bonnie", "Bill", "Beryl", "Bret"]
        threads = [threading.Thread(target=add_comments, args=(a,)) for a in agents]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        events = db.get_history(item.id)
        comments = [e for e in events if e["event_type"] == "comment"]
        assert len(comments) == 50  # 5 agents x 10 comments


# ---------------------------------------------------------------------------
# get_backlog_db singleton
# ---------------------------------------------------------------------------


class TestGetBacklogDbSingleton:
    def test_singleton_returns_same_instance(self, tmp_path: Path) -> None:
        db_path = tmp_path / "singleton.db"
        b1 = get_backlog_db(db_path)
        b2 = get_backlog_db(db_path)
        assert b1 is b2
        b1.close()  # also removes from _instances

    def test_different_paths_different_instances(self, tmp_path: Path) -> None:
        b1 = get_backlog_db(tmp_path / "a.db")
        b2 = get_backlog_db(tmp_path / "b.db")
        assert b1 is not b2
        b1.close()
        b2.close()

    def test_close_removes_from_singleton_cache(self, tmp_path: Path) -> None:
        db_path = tmp_path / "lifecycle.db"
        b1 = get_backlog_db(db_path)
        key = str(db_path.resolve())
        assert key in _instances
        b1.close()
        assert key not in _instances
        # A new call should create a fresh instance
        b2 = get_backlog_db(db_path)
        assert b2 is not b1
        b2.close()


# ---------------------------------------------------------------------------
# updated_at on mutations
# ---------------------------------------------------------------------------


class TestUpdatedAt:
    def test_assign_updates_timestamp(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        updated = db.assign(item.id, "Barry")
        assert updated.updated_at >= original

    def test_priority_updates_timestamp(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=1)
        original = item.updated_at
        updated = db.update_priority(item.id, 99)
        assert updated.updated_at >= original

    def test_timestamp_format_consistent(self, db: ProductBacklog) -> None:
        """created_at (SQLite DEFAULT) and updated_at (Python _now) use same format."""
        item = db.add("Story")
        # Both should be ISO with millisecond precision: YYYY-MM-DDTHH:MM:SS.mmmZ
        assert len(item.created_at) == 24
        assert item.created_at.endswith("Z")
        db.update_status(item.id, "ready")
        refreshed = db.get_item(item.id)
        assert refreshed is not None
        assert len(refreshed.updated_at) == 24
        assert refreshed.updated_at.endswith("Z")


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------


class TestHistory:
    def test_full_lifecycle(self, db: ProductBacklog) -> None:
        item = db.add("Story", created_by="Paula")
        db.assign(item.id, "Barry")
        db.update_status(item.id, "ready", agent="Sam")
        db.comment(item.id, "Barry", "Starting this")
        db.update_status(item.id, "in_progress", agent="Barry")
        db.update_status(item.id, "review", agent="Barry")
        db.update_status(item.id, "done", agent="Sam", result="Shipped!")

        events = db.get_history(item.id)
        types = [e["event_type"] for e in events]
        assert types == [
            "created",
            "assigned",
            "status_change",
            "comment",
            "status_change",
            "status_change",
            "status_change",
        ]
