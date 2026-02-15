#!/usr/bin/env python3
"""Terminal scrimmage board — information radiator for sprint backlogs.

Displays backlog items from ``backlog.db`` in five columns
(**To Do**, **In Progress**, **Review**, **Merged**, **Done**) with colour-coded assignees.
Includes a memory monitor (RAM/Swap) at the top.
Polls every 5 seconds and redraws on terminal resize.

Usage (inline)::

    python3 scrimmage_board.py --sprint sprint-7

Usage (tmux)::

    python3 scrimmage_board.py --sprint sprint-7 --tmux

Programmatic::

    from scrimmage_board import render_board
    render_board("sprint-7")
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

# ── ANSI codes ────────────────────────────────────────────────────────────

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_UNDERLINE = "\033[4m"
ANSI_REVERSE = "\033[7m"

# Colour palette for dynamic agent assignment
_COLOUR_PALETTE = [
    "\033[96m",         # cyan
    "\033[92m",         # green
    "\033[93m",         # yellow
    "\033[95m",         # purple
    "\033[94m",         # blue
    "\033[38;5;208m",   # orange
    "\033[91m",         # red
    "\033[97m",         # white
    "\033[38;5;213m",   # pink
    "\033[38;5;117m",   # light blue
]

# Column header colours
_HEADER_TODO = "\033[97m"       # white
_HEADER_PROGRESS = "\033[93m"   # yellow
_HEADER_REVIEW = "\033[95m"     # purple
_HEADER_MERGED = "\033[96m"     # cyan
_HEADER_DONE = "\033[92m"       # green

# Review indicator
_REVIEW_BADGE = "\033[95m⦿\033[0m"  # purple circle

# Status groupings
_TODO_STATUSES = frozenset({"backlog", "ready"})
_PROGRESS_STATUSES = frozenset({"in_progress"})
_REVIEW_STATUSES = frozenset({"review"})
_MERGED_STATUSES = frozenset({"merged"})
_DONE_STATUSES = frozenset({"done"})


# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class BoardItem:
    """A single backlog item projected for board display."""

    item_id: int
    title: str
    status: str
    assigned_to: str


@dataclass
class BoardData:
    """Categorised sprint items for the five columns."""

    todo: list[BoardItem]
    in_progress: list[BoardItem]
    review: list[BoardItem]
    merged: list[BoardItem]
    done: list[BoardItem]


# ── Colour assignment ─────────────────────────────────────────────────────


class ColourAssigner:
    """Dynamically assigns colours to agent names.

    Colours are assigned in order of first appearance and reused for
    the same agent across refreshes.  This avoids the P2 lesson from
    #161: never hardcode colours to specific agent names.
    """

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._next_idx = 0

    def get(self, agent_name: str) -> str:
        """Return the ANSI colour code for an agent."""
        if not agent_name:
            return ANSI_DIM
        if agent_name not in self._map:
            colour = _COLOUR_PALETTE[self._next_idx % len(_COLOUR_PALETTE)]
            self._map[agent_name] = colour
            self._next_idx += 1
        return self._map[agent_name]


# ── Data fetching ─────────────────────────────────────────────────────────


def _get_backlog_db() -> object:
    """Import and return a backlog DB handle.

    We do a lazy import so the module can be imported without
    backlog_db being on sys.path (tests mock this function).
    """
    # Ensure the repo root is on the path so backlog_db is importable
    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from backlog_db import get_backlog_db
    db_path = repo_root / "backlog.db"
    return get_backlog_db(db_path=db_path)


def fetch_board_data(sprint: str) -> BoardData:
    """Fetch and categorise all items for the given sprint."""
    db = _get_backlog_db()
    items = db.list_items(sprint=sprint)

    todo: list[BoardItem] = []
    in_progress: list[BoardItem] = []
    review: list[BoardItem] = []
    merged: list[BoardItem] = []
    done: list[BoardItem] = []

    for item in items:
        bi = BoardItem(
            item_id=item.id,
            title=item.title,
            status=item.status,
            assigned_to=item.assigned_to or "",
        )
        if bi.status in _TODO_STATUSES:
            todo.append(bi)
        elif bi.status in _PROGRESS_STATUSES:
            in_progress.append(bi)
        elif bi.status in _REVIEW_STATUSES:
            review.append(bi)
        elif bi.status in _MERGED_STATUSES:
            merged.append(bi)
        elif bi.status in _DONE_STATUSES:
            done.append(bi)

    return BoardData(todo=todo, in_progress=in_progress, review=review, merged=merged, done=done)


# ── Memory monitoring ────────────────────────────────────────────────────


def get_memory_stats() -> str:
    """Get current RAM and Swap usage as a formatted string.

    Returns a colour-coded status line like:
    RAM: 2.2/15.6 GB (14%) | Swap: 8/4096 MB (0%)

    Returns "RAM: N/A" if /proc/meminfo is not available (e.g. macOS).
    """
    try:
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return "RAM: N/A"

        meminfo = meminfo_path.read_text()

        # Parse memory values (in kB)
        mem_total = 0
        mem_available = 0
        swap_total = 0
        swap_free = 0

        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1])
            elif line.startswith("SwapTotal:"):
                swap_total = int(line.split()[1])
            elif line.startswith("SwapFree:"):
                swap_free = int(line.split()[1])

        # Calculate used values
        mem_used = mem_total - mem_available
        swap_used = swap_total - swap_free

        # Convert to GB (RAM) and MB (Swap)
        mem_used_gb = mem_used / 1048576  # 1024 * 1024
        mem_total_gb = mem_total / 1048576
        swap_used_mb = swap_used / 1024
        swap_total_mb = swap_total / 1024

        # Calculate percentages
        mem_pct = int((mem_used * 100) / mem_total) if mem_total > 0 else 0
        swap_pct = int((swap_used * 100) / swap_total) if swap_total > 0 else 0

        # Colour coding based on RAM usage
        if mem_pct >= 85:
            colour = "\033[91m"  # red
        elif mem_pct >= 70:
            colour = "\033[93m"  # yellow
        else:
            colour = "\033[92m"  # green

        return (
            f"{colour}RAM: {mem_used_gb:.1f}/{mem_total_gb:.1f} GB ({mem_pct}%) | "
            f"Swap: {swap_used_mb:.0f}/{swap_total_mb:.0f} MB ({swap_pct}%){ANSI_RESET}"
        )
    except Exception:
        return "RAM: N/A"


# ── Rendering ─────────────────────────────────────────────────────────────


def _truncate(text: str, max_width: int) -> str:
    """Truncate text to max_width, adding ellipsis if needed."""
    if len(text) <= max_width:
        return text
    return text[: max_width - 1] + "…"


def _word_wrap(text: str, width: int, max_lines: int = 3) -> list[str]:
    """Word-wrap *text* to *width*, truncating with ellipsis beyond *max_lines*."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""

    for word in words:
        if not current:
            if len(word) > width:
                current = word[: width - 1] + "…"
            else:
                current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            if len(word) > width:
                current = word[: width - 1] + "…"
            else:
                current = word

    if current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if len(last) < width:
            lines[-1] = last + "…"
        else:
            lines[-1] = last[: width - 1] + "…"

    return lines


