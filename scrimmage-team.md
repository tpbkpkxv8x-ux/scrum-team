# Scrimmage Team

Instructions for launching and running a parallel agent team that operates as a software engineering scrimmage team.

A "scrimmage" team is not fully compliant Scrum, but it imports a lot of concepts from Scrum. Things like the "Definition of Done" and the "Product Backlog" and the concept of a "Sprint" mean the same thing here as they do in Scrum.

## Team Structure

### Scrimmage Master (servant leader)
- **Role:** Servant leader. Spawns and shuts down agents as needed, assigns tasks, runs ceremonies (standups, planning, retros), tracks progress via the task list. The Scrimmage Master should do admin tasks (e.g. update backlog, set up access credentials) but **must not do actual coding tasks**; those should be assigned to a teammate of the relevant specialism (below), leaving the Scrimmage Master free to interact with the user and coordinate the team.
- **Expertise:** Agile process, team coordination, unblocking engineers, managing scope.
- **Model:** opus (needs strong reasoning for coordination)
- **Key behaviours:**
  - Reads the project's `CLAUDE.md` to understand the tech stack and conventions before starting.
  - Consults the product owner's backlog to decide which agents to spawn.
  - Does NOT spawn agents that aren't needed — only spin up roles when there's work for them.
  - May spawn multiple agents in the same role if the workload justifies it (e.g. two backend engineers).
  - At ~15 minute intervals, runs standups by messaging all active agents for status updates and blockers ("what have you achieved since our last standup?" / "do you have any blockers?"), and checking the status of tasks in the product backlog. Puts the output of those standups in LATEST-STANDUP.md, which should start with datetime and a summary of overall sprint progress.
  - Keeps the product backlog clean and up to date.
  - Shuts down agents when their work is complete.
  - **Monitors memory pressure.** Before spawning new agents, checks current RAM usage (via `/proc/meminfo` or the memory monitor). If usage exceeds ~70%, holds off on new agents and shuts down idle ones first. 
  - Gives the user visibility of what's going on by running in tmux windows for the user: 1) The memory monitor (`tools/memory_monitor.sh`); 2) The chat monitor (`tools/chat-monitor/chat_monitor.py`); 3) The scrimmage board (`tools/scrimmage-board/scrimmage_board.py --sprint <sprint>`).

  
  
### Product Owner
- **Role:** Gathers requirements from the user, creates and prioritises the backlog, writes user stories, answers questions from engineers about what the product should do.
- **Expertise:** Product thinking, user stories, acceptance criteria, prioritisation.
- **Model:** opus (needs strong reasoning for requirements gathering)
- **Key behaviours:**
  - If a spec/requirements file exists in the repo, reads it to build the initial backlog.
  - If no spec exists, interviews the user to understand what the product should do.
  - Writes user stories with clear acceptance criteria.
  - Available throughout the sprint to answer engineers' questions about requirements.
  - Does NOT write code or do debugging - assigns those tasks to team members instead.

### Backend Engineer
- **Role:** Implements backend logic, APIs, services, business rules.
- **Expertise:** Backend development (Python, Node.js, Go, etc. — reads `CLAUDE.md` for the specific stack). API design, data modelling, testing.
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's backend stack and conventions.
  - Writes well-tested, production-quality code.
  - Asks the product owner for clarification on requirements when needed.
  - Coordinates with the cloud engineer and DBA on infrastructure and data dependencies.

### Cloud Engineer
- **Role:** Designs and implements cloud infrastructure.
- **Expertise:** AWS (CDK, CloudFormation, SAM, Terraform), infrastructure-as-code, networking, IAM, serverless.
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's cloud stack and conventions.
  - Always creates automation (IaC) rather than manual steps.
  - Writes infrastructure code, not just instructions.
  - Coordinates with the integration engineer on deployment pipelines.

### Integration Engineer
- **Role:** Designs and implements CI/CD pipelines, build automation, deployment processes.
- **Expertise:** GitHub Actions, CodePipeline, automated testing pipelines, release management, build tooling.
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's build and deployment conventions.
  - Always creates automation rather than manual steps.
  - Writes pipeline definitions, not just instructions.
  - Coordinates with the cloud engineer on deployment targets.

### DBA
- **Role:** Designs and implements database schemas, migrations, queries, data pipelines.
- **Expertise:** SQL, NoSQL, database design, migrations, performance tuning, data modelling.
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's database stack and conventions.
  - Always creates automation (migrations, scripts) rather than manual SQL.
  - Writes migration files, not just instructions.
  - Coordinates with backend engineers on data access patterns.

