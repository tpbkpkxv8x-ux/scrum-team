"""Tests for chat_monitor.py — real-time team chat monitor."""

from __future__ import annotations

import json
import subprocess
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from chat_monitor import (
    ANSI_BOLD,
    ANSI_COLORS,
    ANSI_DIM,
    ANSI_RESET,
    ChatMessage,
    _color_recipient,
    _format_content,
    _format_display_name,
    _get_color_code,
    _is_system_message,
    _normalize_name,
    _split_recipients,
    build_tmux_command,
    collect_all_messages,
    collect_messages,
    discover_teams,
    format_message,
    launch_monitor,
    load_all_team_colors,
    load_team_colors,
    main,
    monitor_chat,
    read_inbox,
)

# ── Helpers ──────────────────────────────────────────────────────────────

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def team_dir(tmp_path: Path) -> Path:
    """Create a minimal team directory with inbox files and a config."""
    team_root = tmp_path / "test-team"
    inboxes = team_root / "inboxes"
    inboxes.mkdir(parents=True)

    # Team config with member colours
    config: dict[str, Any] = {
        "name": "test-team",
        "members": [
            {"name": "team-lead", "color": "cyan"},
            {"name": "Agent_One", "color": "blue"},
            {"name": "Agent_Two", "color": "yellow"},
        ],
    }
    (team_root / "config.json").write_text(json.dumps(config))

    # Agent's inbox: a real message + a system message
    agent_inbox: list[dict[str, Any]] = [
        {
            "from": "team-lead",
            "text": "Hey, here's your assignment.",
            "timestamp": "2026-02-08T10:00:00.000Z",
            "summary": "Assignment for agent",
            "color": "cyan",
            "read": True,
        },
        {
            "from": "team-lead",
            "text": '{"type":"idle_notification","from":"team-lead","timestamp":"2026-02-08T10:00:05.000Z"}',
            "timestamp": "2026-02-08T10:00:05.000Z",
            "read": True,
        },
    ]
    (inboxes / "Agent_One.json").write_text(json.dumps(agent_inbox))

    # team-lead's inbox: messages from other agents
    lead_inbox: list[dict[str, Any]] = [
        {
            "from": "Agent_One",
            "text": "Starting work on the task.",
            "timestamp": "2026-02-08T10:01:00.000Z",
            "summary": "Starting task",
            "color": "blue",
            "read": True,
        },
        {
            "from": "Agent_Two",
            "text": "Review complete — approved!",
            "timestamp": "2026-02-08T10:05:00.000Z",
            "summary": "Review approved",
            "color": "yellow",
            "read": True,
        },
    ]
    (inboxes / "team-lead.json").write_text(json.dumps(lead_inbox))

    return tmp_path


@pytest.fixture()
def peer_team_dir(tmp_path: Path) -> Path:
    """Team directory with peer-to-peer messages (no team-lead involvement)."""
    team_root = tmp_path / "peer-team"
    inboxes = team_root / "inboxes"
    inboxes.mkdir(parents=True)

    config: dict[str, Any] = {
        "name": "peer-team",
        "members": [
            {"name": "team-lead", "color": "cyan"},
            {"name": "Agent_One", "color": "blue"},
            {"name": "Agent_Two", "color": "yellow"},
            {"name": "Agent_Three", "color": "green"},
        ],
    }
    (team_root / "config.json").write_text(json.dumps(config))

    # Agent_One's inbox: message from team-lead + peer DM from Agent_Two
    agent_one_inbox: list[dict[str, Any]] = [
        {
            "from": "team-lead",
            "text": "Your assignment.",
            "timestamp": "2026-02-08T10:00:00.000Z",
            "summary": "Assignment",
            "color": "cyan",
        },
        {
            "from": "Agent_Two",
            "text": "Hey, can you review my PR?",
            "timestamp": "2026-02-08T10:03:00.000Z",
            "summary": "Review request",
            "color": "yellow",
        },
    ]
    (inboxes / "Agent_One.json").write_text(json.dumps(agent_one_inbox))

    # Agent_Two's inbox: peer DM from Agent_One + peer DM from Agent_Three
    agent_two_inbox: list[dict[str, Any]] = [
        {
            "from": "Agent_One",
            "text": "Sure, looks good to me!",
            "timestamp": "2026-02-08T10:04:00.000Z",
            "summary": "PR approved",
            "color": "blue",
        },
        {
            "from": "Agent_Three",
            "text": "Can we sync on the API contract?",
            "timestamp": "2026-02-08T10:06:00.000Z",
            "summary": "API sync request",
            "color": "green",
        },
    ]
    (inboxes / "Agent_Two.json").write_text(json.dumps(agent_two_inbox))

    # Agent_Three's inbox: peer DM from Agent_Two
    agent_three_inbox: list[dict[str, Any]] = [
        {
            "from": "Agent_Two",
            "text": "Here are the endpoint specs.",
            "timestamp": "2026-02-08T10:07:00.000Z",
            "summary": "Endpoint specs",
            "color": "yellow",
        },
    ]
    (inboxes / "Agent_Three.json").write_text(json.dumps(agent_three_inbox))

    # team-lead's inbox: messages from agents to team-lead
    lead_inbox: list[dict[str, Any]] = [
        {
            "from": "Agent_One",
            "text": "Task complete.",
            "timestamp": "2026-02-08T10:10:00.000Z",
            "summary": "Done",
            "color": "blue",
        },
    ]
    (inboxes / "team-lead.json").write_text(json.dumps(lead_inbox))

    return tmp_path


@pytest.fixture()
def sample_message() -> ChatMessage:
    return ChatMessage(
        timestamp="2026-02-08T10:01:00.000Z",
        sender="Agent_One",
        recipient="team-lead",
        content="Starting work on the task.",
        summary="Starting task",
        color="blue",
    )


# ── _is_system_message ───────────────────────────────────────────────────


class TestIsSystemMessage:
    def test_idle_notification(self) -> None:
        text = '{"type":"idle_notification","from":"Agent","timestamp":"2026-02-08T10:00:00.000Z"}'
        assert _is_system_message(text) is True

    def test_shutdown_request(self) -> None:
        text = '{"type":"shutdown_request","requestId":"abc","from":"team-lead"}'
        assert _is_system_message(text) is True

    def test_shutdown_approved(self) -> None:
        text = '{"type":"shutdown_approved","requestId":"abc","from":"Agent"}'
        assert _is_system_message(text) is True

    def test_shutdown_response(self) -> None:
        text = '{"type":"shutdown_response","requestId":"abc"}'
        assert _is_system_message(text) is True

    def test_plan_approval_request(self) -> None:
        text = '{"type":"plan_approval_request","from":"agent"}'
        assert _is_system_message(text) is True

    def test_plan_approval_response(self) -> None:
        text = '{"type":"plan_approval_response","from":"lead"}'
        assert _is_system_message(text) is True

    def test_regular_message(self) -> None:
        assert _is_system_message("Hey, nice work!") is False

    def test_json_without_type(self) -> None:
        assert _is_system_message('{"from":"Agent","text":"hi"}') is False

    def test_json_with_unknown_type(self) -> None:
        assert _is_system_message('{"type":"message","from":"Agent"}') is False

    def test_empty_string(self) -> None:
        assert _is_system_message("") is False

    def test_malformed_json(self) -> None:
        assert _is_system_message("{not valid json") is False


# ── _is_startup_prompt ────────────────────────────────────────────────────


# ── read_inbox ────────────────────────────────────────────────────────────


