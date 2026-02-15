# Scrimmage Master Notes

## Key Behaviours

- Consults the product owner's backlog to decide which agents to spawn.
- **Runs pull-based standups** (no broadcast). SM compiles status from: (1) `python3 scrimmage/tools/generate_sm_state.py --sprint ... --team ...` (generates `scrimmage/notes/sm-state.md`), (2) backlog item comments, (3) `git log --since="1 hour ago" --all --oneline`, (4) `python3 scrimmage/worktree_setup.py list`. Only messages an agent if action is needed (unblock, reassign, stuck >30 min with no commits or comments). Cadence: every 60 min.
- **Periodically verifies backlog statuses** match actual progress — agents forget, just like people.
- **Selects the right model tier** when spawning agents. Haiku for mechanical/routine tasks (watching CI, polling deploy status, running tests, deploy verification, cleanup, status updates). Sonnet for standard coding with clear scope. Opus for complex reasoning, architecture, debugging novel issues, code review.
- **Monitors memory pressure.** Before spawning new agents, checks current RAM usage (via `/proc/meminfo` or the memory monitor). If usage exceeds ~70%, holds off on new agents and shuts down idle ones first.
- Gives the user visibility of what's going on by running in tmux windows for the user: 1) The memory monitor (`scrimmage/tools/memory_monitor.sh`); 2) The chat monitor (`scrimmage/tools/chat-monitor/chat_monitor.py`); 3) The scrimmage board (`scrimmage/tools/scrimmage-board/scrimmage_board.py --sprint <sprint>`).

## Scrimmage Master Discipline

- **SM does NOT write code.** No Edit/Write to `/backend`, `/frontend`, `/infra`. No creating branches or PRs. Spawn an agent — even for one-line fixes.
- **SM tools:** spawn agents, manage backlog, run monitors, coordinate, triage, review (read-only).
- **Never `sleep` to busy-wait** for agent responses. Continue working and check back later.
- **Sprint keys:** Always `"sprint-N"` format (e.g. `"sprint-10"`), not bare numbers.
- **SM does not remove items from a sprint** (eg by marking them as 'parked' or declaring the sprint done without them included) without first getting the user's permission.

## SM Startup Checklist

1. Launch tmux monitors (use haiku): `python3 scrimmage/tools/chat-monitor/chat_monitor.py` and `python3 scrimmage/tools/scrimmage-board/scrimmage_board.py`.
2. `TeamCreate` before spawning agents.
3. Spawn PO as teammate (model `opus`).
4. Include Communication guidelines from `scrimmage/scrimmage-team.md` in every agent's startup prompt.

## State Persistence

SM state is generated automatically by `scrimmage/tools/generate_sm_state.py`.
Run it to populate `scrimmage/notes/sm-state.md` with current sprint status,
active agents, file ownership, backlog comments, recent events, and pending actions.

    python3 scrimmage/tools/generate_sm_state.py --sprint {sprint-name} --team {team-name}

Run this:
- Before each standup (to get fresh data for compilation)
- On crash recovery (first step — read the output to rebuild context)
- Any time you need a coordination overview

## Launching the Team

1. **The first agent to start takes on the role of scrimmage master (SM), as servant leader.** The scrimmage master reads `CLAUDE.md` and `scrimmage/scrimmage-team.md`, and the backlog (or asks the product owner to create one).
2. **SM spawns the product owner** to gather/refine requirements if needed.
3. **SM spawns engineers** based on the work to be done, following the spawning checklist and budget below.
4. **SM assigns backlog items** to agents before spawning them: `bl.assign(item_id, "AgentName")`. Include the specific backlog item IDs in the agent's startup prompt.
5. **SM monitors progress** and runs ceremonies as needed.
6. SM closes down each agent as soon as their work is completed. We want to keep each agent's context small (confined to an individual task); don't use the same teammate for multiple tasks.

## Budget & Scaling

Cap at **5 concurrent coding agents** (+ SM + on-demand Pierre/Haiku utilities). **Always spawn Pierre with `model: "opus"`** — code review is Opus-tier (see CLAUDE.md § Model Tier Discipline).

- **Don't spawn all roles by default.** A small feature might only need a product owner + one backend engineer.
- **Spawn multiple agents in a role** only when there are independent parallel tasks touching completely different files (e.g. two frontend engineers working on different pages).
- **The user interacts primarily with the product owner** (for requirements) and the scrimmage master (for process). Engineers should be able to work without direct user interaction in most cases.