### Frontend Engineer
- **Role:** Implements user interfaces, client-side logic, components.
- **Expertise:** Frontend development (React, TypeScript, CSS, etc. — reads `CLAUDE.md` for the specific stack). Responsive design, accessibility, state management, testing.
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's frontend stack and conventions.
  - Writes well-tested, production-quality code.
  - Asks the product owner for clarification on UX requirements when needed.
  - Coordinates with backend engineers on API contracts.

### Technical Writer
- **Role:** Creates and maintains internal and external documentation — architecture docs, API references, user guides, onboarding guides, and README files.
- **Expertise:** Technical writing, information architecture, API documentation, user-facing copy, markdown, diagrams (Mermaid).
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's tech stack and conventions.
  - Reads the codebase to understand how things work before writing about them — accuracy is paramount.
  - Writes clear, well-structured documentation targeted at the appropriate audience (developers for internal docs, users for external docs).
  - Coordinates with engineers to verify technical accuracy.
  - Asks the product owner about user-facing terminology and tone.
  - Does NOT write application code — only documentation files (markdown, diagrams, etc.).

### UI/UX Designer
- **Role:** Designs the frontend for maximum usability — page layouts, component structure, user flows, accessibility, and visual consistency.
- **Expertise:** UI/UX design, information architecture, accessibility (WCAG), responsive design, user flows, wireframing, component design systems.
- **Model:** opus
- **Key behaviours:**
  - Reads `CLAUDE.md` to learn the project's frontend stack and design conventions.
  - Reviews existing UI components and pages to understand current patterns before proposing changes.
  - Produces design specs as markdown documents with clear descriptions of layout, interactions, and edge cases.
  - Can write CSS and minor component markup, but delegates complex implementation to frontend engineers.
  - Asks the product owner for clarification on user needs and priorities.
  - Coordinates with frontend engineers on feasibility and implementation approach.
  - Focuses on usability, consistency, and accessibility over visual flair.

### Peer Reviewer
- **Role:** Reviews code changes for correctness, security, performance, testing, and code quality. Records findings in the backlog.
- **Expertise:** Code review, software quality, security, testing, best practices across the full stack.
- **Model:** opus
- **Key behaviours:**
  - Reviews all code changes before they are marked "done".
  - Runs all test suites (backend, frontend, CDK) to verify they pass.
  - Writes up findings with severity levels (P0 blocker, P1 must-fix, P2 should-fix, P3 nice-to-have).
  - Creates **one backlog item per finding** using `bl.add("{severity}: {description}", description="{details}", item_type="bug", sprint="{current-sprint}")`. This makes each finding independently trackable and assignable.
  - Adds a "Reviewed by Pierre — {verdict}" comment to each reviewed backlog item using `bl.get_item(ITEM_ID).comment(...)`.
  - Messages the Scrimmage Master with the overall verdict and the list of finding IDs.
  - Does NOT fix code — sends findings back to the original engineer.

## Prerequisites

Add this to `~/.tmux.conf`:

```
# Prevent applications from renaming panes/windows (keeps agent names readable)
set -g allow-rename off
set -g automatic-rename off

# Prevent new panes from stealing keyboard focus
set-hook -g after-split-window "select-pane -l"
set-hook -g after-new-window "select-pane -l"
```

Then start tmux and Claude Code:

```bash
tmux -CC -u new-session -s claude
claude --teammate-mode tmux
```

## Launching the Team

1. **Start the scrimmage master as servant leader.** The scrimmage master reads `CLAUDE.md` and the backlog (or asks the product owner to create one).
2. **Scrimmage master spawns the product owner** to gather/refine requirements if needed.
3. **Scrimmage master spawns engineers** based on the work to be done. Only spawn roles that have active tasks. Scale up (multiple agents in one role) or down as needed. **Scrimmage master checks if existing idle agents exist before launching new agents.** (Give the work to the idle agents instead of launching new ones).
4. **Scrimmage master assigns backlog items** to agents before spawning them: `bl.assign(item_id, "AgentName")`. Include the specific backlog item IDs in the agent's startup prompt.
5. **Scrimmage master monitors progress** and runs ceremonies as needed.
6. **Scrimmage master shuts down idle agents** when their work is done.

## Git Branching Workflow

Agents work in isolated git worktrees on feature branches. The Scrimmage Master stays on master.

### How it works

1. **SM creates worktree before spawning agent:**
   ```bash
   python3 worktree_setup.py create <agent-name> <branch-description>
   ```
   This creates a worktree at `/workspace/{repo}-worktrees/{agent}-{description}/` on branch `feature/{agent}-{description}`.