class TestReadInbox:
    def test_valid_file(self, tmp_path: Path) -> None:
        data: list[dict[str, str]] = [{"from": "a", "text": "hi", "timestamp": "t"}]
        f = tmp_path / "test.json"
        f.write_text(json.dumps(data))
        result = read_inbox(f)
        assert len(result) == 1
        assert result[0]["from"] == "a"

    def test_missing_file(self, tmp_path: Path) -> None:
        result = read_inbox(tmp_path / "nonexistent.json")
        assert result == []

    def test_malformed_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        result = read_inbox(f)
        assert result == []

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        f.write_text("")
        result = read_inbox(f)
        assert result == []


# ── collect_messages ──────────────────────────────────────────────────────


class TestCollectMessages:
    def test_collects_all_messages(self, team_dir: Path) -> None:
        msgs = collect_messages("test-team", teams_dir=team_dir)
        # 3 regular + 1 system (idle_notification) = 4 total
        assert len(msgs) == 4

    def test_includes_system_messages(self, team_dir: Path) -> None:
        msgs = collect_messages("test-team", teams_dir=team_dir)
        system_msgs = [m for m in msgs if m.is_system]
        assert len(system_msgs) == 1
        assert "idle_notification" in system_msgs[0].content

    def test_system_messages_flagged(self, team_dir: Path) -> None:
        msgs = collect_messages("test-team", teams_dir=team_dir)
        regular = [m for m in msgs if not m.is_system]
        system = [m for m in msgs if m.is_system]
        assert len(regular) == 3
        assert len(system) == 1

    def test_sorted_by_timestamp(self, team_dir: Path) -> None:
        msgs = collect_messages("test-team", teams_dir=team_dir)
        timestamps = [m.timestamp for m in msgs]
        assert timestamps == sorted(timestamps)

    def test_recipient_from_filename(self, team_dir: Path) -> None:
        msgs = collect_messages("test-team", teams_dir=team_dir)
        recipients = {m.recipient for m in msgs}
        assert "Agent_One" in recipients
        assert "team-lead" in recipients

    def test_nonexistent_team(self, team_dir: Path) -> None:
        msgs = collect_messages("no-such-team", teams_dir=team_dir)
        assert msgs == []

    def test_broadcast_deduplication(self, team_dir: Path) -> None:
        """Same message in two inbox files collapses into one entry with all recipients."""
        inboxes = team_dir / "dedup-team" / "inboxes"
        inboxes.mkdir(parents=True)

        msg: dict[str, Any] = {
            "from": "Agent",
            "text": "Same message",
            "timestamp": "2026-02-08T10:00:00.000Z",
        }
        (inboxes / "alice.json").write_text(json.dumps([msg]))
        (inboxes / "bob.json").write_text(json.dumps([msg]))

        msgs = collect_messages("dedup-team", teams_dir=team_dir)
        # Same content from same sender at same time → deduped into one entry
        assert len(msgs) == 1
        assert msgs[0].recipient == "alice, bob"

    def test_different_content_not_deduped(self, team_dir: Path) -> None:
        """Messages with different content are kept separate."""
        inboxes = team_dir / "no-dedup-team" / "inboxes"
        inboxes.mkdir(parents=True)

        msg_a: dict[str, Any] = {
            "from": "Agent",
            "text": "Message for Alice",
            "timestamp": "2026-02-08T10:00:00.000Z",
        }
        msg_b: dict[str, Any] = {
            "from": "Agent",
            "text": "Message for Bob",
            "timestamp": "2026-02-08T10:00:00.000Z",
        }
        (inboxes / "alice.json").write_text(json.dumps([msg_a]))
        (inboxes / "bob.json").write_text(json.dumps([msg_b]))

        msgs = collect_messages("no-dedup-team", teams_dir=team_dir)
        # Different content → not deduped → both appear
        assert len(msgs) == 2

    def test_system_message_broadcast_deduplication(self, team_dir: Path) -> None:
        """System messages sent to multiple recipients should also deduplicate."""
        inboxes = team_dir / "sys-broadcast-team" / "inboxes"
        inboxes.mkdir(parents=True)

        msg: dict[str, Any] = {
            "from": "team-lead",
            "text": '{"type":"shutdown_request","requestId":"abc"}',
            "timestamp": "2026-02-08T10:00:00.000Z",
        }
        (inboxes / "alice.json").write_text(json.dumps([msg]))
        (inboxes / "bob.json").write_text(json.dumps([msg]))

        msgs = collect_messages("sys-broadcast-team", teams_dir=team_dir)
        assert len(msgs) == 1
        assert msgs[0].recipient == "alice, bob"
        assert msgs[0].is_system is True

    def test_includes_startup_prompts(self, team_dir: Path) -> None:
        """All human-readable messages are included, even long startup prompts."""
        inboxes = team_dir / "prompt-team" / "inboxes"
        inboxes.mkdir(parents=True)
        entries: list[dict[str, Any]] = [
            {
                "from": "team-lead",
                "text": "x" * 600 + "\n## Your Assignments\nDo stuff.",
                "timestamp": "2026-02-08T09:00:00.000Z",
            },
            {
                "from": "team-lead",
                "text": "Short real message",
                "timestamp": "2026-02-08T09:01:00.000Z",
            },
        ]
        (inboxes / "agent.json").write_text(json.dumps(entries))
        msgs = collect_messages("prompt-team", teams_dir=team_dir)
        assert len(msgs) == 2

    def test_collects_peer_to_peer_messages(self, peer_team_dir: Path) -> None:
        """Messages between non-lead agents are collected."""
        msgs = collect_messages("peer-team", teams_dir=peer_team_dir)
        peer_msgs = [m for m in msgs if m.sender != "team-lead" and m.recipient != "team-lead"]
        # Agent_Two→Agent_One, Agent_One→Agent_Two, Agent_Three→Agent_Two,
        # Agent_Two→Agent_Three = 4 peer messages
        assert len(peer_msgs) == 4

    def test_peer_messages_have_correct_sender_recipient(self, peer_team_dir: Path) -> None:
        """Peer DMs have the correct sender (from field) and recipient (filename)."""
        msgs = collect_messages("peer-team", teams_dir=peer_team_dir)
        peer_msgs = {(m.sender, m.recipient): m.content for m in msgs}
        assert ("Agent_Two", "Agent_One") in peer_msgs
        assert peer_msgs[("Agent_Two", "Agent_One")] == "Hey, can you review my PR?"
        assert ("Agent_One", "Agent_Two") in peer_msgs
        assert peer_msgs[("Agent_One", "Agent_Two")] == "Sure, looks good to me!"

    def test_peer_and_lead_messages_coexist(self, peer_team_dir: Path) -> None:
        """Both team-lead and peer messages appear in the same collection."""
        msgs = collect_messages("peer-team", teams_dir=peer_team_dir)
        lead_msgs = [m for m in msgs if m.sender == "team-lead" or m.recipient == "team-lead"]
        peer_msgs = [m for m in msgs if m.sender != "team-lead" and m.recipient != "team-lead"]
        assert len(lead_msgs) >= 1
        assert len(peer_msgs) >= 1
        assert len(msgs) == len(lead_msgs) + len(peer_msgs)

    def test_peer_broadcast_deduplication(self, peer_team_dir: Path) -> None:
        """A peer broadcast to multiple agents lists all recipients."""
        inboxes = peer_team_dir / "bcast-peer-team" / "inboxes"
        inboxes.mkdir(parents=True)
        msg: dict[str, Any] = {
            "from": "Agent_One",
            "text": "FYI: API is down",
            "timestamp": "2026-02-08T11:00:00.000Z",
        }
        (inboxes / "Agent_Two.json").write_text(json.dumps([msg]))
        (inboxes / "Agent_Three.json").write_text(json.dumps([msg]))
        msgs = collect_messages("bcast-peer-team", teams_dir=peer_team_dir)
        assert len(msgs) == 1
        assert msgs[0].sender == "Agent_One"
        assert msgs[0].recipient == "Agent_Three, Agent_Two"


# ── _get_color_code ───────────────────────────────────────────────────────


