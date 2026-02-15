# Scrimmage Team

Instructions for launching and running a parallel agent team that operates as a software engineering scrimmage team.

A "scrimmage" team is not fully compliant Scrum, but it imports a lot of concepts from Scrum. Things like the "Definition of Done" and the "Product Backlog" and the concept of a "Sprint" mean the same thing here as they do in Scrum.

## Team Structure

**All agents must** read the project's `CLAUDE.md` on startup to learn the tech stack, conventions, and repo structure.

### Scrimmage Master (servant leader)
- **Role:** Servant leader. Spawns and shuts down agents as needed, assigns tasks, runs ceremonies (standups, planning, retros), tracks progress via the task list. The Scrimmage Master should do admin tasks (e.g. update backlog, set up access credentials) but **must not do actual coding tasks**; those should be assigned to a teammate of the relevant specialism (below), leaving the Scrimmage Master free to interact with the user and coordinate the team.
- **Expertise:** Agile process, team coordination, unblocking engineers, managing scope.
- **Model:** opus (needs strong reasoning for coordination)

### Product Owner
- **Role:** Gathers requirements from the user, creates and prioritises the backlog, writes user stories, answers questions from engineers about what the product should do.
- **Expertise:** Product thinking, user stories, acceptance criteria, prioritisation.
- **Model:** opus (needs strong reasoning for requirements gathering)

### Backend Engineer
- **Role:** Implements backend logic, APIs, services, business rules.
- **Expertise:** Backend development (Python, Node.js, Go, etc.). API design, data modelling, testing.
- **Model:** sonnet

### Cloud Engineer
- **Role:** Designs and implements cloud infrastructure.
- **Expertise:** AWS (CDK, CloudFormation, SAM, Terraform), infrastructure-as-code, networking, IAM, serverless.
- **Model:** sonnet

### Integration Engineer
- **Role:** Designs and implements CI/CD pipelines, build automation, deployment processes.
- **Expertise:** GitHub Actions, CodePipeline, automated testing pipelines, release management, build tooling.
- **Model:** sonnet

### DBA
- **Role:** Designs and implements database schemas, migrations, queries, data pipelines.
- **Expertise:** SQL, NoSQL, database design, migrations, performance tuning, data modelling.
- **Model:** sonnet

### Frontend Engineer
- **Role:** Implements user interfaces, client-side logic, components.
- **Expertise:** Frontend development (React, TypeScript, CSS, etc.). Responsive design, accessibility, state management, testing.
- **Model:** sonnet

### Technical Writer
- **Role:** Creates and maintains internal and external documentation — architecture docs, API references, user guides, onboarding guides, and README files.
- **Expertise:** Technical writing, information architecture, API documentation, user-facing copy, markdown, diagrams (Mermaid).
- **Model:** sonnet

### UI/UX Designer
- **Role:** Designs the frontend for maximum usability — page layouts, component structure, user flows, accessibility, and visual consistency.
- **Expertise:** UI/UX design, information architecture, accessibility (WCAG), responsive design, user flows, wireframing, component design systems.
- **Model:** sonnet

### Peer Reviewer
- **Role:** Reviews code changes for correctness, security, performance, testing, and code quality. Records findings in the backlog.
- **Expertise:** Code review, software quality, security, testing, best practices across the full stack.
- **Model:** opus

## Agent Workflow

Each agent handles **one backlog item**, then writes a handoff comment and exits. If more work remains, SM spawns a fresh agent with a clean context window.

> **Shutdown triggers** — these are interrupts that can fire at any phase:
>
> - **Normal**: Task complete — item moved to `merged`, SM informed, handoff comment written.
> - **Proactive**: Context window below 20% remaining — write handoff comment, inform SM, and exit *before* compaction loses state.
> - **SM-initiated**: Agent running > 45 minutes with no progress (no commits, no backlog comments), or system memory > 70%. SM shuts down idle agents when their work queue is empty.
> - **Blocked**: Dependency not met — write handoff comment noting the blocker, inform SM, exit. SM respawns when dependency merges.
>
> On any non-normal exit: write a handoff comment on the backlog item, update `notes/{role}.md` and `notes/known-issues.md`, tear down your worktree (`--force` if the branch was never merged), inform SM, then shut down.

### Phase 1: Orient

1. Read your role notes (`notes/{role}.md`), `notes/known-issues.md`, and any existing comments on your assigned backlog item.
2. Verify your file ownership scope (listed in your startup prompt).
3. Message SM that you are starting; move the backlog item to `in_progress`.

### Phase 2: Set Up Worktree