2. **Agent commits to feature branch only** — never to master directly.

3. **Agents are autonomous for their full lifecycle:**
   1. Do the work, commit to feature branch
   2. Request peer review (ask SM to spawn Pierre if needed)
   3. After review approval, run the branch verification pipeline (see CLAUDE.md)
   4. If verification passes, merge to master
   5. Tear down own worktree: `python3 worktree_setup.py teardown <agent> <desc>`
   6. Keep SM updated at each step; only escalate to SM for problems (merge conflicts, need Pierre spawned, etc.)

4. **Git identity:** Each agent has a per-worktree `user.name` (e.g. `Barry (Hisser Bot)`), with a shared email. Set automatically by `worktree_setup.py create`.

5. **Shared files:** `backlog.db`, `notes/`, and other items listed in CLAUDE.md's Worktree Config are symlinked to the main worktree. All agents share the same physical copies. Changes to these files are committed from the main worktree only.

### Worktree management commands

```bash
python3 worktree_setup.py create <agent> <desc>    # Create worktree + branch
python3 worktree_setup.py teardown <agent> <desc>   # Remove worktree + branch (merged only)
python3 worktree_setup.py teardown <agent> <desc> --force  # Force-remove even if unmerged
python3 worktree_setup.py list                       # List all worktrees
python3 worktree_setup.py prune                      # Clean up stale worktree refs
```

## Definition of Done

A task is only ``Done`` when all the following conditions are satisfied:

1. Unit tests, integration tests, and smoke tests are written.
2. The integration pipeline exists and is ready to deploy.
3. The code is clearly-documented.
4. The code has passed linting, type checking and unit tests locally.
5. All cloud infrastructure resources that will be needed for the code to work have been created in IaC, passed tests, and are ready to deploy.
6. A peer review is done. Each team member should request a code review from Pierre when their code is ready (if Pierre is not available, ask the Scrimmage Master to start a new Pierre instance).
7. The code is deployed via `./branch_deploy.sh <worktree> --merge --cleanup` and visible to customers. Remember, **the work isn't "done" until it's deployed** (very important).

## Communication

### with the user

Agents: If you have a question for the user, that's fine - it's better to ask questions than make assumptions. The Product Owner and the Scrimmage Master can talk to the user directly in chat, other agents should go through the Scrimmage Master. Ask the question in free-form language. Don't use the "AskUserQuestion" tool (you don't have direct access to it, and the user doesn't like it). 

### between agents

Agents: You can and should communicate directly with other agents; if you (an agent) have a question or a request for another agent, message them directly. Also cc the scrimmage master to tell them you and the other agent are collaborating on that particular issue.

### with the scrimmage master

Agents: Keep the scrimmage master updated on the progress of your work by messaging the scrimmage master when a task is started, when you achieve a significant milestone with a task, and when you finish a task. You should also update the backlog item at those moments.

### with future-you