class TestGetColorCode:
    def test_blue(self) -> None:
        assert _get_color_code("blue") == "\033[94m"

    def test_orange(self) -> None:
        assert _get_color_code("orange") == "\033[38;5;208m"

    def test_yellow(self) -> None:
        assert _get_color_code("yellow") == "\033[93m"

    def test_purple(self) -> None:
        assert _get_color_code("purple") == "\033[95m"

    def test_green(self) -> None:
        assert _get_color_code("green") == "\033[92m"

    def test_cyan(self) -> None:
        assert _get_color_code("cyan") == "\033[96m"

    def test_pink(self) -> None:
        assert _get_color_code("pink") == "\033[38;5;213m"

    def test_unknown_color(self) -> None:
        assert _get_color_code("neon") == ""

    def test_empty_color(self) -> None:
        assert _get_color_code("") == ""


# ── _format_display_name ─────────────────────────────────────────────────


class TestFormatDisplayName:
    def test_simple_name_unchanged(self) -> None:
        assert _format_display_name("team-lead") == "team-lead"

    def test_single_word_unchanged(self) -> None:
        assert _format_display_name("Alice") == "Alice"

    def test_empty_string(self) -> None:
        assert _format_display_name("") == ""

    # -- double-dash format --

    def test_double_dash_name_with_role(self) -> None:
        assert _format_display_name("Cindy--Cloud-Engineer") == "Cindy (Cloud Engineer)"

    def test_double_dash_name_with_role_and_instance(self) -> None:
        assert _format_display_name("Pierre--Peer-Reviewer--2") == "Pierre (Peer Reviewer)-2"

    def test_double_dash_multi_word_role(self) -> None:
        assert _format_display_name("Irene--Integration-Engineer") == "Irene (Integration Engineer)"

    def test_double_dash_instance_number_zero(self) -> None:
        assert _format_display_name("Agent--Worker--0") == "Agent (Worker)-0"

    def test_double_dash_non_numeric_suffix(self) -> None:
        """A non-numeric final part is part of the role, not an instance."""
        assert _format_display_name("Agent--Quality--Assurance") == "Agent (Quality Assurance)"

    def test_double_dash_multiple_role_parts(self) -> None:
        assert _format_display_name("Bob--Senior-Dev--QA--3") == "Bob (Senior Dev QA)-3"

    # -- underscore format --

    def test_underscore_cloud_engineer(self) -> None:
        assert _format_display_name("Cindy_Cloud_Engineer") == "Cindy (Cloud Engineer)"

    def test_underscore_backend_engineer(self) -> None:
        assert _format_display_name("Blake_Backend_Engineer") == "Blake (Backend Engineer)"

    def test_underscore_frontend_engineer(self) -> None:
        assert _format_display_name("Fiona_Frontend_Engineer") == "Fiona (Frontend Engineer)"

    def test_underscore_with_instance(self) -> None:
        assert _format_display_name("Pierre_Peer_Reviewer_2") == "Pierre (Peer Reviewer)-2"

    def test_underscore_two_parts(self) -> None:
        assert _format_display_name("Agent_One") == "Agent (One)"

    def test_double_dash_trailing_dash(self) -> None:
        """Trailing dash in role part should not produce trailing space."""
        assert _format_display_name("Cindy--Cloud-Engineer-") == "Cindy (Cloud Engineer)"

    def test_double_dash_trailing_dash_with_instance(self) -> None:
        assert _format_display_name("Pierre--Peer-Reviewer-") == "Pierre (Peer Reviewer)"


# ── _normalize_name ──────────────────────────────────────────────────────


class TestNormalizeName:
    def test_underscore_format(self) -> None:
        assert _normalize_name("Cindy_Cloud_Engineer") == "cindy cloud engineer"

    def test_double_dash_format(self) -> None:
        assert _normalize_name("Cindy--Cloud-Engineer-") == "cindy cloud engineer"

    def test_display_format_with_parens(self) -> None:
        assert _normalize_name("Cindy (Cloud Engineer)") == "cindy cloud engineer"

    def test_double_dash_with_instance(self) -> None:
        assert _normalize_name("Pierre--Peer-Reviewer--2") == "pierre peer reviewer"

    def test_display_format_no_instance(self) -> None:
        assert _normalize_name("Pierre (Peer Reviewer)") == "pierre peer reviewer"

    def test_underscore_with_instance(self) -> None:
        assert _normalize_name("Pierre_Peer_Reviewer_2") == "pierre peer reviewer"

    def test_simple_name(self) -> None:
        assert _normalize_name("Sam") == "sam"

    def test_hyphenated_name(self) -> None:
        assert _normalize_name("team-lead") == "team lead"

    def test_empty_string(self) -> None:
        assert _normalize_name("") == ""

    def test_all_formats_match(self) -> None:
        """All naming conventions for the same agent produce the same key."""
        variants = [
            "Cindy_Cloud_Engineer",
            "Cindy--Cloud-Engineer-",
            "Cindy (Cloud Engineer)",
        ]
        normalized = {_normalize_name(v) for v in variants}
        assert len(normalized) == 1
        assert normalized == {"cindy cloud engineer"}


# ── _split_recipients ───────────────────────────────────────────────────


class TestSplitRecipients:
    def test_single_recipient(self) -> None:
        assert _split_recipients("Alice") == ["Alice"]

    def test_two_recipients(self) -> None:
        assert _split_recipients("Alice, Bob") == ["Alice", "Bob"]

    def test_three_recipients(self) -> None:
        assert _split_recipients("Alice, Bob, Charlie") == ["Alice", "Bob", "Charlie"]

    def test_name_with_dashes_not_split(self) -> None:
        assert _split_recipients("team-lead") == ["team-lead"]


# ── _color_recipient ────────────────────────────────────────────────────


class TestColorRecipient:
    def test_with_known_color(self) -> None:
        result = _color_recipient("Alice", {"Alice": "blue"})
        assert ANSI_COLORS["blue"] in result
        assert "Alice" in result
        assert ANSI_RESET in result

    def test_without_color(self) -> None:
        result = _color_recipient("Alice", {})
        assert result == "Alice"
        assert ANSI_RESET not in result

    def test_applies_display_name(self) -> None:
        result = _color_recipient("Pierre--Peer-Reviewer--2", {"Pierre--Peer-Reviewer--2": "cyan"})
        assert "Pierre (Peer Reviewer)-2" in result
        assert ANSI_COLORS["cyan"] in result

    def test_display_name_without_color(self) -> None:
        result = _color_recipient("Cindy--Cloud-Engineer", {})
        assert result == "Cindy (Cloud Engineer)"

    def test_cross_format_underscore_config_dash_inbox(self) -> None:
        """Config uses underscore name, inbox uses double-dash name → still colored.

        This is the real-world scenario: team config has Cindy_Cloud_Engineer
        with color 'yellow', but the inbox filename is Cindy--Cloud-Engineer-.json.
        """
        # load_team_colors adds normalised keys, so simulate that
        colors = {
            "Cindy_Cloud_Engineer": "yellow",
            "cindy cloud engineer": "yellow",  # normalised key
        }
        result = _color_recipient("Cindy--Cloud-Engineer-", colors)
        assert ANSI_COLORS["yellow"] in result
        assert "Cindy (Cloud Engineer)" in result

    def test_cross_format_display_config_dash_inbox(self) -> None:
        """Config uses display name with parens, inbox uses double-dash."""
        colors = {
            "Pierre (Peer Reviewer)": "blue",
            "pierre peer reviewer": "blue",  # normalised key
        }
        result = _color_recipient("Pierre--Peer-Reviewer--2", colors)
        assert ANSI_COLORS["blue"] in result
        assert "Pierre (Peer Reviewer)-2" in result


