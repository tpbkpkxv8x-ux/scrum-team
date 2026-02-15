#!/usr/bin/env python3
"""
Git worktree manager for scrimmage team agents.

Creates isolated worktrees with shared symlinked resources, per-agent git
config, and automatic dependency installation — so each agent can slither
through code on its own branch without stepping on another snake's tail.

Usage:
    python3 worktree_setup.py create <agent-name> <branch-description>
    python3 worktree_setup.py teardown <agent-name> <branch-description> [--force]
    python3 worktree_setup.py list
    python3 worktree_setup.py prune
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Utility: stage-name derivation (importable)
# ---------------------------------------------------------------------------

def derive_stage_name(branch_name: str) -> str:
    """Derive a short stage name from a branch name.

    Strips the ``feature/`` prefix, replaces non-alphanumeric characters with
    hyphens, lowercases, and truncates to 20 characters.

    >>> derive_stage_name("feature/barry-add-feed")
    'barry-add-feed'
    >>> derive_stage_name("feature/CINDY-Long-Infrastructure-Setup-Name")
    'cindy-long-infrastru'
    """
    name = re.sub(r"^feature/", "", branch_name)
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return name[:20]


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class DepSpec(NamedTuple):
    dir: str
    cmd: str


class WorktreeConfig(NamedTuple):
    symlinks: list[str]
    deps: list[DepSpec]


def _find_repo_root() -> Path:
    """Return the root of the current git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def _parse_worktree_config(claude_md: Path) -> WorktreeConfig:
    """Parse the ``## Worktree Config`` YAML-like section from CLAUDE.md.

    We do simple line-by-line parsing so we don't need PyYAML.
    """
    if not claude_md.exists():
        return WorktreeConfig(symlinks=[], deps=[])

    text = claude_md.read_text()

    # Find the section
    match = re.search(r"^## Worktree Config\s*\n", text, re.MULTILINE)
    if not match:
        return WorktreeConfig(symlinks=[], deps=[])

    # Extract lines until the next heading or end of file
    section_start = match.end()
    next_heading = re.search(r"^## ", text[section_start:], re.MULTILINE)
    if next_heading:
        section_text = text[section_start : section_start + next_heading.start()]
    else:
        section_text = text[section_start:]

    # Strip code fences if present
    section_text = re.sub(r"^```[a-z]*\s*\n", "", section_text)
    section_text = re.sub(r"\n```\s*$", "", section_text)

    lines = section_text.splitlines()

    symlinks: list[str] = []
    deps: list[DepSpec] = []

    current_key: str | None = None
    current_dep_dir: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Top-level keys
        if line.startswith("symlinks:"):
            current_key = "symlinks"
            current_dep_dir = None
            continue
        if line.startswith("deps:"):
            current_key = "deps"
            current_dep_dir = None
            continue

        # List items
        if current_key == "symlinks" and line.startswith("- "):
            symlinks.append(line[2:].strip())
            continue

        if current_key == "deps":
            if line.startswith("- dir:"):
                current_dep_dir = line.split(":", 1)[1].strip()
                continue
            if line.startswith("dir:"):
                current_dep_dir = line.split(":", 1)[1].strip()
                continue
            if line.startswith("cmd:") and current_dep_dir is not None:
                cmd = line.split(":", 1)[1].strip()
                deps.append(DepSpec(dir=current_dep_dir, cmd=cmd))
                current_dep_dir = None
                continue

    return WorktreeConfig(symlinks=symlinks, deps=deps)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run_git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command, returning the CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        capture_output=True, text=True, check=check, cwd=cwd,
    )


def _branch_exists(branch: str, cwd: Path | None = None) -> bool:
    result = _run_git("rev-parse", "--verify", branch, cwd=cwd, check=False)
    return result.returncode == 0