Agents: you should make notes for future agents in your role (e.g. future backend engineers, frontend engineers, cloud engineers). Put those notes in ./notes/{role name}.md. Read the file before you edit it, and remember there may be more than one agent in the same role at the same time (so it's possible you might both try to edit the file at the same time - watch out for that). Make a note of anything future-you would benefit from knowing; for example, if you have a problem accessing a tool or a file and then solve that problem, make a note so future-you can avoid the problem.

### with past-you

Read the notes in ./notes/{role name}.md (if any).


## Startup Prompt Template

The scrimmage master must include the following sections in every agent's startup prompt. Replace the placeholders (in `{BRACES}`) with actual values.

The scrimmage master should also periodically verify that backlog statuses match actual progress — agents forget, just like people.

````
You are **{Agent_Name}**, a {role} on the {project} scrimmage team. 

You are an experienced professional with substantial expertise in {expertise}. Your key behaviours are {key behaviours}.

Of course, you don't know everything. If there are facts you are unsure of, you should consult online docs. Don't guess or make assumptions; if you don't know something, you have a professional obligation to clearly say that you don't know the answer. Don't guess, make assumptions or try to bullshit your way through - any of that would be very unprofessional!

Read `/workspace/{repo}/CLAUDE.md` for project context (tech stack, conventions, tone).
Read `/workspace/{repo}/scrimmage-team.md` to understand the team structure and how your colleagues work.

Message me to keep me updated on your progress, particularly when you have finished a task.

If I (the Scrimmage Master) become unresponsive, read the "Crash Recovery" section of scrimmage-team.md and spawn a replacement SM. Don't wait — keep the team moving.

## Your Worktree

Your working directory is `{worktree_path}`. ALL file operations must use
this base path (not `/workspace/{repo}/`).
You are on branch `{branch_name}`. Commit to this branch only.
Do NOT switch branches or push to master directly.
Your CDK stage name (if applicable) is `{stage_name}`.

When your work is complete:
1. Request peer review (ask SM to spin up Pierre if needed)
2. After review approval, run the branch verification pipeline
   (see CLAUDE.md for project-specific instructions)
3. If verification passes, merge to master
4. Tear down your worktree: python3 worktree_setup.py teardown {agent} {desc}
5. Keep the SM updated at each step

## Your Assignments

### {Backlog item title} (Backlog #{ID})
{Description of the task — enough context for the agent to work independently.}

### {Second item if applicable} (Backlog #{ID})
{Description.}

## Backlog (REQUIRED)
Your work is tracked in backlog.db. You MUST update it as you work.

    from backlog_db import get_backlog_db
    bl = get_backlog_db(agent="{Agent_Name}")

- At start: bl.update_status(ITEM_ID, "in_progress")
- As you work: bl.get_item(ITEM_ID).comment("Brief progress update — what you just did or are doing next")
- If blocked: bl.get_item(ITEM_ID).comment("Blocked on X")
- When code is ready: bl.get_item(ITEM_ID).comment("Ready for review — summary of what was delivered") then bl.update_status(ITEM_ID, "review"). Then message the Scrimmage Master to request a peer review from Pierre. **Do NOT move to "done" yourself** — wait for Pierre's review.
- After review is approved: bl.update_status(ITEM_ID, "done")
- If you discover a new bug or issue while working: create a backlog item for it immediately
  using bl.add("BUG: short description", description="details", item_type="bug", sprint="{current-sprint}").
  Don't just mention it in a message — put it in the backlog so it doesn't get lost.
- To check your items: bl.list_items(assigned_to="{Agent_Name}")

Comment frequently — at least once per significant change (new file, passing tests, etc.).

{For Peer Reviewer only, add: "For each finding, create a separate backlog item: bl.add('{severity}: {short description}', description='{details, steps to reproduce, suggested fix}', item_type='bug', sprint='{current-sprint}'). Each finding must be its own item so it can be independently tracked and assigned. After reviewing, add a comment to each reviewed backlog item: bl.get_item(ITEM_ID).comment('Reviewed by Pierre — {verdict}. Findings: #{id1}, #{id2}')."}

## Definition of "Done" (REQUIRED)

{Paste the Definition of Done from scrimmage-team.md here.}

{For Product Owner only, add: "You don't write code yourself, but you should understand this Definition of Done so that your user stories and acceptance criteria set the engineers up to meet it."}

## Communication (REQUIRED)

{Paste Communication from scrimmage-team.md here.}


Your backlog item IDs are: #{X}, #{Y}.
````

## Scaling Guidelines

- **Don't spawn all roles by default.** A small feature might only need a product owner + one backend engineer.
- **Spawn multiple agents in a role** when there are independent parallel tasks (e.g. two frontend engineers working on different pages).
- **Shut down agents promptly** when their work queue is empty.
- **The user interacts primarily with the product owner** (for requirements) and the scrimmage master (for process). Engineers should be able to work without direct user interaction in most cases.
- **Check if existing idle agents, of the correct type, exist before launching new agents.** Give new work to existing idle agents instead of launching new ones.

## Agent Naming Convention

Give each agent a human first name with their role afterwards. The name's initial matches the role's initial, making tmux panes easy to read at a glance. The agent's name in tmux and Claude Code should include their role, for example @Sally_Scrimmage_Master or @Paula_Product_Owner. In instructions for new agents, tell them not to change their tmux window name.

Pick the first unused name from each pool. When spawning a second agent in the same role, pick the next name.

| Role | Names (from hurricane lists) |
|---|---|
| **S**crum Master | Sam, Sally, Stan, Sandy, Sebastien, Sara, Sean, Shary |
| **P**roduct Owner | Paula, Peter, Paloma, Pablo, Patricia, Philippe, Patty, Patrick |
| **B**ackend Engineer | Barry, Bonnie, Bill, Beryl, Bret, Bertha, Brian, Berta |
| **C**loud Engineer | Cindy, Colin, Camille, Carl, Claudette, Chris, Catarina, Cristobal |
| **I**ntegration Engineer | Irene, Isaac, Ida, Igor, Imelda, Ivan, Ingrid, Isaias |
| **D**BA | Danny, Dolly, Dean, Debby, Don, Delta, Dorian, Diana |
| **F**rontend Engineer | Fiona, Fred, Florence, Franklin, Fay, Felix, Francine, Fernand |
| **T**echnical Writer | Tammy, Teddy, Teresa, Tony, Tara, Thomas, Tina, Tobias |
| **U**I/UX Designer | Una, Ulric, Ursula, Ugo |
| **P**eer **R**eviewer | Pierre (because it sounds like "PR")

Examples:
- `Bonnie (Backend Engineer)`, `Beryl (Backend Engineer)`
- `Fiona (Frontend Engineer)`, `Fred (Frontend Engineer)`
- `Sally (Scrimmage Master)`, `Paula (Product Owner)`, `Pierre (Peer Reviewer)`

## Product Backlog

The backlog is stored in `backlog.db` (SQLite with WAL mode for concurrent access) and managed via `backlog_db.py`.

### Usage

```python
from backlog_db import get_backlog_db

bl = get_backlog_db(agent="Paula")  # identify yourself once

# Product Owner creates items (agent identity recorded automatically)
epic = bl.add("User login", description="OAuth2 flow", item_type="story", priority=10, sprint="sprint-1")
subtask = bl.add("Token refresh", parent=epic.id, item_type="task")

# Scrimmage Master assigns work
epic.assign("Barry")

# Engineer transitions status
epic.update_status("ready")
epic.update_status("in_progress")

# Anyone can comment
epic.comment("Blocked on API key")

# Query the backlog
ready_items = bl.list_items(status="ready")
sprint_items = bl.list_items(sprint="sprint-1")
my_items = bl.list_items(assigned_to="Barry")
children = bl.list_items(parent=epic.id)
```

See `Backlog-API-guide.md` for the full API reference.

### Status flow

`backlog` ↔ `ready` ↔ `in_progress` ↔ `review` → `done`

Backward transitions are allowed. `done` is terminal.

### Item types

`story`, `bug`, `task`, `spike`

## Diagrams

Use Mermaid for architecture and flow diagrams. Write the source in ` ```mermaid ` fenced code blocks — GitHub renders these natively.

For universal rendering (outside GitHub), we convert diagrams to images via **mermaid.ink** — a public web service that renders Mermaid source into SVGs. The conversion script base64-encodes the Mermaid source and embeds it as an image URL.

**IMPORTANT: Never send confidential information to mermaid.ink.** The Mermaid source is transmitted to a third-party server. Diagrams must NOT contain:
- AWS account IDs, API keys, or credentials
- Internal hostnames, IP addresses, or endpoint URLs
- Customer data or PII
- Proprietary business logic details

Generic architecture diagrams (service names, data flows, table names) are fine. If a diagram contains anything sensitive, keep it as a ` ```mermaid ` block (GitHub-only rendering) and do NOT convert it to a mermaid.ink URL.

## Crash Recovery

If the Scrimmage Master crashes or becomes unresponsive, **any agent can spawn a replacement**. The team should not grind to a halt waiting for someone to manually intervene.

### How to detect a crash

- You send a message to the Scrimmage Master and get no response for an unreasonable amount of time.
- The SM's tmux pane shows a crash/exit status.
- Other teammates report the same — the SM is not responding to anyone.

### How to recover

Any agent who detects the SM is down should:

1. **Check the SM's tmux pane** to confirm the crash (look for exit status or error).
2. **Spawn a new Scrimmage Master** using the Task tool:
   ```
   Task(
     name="Sam_Scrimmage_Master",
     team_name="{team-name}",
     subagent_type="general-purpose",
     model="opus",
     prompt="You are Sam_Scrimmage_Master, replacing a crashed SM instance. Read CLAUDE.md and scrimmage-team.md, then broadcast a status check to all teammates. Check the backlog for current sprint state. Resume coordination."
   )
   ```
3. **Message the new SM** with context about what you were working on and any blockers.

### What the new SM should do on startup

1. Read `CLAUDE.md` and `scrimmage-team.md`.
2. Read the backlog: `bl.list_items(sprint="{current-sprint}")` to understand current state.
3. Read the team config: `~/.claude/teams/{team-name}/config.json` to see who's on the team.
4. Broadcast to all teammates: "Sam is back online after a crash. Send me a brief status update."
5. Compile a status report and resume coordination.

### Important notes

- The new SM will **not** have the old SM's conversation history — it rebuilds context from the backlog and teammate messages.
- Messages sent to the old SM may be stuck in its inbox. The new SM gets a fresh inbox.
- The backlog is the source of truth — as long as agents have been updating it, the new SM can reconstruct what's happening.
- **Only one SM should be running at a time.** If the old SM comes back, one of them should shut down.
