# Scrimmage Team

**NB**: The details in this file (Tech Stack, Repo Structure, etc) are specific to the particular project the Scrimmage Team is working on in this repo.

## Getting Started

Read `scrimmage/scrimmage-team.md` in this repo and follow it. If you are the only agent in your team then you are the scrimmage master (servant leader).

## Tech Stack

<!-- Customize for your project -->
- **Frontend:** React (TypeScript)
- **Backend:** Python
- **Database:** DynamoDB
- **Infrastructure:** AWS CDK (TypeScript)
- **Cloud:** AWS

## Repo Structure

<!-- Customize for your project -->
Monorepo layout:

```
/frontend    — React app
/backend     — Python services
/infra       — CDK stacks
```

## Conventions

- All infrastructure must be defined as CDK code in `/infra` — no manual AWS console changes.
- Backend code goes in `/backend` with tests alongside.
- Frontend code goes in `/frontend` with tests alongside.
- The product owner will be briefed by the user at runtime — do not assume what the product is.
- The **Product Backlog** lives in `scrimmage/backlog.db` (SQLite, WAL mode), managed via `scrimmage/backlog_db.py`. Import `get_backlog_db` to access it. The DB supports concurrent read/write by multiple agents.

## Worktree Config

Configuration for `worktree_setup.py` — parsed automatically when creating agent worktrees.

<!-- Customize: update symlinks and deps for your project -->
```yaml
symlinks:
  - scrimmage
  - infra
deps:
  - dir: backend
    cmd: pip install -e ".[dev]"
  - dir: frontend
    cmd: npm ci
```

## Local Verification Pipeline

See `scrimmage/scrimmage-team.md` § Local Verification Pipeline for the standard checks to run before requesting review.

## Model Tier Discipline

Use the right model tier for each task to balance cost and capability:

- **Haiku** — low-stakes reads and searches: grep/glob operations, reading files, running tests, linting. Use haiku subagents for anything that doesn't require reasoning.
- **Sonnet** — standard implementation: writing code, fixing bugs, writing tests, documentation. Most engineering work uses sonnet.
- **Opus** — complex reasoning only: architecture decisions, cross-cutting refactors, debugging subtle issues, coordination. SM and PO default to opus.

**Rule:** If a task can be done by a cheaper tier, use the cheaper tier. Opus agents should delegate mechanical subtasks (running tests, searching code, reading files) to haiku subagents.

## Key Process Rules

- **Never commit directly to master** from a worktree. Always use feature branches and merge via the standard workflow.
- **Deploy from main repo** — branch deploys use `scrimmage/branch_deploy.sh` from the main repo path, not from worktrees.
- **Backlog is the source of truth** — all work items, status changes, and comments go through `scrimmage/backlog_db.py`.
- **One item per agent** — each agent works on one backlog item at a time, then exits.

## Environment

- Architecture: aarch64 (ARM64) Linux container
- Python 3 available system-wide
- Node.js and npm available system-wide
- No sudo access — install Python packages with `pip install --user` or in a venv
- AWS credentials: see `scrimmage/docs/aws-credentials-setup.md` for MFA-protected temporary credential setup

## Knowledge Management

Write lessons learned to `scrimmage/notes/*.md`, NOT to Claude auto-memory (`~/.claude/`). The `scrimmage/notes/` directory is git-tracked and survives clones.

- Role-specific lessons → `scrimmage/notes/{role}.md`
- Cross-cutting issues → `scrimmage/notes/known-issues.md`
- Critical always-know-this rules → propose additions to this file (`CLAUDE.md`)

## Compaction Instructions

When auto-compaction triggers or `/compact` is used, follow these rules strictly:

### MUST re-read and follow ALL of:

- this file ./CLAUDE.md
- scrimmage/scrimmage-team.md
- ./scrimmage/notes/{role}.md matching your role. Files: `backend-engineer.md`, `frontend-engineer.md`, `cloud-engineer.md`, `integration-engineer.md`,
  `dba.md`, `product-owner.md`, `peer-reviewer.md`, `scrimmage-master.md`, `ui-ux-designer.md`, `technical-writer.md`
 - ./scrimmage/notes/known-issues.md

> MUST: After compaction, re-read every file you plan to edit before making changes. Do not rely on pre-compaction memory of file contents

### MUST Preserve (Full Detail)
1. **Most recent task exchange** - Preserve the full detail of the most recent task exchange — the current request, the last actions taken, and any pending questions or response.
2. **Current task state** - What we're actively working on, pending items, blockers
3. **All file modifications in the current task** - Every file path, what changed, and why
4. **Key code info** - Key code patterns or logic that would be non-obvious on re-read (eg,  workaround rationale, tricky conditionals).
5. **Decisions made** - Technical choices, user preferences, rejected alternatives
6. **Errors encountered** - Error messages, stack traces, and their resolutions

### MUST Summarize (Condensed)
1. **Exploration/research** - Condense to: "Searched X, found Y in Z location"
2. **File reads** - Condense to: "Read [file] - contains [key info]"
3. **Failed attempts** - Condense to: "Tried X, failed because Y"
4. **General discussion** - Extract only actionable conclusions

### MUST Include (Structured Summary Block)
```
## Session Context (Post-Compaction)
- **Sprint**: [sprint name]
- **Team**: [team name]
- **Active teammates**: [names and current tasks]
- **Role**: [role eg Backend Engineer, Frontend Engineer]
- **Team member name**: [your name e.g. Barry, Fiona]
- **Task number(s)**: [task ids in the backlog database for the issues we're working on now]
- **Worktree**: [path]
- **Branch**: [branch name]
- **Files Modified**: [list with brief descriptions]
- **Key Decisions**: [numbered list]
- **Pending Actions**: [what's left to do]
```

### Priority Order
If space is limited, preserve in this order:
1. Current task: backlog item ID, status, branch, what's been done, what remains.
2. File changes and code written
3. Decisions and user preferences
4. Error resolutions
5. Everything else as summary