# ── load_team_colors ─────────────────────────────────────────────────────


class TestLoadTeamColors:
    def test_loads_colors_from_config(self, team_dir: Path) -> None:
        colors = load_team_colors("test-team", teams_dir=team_dir)
        assert colors["team-lead"] == "cyan"
        assert colors["Agent_One"] == "blue"
        assert colors["Agent_Two"] == "yellow"

    def test_missing_team(self, tmp_path: Path) -> None:
        colors = load_team_colors("no-such-team", teams_dir=tmp_path)
        assert colors == {}

    def test_malformed_config(self, tmp_path: Path) -> None:
        team_root = tmp_path / "bad-team"
        team_root.mkdir()
        (team_root / "config.json").write_text("{bad json")
        colors = load_team_colors("bad-team", teams_dir=tmp_path)
        assert colors == {}

    def test_missing_color_field(self, tmp_path: Path) -> None:
        team_root = tmp_path / "no-color"
        team_root.mkdir()
        config: dict[str, Any] = {
            "members": [{"name": "agent-a"}],
        }
        (team_root / "config.json").write_text(json.dumps(config))
        colors = load_team_colors("no-color", teams_dir=tmp_path)
        assert colors["agent-a"] == ""

    def test_normalized_keys_added(self, tmp_path: Path) -> None:
        """Members with colors get an additional normalised key."""
        team_root = tmp_path / "norm-team"
        team_root.mkdir()
        config: dict[str, Any] = {
            "members": [
                {"name": "Cindy_Cloud_Engineer", "color": "yellow"},
                {"name": "Pierre (Peer Reviewer)", "color": "blue"},
            ],
        }
        (team_root / "config.json").write_text(json.dumps(config))
        colors = load_team_colors("norm-team", teams_dir=tmp_path)
        # Raw keys
        assert colors["Cindy_Cloud_Engineer"] == "yellow"
        assert colors["Pierre (Peer Reviewer)"] == "blue"
        # Normalised keys
        assert colors["cindy cloud engineer"] == "yellow"
        assert colors["pierre peer reviewer"] == "blue"

    def test_no_normalized_key_for_empty_color(self, tmp_path: Path) -> None:
        """Members with no color should not add a normalised key."""
        team_root = tmp_path / "empty-color"
        team_root.mkdir()
        config: dict[str, Any] = {
            "members": [{"name": "team-lead"}],
        }
        (team_root / "config.json").write_text(json.dumps(config))
        colors = load_team_colors("empty-color", teams_dir=tmp_path)
        assert colors["team-lead"] == ""
        assert "team lead" not in colors


# ── _format_content ──────────────────────────────────────────────────────


class TestFormatContent:
    def test_plain_text_unchanged(self) -> None:
        assert _format_content("Hello world") == "Hello world"

    def test_json_object_pretty_printed(self) -> None:
        result = _format_content('{"type":"idle","status":"ok"}')
        assert result.startswith("\n")
        assert "    " in result  # indented
        assert '"type": "idle"' in result
        assert '"status": "ok"' in result

    def test_json_strips_from_field(self) -> None:
        result = _format_content('{"type":"idle","from":"agent","status":"ok"}')
        assert '"from"' not in result
        assert '"status": "ok"' in result

    def test_json_strips_requestId_field(self) -> None:
        result = _format_content('{"type":"shutdown_request","requestId":"abc-123","content":"bye"}')
        assert '"requestId"' not in result
        assert '"content": "bye"' in result

    def test_json_strips_both_hidden_fields(self) -> None:
        result = _format_content('{"from":"agent","requestId":"abc","type":"idle"}')
        assert '"from"' not in result
        assert '"requestId"' not in result
        assert '"type": "idle"' in result

    def test_json_strips_timestamp_field(self) -> None:
        result = _format_content('{"type":"idle_notification","timestamp":"2026-02-08T10:00:00.000Z","reason":"done"}')
        assert '"timestamp"' not in result
        assert '"reason": "done"' in result

    def test_json_strips_paneId_field(self) -> None:
        result = _format_content('{"type":"idle_notification","paneId":"abc-123","reason":"done"}')
        assert '"paneId"' not in result
        assert '"reason": "done"' in result

    def test_json_strips_backendType_field(self) -> None:
        result = _format_content('{"type":"idle_notification","backendType":"local","reason":"done"}')
        assert '"backendType"' not in result
        assert '"reason": "done"' in result

    def test_json_strips_all_hidden_fields(self) -> None:
        raw = '{"from":"a","requestId":"b","timestamp":"c","paneId":"d","backendType":"e","type":"idle"}'
        result = _format_content(raw)
        for key in ("from", "requestId", "timestamp", "paneId", "backendType"):
            assert f'"{key}"' not in result
        assert '"type": "idle"' in result

    def test_unicode_characters_not_escaped(self) -> None:
        """Non-ASCII characters like em-dash should render properly, not as \\uXXXX."""
        result = _format_content('{"reason":"Thanks Pierre \\u2014 review done"}')
        assert "\u2014" in result
        assert "\\u2014" not in result

    def test_unicode_emoji_not_escaped(self) -> None:
        result = _format_content('{"status":"All good \\ud83d\\ude00"}')
        # Should contain the actual emoji, not the escape sequence
        assert "\\ud83d" not in result

    def test_json_array_not_filtered(self) -> None:
        """Arrays are not filtered — only top-level object keys."""
        result = _format_content('[{"from":"agent"}]')
        assert '"from"' in result

    def test_json_array_pretty_printed(self) -> None:
        result = _format_content("[1, 2, 3]")
        assert result.startswith("\n")
        assert "1" in result

    def test_invalid_json_starting_with_brace(self) -> None:
        text = "{not valid json at all"
        assert _format_content(text) == text

    def test_text_starting_with_brace_but_not_json(self) -> None:
        text = "{this is just text}"
        # This is actually parseable as... no, this will fail JSON parse
        assert _format_content(text) == text


# ── format_message ────────────────────────────────────────────────────────


