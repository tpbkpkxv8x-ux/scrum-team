"""Tests for backlog_db.py — Product Backlog."""

from __future__ import annotations

import os
import threading
from collections.abc import Generator
from pathlib import Path

import pytest

from backlog_db import BacklogItem, ProductBacklog, _instances, get_backlog_db


@pytest.fixture()
def db(tmp_path: Path) -> Generator[ProductBacklog]:
    """Fresh backlog database in a temp directory."""
    db_path = tmp_path / "test_backlog.db"
    backlog = ProductBacklog(db_path, agent="Test")
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
        assert item.parent is None

    def test_add_full(self, db: ProductBacklog) -> None:
        item = db.add(
            "Fix login crash",
            description="App crashes on empty password",
            item_type="bug",
            priority=10,
            sprint="sprint-1",
        )
        assert item.item_type == "bug"
        assert item.priority == 10
        assert item.sprint == "sprint-1"
        assert item.created_by is not None
        assert item.created_by.startswith("Test/pid=")
        assert item.description == "App crashes on empty password"

    def test_add_all_item_types(self, db: ProductBacklog) -> None:
        for item_type in ("story", "bug", "task", "spike"):
            item = db.add(f"A {item_type}", item_type=item_type)
            assert item.item_type == item_type

    def test_add_invalid_type(self, db: ProductBacklog) -> None:
        with pytest.raises(ValueError, match="Invalid item_type"):
            db.add("Bad item", item_type="epic")

    def test_add_creates_event(self, db: ProductBacklog) -> None:
        item = db.add("Story one")
        events = db.get_history(item.id)
        assert len(events) == 1
        assert events[0]["event_type"] == "created"
        assert events[0]["agent_id"] is not None
        assert events[0]["agent_id"].startswith("Test/pid=")

    def test_add_with_parent(self, db: ProductBacklog) -> None:
        parent = db.add("Epic")
        child = db.add("Subtask", parent=parent.id)
        assert child.parent == parent.id

    def test_add_empty_title(self, db: ProductBacklog) -> None:
        with pytest.raises(ValueError, match="Title must not be empty"):
            db.add("")

    def test_add_whitespace_only_title(self, db: ProductBacklog) -> None:
        with pytest.raises(ValueError, match="Title must not be empty"):
            db.add("   ")

    def test_add_non_int_priority(self, db: ProductBacklog) -> None:
        with pytest.raises(TypeError, match="Priority must be an integer"):
            db.add("Story", priority="high")  # type: ignore[arg-type]

    def test_add_bool_priority_rejected(self, db: ProductBacklog) -> None:
        with pytest.raises(TypeError, match="Priority must be an integer"):
            db.add("Story", priority=True)

    def test_add_nonexistent_parent(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError, match="Parent item 999 not found"):
            db.add("Child", parent=999)


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
        db.assign(item.id, "Barry")
        events = db.get_history(item.id)
        assign_events = [e for e in events if e["event_type"] == "assigned"]
        assert assign_events[0]["new_value"] == "Barry"
        assert assign_events[0]["agent_id"] is not None
        assert assign_events[0]["agent_id"].startswith("Test/pid=")

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
        item = db.update_status(item.id, "ready")
        assert item.status == "ready"
        item = db.update_status(item.id, "in_progress")
        assert item.status == "in_progress"
        item = db.update_status(item.id, "review")
        assert item.status == "review"
        item = db.update_status(item.id, "done")
        assert item.status == "done"

    def test_happy_path_via_merged(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        item = db.update_status(item.id, "merged")
        assert item.status == "merged"
        item = db.update_status(item.id, "done")
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
        for status in ("backlog", "ready", "in_progress", "review", "merged"):
            with pytest.raises(ValueError, match="Cannot transition"):
                db.update_status(item.id, status)

    def test_merged_to_in_progress(self, db: ProductBacklog) -> None:
        """merged can go back to in_progress if rework is needed."""
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        db.update_status(item.id, "merged")
        updated = db.update_status(item.id, "in_progress")
        assert updated.status == "in_progress"

    def test_merged_to_parked(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        db.update_status(item.id, "merged")
        updated = db.update_status(item.id, "parked")
        assert updated.status == "parked"

    def test_backlog_to_merged_invalid(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(ValueError, match="Cannot transition"):
            db.update_status(item.id, "merged")

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

    def test_clear_result(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready", result="some note")
        fetched = db.get_item(item.id)
        assert fetched is not None
        assert fetched.result == "some note"
        db.update_status(item.id, "in_progress", result=None)
        fetched = db.get_item(item.id)
        assert fetched is not None
        assert fetched.result is None

    def test_omit_result_preserves_existing(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready", result="some note")
        db.update_status(item.id, "in_progress")  # no result kwarg
        fetched = db.get_item(item.id)
        assert fetched is not None
        assert fetched.result == "some note"

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_status(999, "ready")

    def test_non_string_result_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(TypeError, match="Result must be a string or None"):
            db.update_status(item.id, "ready", result={"k": "v"})

    def test_status_events(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        events = db.get_history(item.id)
        status_events = [e for e in events if e["event_type"] == "status_change"]
        assert len(status_events) == 1
        assert status_events[0]["old_value"] == "backlog"
        assert status_events[0]["new_value"] == "ready"
        assert status_events[0]["agent_id"] is not None
        assert status_events[0]["agent_id"].startswith("Test/pid=")


# ---------------------------------------------------------------------------
# update_priority
# ---------------------------------------------------------------------------


class TestUpdatePriority:
    def test_update_priority(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=5)
        updated = db.update_priority(item.id, 20)
        assert updated.priority == 20

    def test_priority_event(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=5)
        db.update_priority(item.id, 20)
        events = db.get_history(item.id)
        prio_events = [e for e in events if e["event_type"] == "priority_change"]
        assert len(prio_events) == 1
        assert prio_events[0]["old_value"] == "5"
        assert prio_events[0]["new_value"] == "20"

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_priority(999, 10)

    def test_non_int_priority_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(TypeError, match="Priority must be an integer"):
            db.update_priority(item.id, "high")  # type: ignore[arg-type]

    def test_float_priority_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(TypeError, match="Priority must be an integer"):
            db.update_priority(item.id, 3.14)  # type: ignore[arg-type]

    def test_bool_priority_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(TypeError, match="Priority must be an integer"):
            db.update_priority(item.id, True)


# ---------------------------------------------------------------------------
# update_sprint
# ---------------------------------------------------------------------------


class TestUpdateSprint:
    def test_set_sprint(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        assert item.sprint is None
        updated = db.update_sprint(item.id, "sprint-1")
        assert updated.sprint == "sprint-1"

    def test_change_sprint(self, db: ProductBacklog) -> None:
        item = db.add("Story", sprint="sprint-1")
        updated = db.update_sprint(item.id, "sprint-2")
        assert updated.sprint == "sprint-2"

    def test_remove_sprint(self, db: ProductBacklog) -> None:
        item = db.add("Story", sprint="sprint-1")
        updated = db.update_sprint(item.id, None)
        assert updated.sprint is None

    def test_sprint_event(self, db: ProductBacklog) -> None:
        item = db.add("Story", sprint="sprint-1")
        db.update_sprint(item.id, "sprint-2")
        events = db.get_history(item.id)
        sprint_events = [e for e in events if e["event_type"] == "sprint_change"]
        assert len(sprint_events) == 1
        assert sprint_events[0]["old_value"] == "sprint-1"
        assert sprint_events[0]["new_value"] == "sprint-2"
        assert sprint_events[0]["agent_id"] is not None

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_sprint(999, "sprint-1")

    def test_updates_timestamp(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        updated = db.update_sprint(item.id, "sprint-1")
        assert updated.updated_at >= original


# ---------------------------------------------------------------------------
# update_parent
# ---------------------------------------------------------------------------


class TestUpdateParent:
    def test_set_parent(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child")
        assert child.parent is None
        updated = db.update_parent(child.id, epic.id)
        assert updated.parent == epic.id

    def test_change_parent(self, db: ProductBacklog) -> None:
        epic1 = db.add("Epic 1")
        epic2 = db.add("Epic 2")
        child = db.add("Child", parent=epic1.id)
        updated = db.update_parent(child.id, epic2.id)
        assert updated.parent == epic2.id

    def test_remove_parent(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child", parent=epic.id)
        updated = db.update_parent(child.id, None)
        assert updated.parent is None

    def test_parent_event(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child")
        db.update_parent(child.id, epic.id)
        events = db.get_history(child.id)
        parent_events = [e for e in events if e["event_type"] == "parent_change"]
        assert len(parent_events) == 1
        assert parent_events[0]["old_value"] is None
        assert parent_events[0]["new_value"] == str(epic.id)
        assert parent_events[0]["agent_id"] is not None

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_parent(999, None)

    def test_updates_timestamp(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child")
        original = child.updated_at
        updated = db.update_parent(child.id, epic.id)
        assert updated.updated_at >= original

    def test_parent_event_remove(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child", parent=epic.id)
        db.update_parent(child.id, None)
        events = db.get_history(child.id)
        parent_events = [e for e in events if e["event_type"] == "parent_change"]
        assert len(parent_events) == 1
        assert parent_events[0]["old_value"] == str(epic.id)
        assert parent_events[0]["new_value"] is None

    def test_self_reference_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Item")
        with pytest.raises(ValueError, match="cannot be its own parent"):
            db.update_parent(item.id, item.id)

    def test_circular_reference_rejected(self, db: ProductBacklog) -> None:
        a = db.add("A")
        b = db.add("B", parent=a.id)
        with pytest.raises(ValueError, match="[Cc]ircular parent reference"):
            db.update_parent(a.id, b.id)

    def test_deep_circular_reference_rejected(self, db: ProductBacklog) -> None:
        a = db.add("A")
        b = db.add("B", parent=a.id)
        c = db.add("C", parent=b.id)
        with pytest.raises(ValueError, match="[Cc]ircular parent reference"):
            db.update_parent(a.id, c.id)

    def test_nonexistent_parent_rejected(self, db: ProductBacklog) -> None:
        child = db.add("Child")
        with pytest.raises(LookupError, match="Parent item 999 not found"):
            db.update_parent(child.id, 999)


# ---------------------------------------------------------------------------
# comment
# ---------------------------------------------------------------------------


class TestComment:
    def test_comment(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "Started working on this")
        events = db.get_history(item.id)
        comments = [e for e in events if e["event_type"] == "comment"]
        assert len(comments) == 1
        assert comments[0]["agent_id"] is not None
        assert comments[0]["agent_id"].startswith("Test/pid=")
        assert comments[0]["comment"] == "Started working on this"

    def test_multiple_comments(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "First comment")
        db.comment(item.id, "Second comment")
        db.comment(item.id, "Third comment")
        events = db.get_history(item.id)
        comments = [e for e in events if e["event_type"] == "comment"]
        assert len(comments) == 3
        assert comments[0]["comment"] == "First comment"
        assert comments[2]["comment"] == "Third comment"

    def test_comment_updates_timestamp(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        db.comment(item.id, "A comment")
        refreshed = db.get_item(item.id)
        assert refreshed is not None
        assert refreshed.updated_at >= original

    def test_comment_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.comment(999, "text")

    def test_empty_comment_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(ValueError, match="Comment text must not be empty"):
            db.comment(item.id, "")

    def test_whitespace_only_comment_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        with pytest.raises(ValueError, match="Comment text must not be empty"):
            db.comment(item.id, "   ")

    def test_comment_returns_backlog_item(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        result = db.comment(item.id, "Hello")
        assert isinstance(result, BacklogItem)
        assert result.id == item.id


# ---------------------------------------------------------------------------
# get_comments
# ---------------------------------------------------------------------------


class TestGetComments:
    def test_no_comments(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        assert db.get_comments(item.id) == []

    def test_single_comment(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "First note")
        comments = db.get_comments(item.id)
        assert len(comments) == 1
        assert comments[0]["comment"] == "First note"
        assert comments[0]["event_type"] == "comment"
        assert comments[0]["item_id"] == item.id

    def test_multiple_comments_ordered(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "Alpha")
        db.comment(item.id, "Beta")
        db.comment(item.id, "Gamma")
        comments = db.get_comments(item.id)
        assert len(comments) == 3
        assert [c["comment"] for c in comments] == ["Alpha", "Beta", "Gamma"]

    def test_excludes_non_comment_events(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        db.comment(item.id, "Only this")
        db.assign(item.id, "Barry")
        comments = db.get_comments(item.id)
        assert len(comments) == 1
        assert comments[0]["comment"] == "Only this"

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError, match="Backlog item 999 not found"):
            db.get_comments(999)

    def test_deleted_item_returns_comments(self, db: ProductBacklog) -> None:
        item = db.add("Doomed")
        db.comment(item.id, "Before deletion")
        item_id = item.id
        db.delete(item_id)
        comments = db.get_comments(item_id)
        assert len(comments) == 1
        assert comments[0]["comment"] == "Before deletion"

    def test_records_agent_id(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "By agent")
        comments = db.get_comments(item.id)
        assert comments[0]["agent_id"] is not None
        assert comments[0]["agent_id"].startswith("Test/pid=")

    def test_deleted_item_no_comments_returns_empty(self, db: ProductBacklog) -> None:
        item = db.add("Doomed")
        item_id = item.id
        db.delete(item_id)
        comments = db.get_comments(item_id)
        assert comments == []

    def test_comments_isolated_between_items(self, db: ProductBacklog) -> None:
        a = db.add("Item A")
        b = db.add("Item B")
        db.comment(a.id, "A's comment")
        db.comment(b.id, "B's comment")
        comments_a = db.get_comments(a.id)
        comments_b = db.get_comments(b.id)
        assert len(comments_a) == 1
        assert comments_a[0]["comment"] == "A's comment"
        assert len(comments_b) == 1
        assert comments_b[0]["comment"] == "B's comment"

    def test_via_backlog_item_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.comment("Hello")
        item.comment("World")
        comments = item.get_comments()
        assert len(comments) == 2
        assert comments[0]["comment"] == "Hello"
        assert comments[1]["comment"] == "World"


# ---------------------------------------------------------------------------
# update_title
# ---------------------------------------------------------------------------


class TestUpdateTitle:
    def test_update_title(self, db: ProductBacklog) -> None:
        item = db.add("Original")
        updated = db.update_title(item.id, "Renamed")
        assert updated.title == "Renamed"

    def test_title_event(self, db: ProductBacklog) -> None:
        item = db.add("Original")
        db.update_title(item.id, "Renamed")
        events = db.get_history(item.id)
        title_events = [e for e in events if e["event_type"] == "title_change"]
        assert len(title_events) == 1
        assert title_events[0]["old_value"] == "Original"
        assert title_events[0]["new_value"] == "Renamed"

    def test_empty_title_rejected(self, db: ProductBacklog) -> None:
        item = db.add("Original")
        with pytest.raises(ValueError, match="Title must not be empty"):
            db.update_title(item.id, "")

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_title(999, "New")


# ---------------------------------------------------------------------------
# update_description
# ---------------------------------------------------------------------------


class TestUpdateDescription:
    def test_set_description(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        assert item.description is None
        updated = db.update_description(item.id, "Detailed requirements")
        assert updated.description == "Detailed requirements"

    def test_clear_description(self, db: ProductBacklog) -> None:
        item = db.add("Story", description="Old")
        updated = db.update_description(item.id, None)
        assert updated.description is None

    def test_description_event(self, db: ProductBacklog) -> None:
        item = db.add("Story", description="Old")
        db.update_description(item.id, "New")
        events = db.get_history(item.id)
        desc_events = [e for e in events if e["event_type"] == "description_change"]
        assert len(desc_events) == 1
        assert desc_events[0]["old_value"] == "Old"
        assert desc_events[0]["new_value"] == "New"

    def test_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.update_description(999, "desc")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.delete(item.id)
        assert db.get_item(item.id) is None

    def test_delete_not_found(self, db: ProductBacklog) -> None:
        with pytest.raises(LookupError):
            db.delete(999)

    def test_delete_unparents_children(self, db: ProductBacklog) -> None:
        parent = db.add("Epic")
        child = db.add("Child", parent=parent.id)
        db.delete(parent.id)
        refreshed_child = db.get_item(child.id)
        assert refreshed_child is not None
        assert refreshed_child.parent is None

    def test_delete_records_parent_change_for_children(self, db: ProductBacklog) -> None:
        parent = db.add("Epic")
        child = db.add("Child", parent=parent.id)
        original_updated_at = child.updated_at
        db.delete(parent.id)
        # Child should have a parent_change event
        events = db.get_history(child.id)
        parent_events = [e for e in events if e["event_type"] == "parent_change"]
        assert len(parent_events) == 1
        assert parent_events[0]["old_value"] == str(parent.id)
        assert parent_events[0]["new_value"] is None
        assert "deleted" in parent_events[0]["comment"]
        # Child's updated_at should have advanced
        refreshed = db.get_item(child.id)
        assert refreshed is not None
        assert refreshed.updated_at >= original_updated_at

    def test_delete_preserves_audit_log(self, db: ProductBacklog) -> None:
        import json

        item = db.add("Story")
        db.comment(item.id, "A note")
        item_id = item.id
        db.delete(item_id)
        # Events are preserved via public API (including the deletion event)
        events = db.get_history(item_id)
        assert len(events) == 3
        types = [e["event_type"] for e in events]
        assert types == ["created", "comment", "deleted"]
        # Deleted event stores the item's final state as JSON
        deleted_event = events[2]
        final_state = json.loads(deleted_event["old_value"])
        assert final_state["title"] == "Story"
        assert final_state["id"] == item_id

    def test_delete_removes_from_list(self, db: ProductBacklog) -> None:
        db.add("Keep")
        item = db.add("Remove")
        db.delete(item.id)
        items = db.list_items()
        assert len(items) == 1
        assert items[0].title == "Keep"


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
        with pytest.raises(LookupError):
            db.get_history(999)

    def test_list_items_by_parent(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child1 = db.add("Child 1", parent=epic.id)
        child2 = db.add("Child 2", parent=epic.id)
        db.add("Top level")
        children = db.list_items(parent=epic.id)
        assert len(children) == 2
        assert {c.id for c in children} == {child1.id, child2.id}

    def test_list_items_top_level_only(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        db.add("Child", parent=epic.id)
        db.add("Another top level")
        top = db.list_items(parent=None)
        assert len(top) == 2
        assert all(i.parent is None for i in top)

    def test_list_items_parent_omitted_returns_all(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        db.add("Child", parent=epic.id)
        all_items = db.list_items()
        assert len(all_items) == 2

    def test_list_items_top_level_only_and_parent_conflict(self, db: ProductBacklog) -> None:
        with pytest.raises(ValueError, match="Cannot specify both"):
            db.list_items(top_level_only=True, parent=1)

    def test_list_items_top_level_only_flag(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        db.add("Child", parent=epic.id)
        db.add("Another top level")
        top = db.list_items(top_level_only=True)
        assert len(top) == 2
        assert all(i.parent is None for i in top)


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
        item.update_status("ready")
        assert item.status == "ready"

    def test_update_status_method_with_result(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.update_status("ready")
        item.update_status("in_progress")
        item.update_status("review")
        item.update_status("done", result="Shipped!")
        assert item.status == "done"
        assert item.result == "Shipped!"
        item.refresh()
        assert item.result == "Shipped!"

    def test_assign_method_records_agent(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.assign("Barry")
        events = item.get_history()
        assign_events = [e for e in events if e["event_type"] == "assigned"]
        assert assign_events[0]["agent_id"] is not None
        assert assign_events[0]["agent_id"].startswith("Test/pid=")
        assert assign_events[0]["new_value"] == "Barry"

    def test_bound_methods_sync_updated_at(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        item.update_status("ready")
        assert item.updated_at >= original
        after_status = item.updated_at
        item.assign("Barry")
        assert item.updated_at >= after_status

    def test_update_priority_method(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=5)
        item.update_priority(20)
        assert item.priority == 20
        item.refresh()
        assert item.priority == 20

    def test_update_sprint_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.update_sprint("sprint-1")
        assert item.sprint == "sprint-1"
        item.refresh()
        assert item.sprint == "sprint-1"

    def test_update_sprint_method_remove(self, db: ProductBacklog) -> None:
        item = db.add("Story", sprint="sprint-1")
        item.update_sprint(None)
        assert item.sprint is None
        item.refresh()
        assert item.sprint is None

    def test_update_parent_method(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child")
        child.update_parent(epic.id)
        assert child.parent == epic.id
        child.refresh()
        assert child.parent == epic.id

    def test_update_parent_method_remove(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child", parent=epic.id)
        child.update_parent(None)
        assert child.parent is None
        child.refresh()
        assert child.parent is None

    def test_update_title_method(self, db: ProductBacklog) -> None:
        item = db.add("Original")
        item.update_title("Renamed")
        assert item.title == "Renamed"
        item.refresh()
        assert item.title == "Renamed"

    def test_update_description_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.update_description("New desc")
        assert item.description == "New desc"
        item.refresh()
        assert item.description == "New desc"

    def test_delete_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item_id = item.id
        item.delete()
        assert db.get_item(item_id) is None
        # Item should be unbound after delete
        with pytest.raises(RuntimeError, match="not bound"):
            item.refresh()

    def test_comment_method(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        item.comment("Looks good")
        history = item.get_history()
        comments = [e for e in history if e["event_type"] == "comment"]
        assert len(comments) == 1
        assert comments[0]["comment"] == "Looks good"
        assert comments[0]["agent_id"] is not None

    def test_comment_method_syncs_updated_at(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        original = item.updated_at
        item.comment("A comment")
        assert item.updated_at >= original
        # Verify in-memory matches DB (fix for timestamp drift)
        item.refresh()
        fetched = db.get_item(item.id)
        assert fetched is not None
        assert item.updated_at == fetched.updated_at

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
                db.update_status(item.id, "in_progress")
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

    def test_stale_connection_after_close(self, tmp_path: Path) -> None:
        """After close(), worker threads get fresh connections, not stale ones."""
        db_path = tmp_path / "stale.db"
        bl = ProductBacklog(db_path, agent="Test")
        errors: list[Exception] = []

        def use_from_thread() -> None:
            try:
                bl.add("Before close")
            except Exception as e:
                errors.append(e)

        # Create connection in worker thread
        t = threading.Thread(target=use_from_thread)
        t.start()
        t.join()
        assert not errors

        # Close all connections
        bl.close()

        # Worker thread should get a fresh connection, not ProgrammingError
        bl2 = ProductBacklog(db_path, agent="Test")

        def use_after_close() -> None:
            try:
                bl2.add("After close")
            except Exception as e:
                errors.append(e)

        t2 = threading.Thread(target=use_after_close)
        t2.start()
        t2.join()
        assert not errors
        items = bl2.list_items()
        assert len(items) == 2
        bl2.close()

    def test_concurrent_delete_same_item(self, db: ProductBacklog) -> None:
        """Two agents try to delete the same item — one succeeds, one gets LookupError."""
        item = db.add("Contested")
        results: list[str] = []

        def try_delete(agent: str) -> None:
            try:
                db.delete(item.id)
                results.append(f"{agent}:ok")
            except LookupError:
                results.append(f"{agent}:not_found")

        t1 = threading.Thread(target=try_delete, args=("A",))
        t2 = threading.Thread(target=try_delete, args=("B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        ok = [r for r in results if r.endswith(":ok")]
        not_found = [r for r in results if r.endswith(":not_found")]
        assert len(ok) == 1
        assert len(not_found) == 1
        assert db.get_item(item.id) is None

    def test_close_all_thread_connections(self, db: ProductBacklog) -> None:
        """close() should close connections from all threads."""
        # Create connections from worker threads
        def use_from_thread() -> None:
            db.add("From thread")

        threads = [threading.Thread(target=use_from_thread) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Main thread also has a connection
        db.add("From main")
        # Should have 1 (main from fixture init) + 3 worker + possibly more
        with db._conn_lock:
            num_conns = len(db._all_conns)
        assert num_conns >= 4
        db.close()
        with db._conn_lock:
            assert len(db._all_conns) == 0

    def test_concurrent_comments_same_item(self, db: ProductBacklog) -> None:
        """Multiple agents commenting on the same item concurrently."""
        item = db.add("Contested item")
        errors: list[Exception] = []

        def add_comments(agent: str) -> None:
            try:
                for i in range(10):
                    db.comment(item.id, f"{agent} comment {i}")
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
        b1 = get_backlog_db(db_path, agent="Test")
        b2 = get_backlog_db(db_path, agent="Test")
        assert b1 is b2
        b1.close()  # also removes from _instances

    def test_different_agents_different_instances(self, tmp_path: Path) -> None:
        db_path = tmp_path / "multi.db"
        b1 = get_backlog_db(db_path, agent="Alice")
        b2 = get_backlog_db(db_path, agent="Bob")
        assert b1 is not b2
        assert b1.agent_name is not None
        assert "Alice" in b1.agent_name
        assert b2.agent_name is not None
        assert "Bob" in b2.agent_name
        b1.close()
        b2.close()

    def test_different_paths_different_instances(self, tmp_path: Path) -> None:
        b1 = get_backlog_db(tmp_path / "a.db", agent="Test")
        b2 = get_backlog_db(tmp_path / "b.db", agent="Test")
        assert b1 is not b2
        b1.close()
        b2.close()

    def test_close_removes_from_singleton_cache(self, tmp_path: Path) -> None:
        db_path = tmp_path / "lifecycle.db"
        b1 = get_backlog_db(db_path, agent="Test")
        key = f"{db_path.resolve()}::Test"
        assert key in _instances
        b1.close()
        assert key not in _instances
        # A new call should create a fresh instance
        b2 = get_backlog_db(db_path, agent="Test")
        assert b2 is not b1
        b2.close()


# ---------------------------------------------------------------------------
# Agent identity
# ---------------------------------------------------------------------------


class TestAgentIdentity:
    def test_agent_name_format(self, tmp_path: Path) -> None:
        db_path = tmp_path / "agent.db"
        bl = ProductBacklog(db_path, agent="Barry")
        name = bl.agent_name
        assert name is not None
        assert name.startswith("Barry/pid=")
        assert f"pid={os.getpid()}" in name
        assert threading.current_thread().name in name
        bl.close()

    def test_no_agent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "noagent.db"
        bl = ProductBacklog(db_path)
        assert bl.agent_name is None
        item = bl.add("Story")
        assert item.created_by is None
        events = bl.get_history(item.id)
        assert events[0]["agent_id"] is None
        bl.close()

    def test_agent_recorded_in_add(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        assert item.created_by is not None
        assert item.created_by.startswith("Test/pid=")

    def test_agent_recorded_in_comment(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.comment(item.id, "Hello")
        events = db.get_history(item.id)
        comments = [e for e in events if e["event_type"] == "comment"]
        assert comments[0]["agent_id"] is not None
        assert comments[0]["agent_id"].startswith("Test/pid=")

    def test_agent_recorded_in_status_change(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_status(item.id, "ready")
        events = db.get_history(item.id)
        status_events = [e for e in events if e["event_type"] == "status_change"]
        assert status_events[0]["agent_id"] is not None
        assert status_events[0]["agent_id"].startswith("Test/pid=")

    def test_agent_recorded_in_assign(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.assign(item.id, "Barry")
        events = db.get_history(item.id)
        assign_events = [e for e in events if e["event_type"] == "assigned"]
        assert assign_events[0]["agent_id"] is not None
        assert assign_events[0]["agent_id"].startswith("Test/pid=")

    def test_agent_recorded_in_priority_change(self, db: ProductBacklog) -> None:
        item = db.add("Story", priority=5)
        db.update_priority(item.id, 20)
        events = db.get_history(item.id)
        prio_events = [e for e in events if e["event_type"] == "priority_change"]
        assert prio_events[0]["agent_id"] is not None
        assert prio_events[0]["agent_id"].startswith("Test/pid=")

    def test_agent_recorded_in_sprint_change(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.update_sprint(item.id, "sprint-1")
        events = db.get_history(item.id)
        sprint_events = [e for e in events if e["event_type"] == "sprint_change"]
        assert sprint_events[0]["agent_id"] is not None
        assert sprint_events[0]["agent_id"].startswith("Test/pid=")

    def test_agent_recorded_in_parent_change(self, db: ProductBacklog) -> None:
        epic = db.add("Epic")
        child = db.add("Child")
        db.update_parent(child.id, epic.id)
        events = db.get_history(child.id)
        parent_events = [e for e in events if e["event_type"] == "parent_change"]
        assert parent_events[0]["agent_id"] is not None
        assert parent_events[0]["agent_id"].startswith("Test/pid=")


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
        item = db.add("Story")
        db.assign(item.id, "Barry")
        db.update_status(item.id, "ready")
        db.comment(item.id, "Starting this")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        db.update_status(item.id, "done", result="Shipped!")

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

    def test_full_lifecycle_via_merged(self, db: ProductBacklog) -> None:
        item = db.add("Story")
        db.assign(item.id, "Barry")
        db.update_status(item.id, "ready")
        db.update_status(item.id, "in_progress")
        db.update_status(item.id, "review")
        db.update_status(item.id, "merged")
        db.update_status(item.id, "done", result="Deployed!")

        events = db.get_history(item.id)
        types = [e["event_type"] for e in events]
        assert types == [
            "created",
            "assigned",
            "status_change",
            "status_change",
            "status_change",
            "status_change",
            "status_change",
        ]

    def test_get_history_on_deleted_item(self, db: ProductBacklog) -> None:
        """get_history() returns preserved events for deleted items."""
        item = db.add("Doomed")
        db.comment(item.id, "Last words")
        item_id = item.id
        db.delete(item_id)
        # Item is gone
        assert db.get_item(item_id) is None
        # But history is still accessible
        events = db.get_history(item_id)
        assert len(events) >= 3  # created, comment, deleted
        types = [e["event_type"] for e in events]
        assert "created" in types
        assert "comment" in types
        assert "deleted" in types


# ---------------------------------------------------------------------------
# Unbound BacklogItem (not attached to a ProductBacklog)
# ---------------------------------------------------------------------------


class TestUnboundBacklogItem:
    @pytest.fixture()
    def unbound(self) -> BacklogItem:
        return BacklogItem(
            id=1, title="t", description=None, item_type="story",
            status="backlog", priority=0, sprint=None, assigned_to=None,
            created_by=None, result=None, parent=None,
            created_at="x", updated_at="x",
        )

    def test_assign_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.assign("Barry")

    def test_update_status_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.update_status("ready")

    def test_update_priority_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.update_priority(10)

    def test_update_sprint_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.update_sprint("sprint-1")

    def test_update_parent_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.update_parent(1)

    def test_update_title_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.update_title("New")

    def test_update_description_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.update_description("New")

    def test_comment_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.comment("text")

    def test_delete_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.delete()

    def test_refresh_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.refresh()

    def test_get_comments_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.get_comments()

    def test_get_history_raises(self, unbound: BacklogItem) -> None:
        with pytest.raises(RuntimeError, match="not bound"):
            unbound.get_history()


# ---------------------------------------------------------------------------
# Schema evolution — extra columns don't break reads
# ---------------------------------------------------------------------------


class TestSchemaEvolution:
    def test_extra_column_ignored(self, db: ProductBacklog) -> None:
        """Adding a column to the table shouldn't break _row_to_item."""
        db._conn.execute("ALTER TABLE backlog_items ADD COLUMN extra TEXT DEFAULT 'hello'")
        item = db.add("Story")
        assert item.title == "Story"
        fetched = db.get_item(item.id)
        assert fetched is not None
        assert fetched.title == "Story"
