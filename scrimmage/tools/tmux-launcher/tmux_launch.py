"""Launch a Claude Code agent in a detached tmux window.

Wraps ``tmux new-window -d`` so the new window does NOT steal focus from the
caller's current window.  Sets the required env vars and passes all agent
parameters through to the ``claude`` CLI.

Usage (CLI)::

    python3 tmux_launch.py \\
        --agent-name Pierre_Peer_Reviewer \\
        --team-name mypy-ignore-fixes \\
        --agent-color yellow \\
        --parent-session-id 1ad512d5-b247-40fc-bbe9-5ed21cf848d3 \\
        --agent-type general-purpose \\
        --model opus \\
        --work-dir /path/to/project

Programmatic::

    from tmux_launch import build_tmux_command, launch_agent, AgentConfig

    cfg = AgentConfig(
        agent_name="Pierre_Peer_Reviewer",
        team_name="mypy-ignore-fixes",
        agent_color="yellow",
        parent_session_id="1ad512d5-b247-40fc-bbe9-5ed21cf848d3",
        agent_type="general-purpose",
        model="opus",
    )
    launch_agent(cfg)
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field

CLAUDE_BIN = shutil.which("claude") or "/usr/local/bin/claude"

# Environment variables injected into every agent window.
AGENT_ENV: dict[str, str] = {
    "CLAUDECODE": "1",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
}


@dataclass(frozen=True)
class AgentConfig:
    """All parameters needed to launch a Claude Code agent."""

    agent_name: str
    team_name: str
    agent_color: str
    parent_session_id: str
    agent_type: str
    model: str
    work_dir: str = field(default_factory=os.getcwd)


def _build_agent_id(agent_name: str, team_name: str) -> str:
    """Derive the ``--agent-id`` value: ``<name>@<team>``."""
    return f"{agent_name}@{team_name}"


def build_claude_command(config: AgentConfig) -> list[str]:
    """Build the ``claude`` CLI argv for launching an agent."""
    agent_id = _build_agent_id(config.agent_name, config.team_name)
    return [
        CLAUDE_BIN,
        "--agent-id",
        agent_id,
        "--agent-name",
        config.agent_name,
        "--team-name",
        config.team_name,
        "--agent-color",
        config.agent_color,
        "--parent-session-id",
        config.parent_session_id,
        "--agent-type",
        config.agent_type,
        "--dangerously-skip-permissions",
        "--model",
        config.model,
    ]


def _sanitize_window_name(name: str) -> str:
    """Sanitize a string for use as a tmux window name.

    Tmux treats ``.``, ``:``, and ``!`` specially in its target syntax
    (``session:window.pane``).  Strip these and any other non-alphanumeric,
    non-underscore, non-hyphen characters to prevent targeting confusion.
    """
    import re

    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", name)
    return sanitized or "agent"


def build_tmux_command(config: AgentConfig) -> list[str]:
    """Build the full ``tmux new-window -d`` command list.

    The shell string executed inside the new window:
    1. ``cd`` to the working directory
    2. exports the required env vars
    3. runs the ``claude`` CLI with all agent flags
    """
    claude_argv = build_claude_command(config)

    # Build the shell snippet that runs inside the new tmux window.
    parts: list[str] = [f"cd {shlex.quote(config.work_dir)}"]
    for key, value in AGENT_ENV.items():
        parts.append(f"export {key}={shlex.quote(value)}")
    parts.append(shlex.join(claude_argv))
    shell_cmd = " && ".join(parts)

    window_name = _sanitize_window_name(config.agent_name)

    return [
        "tmux",
        "new-window",
        "-d",  # detached — do NOT steal focus
        "-n",
        window_name,
        shell_cmd,
    ]


def launch_agent(config: AgentConfig) -> subprocess.CompletedProcess[bytes]:
    """Launch an agent in a new detached tmux window.

    Returns the ``CompletedProcess`` from the ``tmux`` invocation.
    Raises ``subprocess.CalledProcessError`` if tmux exits non-zero.
    """
    cmd = build_tmux_command(config)
    return subprocess.run(cmd, check=True, capture_output=True)


def _parse_args(argv: list[str] | None = None) -> AgentConfig:
    parser = argparse.ArgumentParser(
        description="Launch a Claude Code agent in a detached tmux window.",
    )
    parser.add_argument("--agent-name", required=True, help="Agent display name")
    parser.add_argument("--team-name", required=True, help="Team name for coordination")
    parser.add_argument("--agent-color", required=True, help="Agent colour in the UI")
    parser.add_argument("--parent-session-id", required=True, help="Parent session UUID")
    parser.add_argument("--agent-type", required=True, help="Agent type (e.g. general-purpose)")
    parser.add_argument("--model", required=True, help="Model name (e.g. opus, sonnet)")
    parser.add_argument(
        "--work-dir",
        default=os.getcwd(),
        help="Working directory for the agent (default: current directory)",
    )
    args = parser.parse_args(argv)
    return AgentConfig(
        agent_name=args.agent_name,
        team_name=args.team_name,
        agent_color=args.agent_color,
        parent_session_id=args.parent_session_id,
        agent_type=args.agent_type,
        model=args.model,
        work_dir=args.work_dir,
    )


def main(argv: list[str] | None = None) -> None:
    config = _parse_args(argv)
    launch_agent(config)


if __name__ == "__main__":
    main()