class TestFormatMessage:
    def test_contains_timestamp(self, sample_message: ChatMessage) -> None:
        line = format_message(sample_message)
        assert "10:01:00" in line

    def test_contains_sender(self, sample_message: ChatMessage) -> None:
        line = format_message(sample_message)
        assert "Agent (One)" in line

    def test_contains_recipient(self, sample_message: ChatMessage) -> None:
        line = format_message(sample_message)
        assert "team-lead" in line

    def test_shows_full_content(self, sample_message: ChatMessage) -> None:
        line = format_message(sample_message)
        assert sample_message.content in line

    def test_no_truncation_on_long_content(self) -> None:
        long_content = "x" * 300
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Agent_One",
            recipient="team-lead",
            content=long_content,
            summary="",
            color="blue",
        )
        line = format_message(msg)
        assert long_content in line
        assert "..." not in line

    def test_contains_ansi_codes(self, sample_message: ChatMessage) -> None:
        line = format_message(sample_message)
        assert ANSI_DIM in line
        assert ANSI_BOLD in line
        assert ANSI_RESET in line

    def test_short_timestamp(self) -> None:
        msg = ChatMessage(
            timestamp="short",
            sender="Agent_One",
            recipient="team-lead",
            content="hi",
            summary="",
            color="blue",
        )
        line = format_message(msg)
        assert "short" in line

    def test_uses_message_color(self) -> None:
        """Color comes from the message's color field, not agent name."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Unknown_Agent",
            recipient="team-lead",
            content="hi",
            summary="",
            color="green",
        )
        line = format_message(msg)
        assert "\033[92m" in line  # green ANSI code

    def test_system_message_has_tag(self) -> None:
        """System messages include a [system] tag."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:05.000Z",
            sender="team-lead",
            recipient="Agent_One",
            content='{"type":"idle_notification"}',
            summary="",
            color="",
            is_system=True,
        )
        line = format_message(msg)
        assert "[system]" in line

    def test_system_message_header_dim_content_normal(self) -> None:
        """System messages have dim header but normal content text."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:05.000Z",
            sender="team-lead",
            recipient="Agent_One",
            content='{"type":"idle_notification"}',
            summary="",
            color="",
            is_system=True,
        )
        line = format_message(msg)
        assert line.startswith(ANSI_DIM)
        # Content follows RESET (not wrapped in DIM)
        system_tag_pos = line.index("[system]")
        reset_after_tag = line.index(ANSI_RESET, system_tag_pos)
        content_after_reset = line[reset_after_tag + len(ANSI_RESET) :]
        assert ANSI_DIM not in content_after_reset

    def test_system_message_no_bold(self) -> None:
        """System messages should not use bold styling."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:05.000Z",
            sender="team-lead",
            recipient="Agent_One",
            content='{"type":"idle_notification"}',
            summary="",
            color="cyan",
            is_system=True,
        )
        line = format_message(msg)
        assert ANSI_BOLD not in line

    def test_recipient_colored_with_member_colors(self) -> None:
        """Recipient name uses its color from member_colors."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Agent_One",
            recipient="team-lead",
            content="hi",
            summary="",
            color="blue",
        )
        colors = {"Agent_One": "blue", "team-lead": "cyan"}
        line = format_message(msg, member_colors=colors)
        # Recipient "team-lead" should appear with cyan ANSI code
        assert ANSI_COLORS["cyan"] in line

    def test_sender_uses_config_color_over_message(self) -> None:
        """When member_colors provides a color, it takes precedence."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Agent_One",
            recipient="team-lead",
            content="hi",
            summary="",
            color="red",  # message says red
        )
        colors = {"Agent_One": "green"}  # config says green
        line = format_message(msg, member_colors=colors)
        assert ANSI_COLORS["green"] in line

    def test_json_content_pretty_printed(self) -> None:
        """JSON message content is pretty-printed with indentation."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Agent_One",
            recipient="team-lead",
            content='{"status":"done","items":3}',
            summary="",
            color="blue",
        )
        line = format_message(msg)
        assert '"status": "done"' in line
        assert "\n" in line  # multi-line output

    def test_no_member_colors_falls_back(self) -> None:
        """Without member_colors, sender uses msg.color field."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Agent_One",
            recipient="team-lead",
            content="hi",
            summary="",
            color="green",
        )
        line = format_message(msg)
        assert ANSI_COLORS["green"] in line

    def test_empty_config_color_falls_back_to_message(self) -> None:
        """When config has empty color for sender, fall back to msg.color."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Agent_One",
            content="hi",
            summary="",
            color="cyan",  # message carries sender's color
        )
        # Config has team-lead with empty color (no color field in config)
        colors = {"team-lead": "", "Agent_One": "blue"}
        line = format_message(msg, member_colors=colors)
        # Sender should fall back to msg.color="cyan"
        assert ANSI_COLORS["cyan"] in line

    def test_underscore_sender_display_name(self) -> None:
        """Sender with underscore format is rendered as human-friendly name."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Cindy_Cloud_Engineer",
            recipient="team-lead",
            content="Deploy done.",
            summary="",
            color="yellow",
        )
        line = format_message(msg)
        assert "Cindy (Cloud Engineer)" in line
        assert "Cindy_Cloud_Engineer" not in line

    def test_underscore_recipient_display_name(self) -> None:
        """Recipient with underscore format is rendered as human-friendly name."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Blake_Backend_Engineer",
            content="Your task.",
            summary="",
            color="cyan",
        )
        colors = {"Blake_Backend_Engineer": "cyan"}
        line = format_message(msg, member_colors=colors)
        assert "Blake (Backend Engineer)" in line
        assert "Blake_Backend_Engineer" not in line

    def test_sender_display_name_formatted(self) -> None:
        """Sender with -- format is rendered as a human-friendly display name."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Pierre--Peer-Reviewer--2",
            recipient="team-lead",
            content="Review done.",
            summary="",
            color="cyan",
        )
        line = format_message(msg)
        assert "Pierre (Peer Reviewer)-2" in line
        assert "Pierre--Peer-Reviewer--2" not in line

    def test_recipient_display_name_formatted(self) -> None:
        """Recipient with -- format is rendered as a human-friendly display name."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Cindy--Cloud-Engineer",
            content="Your task.",
            summary="",
            color="cyan",
        )
        line = format_message(msg)
        assert "Cindy (Cloud Engineer)" in line
        assert "Cindy--Cloud-Engineer" not in line

    def test_multi_recipient_all_names_shown(self) -> None:
        """Multi-recipient messages list all recipient names."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Alice, Bob",
            content="All hands update.",
            summary="",
            color="cyan",
        )
        line = format_message(msg)
        assert "Alice" in line
        assert "Bob" in line

    def test_multi_recipient_each_colored(self) -> None:
        """Each recipient in a multi-recipient message gets its own color."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Alice, Bob",
            content="Update.",
            summary="",
            color="cyan",
        )
        colors = {"team-lead": "cyan", "Alice": "blue", "Bob": "yellow"}
        line = format_message(msg, member_colors=colors)
        assert ANSI_COLORS["blue"] in line
        assert ANSI_COLORS["yellow"] in line

    def test_multi_recipient_display_names(self) -> None:
        """Multi-recipient message with -- names shows display format."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Cindy--Cloud-Engineer, Irene--Integration-Engineer",
            content="Sprint planning.",
            summary="",
            color="cyan",
        )
        line = format_message(msg)
        assert "Cindy (Cloud Engineer)" in line
        assert "Irene (Integration Engineer)" in line

    def test_system_message_display_names(self) -> None:
        """System messages also use human-friendly display names."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:05.000Z",
            sender="Pierre--Peer-Reviewer--2",
            recipient="Barry--Backend-Engineer",
            content='{"type":"idle_notification"}',
            summary="",
            color="",
            is_system=True,
        )
        line = format_message(msg)
        assert "Pierre (Peer Reviewer)-2" in line
        assert "Barry (Backend Engineer)" in line
        assert "Pierre--Peer-Reviewer--2" not in line
        assert "Barry--Backend-Engineer" not in line

    def test_system_multi_recipient_display_names(self) -> None:
        """System messages with multiple recipients show all display names."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:05.000Z",
            sender="team-lead",
            recipient="Alice, Bob--Backend-Dev",
            content='{"type":"shutdown_request"}',
            summary="",
            color="",
            is_system=True,
        )
        line = format_message(msg)
        assert "Alice" in line
        assert "Bob (Backend Dev)" in line

    def test_recipient_colored_cross_format(self) -> None:
        """Recipient color found via normalised lookup when name formats differ.

        Reproduces the real-world bug: team config has 'Cindy_Cloud_Engineer'
        with color 'yellow', but the inbox filename (and therefore recipient
        field) is 'Cindy--Cloud-Engineer-'.  The recipient MUST be colored.
        """
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Cindy--Cloud-Engineer-",
            content="Your task.",
            summary="",
            color="",
        )
        # Simulate what load_team_colors returns (raw + normalised keys)
        colors = {
            "team-lead": "",
            "Cindy_Cloud_Engineer": "yellow",
            "cindy cloud engineer": "yellow",
        }
        line = format_message(msg, member_colors=colors)
        assert ANSI_COLORS["yellow"] in line
        assert "Cindy (Cloud Engineer)" in line

    def test_sender_colored_cross_format(self) -> None:
        """Sender color found via normalised lookup when name formats differ."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Pierre--Peer-Reviewer--2",
            recipient="team-lead",
            content="Review done.",
            summary="",
            color="",
        )
        colors = {
            "Pierre (Peer Reviewer)": "blue",
            "pierre peer reviewer": "blue",
            "team-lead": "",
        }
        line = format_message(msg, member_colors=colors)
        assert ANSI_COLORS["blue"] in line


# ── monitor_chat (integration: cross-format colors) ─────────────────


class TestMonitorChatCrossFormatColors:
    """End-to-end test: config names differ from inbox filenames."""

    def test_recipient_colored_in_monitor_output(self, tmp_path: Path) -> None:
        """Full pipeline: config has underscore names, inboxes use dashes."""
        team_root = tmp_path / "xfmt-team"
        inboxes = team_root / "inboxes"
        inboxes.mkdir(parents=True)

        # Config uses underscore names (like project-sprint-7)
        config: dict[str, Any] = {
            "name": "xfmt-team",
            "members": [
                {"name": "team-lead"},
                {"name": "Cindy_Cloud_Engineer", "color": "yellow"},
            ],
        }
        (team_root / "config.json").write_text(json.dumps(config))

        # Inbox filename uses double-dash format (like a real team)
        inbox_entries: list[dict[str, Any]] = [
            {
                "from": "team-lead",
                "text": "Deploy the stack.",
                "timestamp": "2026-02-08T10:00:00.000Z",
                "summary": "Deploy task",
                "color": "",
            },
        ]
        (inboxes / "Cindy--Cloud-Engineer-.json").write_text(json.dumps(inbox_entries))

        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("xfmt-team", teams_dir=tmp_path, output=output)

        text = output.getvalue()
        # Recipient must be colored despite name format mismatch
        assert ANSI_COLORS["yellow"] in text
        assert "Cindy (Cloud Engineer)" in text


# ── monitor_chat ──────────────────────────────────────────────────────────


class TestMonitorChat:
    def test_prints_header(self, team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("test-team", teams_dir=team_dir, output=output)
        text = output.getvalue()
        assert "Chat monitor" in text
        assert "test-team" in text

    def test_prints_messages(self, team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("test-team", teams_dir=team_dir, output=output)
        text = output.getvalue()
        assert "Agent (One)" in text

    def test_prints_system_messages(self, team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("test-team", teams_dir=team_dir, output=output)
        text = output.getvalue()
        assert "[system]" in text
        assert "idle_notification" in text

    def test_prints_stop_message(self, team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("test-team", teams_dir=team_dir, output=output)
        text = output.getvalue()
        assert "Monitor stopped" in text

    def test_incremental_polling(self, team_dir: Path) -> None:
        """On second poll, only new messages should be printed."""
        output = StringIO()
        call_count = 0

        def fake_sleep(interval: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                inboxes = team_dir / "test-team" / "inboxes"
                inbox = json.loads((inboxes / "team-lead.json").read_text())
                inbox.append(
                    {
                        "from": "Agent_Three",
                        "text": "New message after poll!",
                        "timestamp": "2026-02-08T10:10:00.000Z",
                        "summary": "New from Agent_Three",
                        "color": "green",
                    }
                )
                (inboxes / "team-lead.json").write_text(json.dumps(inbox))
            elif call_count >= 2:
                raise KeyboardInterrupt

        with patch("chat_monitor.time.sleep", side_effect=fake_sleep):
            monitor_chat("test-team", teams_dir=team_dir, output=output)

        text = output.getvalue()
        assert "New message after poll!" in text

    def test_out_of_order_timestamp(self, team_dir: Path) -> None:
        """A new message with an earlier timestamp must still be printed."""
        output = StringIO()
        call_count = 0

        def fake_sleep(interval: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Add a message with a timestamp BEFORE existing ones
                inboxes = team_dir / "test-team" / "inboxes"
                inbox = json.loads((inboxes / "team-lead.json").read_text())
                inbox.append(
                    {
                        "from": "Agent_Four",
                        "text": "Backdated message",
                        "timestamp": "2026-02-08T09:00:00.000Z",
                        "summary": "Backdated from Agent_Four",
                        "color": "purple",
                    }
                )
                (inboxes / "team-lead.json").write_text(json.dumps(inbox))
            elif call_count >= 2:
                raise KeyboardInterrupt

        with patch("chat_monitor.time.sleep", side_effect=fake_sleep):
            monitor_chat("test-team", teams_dir=team_dir, output=output)

        text = output.getvalue()
        assert "Backdated message" in text

    def test_no_duplicate_prints(self, team_dir: Path) -> None:
        """Existing messages should not be reprinted on subsequent polls."""
        output = StringIO()
        call_count = 0

        def fake_sleep(interval: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt

        with patch("chat_monitor.time.sleep", side_effect=fake_sleep):
            monitor_chat("test-team", teams_dir=team_dir, output=output)

        text = output.getvalue()
        # The first message content should appear exactly once (no duplicate prints)
        assert text.count("Hey, here's your assignment.") == 1

    def test_prints_peer_messages(self, peer_team_dir: Path) -> None:
        """Peer-to-peer messages (no team-lead) appear in monitor output."""
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("peer-team", teams_dir=peer_team_dir, output=output)
        text = output.getvalue()
        # Peer DM from Agent_Two to Agent_One
        assert "review my PR" in text
        # Peer DM from Agent_One to Agent_Two
        assert "looks good to me" in text
        # Peer DM from Agent_Three to Agent_Two
        assert "API contract" in text
        # Peer DM from Agent_Two to Agent_Three
        assert "endpoint specs" in text

    def test_peer_messages_not_suppressed_by_lead_messages(self, peer_team_dir: Path) -> None:
        """Peer messages still appear when mixed with team-lead messages."""
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("peer-team", teams_dir=peer_team_dir, output=output)
        text = output.getvalue()
        # team-lead message exists
        assert "Your assignment" in text
        # Agent→team-lead message exists
        assert "Task complete" in text
        # Peer messages also exist alongside
        assert "review my PR" in text
        assert "endpoint specs" in text

    def test_same_timestamp_sender_recipient_different_content(self, tmp_path: Path) -> None:
        """Two messages at the same instant from the same sender to the same
        recipient but with different content must both be printed."""
        team_root = tmp_path / "collision-team"
        inboxes = team_root / "inboxes"
        inboxes.mkdir(parents=True)
        entries: list[dict[str, Any]] = [
            {
                "from": "Agent_One",
                "text": "First message",
                "timestamp": "2026-02-08T10:00:00.000Z",
            },
            {
                "from": "Agent_One",
                "text": "Second message",
                "timestamp": "2026-02-08T10:00:00.000Z",
            },
        ]
        (inboxes / "Agent_Two.json").write_text(json.dumps(entries))
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("collision-team", teams_dir=tmp_path, output=output)
        text = output.getvalue()
        assert "First message" in text
        assert "Second message" in text

    def test_broadcast_recipient_change_no_duplicate(self, tmp_path: Path) -> None:
        """When a message flips from single-recipient to broadcast between
        polls, it must not be printed a second time."""
        team_root = tmp_path / "flip-team"
        inboxes = team_root / "inboxes"
        inboxes.mkdir(parents=True)
        msg: dict[str, Any] = {
            "from": "Agent_One",
            "text": "Shared update",
            "timestamp": "2026-02-08T10:00:00.000Z",
        }
        # Poll 1: only in Agent_Two's inbox (single recipient)
        (inboxes / "Agent_Two.json").write_text(json.dumps([msg]))

        output = StringIO()
        call_count = 0

        def fake_sleep(interval: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Between polls: same message now also in Agent_Three's inbox
                (inboxes / "Agent_Three.json").write_text(json.dumps([msg]))
            elif call_count >= 2:
                raise KeyboardInterrupt

        with patch("chat_monitor.time.sleep", side_effect=fake_sleep):
            monitor_chat("flip-team", teams_dir=tmp_path, output=output)
        text = output.getvalue()
        # "Shared update" should appear exactly once
        assert text.count("Shared update") == 1

    def test_new_peer_inbox_detected_on_poll(self, tmp_path: Path) -> None:
        """A peer inbox file created between polls is picked up."""
        team_root = tmp_path / "late-peer-team"
        inboxes = team_root / "inboxes"
        inboxes.mkdir(parents=True)
        (inboxes / "team-lead.json").write_text(
            json.dumps(
                [
                    {
                        "from": "Agent_One",
                        "text": "Status update.",
                        "timestamp": "2026-02-08T10:00:00.000Z",
                    },
                ]
            )
        )

        output = StringIO()
        call_count = 0

        def fake_sleep(interval: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # New peer inbox appears between polls
                (inboxes / "Agent_Two.json").write_text(
                    json.dumps(
                        [
                            {
                                "from": "Agent_Three",
                                "text": "Peer DM arrived late!",
                                "timestamp": "2026-02-08T10:05:00.000Z",
                            },
                        ]
                    )
                )
            elif call_count >= 2:
                raise KeyboardInterrupt

        with patch("chat_monitor.time.sleep", side_effect=fake_sleep):
            monitor_chat("late-peer-team", teams_dir=tmp_path, output=output)
        text = output.getvalue()
        assert "Status update" in text
        assert "Peer DM arrived late!" in text


# ── build_tmux_command ────────────────────────────────────────────────────


class TestBuildTmuxCommand:
    def test_starts_with_tmux(self) -> None:
        cmd = build_tmux_command("my-team")
        assert cmd[0] == "tmux"
        assert cmd[1] == "new-window"

    def test_detached(self) -> None:
        cmd = build_tmux_command("my-team")
        assert "-d" in cmd

    def test_window_name(self) -> None:
        cmd = build_tmux_command("my-team")
        idx = cmd.index("-n")
        assert cmd[idx + 1] == "chat-monitor"

    def test_shell_cmd_contains_team_name(self) -> None:
        cmd = build_tmux_command("my-team")
        shell_cmd = cmd[-1]
        assert "my-team" in shell_cmd

    def test_shell_injection_blocked(self) -> None:
        """A semicolon in team name must not break out of the command."""
        cmd = build_tmux_command("evil;rm -rf /")
        shell_cmd = cmd[-1]
        # The malicious payload must be inside quotes, not bare
        assert ";rm -rf /" not in shell_cmd.split("'")[0]


# ── launch_monitor ────────────────────────────────────────────────────────


class TestLaunchMonitor:
    @patch("chat_monitor.subprocess.run")
    def test_calls_subprocess(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_monitor("my-team")
        mock_run.assert_called_once()

    @patch("chat_monitor.subprocess.run")
    def test_passes_check_true(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_monitor("my-team")
        _args, kwargs = mock_run.call_args
        assert kwargs["check"] is True

    @patch("chat_monitor.subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux"))
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            launch_monitor("my-team")

    @patch("chat_monitor.subprocess.run")
    def test_calls_subprocess_no_team(self, mock_run: MagicMock) -> None:
        """launch_monitor(None) builds a command without --team-name."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_monitor(None)
        mock_run.assert_called_once()
        shell_cmd = mock_run.call_args[0][0][-1]
        assert "--team-name" not in shell_cmd