def _format_item(
    item: BoardItem,
    col_width: int,
    colours: ColourAssigner,
) -> list[str]:
    """Format a single item as multiple lines within col_width.

    Line 1:   #{id} title (word-wrapped)
    Line 2+:  title continuation (indented to align)
    Last line: assignee (colour-coded)  [review badge if applicable]
    """
    lines: list[str] = []

    # Title with word wrap
    prefix = f"#{item.item_id} "
    title_width = max(col_width - len(prefix), 10)
    title_lines = _word_wrap(item.title, title_width, max_lines=3)

    # First title line with bold ID prefix
    lines.append(f"{ANSI_BOLD}{prefix}{ANSI_RESET}{title_lines[0]}")

    # Continuation title lines, indented to align with title start
    indent = " " * len(prefix)
    for tl in title_lines[1:]:
        lines.append(f"{indent}{tl}")

    # Assignee + review badge
    agent_colour = colours.get(item.assigned_to)
    agent_display = item.assigned_to if item.assigned_to else "unassigned"
    agent_short = _shorten_agent_name(agent_display)

    badge = ""
    if item.status == "review":
        badge = f" {_REVIEW_BADGE}"

    lines.append(f"  {agent_colour}{agent_short}{ANSI_RESET}{badge}")

    return lines


def _shorten_agent_name(name: str) -> str:
    """Shorten agent names to fit columns.

    'Barry_Backend_Engineer' → 'Barry_BE'
    'Cindy_Cloud_Engineer' → 'Cindy_CE'
    'team-lead' → 'team-lead'
    """
    if "_" not in name:
        return name
    parts = name.split("_")
    if len(parts) >= 3:
        first = parts[0]
        initials = "".join(p[0].upper() for p in parts[1:])
        return f"{first}_{initials}"
    return name