1. Create a worktree:
   ```bash
   python3 worktree_setup.py create <agent-name> <branch-description>
   ```
   This creates a worktree at `/workspace/{repo}-worktrees/{agent}-{description}/` on branch `feature/{agent}-{description}`.
2. All subsequent work happens inside the worktree path. `cd` into it now.
3. **Git identity** is set automatically by `worktree_setup.py`.
4. **Shared files** (`backlog.db`, `notes/`, and other items listed in CLAUDE.md's Worktree Config) are symlinked to the main worktree — all agents share the same physical copies. Changes to these files are committed from the main worktree only.

### Phase 3: Plan or Execute

**Path A — Planning agent** (non-trivial: 4+ files, needs investigation, cross-cutting concerns, no existing pattern):

1. Explore the codebase, write a plan to `notes/plans/{item-id}-plan.md`.
2. Write a handoff comment on the backlog item summarising the plan.
3. Jump to **Phase 8** — tear down the worktree with `--force` (no merge needed for a plan-only agent).

**Path B — Executing agent** (well-scoped task, or executing an existing plan):

1. If a plan file exists (`notes/plans/{item-id}-plan.md`), read it first. If the plan is wrong, write a handoff comment explaining why and exit — SM spawns a new planning agent to revise.
2. Implement on the feature branch — **never commit directly to master**.
3. Write tests and document code as you go.
4. Post progress comments on the backlog item at milestones (e.g. "core logic done, starting tests").
5. Continue to **Phase 4**.

### Phase 4: Local Verification

Run checks only for the areas you touched:

**Backend:**
```bash
cd <worktree-path>/backend
python3 -m ruff check .
python3 -m pytest tests/ -v
```

**Frontend:**
```bash
cd <worktree-path>/frontend
npx tsc --noEmit
npx vitest run
```

**CDK / Infrastructure:**
```bash
cd <worktree-path>/infra
npx jest
```

Fix any failures before proceeding.

### Phase 5: Rebase Check

1. Check if master has advanced since you branched:
   ```bash
   git fetch origin master
   git rev-list HEAD..origin/master --count
   ```
2. If the count is greater than 0, rebase:
   ```bash
   git rebase origin/master
   ```
3. **After every rebase** (whether or not there were conflicts), check for collateral damage:
   ```bash
   git diff --stat origin/master..HEAD
   ```
   Look for unexpected changes — especially deletions outside your file ownership scope. If files in `notes/`, `tools/`, or `.claude/` are deleted or replaced with symlinks, your rebase went wrong. Run `git rebase --abort` and ask SM for help.
4. If the rebase produced conflicts and you resolved them, re-run **Phase 4** to verify nothing broke.
5. **Stuck rebase** (can't resolve conflicts within 5 minutes):
   ```bash
   git rebase --abort
   ```
   Write a handoff comment noting the conflict, inform SM then exit → **Phase 8**.

### Phase 6: Request Review

1. Verify all **Definition of Done** criteria are met (see below).
2. Move the backlog item to `review`.
3. Write a structured handoff comment summarising the change.
4. Message SM to spawn Pierre (Peer Reviewer).
5. Address any review findings — if you make changes, re-run **Phase 4** before continuing.

### Phase 7: Merge & Ship

1. **Second rebase check** — master may have advanced during review:
   ```bash
   git fetch origin master
   git rebase origin/master
   ```
   Re-run **Phase 4** if conflicts were resolved.
2. Merge and push:
   ```bash
   cd <worktree-path>
   git checkout master && git pull origin master
   git merge <feature-branch>
   git push origin master
   ```
   The push triggers the CI/CD pipeline (CI/CD pipeline handles deployment), which deploys to AWS and runs e2e smoke tests.
3. Move the backlog item to `merged`. (SM will later move `merged` → `done` after verifying the deployment is live.)


### Phase 8: Cleanup & Exit

1. Tear down the worktree:
   ```bash
   python3 worktree_setup.py teardown <agent-name> <branch-description>          # merged branches
   python3 worktree_setup.py teardown <agent-name> <branch-description> --force   # unmerged branches (plan-only, blocked, stuck rebase)
   ```
2. Update `notes/{role}.md` and `notes/known-issues.md` with lessons learned during the task.
3. Write a structured handoff comment on the backlog item (if not already written):

       Handoff: {status — e.g. "code complete, tests passing, awaiting review"}
       Done: {brief description of completed work, key files changed}
       Decisions: {architecture choices, trade-offs}

4. Shut down.

## Definition of Done

A task is only `Done` when **all** of the following are satisfied:

1. Unit tests, integration tests, and smoke tests are written (Phase 3).
2. The code has passed linting, type checking, and unit tests locally (Phase 4).
3. All cloud infrastructure resources needed for the code to work have been created in IaC, passed tests, and are ready to deploy (Phase 4).
4. The code is clearly documented (Phase 3).
5. A peer review is done — request from Pierre; if unavailable, ask SM to spawn a new instance (Phase 6).
6. The code is merged to master and pushed. CI/CD handles deployment to AWS (Phase 7).

## Communication

### With the user

If you have a question for the user, that's fine — it's better to ask questions than make assumptions. The Product Owner and the Scrimmage Master can talk to the user directly in chat; other agents should go through the Scrimmage Master. Ask the question in free-form language. Don't use the "AskUserQuestion" tool (you don't have direct access to it, and the user doesn't like it).

### Between agents

You can and should communicate directly with other agents. If you have a question or a request for another agent, message them directly. Also cc the scrimmage master to tell them you and the other agent are collaborating on that particular issue.

### With the scrimmage master

Keep the scrimmage master updated on the progress of your work by messaging them when a task is started, when you achieve a significant milestone, and when you finish. Update the backlog item at those same moments.

## Knowledge Management

Agents maintain three types of shared knowledge. All are symlinked across worktrees, so every agent sees the same files.

### Role notes (`notes/{role}.md`)

Each role has a shared notes file (e.g. `notes/backend-engineer.md`, `notes/frontend-engineer.md`). Use it to record anything a future agent in your role would benefit from knowing — solved problems, access quirks, codebase gotchas, patterns.

- **Read your role notes on startup** before starting work.
- **Write to them throughout your work**, not just at handoff.
- Multiple agents in the same role may edit the file concurrently — read before editing and watch for conflicts.

### Known issues (`notes/known-issues.md`)

Shared across all roles. If you discover a non-obvious issue (something that took you >5 minutes to figure out, or that other agents might hit), add it **IMMEDIATELY** — don't wait until handoff.

## Context managment

Each agent has only a limited amount of context window; each agent MUST take responsibility for using that context window wisely. Some CLI commands (such as running tests) can generate a lot of low-signal text, which uses a lot of context window. Don't run those CLI commands yourself, get a haiku or sonnet agent to run them for you (so your context window isn't used up).

## Worktree management commands

```bash
python3 worktree_setup.py create <agent> <desc>    # Create worktree + branch
python3 worktree_setup.py teardown <agent> <desc>   # Remove worktree + branch (merged only)
python3 worktree_setup.py teardown <agent> <desc> --force  # Force-remove even if unmerged
python3 worktree_setup.py list                       # List all worktrees
python3 worktree_setup.py prune                      # Clean up stale worktree refs
```

## Product Backlog

The backlog is stored in `./backlog.db` (SQLite with WAL mode for concurrent access) and managed via `./backlog_db.py`.

### Usage

```python
from backlog_db import get_backlog_db

bl = get_backlog_db(agent="Paula")  # identify yourself once

# Product Owner creates items (agent identity recorded automatically)
epic = bl.add("User login", description="OAuth2 flow", item_type="story", priority=10, sprint="sprint-1")
subtask = bl.add("Token refresh", parent=epic.id, item_type="task")

# Scrimmage Master assigns work
epic.assign("Barry")

# Engineer gets info on the assigned work
bl.get_history(<item_id>)

# Engineer transitions status
bl.update_status(<item_id>, "ready")
bl.update_status(<item_id>, "in_progress")

# Anyone can comment
bl.comment(<item_id>, "Blocked on API key")

# Query the backlog
ready_items = bl.list_items(status="ready")
sprint_items = bl.list_items(sprint="sprint-1")
my_items = bl.list_items(assigned_to="Barry")
children = bl.list_items(parent=epic.id)
```

See `Backlog-API-guide.md` for the full API reference.

### Status flow

`backlog` ↔ `ready` ↔ `in_progress` ↔ `review` → `merged` → `done`

- **`merged`** = code is on master branch.
- **`done`** = confirmed deployed and working in production.
- `review` can go directly to `done` (skipping `merged`), but the recommended flow is through `merged`.
- `merged` can go back to `in_progress` if rework is needed.
- Backward transitions are allowed except out of `done`. **`done` is terminal.**
- Who moves `merged` → `done`: SM, after verifying the deployment is live and working.

### Item types

`story`, `bug`, `task`, `spike`

> See `notes/scrimmage-master.md` § Agent Naming Convention.

## Diagrams

If you need to create documentation with diagrams, see [`docs/diagrams-howto.md`](docs/diagrams-howto.md) for conventions and security guidelines.