# ── CLI ───────────────────────────────────────────────────────────────────


class TestCLI:
    @patch("chat_monitor.monitor_chat")
    def test_inline_mode(self, mock_monitor: MagicMock) -> None:
        main(["--team-name", "my-team"])
        mock_monitor.assert_called_once_with("my-team")

    @patch("chat_monitor.launch_monitor")
    def test_tmux_mode(self, mock_launch: MagicMock) -> None:
        mock_launch.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        main(["--team-name", "my-team", "--tmux"])
        mock_launch.assert_called_once_with("my-team")

    @patch("chat_monitor.monitor_chat")
    def test_no_team_name_monitors_all(self, mock_monitor: MagicMock) -> None:
        """Omitting --team-name passes None to monitor_chat (all-teams mode)."""
        main([])
        mock_monitor.assert_called_once_with(None)

    @patch("chat_monitor.launch_monitor")
    def test_tmux_no_team_name(self, mock_launch: MagicMock) -> None:
        """Omitting --team-name with --tmux passes None to launch_monitor."""
        mock_launch.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        main(["--tmux"])
        mock_launch.assert_called_once_with(None)


# ── Multi-team fixture ───────────────────────────────────────────────────


@pytest.fixture()
def multi_team_dir(tmp_path: Path) -> Path:
    """Create two teams (alpha-team, beta-team) with distinct messages."""
    # --- alpha-team ---
    alpha = tmp_path / "alpha-team"
    alpha_inboxes = alpha / "inboxes"
    alpha_inboxes.mkdir(parents=True)
    (alpha / "config.json").write_text(
        json.dumps(
            {
                "name": "alpha-team",
                "members": [
                    {"name": "team-lead", "color": "cyan"},
                    {"name": "Alice", "color": "blue"},
                ],
            }
        )
    )
    (alpha_inboxes / "Alice.json").write_text(
        json.dumps(
            [
                {
                    "from": "team-lead",
                    "text": "Alpha task assigned.",
                    "timestamp": "2026-02-08T10:00:00.000Z",
                    "summary": "Alpha assignment",
                    "color": "cyan",
                },
            ]
        )
    )
    (alpha_inboxes / "team-lead.json").write_text(
        json.dumps(
            [
                {
                    "from": "Alice",
                    "text": "Alpha task done.",
                    "timestamp": "2026-02-08T10:05:00.000Z",
                    "summary": "Alpha done",
                    "color": "blue",
                },
            ]
        )
    )

    # --- beta-team ---
    beta = tmp_path / "beta-team"
    beta_inboxes = beta / "inboxes"
    beta_inboxes.mkdir(parents=True)
    (beta / "config.json").write_text(
        json.dumps(
            {
                "name": "beta-team",
                "members": [
                    {"name": "team-lead", "color": "green"},
                    {"name": "Bob", "color": "yellow"},
                ],
            }
        )
    )
    (beta_inboxes / "Bob.json").write_text(
        json.dumps(
            [
                {
                    "from": "team-lead",
                    "text": "Beta task assigned.",
                    "timestamp": "2026-02-08T10:02:00.000Z",
                    "summary": "Beta assignment",
                    "color": "green",
                },
            ]
        )
    )
    (beta_inboxes / "team-lead.json").write_text(
        json.dumps(
            [
                {
                    "from": "Bob",
                    "text": "Beta task done.",
                    "timestamp": "2026-02-08T10:07:00.000Z",
                    "summary": "Beta done",
                    "color": "yellow",
                },
            ]
        )
    )
    return tmp_path


