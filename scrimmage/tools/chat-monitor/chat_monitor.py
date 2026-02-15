#!/usr/bin/env python3
"""Real-time chat monitor for Claude Code agent teams.

Opens a detached tmux window that tails team messages, colour-coded by agent.
Polls inbox files every second and prints new messages as they arrive.

Usage (single team)::

    python3 chat_monitor.py --team-name mypy-ignore-fixes

Usage (all teams)::

    python3 chat_monitor.py

Usage (tmux)::

    python3 chat_monitor.py --team-name mypy-ignore-fixes --tmux

Programmatic::

    from chat_monitor import monitor_chat
    monitor_chat("mypy-ignore-fixes")   # single team
    monitor_chat()                       # all teams
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

# ── ANSI colour codes ────────────────────────────────────────────────────

ANSI_COLORS: dict[str, str] = {
    "blue": "\033[94m",
    "orange": "\033[38;5;208m",
    "yellow": "\033[93m",
    "purple": "\033[95m",
    "green": "\033[92m",
    "red": "\033[91m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "pink": "\033[38;5;213m",
}
ANSI_RESET = "\033[0m"
ANSI_DIM = "\033[2m"
ANSI_BOLD = "\033[1m"

# System-level message types flagged with is_system=True and rendered dimmed.
_SYSTEM_MESSAGE_TYPES = frozenset(
    {
        "idle_notification",
        "shutdown_request",
        "shutdown_approved",
        "shutdown_response",
        "plan_approval_request",
        "plan_approval_response",
    }
)

TEAMS_DIR = Path.home() / ".claude" / "teams"


def load_team_colors(team_name: str, teams_dir: Path = TEAMS_DIR) -> dict[str, str]:
    """Load member name -> color mapping from the team config.

    Entries are stored under both the raw config name **and** a normalised
    key so that inbox filenames (which may use a different naming
    convention) can still match.
    """
    config_path = teams_dir / team_name / "config.json"
    try:
        config: dict[str, object] = json.loads(config_path.read_text(encoding="utf-8"))
        members = config.get("members", [])
        if not isinstance(members, list):
            return {}
        colors: dict[str, str] = {}
        for m in members:
            if not isinstance(m, dict) or "name" not in m:
                continue
            name = m["name"]
            color = m.get("color", "")
            colors[name] = color
            # Register under normalised key for cross-format matching
            if color:
                normalized = _normalize_name(name)
                if normalized:
                    colors.setdefault(normalized, color)
        return colors
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


# ── Data model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatMessage:
    """A single chat message extracted from an inbox file."""

    timestamp: str
    sender: str
    recipient: str
    content: str
    summary: str
    color: str
    is_system: bool = False
    team: str = ""


def _is_system_message(text: str) -> bool:
    """Return True if the message text is a JSON-encoded system message."""
    if not text.startswith("{"):
        return False
    try:
        parsed: dict[str, object] = json.loads(text)
        msg_type = parsed.get("type", "")
        return isinstance(msg_type, str) and msg_type in _SYSTEM_MESSAGE_TYPES
    except (json.JSONDecodeError, TypeError):
        return False


def read_inbox(filepath: Path) -> list[dict[str, str]]:
    """Read and parse a single inbox JSON file."""
    try:
        raw = filepath.read_text(encoding="utf-8")
        result: list[dict[str, str]] = json.loads(raw)
        return result
    except (json.JSONDecodeError, OSError):
        return []


def collect_messages(team_name: str, teams_dir: Path = TEAMS_DIR) -> list[ChatMessage]:
    """Collect all chat messages from a team's inbox files.

    Reads every ``{teams_dir}/{team_name}/inboxes/*.json`` file, flags
    protocol-level system messages with ``is_system=True``, and returns a
    de-duplicated list sorted by timestamp.
    """
    inboxes_dir = teams_dir / team_name / "inboxes"
    if not inboxes_dir.is_dir():
        return []

    # Two-pass dedup: broadcasts (same sender, timestamp, content) sent to
    # multiple recipients collapse into a single "[broadcast]" line.
    _ContentKey = tuple[str, str, str]  # (timestamp, sender, content_hash)

    pending: dict[_ContentKey, dict[str, object]] = {}
    recipient_sets: dict[_ContentKey, set[str]] = {}

    for inbox_file in sorted(inboxes_dir.glob("*.json")):
        recipient = inbox_file.stem
        entries = read_inbox(inbox_file)

        for entry in entries:
            text = entry.get("text", "")
            sender = entry.get("from", "unknown")
            timestamp = entry.get("timestamp", "")
            summary = entry.get("summary", "")
            color = entry.get("color", "")

            is_system = _is_system_message(text)

            content_hash = hashlib.md5(text.encode()).hexdigest()
            key: _ContentKey = (timestamp, sender, content_hash)

            if key not in pending:
                pending[key] = {
                    "timestamp": timestamp,
                    "sender": sender,
                    "recipient": recipient,
                    "content": text,
                    "summary": summary,
                    "color": color,
                    "is_system": is_system,
                }
                recipient_sets[key] = {recipient}
            else:
                recipient_sets[key].add(recipient)

    messages: list[ChatMessage] = []
    for key, data in pending.items():
        recipients = recipient_sets[key]
        recipient = ", ".join(sorted(recipients)) if len(recipients) > 1 else next(iter(recipients))
        messages.append(
            ChatMessage(
                timestamp=str(data["timestamp"]),
                sender=str(data["sender"]),
                recipient=recipient,
                content=str(data["content"]),
                summary=str(data["summary"]),
                color=str(data["color"]),
                is_system=bool(data.get("is_system", False)),
                team=team_name,
            )
        )

    messages.sort(key=lambda m: m.timestamp)
    return messages


def discover_teams(teams_dir: Path = TEAMS_DIR) -> list[str]:
    """Return sorted list of team names found in the teams directory."""
    if not teams_dir.is_dir():
        return []
    return sorted(d.name for d in teams_dir.iterdir() if d.is_dir() and (d / "inboxes").is_dir())


def load_all_team_colors(teams_dir: Path = TEAMS_DIR) -> dict[str, str]:
    """Load member colors from all team configs, merged into one dict."""
    colors: dict[str, str] = {}
    for team_name in discover_teams(teams_dir):
        colors.update(load_team_colors(team_name, teams_dir=teams_dir))
    return colors


def collect_all_messages(teams_dir: Path = TEAMS_DIR) -> list[ChatMessage]:
    """Collect messages from all teams, sorted by timestamp."""
    all_msgs: list[ChatMessage] = []
    for team_name in discover_teams(teams_dir):
        all_msgs.extend(collect_messages(team_name, teams_dir=teams_dir))
    all_msgs.sort(key=lambda m: m.timestamp)
    return all_msgs


# ── Display ───────────────────────────────────────────────────────────────


def _get_color_code(color_name: str) -> str:
    """Resolve the ANSI escape code from a color name."""
    return ANSI_COLORS.get(color_name, "")


def _normalize_name(name: str) -> str:
    """Normalize an agent name for fuzzy color matching.

    Different data sources use different naming conventions for the same
    agent.  This function strips all separators and instance numbers so
    that every variant produces the same canonical key::

        Cindy_Cloud_Engineer       →  cindy cloud engineer
        Cindy--Cloud-Engineer-     →  cindy cloud engineer
        Cindy (Cloud Engineer)     →  cindy cloud engineer
        Pierre--Peer-Reviewer--2   →  pierre peer reviewer
        Pierre (Peer Reviewer)     →  pierre peer reviewer
        Pierre_Peer_Reviewer_2     →  pierre peer reviewer
        team-lead                  →  team lead
        Sam                        →  sam
    """
    # Replace structural separators with spaces
    cleaned = name.replace("--", " ").replace("_", " ").replace("(", " ").replace(")", " ")
    # Split on whitespace, then sub-split on remaining single dashes
    parts: list[str] = []
    for word in cleaned.split():
        for sub in word.split("-"):
            if sub:
                parts.append(sub.lower())
    # Drop trailing numeric instance suffixes (e.g. "2" in Pierre-...-2)
    while parts and parts[-1].isdigit():
        parts.pop()
    return " ".join(parts)


def _format_display_name(name: str) -> str:
    """Convert agent file-system names to human-friendly display format.

    Supports both ``--`` and ``_`` separated naming conventions::

        Pierre--Peer-Reviewer--2   →  Pierre (Peer Reviewer)-2
        Cindy_Cloud_Engineer       →  Cindy (Cloud Engineer)
        Blake_Backend_Engineer     →  Blake (Backend Engineer)
        team-lead                  →  team-lead  (unchanged)
    """
    # Try double-dash format first: Pierre--Peer-Reviewer--2
    if "--" in name:
        parts = name.split("--")
        first = parts[0]
        if len(parts) > 2 and parts[-1].isdigit():
            role_parts = parts[1:-1]
            suffix = f"-{parts[-1]}"
        else:
            role_parts = parts[1:]
            suffix = ""
        role = " ".join(p.replace("-", " ") for p in role_parts).strip()
        return f"{first} ({role}){suffix}" if role else name

    # Try underscore format: Cindy_Cloud_Engineer
    if "_" in name:
        parts = name.split("_")
        if len(parts) >= 2:
            first = parts[0]
            if len(parts) > 2 and parts[-1].isdigit():
                role_parts = parts[1:-1]
                suffix = f"-{parts[-1]}"
            else:
                role_parts = parts[1:]
                suffix = ""
            role = " ".join(p for p in role_parts if p).strip()
            return f"{first} ({role}){suffix}" if role else name

    return name


_HIDDEN_JSON_KEYS = {"from", "requestId", "timestamp", "paneId", "backendType"}


def _format_content(text: str) -> str:
    """Pretty-print JSON content, or return text as-is.

    Strips keys listed in ``_HIDDEN_JSON_KEYS`` from top-level JSON objects
    before display — these are either redundant (already shown in the header)
    or internal implementation details (``paneId``, ``backendType``).
    """
    if not text.startswith(("{", "[")):
        return text
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = {k: v for k, v in parsed.items() if k not in _HIDDEN_JSON_KEYS}
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
        indented = "\n".join("    " + line for line in formatted.splitlines())
        return "\n" + indented
    except (json.JSONDecodeError, TypeError):
        return text


def _color_recipient(name: str, member_colors: dict[str, str]) -> str:
    """Colour and format a single recipient name for display."""
    display = _format_display_name(name)
    color = member_colors.get(name) or member_colors.get(_normalize_name(name)) or ""
    ansi = _get_color_code(color)
    if ansi:
        return f"{ansi}{display}{ANSI_RESET}"
    return display


def _split_recipients(recipient_field: str) -> list[str]:
    """Split a recipient field into individual names.

    Single recipients are returned as a one-element list.  Multi-recipient
    fields (comma-separated) are split and stripped.
    """
    return [r.strip() for r in recipient_field.split(", ")] if ", " in recipient_field else [recipient_field]


def format_message(
    msg: ChatMessage,
    member_colors: dict[str, str] | None = None,
    show_team: bool = False,
) -> str:
    """Format a ChatMessage as a coloured terminal line."""
    colors = member_colors or {}

    # Display names
    sender_display = _format_display_name(msg.sender)

    # Sender color: try raw name, then normalised name, then msg.color.
    sender_color = colors.get(msg.sender) or colors.get(_normalize_name(msg.sender)) or msg.color
    sender_ansi = _get_color_code(sender_color)

    # Recipient names (may be comma-separated for multi-recipient messages)
    recipient_names = _split_recipients(msg.recipient)

    # Truncate timestamp to HH:MM:SS
    time_part = msg.timestamp[11:19] if len(msg.timestamp) >= 19 else msg.timestamp

    # Pretty-print JSON content
    display_text = _format_content(msg.content)

    # Team tag (for all-teams mode)
    team_tag = f" {ANSI_DIM}[{msg.team}]{ANSI_RESET}" if show_team and msg.team else ""

    # Build coloured recipient list
    colored_recipients = ", ".join(_color_recipient(name, colors) for name in recipient_names)

    if msg.is_system:
        # System messages: dim header, normal content text
        team_text = f"[{msg.team}] " if show_team and msg.team else ""
        recipient_displays = ", ".join(_format_display_name(name) for name in recipient_names)
        return (
            f"{ANSI_DIM}{time_part} {team_text}{sender_display} "
            f"\u2192 {recipient_displays} [system]{ANSI_RESET} {display_text}"
        )

    return (
        f"{ANSI_DIM}{time_part}{ANSI_RESET}"
        f"{team_tag} "
        f"{sender_ansi}{ANSI_BOLD}{sender_display}{ANSI_RESET} "
        f"{ANSI_DIM}\u2192{ANSI_RESET} {colored_recipients} "
        f"{display_text}"
    )


def monitor_chat(
    team_name: str | None = None,
    poll_interval: float = 1.0,
    teams_dir: Path = TEAMS_DIR,
    output: TextIO = sys.stdout,
) -> None:
    """Poll for new messages and print them. Runs until interrupted.

    When *team_name* is ``None``, messages from **all** teams are shown
    with a ``[team]`` tag to distinguish them.
    """
    # Dedup key: (team, timestamp, sender, content_hash).
    # Including team prevents cross-team false-positive dedup.
    # Using content hash instead of recipient avoids two problems:
    #   1. Two messages at the same instant from the same sender to the same
    #      recipient but with different content both get printed.
    #   2. A message whose recipient flips between a name and "[broadcast]"
    #      across polls is not printed twice.
    seen_keys: set[tuple[str, str, str, str]] = set()
    show_team = team_name is None

    if team_name:
        output.write(f"Chat monitor for team '{team_name}' -- Ctrl-C to stop\n")
    else:
        output.write("Chat monitor for all teams -- Ctrl-C to stop\n")
    output.write("-" * 60 + "\n")
    output.flush()

    try:
        while True:
            if team_name:
                member_colors = load_team_colors(team_name, teams_dir=teams_dir)
                messages = collect_messages(team_name, teams_dir=teams_dir)
            else:
                member_colors = load_all_team_colors(teams_dir=teams_dir)
                messages = collect_all_messages(teams_dir=teams_dir)
            for msg in messages:
                content_hash = hashlib.md5(msg.content.encode()).hexdigest()
                key = (msg.team, msg.timestamp, msg.sender, content_hash)
                if key not in seen_keys:
                    seen_keys.add(key)
                    output.write(format_message(msg, member_colors=member_colors, show_team=show_team) + "\n")
                    output.flush()
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        output.write("\nMonitor stopped.\n")
        output.flush()


# ── tmux launcher ─────────────────────────────────────────────────────────


def build_tmux_command(team_name: str | None = None) -> list[str]:
    """Build a ``tmux new-window -d`` command to launch the monitor."""
    script_path = os.path.abspath(__file__)
    if team_name:
        shell_cmd = f"python3 {shlex.quote(script_path)} --team-name {shlex.quote(team_name)}"
    else:
        shell_cmd = f"python3 {shlex.quote(script_path)}"
    return [
        "tmux",
        "new-window",
        "-d",
        "-n",
        "chat-monitor",
        shell_cmd,
    ]


def launch_monitor(team_name: str | None = None) -> subprocess.CompletedProcess[bytes]:
    """Open the chat monitor in a detached tmux window."""
    cmd = build_tmux_command(team_name)
    return subprocess.run(cmd, check=True, capture_output=True)


# ── CLI ───────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real-time chat monitor for Claude Code agent teams.",
    )
    parser.add_argument("--team-name", default=None, help="Team name to monitor (omit to monitor all teams)")
    parser.add_argument(
        "--tmux",
        action="store_true",
        help="Launch in a detached tmux window instead of running inline",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.tmux:
        launch_monitor(args.team_name)
    else:
        monitor_chat(args.team_name)


if __name__ == "__main__":
    main()