def render_board(
    sprint: str,
    output: TextIO = sys.stdout,
    term_width: int | None = None,
    term_height: int | None = None,
) -> str:
    """Render the scrimmage board as a string and write to output.

    Returns the rendered string (useful for testing).
    """
    data = fetch_board_data(sprint)
    return render_board_data(data, sprint, output, term_width, term_height)


def render_board_data(
    data: BoardData,
    sprint: str,
    output: TextIO = sys.stdout,
    term_width: int | None = None,
    term_height: int | None = None,
) -> str:
    """Render pre-fetched board data. Separated for testability."""
    if term_width is None or term_height is None:
        size = shutil.get_terminal_size((120, 40))
        term_width = term_width or size.columns
        term_height = term_height or size.lines

    colours = ColourAssigner()
    lines: list[str] = []

    # Memory stats at the top
    memory_stats = get_memory_stats()
    lines.append(memory_stats)
    lines.append("")

    # Header
    header = f" Scrimmage Board — {sprint} "
    lines.append(f"{ANSI_REVERSE}{ANSI_BOLD}{header:^{term_width}}{ANSI_RESET}")
    lines.append("")

    # Column widths: split terminal into 5 equal columns with separators
    separator_width = 3  # " │ "
    usable = term_width - (separator_width * 4)
    col_w = max(usable // 5, 12)

    # Column headers with counts
    todo_header = f"To Do ({len(data.todo)})"
    prog_header = f"In Progress ({len(data.in_progress)})"
    review_header = f"Review ({len(data.review)})"
    merged_header = f"Merged ({len(data.merged)})"
    done_header = f"Done ({len(data.done)})"

    header_line = (
        f"{_HEADER_TODO}{ANSI_BOLD}{ANSI_UNDERLINE}{todo_header:<{col_w}}{ANSI_RESET}"
        f" │ "
        f"{_HEADER_PROGRESS}{ANSI_BOLD}{ANSI_UNDERLINE}{prog_header:<{col_w}}{ANSI_RESET}"
        f" │ "
        f"{_HEADER_REVIEW}{ANSI_BOLD}{ANSI_UNDERLINE}{review_header:<{col_w}}{ANSI_RESET}"
        f" │ "
        f"{_HEADER_MERGED}{ANSI_BOLD}{ANSI_UNDERLINE}{merged_header:<{col_w}}{ANSI_RESET}"
        f" │ "
        f"{_HEADER_DONE}{ANSI_BOLD}{ANSI_UNDERLINE}{done_header:<{col_w}}{ANSI_RESET}"
    )
    lines.append(header_line)
    lines.append("")

    # Render each column's items
    todo_lines = _render_column(data.todo, col_w, colours)
    prog_lines = _render_column(data.in_progress, col_w, colours)
    review_lines = _render_column(data.review, col_w, colours)
    merged_lines = _render_column(data.merged, col_w, colours)
    done_lines = _render_column(data.done, col_w, colours)

    # Interleave columns row by row
    max_rows = max(len(todo_lines), len(prog_lines), len(review_lines), len(merged_lines), len(done_lines))

    # Cap display at available terminal height (leave room for memory + header + footer)
    display_rows = min(max_rows, term_height - 8)

    for i in range(display_rows):
        col1 = todo_lines[i] if i < len(todo_lines) else ""
        col2 = prog_lines[i] if i < len(prog_lines) else ""
        col3 = review_lines[i] if i < len(review_lines) else ""
        col4 = merged_lines[i] if i < len(merged_lines) else ""
        col5 = done_lines[i] if i < len(done_lines) else ""

        # Pad to col_w (accounting for ANSI codes which don't take visual space)
        col1_pad = _pad_ansi(col1, col_w)
        col2_pad = _pad_ansi(col2, col_w)
        col3_pad = _pad_ansi(col3, col_w)
        col4_pad = _pad_ansi(col4, col_w)
        col5_pad = _pad_ansi(col5, col_w)

        lines.append(f"{col1_pad} │ {col2_pad} │ {col3_pad} │ {col4_pad} │ {col5_pad}")

    # Footer
    lines.append("")
    timestamp = time.strftime("%H:%M:%S")
    footer = f"{ANSI_DIM}Updated {timestamp} — refreshes every 5s — Ctrl-C to stop{ANSI_RESET}"
    lines.append(footer)

    rendered = "\n".join(lines)
    output.write(rendered)
    output.write("\033[J")  # Clear from cursor to end of screen
    output.flush()
    return rendered + "\033[J"


def _render_column(
    items: list[BoardItem],
    col_width: int,
    colours: ColourAssigner,
) -> list[str]:
    """Render a column's items as a flat list of lines."""
    lines: list[str] = []
    for item in items:
        item_lines = _format_item(item, col_width, colours)
        lines.extend(item_lines)
        lines.append("")  # blank separator between items
    return lines


def _visible_length(s: str) -> int:
    """Return the visible length of a string, ignoring ANSI escape codes."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _pad_ansi(s: str, width: int) -> str:
    """Pad a string containing ANSI codes to a visible width."""
    visible = _visible_length(s)
    if visible >= width:
        return s
    return s + " " * (width - visible)


# ── Live monitor ──────────────────────────────────────────────────────────


def monitor_board(
    sprint: str,
    poll_interval: float = 5.0,
    output: TextIO = sys.stdout,
) -> None:
    """Poll and redraw the board until interrupted."""
    # Handle terminal resize
    def _on_resize(signum: int, frame: object) -> None:
        pass  # next poll will pick up new size

    if hasattr(signal, "SIGWINCH"):
        signal.signal(signal.SIGWINCH, _on_resize)

    # Enter alternate screen buffer
    output.write("\033[?1049h")
    output.flush()

    try:
        while True:
            # Move cursor to home position
            output.write("\033[H")
            output.flush()
            render_board(sprint, output=output)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass  # Exit gracefully
    finally:
        # Leave alternate screen buffer
        output.write("\033[?1049l")
        output.write(f"{ANSI_DIM}Board stopped.{ANSI_RESET}\n")
        output.flush()


# ── tmux launcher ─────────────────────────────────────────────────────────


def build_tmux_command(sprint: str) -> list[str]:
    """Build a ``tmux new-window -d`` command to launch the board."""
    script_path = os.path.abspath(__file__)
    shell_cmd = f"python3 {shlex.quote(script_path)} --sprint {shlex.quote(sprint)}"
    return [
        "tmux",
        "new-window",
        "-d",
        "-n",
        "scrimmage-board",
        shell_cmd,
    ]


def launch_board(sprint: str) -> subprocess.CompletedProcess[bytes]:
    """Open the scrimmage board in a detached tmux window."""
    cmd = build_tmux_command(sprint)
    return subprocess.run(cmd, check=True, capture_output=True)


# ── CLI ───────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Terminal scrimmage board — information radiator for sprint backlogs.",
    )
    parser.add_argument("--sprint", required=True, help="Sprint name to display (e.g. sprint-7)")
    parser.add_argument(
        "--tmux",
        action="store_true",
        help="Launch in a detached tmux window instead of running inline",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.tmux:
        launch_board(args.sprint)
    else:
        monitor_board(args.sprint)


if __name__ == "__main__":
    main()