# ── discover_teams ───────────────────────────────────────────────────────


class TestDiscoverTeams:
    def test_finds_teams_with_inboxes(self, multi_team_dir: Path) -> None:
        teams = discover_teams(multi_team_dir)
        assert teams == ["alpha-team", "beta-team"]

    def test_ignores_dirs_without_inboxes(self, tmp_path: Path) -> None:
        """Directories without an inboxes/ subdirectory are not teams."""
        (tmp_path / "not-a-team").mkdir()
        (tmp_path / "real-team" / "inboxes").mkdir(parents=True)
        teams = discover_teams(tmp_path)
        assert teams == ["real-team"]

    def test_empty_directory(self, tmp_path: Path) -> None:
        teams = discover_teams(tmp_path)
        assert teams == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        teams = discover_teams(tmp_path / "nope")
        assert teams == []

    def test_sorted_alphabetically(self, tmp_path: Path) -> None:
        for name in ["zulu", "alpha", "mike"]:
            (tmp_path / name / "inboxes").mkdir(parents=True)
        teams = discover_teams(tmp_path)
        assert teams == ["alpha", "mike", "zulu"]


# ── load_all_team_colors ─────────────────────────────────────────────────


class TestLoadAllTeamColors:
    def test_merges_colors_from_all_teams(self, multi_team_dir: Path) -> None:
        colors = load_all_team_colors(multi_team_dir)
        assert colors["Alice"] == "blue"
        assert colors["Bob"] == "yellow"

    def test_last_team_wins_for_shared_names(self, multi_team_dir: Path) -> None:
        """Both teams have 'team-lead'; beta-team (sorted second) wins."""
        colors = load_all_team_colors(multi_team_dir)
        assert colors["team-lead"] == "green"  # beta-team's color

    def test_empty_dir(self, tmp_path: Path) -> None:
        colors = load_all_team_colors(tmp_path)
        assert colors == {}