def _worktree_exists(worktree_dir: Path) -> bool:
    """Check if a worktree is registered at the given path."""
    result = _run_git("worktree", "list", "--porcelain")
    return f"worktree {worktree_dir}" in result.stdout


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root()
    repo_name = repo_root.name

    agent = args.agent_name
    description = args.branch_description
    branch = f"feature/{agent}-{description}"
    worktree_dir = Path(f"/workspace/{repo_name}-worktrees/{agent}-{description}")
    stage_name = derive_stage_name(branch)

    # --- Guard: worktree already exists ---
    if worktree_dir.exists():
        print(f"Error: worktree directory already exists at {worktree_dir}", file=sys.stderr)
        sys.exit(1)

    # --- Guard: branch already exists ---
    if _branch_exists(branch):
        print(f"Error: branch '{branch}' already exists", file=sys.stderr)
        sys.exit(1)

    # --- Read config ---
    config = _parse_worktree_config(repo_root / "CLAUDE.md")

    # --- Create worktree from current HEAD of master ---
    print(f"Creating worktree at {worktree_dir} on branch {branch} ...")
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_git("worktree", "add", "-b", branch, str(worktree_dir), "master")

    # --- Symlink shared files/dirs ---
    for item in config.symlinks:
        wt_path = worktree_dir / item
        main_path = repo_root / item

        # skip-worktree in the new worktree so git ignores local changes
        _run_git("update-index", "--skip-worktree", item, cwd=worktree_dir, check=False)

        # Remove the checked-out copy
        if wt_path.is_dir():
            # Remove directory tree
            subprocess.run(["rm", "-rf", str(wt_path)], check=True)
        elif wt_path.exists() or wt_path.is_symlink():
            wt_path.unlink()

        # Create symlink: worktree path → main worktree path (relative)
        rel_path = os.path.relpath(main_path, wt_path.parent)
        wt_path.symlink_to(rel_path)
        print(f"  Symlinked {item} → {rel_path}")

    # --- Per-agent git config ---
    project_name = repo_name.replace("-", " ").title().replace(" ", "")
    agent_display = agent.replace("-", " ").title().replace(" ", "_")
    _run_git("config", "user.name", f"{agent_display} ({project_name} Bot)", cwd=worktree_dir)
    print(f"  Git user.name = \"{agent_display} ({project_name} Bot)\"")

    # --- Dependency installation ---
    for dep in config.deps:
        dep_dir = worktree_dir / dep.dir
        if dep_dir.is_dir():
            print(f"  Installing deps in {dep.dir}: {dep.cmd}")
            result = subprocess.run(
                dep.cmd, shell=True, cwd=dep_dir,
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  Warning: dep install failed in {dep.dir}:\n{result.stderr}", file=sys.stderr)
        else:
            print(f"  Skipping deps for {dep.dir} (directory not found)")

    # --- Summary ---
    print()
    print("=== Worktree Created ===")
    print(f"  Path:       {worktree_dir}")
    print(f"  Branch:     {branch}")
    print(f"  Stage name: {stage_name}")
    print()


def cmd_teardown(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root()
    repo_name = repo_root.name

    agent = args.agent_name
    description = args.branch_description
    branch = f"feature/{agent}-{description}"
    worktree_dir = Path(f"/workspace/{repo_name}-worktrees/{agent}-{description}")

    if not worktree_dir.exists() and not _worktree_exists(worktree_dir):
        print(f"Error: worktree not found at {worktree_dir}", file=sys.stderr)
        sys.exit(1)

    # Remove worktree
    print(f"Removing worktree at {worktree_dir} ...")
    result = _run_git("worktree", "remove", str(worktree_dir), check=False)
    if result.returncode != 0:
        if args.force:
            print("  Forcing removal ...")
            _run_git("worktree", "remove", "--force", str(worktree_dir))
        else:
            print(f"Error: could not remove worktree: {result.stderr.strip()}", file=sys.stderr)
            print("  Use --force to force removal.", file=sys.stderr)
            sys.exit(1)

    # Delete branch
    if _branch_exists(branch):
        flag = "-D" if args.force else "-d"
        print(f"Deleting branch {branch} ({flag}) ...")
        result = _run_git("branch", flag, branch, check=False)
        if result.returncode != 0:
            print(f"Warning: could not delete branch: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(f"  Branch {branch} does not exist, skipping.")

    print("Teardown complete.")


def cmd_list(_args: argparse.Namespace) -> None:
    result = _run_git("worktree", "list")
    print(result.stdout)


def cmd_prune(_args: argparse.Namespace) -> None:
    print("Pruning stale worktrees ...")
    result = _run_git("worktree", "prune")
    if result.stdout:
        print(result.stdout)
    print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Git worktree manager for scrimmage team agents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new agent worktree")
    p_create.add_argument("agent_name", help="Agent name (e.g. barry, cindy)")
    p_create.add_argument("branch_description", help="Short branch description (e.g. add-feed)")
    p_create.set_defaults(func=cmd_create)

    # teardown
    p_teardown = subparsers.add_parser("teardown", help="Remove an agent worktree")
    p_teardown.add_argument("agent_name", help="Agent name")
    p_teardown.add_argument("branch_description", help="Branch description used during create")
    p_teardown.add_argument("--force", action="store_true", help="Force remove even with uncommitted changes")
    p_teardown.set_defaults(func=cmd_teardown)

    # list
    p_list = subparsers.add_parser("list", help="List all worktrees")
    p_list.set_defaults(func=cmd_list)

    # prune
    p_prune = subparsers.add_parser("prune", help="Prune stale worktrees")
    p_prune.set_defaults(func=cmd_prune)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
