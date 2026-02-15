#!/usr/bin/env python3
"""Generate SM state snapshot from existing data sources.

Queries the backlog DB, git worktrees, git log, and optional team config
to produce a populated ``scrimmage/notes/sm-state.md`` that the Scrimmage Master
can read for coordination context.

Usage::

    python3 scrimmage/tools/generate_sm_state.py --sprint sprint-8
    python3 scrimmage/tools/generate_sm_state.py --sprint sprint-8 --team my-project
    python3 scrimmage/tools/generate_sm_state.py --sprint sprint-8 --output /tmp/state.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo / path helpers
# ---------------------------------------------------------------------------

SCRIMMAGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIMMAGE_DIR.parent

# Ensure scrimmage dir is importable (for backlog_db, worktree_setup)
if str(SCRIMMAGE_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIMMAGE_DIR))

from backlog_db import get_backlog_db  # noqa: E402
from worktree_setup import derive_stage_name  # noqa: E402


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: str | Path | None = None) -> str:
    """Run a command and return stripped stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True,
            cwd=cwd,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _collect_sprint_section(bl, sprint: str) -> str:
    """Sprint summary: name and item counts by status."""
    items = bl.list_items(sprint=sprint)
    total = len(items)
    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1

    done = counts.get("done", 0)
    in_progress = counts.get("in_progress", 0)
    review = counts.get("review", 0)
    merged = counts.get("merged", 0)
    ready = counts.get("ready", 0)
    backlog = counts.get("backlog", 0)
    parked = counts.get("parked", 0)

    lines = [
        "## Sprint\n",
        f"- **Name:** {sprint}",
        f"- **Total items:** {total}",
        f"- **Done:** {done}  |  **Merged:** {merged}  |  **Review:** {review}  |  **In Progress:** {in_progress}  |  **Ready:** {ready}  |  **Backlog:** {backlog}",
    ]
    if parked:
        lines.append(f"- **Parked:** {parked}")
    return "\n".join(lines)


def _collect_agents_section(team_name: str | None, bl, sprint: str) -> str:
    """Active agents from team config, cross-referenced with backlog assignments."""
    lines = ["## Active Agents\n"]

    members: list[dict] = []
    if team_name:
        config_path = Path.home() / ".claude" / "teams" / team_name / "config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                members = config.get("members", [])
            except (json.JSONDecodeError, KeyError):
                pass

    if not members:
        lines.append("_No team config available — skipping agent metadata._")
        return "\n".join(lines)

    # Build assignment map: agent_name -> list of (item_id, title, status)
    items = bl.list_items(sprint=sprint)
    assignment_map: dict[str, list[tuple[int, str, str]]] = {}
    for item in items:
        if item.assigned_to:
            # Normalize: agent names in backlog may differ from team config
            assignment_map.setdefault(item.assigned_to, []).append(
                (item.id, item.title, item.status)
            )

    lines.append("| Agent | Role | Model | Item | Status | Joined |")
    lines.append("|-------|------|-------|------|--------|--------|")

    for member in members:
        name = member.get("name", "?")
        role = member.get("agentType", "?")
        model = member.get("model", "?")
        joined = member.get("joinedAt", "?")
        if isinstance(joined, str) and len(joined) > 19:
            joined = joined[:19]  # trim to readable length

        # Find assigned items for this agent
        assigned = assignment_map.get(name, [])
        if assigned:
            for item_id, title, status in assigned:
                short_title = title[:30] + "…" if len(title) > 30 else title
                lines.append(
                    f"| {name} | {role} | {model} | #{item_id} {short_title} | {status} | {joined} |"
                )
        else:
            lines.append(f"| {name} | {role} | {model} | — | idle | {joined} |")

    return "\n".join(lines)