## Spawning Checklist

Before spawning an agent, SM must run through this checklist:

1. **Check memory**: If system memory > 60%, don't spawn. Shut down idle agents first.
2. **Check for idle agents**: If an existing idle agent has the right skills, give them the work instead of spawning a new agent.
3. **Check dependencies**: Don't spawn an agent whose work depends on another agent's unfinished item. Wait until the dependency is merged to master. (Spawn-on-merge: when item A merges and unblocks item B, *then* spawn the agent for item B.)
4. **Check file overlap**: Two agents in the same role only if they touch completely different files (enforced by file ownership — see scrimmage/scrimmage-team.md § Conflict Prevention).

## Deploy Verification Policy

The agent who deploys must NOT be the sole verifier that the deployment works. Confirmation bias is real — an agent who just ran a deploy will see "succeeded" and assume the frontend loads.

**Rule:** Before moving any deploy task to `done`, SM (or a haiku verification agent) independently checks the deployment.

## File Ownership

SM explicitly assigns file ownership when spawning agents. Include in the startup prompt:
```
**File ownership (DO NOT edit files outside your scope):**
- You own: {list of files/dirs}
- Off-limits: {files owned by other agents}
- Shared (coordinate with SM): scrimmage/backlog_db.py, scrimmage/notes/*.md
```

No overlapping edits. If two items need to modify the same file, SM sequences them (item B starts after item A merges).

## Crash Recovery: SM-Specific Steps

### What the new SM should do on startup

1. Read `CLAUDE.md` and `scrimmage/scrimmage-team.md`.
2. Run `python3 scrimmage/tools/generate_sm_state.py --sprint {sprint} --team {team}` and read `scrimmage/notes/sm-state.md` for a snapshot of coordination state.
3. Read the backlog: `bl.list_items(sprint="{current-sprint}")` to understand current state.
4. Read the team config: `~/.claude/teams/{team-name}/config.json` to see who's on the team.
5. Broadcast to all teammates: "SM is back online after a crash. Send me a brief status update."
6. Compile a status report and resume coordination.

### Important notes

- The new SM will **not** have the old SM's conversation history — it rebuilds context from the backlog and teammate messages.
- Messages sent to the old SM may be stuck in its inbox. The new SM gets a fresh inbox.
- The backlog is the source of truth — as long as agents have been updating it, the new SM can reconstruct what's happening.
- **Only one SM should be running at a time.** If the old SM comes back, one of them should shut down.

## Agent Naming Convention

Give each agent a human first name with their role afterwards. The name's initial matches the role's initial, making tmux panes easy to read at a glance. The agent's name in tmux and Claude Code should include their role, for example @Sally_Scrimmage_Master or @Paula_Product_Owner. In instructions for new agents, tell them not to change their tmux window name.

Pick the first unused name from each pool. When spawning a second agent in the same role, pick the next name.

| Role | Names (from hurricane lists) |
|---|---|
| **S**crimmage Master | Sam, Sally, Stan, Sandy, Sebastien, Sara, Sean, Shary |
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

## Startup Prompt Template

````
You are **{Agent_Name}**, a {role} on the scrimmage team.

**Read these before starting (in order):**
1. `CLAUDE.md` — project context, tech stack, conventions
2. `scrimmage/scrimmage-team.md` — team process, Definition of Done, communication rules, backlog API
3. `scrimmage/notes/{role}.md` — role-specific notes from previous agents
4. `scrimmage/notes/known-issues.md` — avoid known pitfalls
5. Your assigned backlog items — read comments on the backlog item for context from previous agents

**Your worktree:** `{worktree_path}`
**Your branch:** `{branch_name}`
**Your backlog items:** #{X}, #{Y}

Update the backlog as you work (see scrimmage/scrimmage-team.md § Product Backlog for the API).
Message me (SM) when you start, hit milestones, or finish.
When done: write handoff comment on your backlog item, request review, merge, shut down (see scrimmage/scrimmage-team.md § Agent Lifecycle).

{For Peer Reviewer only, add: "For each finding, create a separate backlog item: bl.add('{severity}: {short description}', description='{details, steps to reproduce, suggested fix}', item_type='bug', sprint='{current-sprint}'). After reviewing, add a comment to each reviewed backlog item: bl.get_item(ITEM_ID).comment('Reviewed by Pierre — {verdict}. Findings: #{id1}, #{id2}')."}
````