# ── collect_all_messages ─────────────────────────────────────────────────


class TestCollectAllMessages:
    def test_collects_from_all_teams(self, multi_team_dir: Path) -> None:
        msgs = collect_all_messages(multi_team_dir)
        assert len(msgs) == 4  # 2 per team
        teams = {m.team for m in msgs}
        assert teams == {"alpha-team", "beta-team"}

    def test_sorted_by_timestamp_across_teams(self, multi_team_dir: Path) -> None:
        msgs = collect_all_messages(multi_team_dir)
        timestamps = [m.timestamp for m in msgs]
        assert timestamps == sorted(timestamps)

    def test_messages_have_team_field_set(self, multi_team_dir: Path) -> None:
        msgs = collect_all_messages(multi_team_dir)
        for msg in msgs:
            assert msg.team in ("alpha-team", "beta-team")

    def test_empty_dir(self, tmp_path: Path) -> None:
        msgs = collect_all_messages(tmp_path)
        assert msgs == []

    def test_interleaved_timestamps(self, multi_team_dir: Path) -> None:
        """Messages from different teams are interleaved by timestamp."""
        msgs = collect_all_messages(multi_team_dir)
        # alpha: 10:00, 10:05 — beta: 10:02, 10:07
        # expected order: alpha(10:00), beta(10:02), alpha(10:05), beta(10:07)
        assert msgs[0].team == "alpha-team"
        assert msgs[1].team == "beta-team"
        assert msgs[2].team == "alpha-team"
        assert msgs[3].team == "beta-team"


# ── collect_messages team field ──────────────────────────────────────────


class TestCollectMessagesTeamField:
    def test_team_field_set(self, team_dir: Path) -> None:
        """collect_messages sets the team field on every message."""
        msgs = collect_messages("test-team", teams_dir=team_dir)
        for msg in msgs:
            assert msg.team == "test-team"


# ── format_message show_team ─────────────────────────────────────────────


class TestFormatMessageShowTeam:
    def test_show_team_false_no_tag(self) -> None:
        """With show_team=False (default), no team tag appears."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Alice",
            recipient="Bob",
            content="hi",
            summary="",
            color="blue",
            team="alpha-team",
        )
        line = format_message(msg, show_team=False)
        assert "[alpha-team]" not in line

    def test_show_team_true_has_tag(self) -> None:
        """With show_team=True, the team name appears in brackets."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Alice",
            recipient="Bob",
            content="hi",
            summary="",
            color="blue",
            team="alpha-team",
        )
        line = format_message(msg, show_team=True)
        assert "[alpha-team]" in line

    def test_show_team_true_empty_team_no_tag(self) -> None:
        """With show_team=True but empty team field, no tag appears."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="Alice",
            recipient="Bob",
            content="hi",
            summary="",
            color="blue",
            team="",
        )
        line = format_message(msg, show_team=True)
        # Should not have empty brackets
        assert "[]" not in line

    def test_system_message_show_team(self) -> None:
        """System messages also show team tag when show_team=True."""
        msg = ChatMessage(
            timestamp="2026-02-08T10:00:00.000Z",
            sender="team-lead",
            recipient="Alice",
            content='{"type":"idle_notification"}',
            summary="",
            color="",
            is_system=True,
            team="alpha-team",
        )
        line = format_message(msg, show_team=True)
        assert "[alpha-team]" in line
        assert "[system]" in line


# ── monitor_chat all-teams mode ──────────────────────────────────────────


class TestMonitorChatAllTeams:
    def test_header_says_all_teams(self, multi_team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat(None, teams_dir=multi_team_dir, output=output)
        text = output.getvalue()
        assert "all teams" in text

    def test_prints_messages_from_both_teams(self, multi_team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat(None, teams_dir=multi_team_dir, output=output)
        text = output.getvalue()
        assert "Alpha task assigned" in text
        assert "Beta task assigned" in text

    def test_team_tags_shown(self, multi_team_dir: Path) -> None:
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat(None, teams_dir=multi_team_dir, output=output)
        text = output.getvalue()
        assert "[alpha-team]" in text
        assert "[beta-team]" in text

    def test_single_team_no_team_tags(self, team_dir: Path) -> None:
        """When monitoring a single team, no team tags appear."""
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat("test-team", teams_dir=team_dir, output=output)
        text = output.getvalue()
        assert "[test-team]" not in text

    def test_no_cross_team_dedup(self, tmp_path: Path) -> None:
        """Same sender+timestamp+content in two different teams → both printed."""
        for team in ("team-a", "team-b"):
            inboxes = tmp_path / team / "inboxes"
            inboxes.mkdir(parents=True)
            (tmp_path / team / "config.json").write_text(json.dumps({"members": []}))
            (inboxes / "agent.json").write_text(
                json.dumps(
                    [
                        {
                            "from": "lead",
                            "text": "Identical message",
                            "timestamp": "2026-02-08T10:00:00.000Z",
                        },
                    ]
                )
            )
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat(None, teams_dir=tmp_path, output=output)
        text = output.getvalue()
        # "Identical message" should appear twice (once per team)
        assert text.count("Identical message") == 2

    def test_new_team_detected_on_poll(self, multi_team_dir: Path) -> None:
        """A new team directory created between polls is picked up."""
        output = StringIO()
        call_count = 0

        def fake_sleep(interval: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                gamma = multi_team_dir / "gamma-team"
                gamma_inboxes = gamma / "inboxes"
                gamma_inboxes.mkdir(parents=True)
                (gamma / "config.json").write_text(json.dumps({"members": []}))
                (gamma_inboxes / "agent.json").write_text(
                    json.dumps(
                        [
                            {
                                "from": "lead",
                                "text": "Gamma message!",
                                "timestamp": "2026-02-08T11:00:00.000Z",
                            },
                        ]
                    )
                )
            elif call_count >= 2:
                raise KeyboardInterrupt

        with patch("chat_monitor.time.sleep", side_effect=fake_sleep):
            monitor_chat(None, teams_dir=multi_team_dir, output=output)
        text = output.getvalue()
        assert "Gamma message!" in text

    def test_empty_teams_dir(self, tmp_path: Path) -> None:
        """All-teams mode with no teams prints header and stops gracefully."""
        output = StringIO()
        with patch("chat_monitor.time.sleep", side_effect=KeyboardInterrupt):
            monitor_chat(None, teams_dir=tmp_path, output=output)
        text = output.getvalue()
        assert "all teams" in text
        assert "Monitor stopped" in text


# ── build_tmux_command all-teams ─────────────────────────────────────────


class TestBuildTmuxCommandAllTeams:
    def test_no_team_name_omits_flag(self) -> None:
        cmd = build_tmux_command(None)
        shell_cmd = cmd[-1]
        assert "--team-name" not in shell_cmd

    def test_with_team_name_includes_flag(self) -> None:
        cmd = build_tmux_command("my-team")
        shell_cmd = cmd[-1]
        assert "--team-name" in shell_cmd
        assert "my-team" in shell_cmd