def _collect_worktrees() -> list[dict[str, str]]:
    """Parse ``git worktree list --porcelain`` into a list of dicts."""
    raw = _run(["git", "worktree", "list", "--porcelain"], cwd=REPO_ROOT)
    if not raw:
        return []

    worktrees: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            if current:
                worktrees.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[len("worktree "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line == "bare":
            current["bare"] = "true"
    if current:
        worktrees.append(current)

    return worktrees


def _collect_file_ownership(worktrees: list[dict[str, str]]) -> str:
    """For each worktree branch, show files changed vs master."""
    lines = ["## File Ownership\n"]

    branches = [
        wt for wt in worktrees
        if wt.get("branch", "").startswith("refs/heads/feature/")
    ]

    if not branches:
        lines.append("_No feature branches active._")
        return "\n".join(lines)

    lines.append("| Agent/Branch | Changed Files |")
    lines.append("|-------------|---------------|")

    for wt in branches:
        branch = wt["branch"].replace("refs/heads/", "")
        wt_path = wt.get("path", "")
        diff_output = _run(
            ["git", "diff", "--name-only", f"master...{branch}"],
            cwd=REPO_ROOT,
        )
        files = diff_output.splitlines() if diff_output else []
        files_str = ", ".join(f"`{f}`" for f in files[:10])
        if len(files) > 10:
            files_str += f" (+{len(files) - 10} more)"
        if not files_str:
            files_str = "_(no changes yet)_"
        lines.append(f"| {branch} | {files_str} |")

    return "\n".join(lines)


def _collect_comments_section(bl, sprint: str) -> str:
    """Backlog item comments for all non-done sprint items."""
    lines = ["## Backlog Item Comments\n"]

    items = bl.list_items(sprint=sprint)
    active_items = [i for i in items if i.status != "done"]

    if not active_items:
        lines.append("_No active items in sprint._")
        return "\n".join(lines)

    found_any = False
    for item in active_items:
        history = bl.get_history(item.id)
        comments = [e for e in history if e.get("event_type") == "comment"]
        if not comments:
            continue
        found_any = True
        lines.append(f"### #{item.id} — {item.title} [{item.status}]\n")
        for evt in comments:
            ts = evt.get("created_at", "?")[:19]
            agent = evt.get("agent_id") or "?"
            # Extract just the agent name prefix (before /pid=)
            if "/" in agent:
                agent = agent.split("/")[0]
            text = evt.get("comment", "")
            lines.append(f"- **{ts}** ({agent}): {text}")
        lines.append("")

    if not found_any:
        lines.append("_No comments on active items._")

    return "\n".join(lines)


def _collect_recent_events(bl, sprint: str) -> str:
    """Merge backlog audit events with recent git commits, take last 10."""
    lines = ["## Recent Events (last 10)\n"]

    events: list[tuple[str, str]] = []  # (timestamp, description)

    # Backlog events: query all events for sprint items
    items = bl.list_items(sprint=sprint)
    item_titles = {i.id: i.title for i in items}

    for item in items:
        history = bl.get_history(item.id)
        for evt in history:
            ts = evt.get("created_at", "")
            etype = evt.get("event_type", "")
            agent = evt.get("agent_id") or "?"
            if "/" in agent:
                agent = agent.split("/")[0]

            if etype == "status_change":
                desc = f"#{item.id} status: {evt.get('old_value')} → {evt.get('new_value')} ({agent})"
            elif etype == "assigned":
                new_val = evt.get("new_value", "unassigned")
                desc = f"#{item.id} assigned to {new_val} ({agent})"
            elif etype == "comment":
                comment_text = (evt.get("comment", "") or "")[:60]
                desc = f"#{item.id} comment by {agent}: {comment_text}"
            elif etype == "created":
                desc = f"#{item.id} created: {evt.get('new_value', '')} ({agent})"
            else:
                desc = f"#{item.id} {etype} ({agent})"
            events.append((ts, desc))

    # Git merge commits (last hour)
    git_log = _run(
        ["git", "log", "--since=2 hours ago", "--all", "--oneline",
         "--format=%aI %s"],
        cwd=REPO_ROOT,
    )
    for log_line in git_log.splitlines():
        if not log_line.strip():
            continue
        parts = log_line.split(" ", 1)
        if len(parts) == 2:
            events.append((parts[0], f"git: {parts[1]}"))

    # Sort by timestamp descending, take last 10
    events.sort(key=lambda x: x[0], reverse=True)
    recent = events[:10]

    if not recent:
        lines.append("_No recent events._")
        return "\n".join(lines)

    for ts, desc in recent:
        short_ts = ts[:19] if len(ts) > 19 else ts
        lines.append(f"- {short_ts}: {desc}")

    return "\n".join(lines)


def _collect_pending_actions(bl, sprint: str) -> str:
    """Flag items that look like they need SM attention."""
    lines = ["## Pending Actions\n"]

    items = bl.list_items(sprint=sprint)
    actions: list[str] = []

    for item in items:
        if item.status == "ready" and not item.assigned_to:
            actions.append(f"- [ ] **Assign** #{item.id} ({item.title}) — ready but unassigned")
        elif item.status == "review":
            actions.append(f"- [ ] **Review** #{item.id} ({item.title}) — awaiting review")
        elif item.status == "merged":
            actions.append(f"- [ ] **Verify deploy** #{item.id} ({item.title}) — merged, needs deploy verification")

    if not actions:
        lines.append("_No pending actions — all clear._")
    else:
        lines.extend(actions)

    return "\n".join(lines)


def _collect_deployments(worktrees: list[dict[str, str]]) -> str:
    """List active worktree branches with derived stage names."""
    lines = ["## Active Branch Deployments\n"]

    branches = [
        wt for wt in worktrees
        if wt.get("branch", "").startswith("refs/heads/feature/")
    ]

    if not branches:
        lines.append("_No active feature branches._")
        return "\n".join(lines)

    lines.append("| Stage | Branch | Worktree |")
    lines.append("|-------|--------|----------|")

    for wt in branches:
        branch = wt["branch"].replace("refs/heads/", "")
        stage = derive_stage_name(branch)
        wt_path = wt.get("path", "?")
        lines.append(f"| {stage} | {branch} | {wt_path} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def generate_sm_state(
    sprint: str,
    team_name: str | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate the full SM state markdown and write it to output_path."""
    if output_path is None:
        output_path = SCRIMMAGE_DIR / "notes" / "sm-state.md"
    bl = get_backlog_db(db_path=SCRIMMAGE_DIR / "backlog.db")
    worktrees = _collect_worktrees()

    sections = [
        f"# SM State — {_now_iso()}\n",
        _collect_sprint_section(bl, sprint),
        _collect_agents_section(team_name, bl, sprint),
        _collect_file_ownership(worktrees),
        _collect_comments_section(bl, sprint),
        _collect_recent_events(bl, sprint),
        _collect_pending_actions(bl, sprint),
        _collect_deployments(worktrees),
    ]

    content = "\n\n".join(sections) + "\n"

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)

    return content


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SM state snapshot from backlog, git, and team config.",
    )
    parser.add_argument("--sprint", required=True, help="Sprint name to query (e.g. sprint-8)")
    parser.add_argument("--team", default=None, help="Team name for agent metadata (reads ~/.claude/teams/{team}/config.json)")
    default_output = str(SCRIMMAGE_DIR / "notes" / "sm-state.md")
    parser.add_argument("--output", default=default_output, help=f"Output path (default: {default_output})")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    content = generate_sm_state(
        sprint=args.sprint,
        team_name=args.team,
        output_path=args.output,
    )
    print(f"SM state written to {args.output} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
