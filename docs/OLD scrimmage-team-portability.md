# Scrimmage Team Framework — Portability & Reusability Guide

This guide documents which files in the Hisser repository are **generic/reusable** (applicable to any project using the "scrimmage team" workflow) versus **Hisser-specific** (only relevant to this snake social network project).

Use this guide when you want to:
- Adapt the scrimmage team framework for a new project
- Understand which files are part of the framework vs the application
- Extract the scrimmage team tooling for use in another repository

---

## Quick Reference Table

| File/Directory | Category | Customization Needed | Notes |
|---|---|---|---|
| **Process & Documentation** | | | |
| `scrimmage-team.md` | Generic | ✅ Minor | Core process document; review team roles for your domain |
| `CLAUDE.md` | Template | ✅ Extensive | Mix of generic structure + Hisser-specific config (see below) |
| `Backlog-API-guide.md` | Generic | ❌ None | Backlog database API reference |
| `README.md` | Hisser-specific | N/A | Replace entirely with your project's README |
| `ARCHITECTURE.md` | Hisser-specific | N/A | Replace with your architecture |
| `AWS-RESOURCES.md` | Hisser-specific | N/A | Replace with your resource catalog |
| `DEPLOY.md` | Hisser-specific | N/A | Replace with your deploy guide |
| `TEST-USERS.md` | Hisser-specific | N/A | Project-specific test data |
| **Backlog System** | | | |
| `backlog_db.py` | Generic | ❌ None | SQLite backlog database manager |
| `backlog.db` | Instance data | N/A | Created automatically; symlinked in worktrees |
| `test_backlog_db.py` | Generic | ❌ None | Comprehensive test suite for backlog DB |
| **Worktree Management** | | | |
| `worktree_setup.py` | Generic | ✅ Minor | Parse config from CLAUDE.md; agent naming is generic |
| **Project Configuration** | | | |
| `.gitignore` | Template | ✅ Minor | Generic structure; has ruff/pytest/CDK/node_modules exclusions |
| `pyproject.toml` | Template | ✅ Moderate | Has ruff, mypy, pytest config; customize for your linters/tools |
| **Deploy Scripts** | | | |
| `branch_deploy.sh` | Template | ✅ Moderate | Deploy logic is generic; CDK/AWS-specific, but adaptable |
| `branch_teardown.sh` | Template | ✅ Moderate | Teardown logic is generic; CDK/AWS-specific |
| `test_branch_deploy_vite_base.sh` | Hisser-specific | N/A | Tests Hisser's Vite base path behavior |
| **Tools** | | | |
| `tools/memory_monitor.sh` | Generic | ❌ None | OOM monitoring for long-running agents |
| `tools/oom_protect.sh` | Generic | ❌ None | Kill agent gracefully before OOM crash |
| `tools/assume-deploy-role.sh` | Template | ✅ Extensive | AWS STS assume-role helper; customize IAM role ARN |
| `tools/get-aws-creds.sh` | Template | ✅ Extensive | Wrapper for assume-role; clears stale tokens, saves to /tmp for multi-agent use |
| `tools/check_key_status.sh` | Template | ✅ Minor | Check AWS IAM key status; customize for your setup |
| `tools/test_assume_role_components.sh` | Template | ✅ Minor | Test assume-role components; customize for your IAM |
| `tools/chat-monitor/` | Generic | ❌ None | Real-time agent message monitor (tmux integration) |
| `tools/scrimmage-board/` | Generic | ❌ None | Sprint board display tool (backlog visualization) |
| `tools/generate_sm_state.py` | Generic | ✅ Minor | Scrimmage Master state generator (may need tweaks for non-AWS) |
| `tools/cfn_output.py` | Template | ❌ None (if using AWS) | CloudFormation output helper; only needed for AWS projects |
| `tools/test_cfn_output.py` | Template | ❌ None (if using AWS) | Tests for CFN output helper |
| `tools/tmux-launcher/` | Generic | ✅ Minor | Tmux session launcher; may need project-specific window setup |
| **Knowledge Base** | | | |
| `notes/` directory structure | Generic | ✅ Minor | Role-specific knowledge management; file names match roles in `scrimmage-team.md` |
| `notes/backend-engineer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/frontend-engineer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/cloud-engineer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/integration-engineer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/dba.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/product-owner.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/peer-reviewer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/scrimmage-master.md` | Mix | ✅ Moderate | Generic SM process + Hisser-specific conventions |
| `notes/ui-ux-designer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/technical-writer.md` | Mix | ✅ Minor | Key Behaviours section is generic; replace project-specific content below it |
| `notes/known-issues.md` | Hisser-specific | N/A | Start fresh for your project |
| `notes/plans/` | Hisser-specific | N/A | Planning docs for Hisser features |
| **CI/CD** | | | |
| `.github/workflows/ci.yml` | Template | ✅ Moderate | Generic CI structure; customize for your build/test commands |
| `.github/workflows/deploy.yml` | Template | ✅ Extensive | AWS CDK deploy pipeline; customize for your stack names, env vars |
| **Application Code** | | | |
| `/backend/` | Hisser-specific | N/A | Python Lambda handlers, services, models |
| `/frontend/` | Hisser-specific | N/A | React app (TypeScript) |
| `/infra/` | Hisser-specific | N/A | AWS CDK infrastructure stacks |
| `/e2e/` | Hisser-specific | N/A | Playwright end-to-end tests |
| **Documentation** | | | |
| `docs/scrimmage-team-portability.md` | Generic | ❌ None | This guide (framework portability reference) |
| `docs/diagrams-howto.md` | Generic | ❌ None | Mermaid diagram conventions and security guidelines |
| `docs/aws-credentials-setup.md` | Template | ✅ Extensive | AWS STS MFA setup; customize for your cloud provider |
| `docs/assume-role-verification.md` | Template | ✅ Moderate | Verification steps for AWS assume-role; customize IAM |
| `docs/deactivate-static-keys-runbook.md` | Template | ✅ Moderate | AWS IAM key deactivation runbook |
| `docs/delete-static-keys-runbook.md` | Template | ✅ Moderate | AWS IAM key deletion runbook |
| `docs/lambdas.md` | Hisser-specific | N/A | Hisser Lambda handler documentation |
| **Configuration** | | | |
| `.claude/` | Mix | ✅ Minor | Claude Code hooks (generic) + project config |
| `.claude/settings.json` | Generic | ❌ None | Claude Code project settings |
| `.claude/settings.local.json` | Project-specific | N/A | Local overrides (gitignored, if present) |
| `.claude/hooks/block-tmux-rename.sh` | Generic | ❌ None | Prevents agents from renaming tmux windows |
| `.claude/hooks/test_hook.py` | Generic | ❌ None | Test hook for validating hook setup |

---

## CLAUDE.md Anatomy

The `CLAUDE.md` file is a **template** with both generic and project-specific sections. Here's what to customize:

### Generic Sections (Keep, Review, Adapt)

These sections define the scrimmage team framework and should be kept with minor edits:

1. **Getting Started** — Points to `scrimmage-team.md`; generic
2. **Conventions** — Generic workflow rules (backlog DB, no manual infra changes, etc.)
3. **Worktree Config** — Generic structure; customize `symlinks` and `deps` for your project
4. **Model Tier Discipline** — Generic guidance on when to use Haiku/Sonnet/Opus
5. **Key Process Rules** — Generic backlog flow, review process, deploy pipeline
6. **Knowledge Management** — Generic notes structure
7. **Compaction Instructions** — Generic context window management rules

### Project-Specific Sections (Replace)

These sections are Hisser-specific and must be replaced for a new project:

1. **Tech Stack** — Replace with your stack (e.g., Django, Next.js, Terraform, GCP)
2. **Repo Structure** — Replace with your monorepo layout or file structure
3. **Playwright / Chromium** — Hisser uses pre-installed Chromium; customize or remove
4. **Local Verification** — Replace with your linting, testing, build commands
5. **Environment** — Generic container notes + Hisser-specific AWS credential setup; customize AWS section
6. **Non-Prod Frontend Serving** — Hisser-specific (API Gateway S3 proxy); replace with your frontend deployment model
7. **Deployed Resources** — Hisser-specific AWS resource IDs; replace with your resource catalog

---

## Step-by-Step: Deploying the Framework to a New Repo

### 1. Copy Framework Files

Copy these files from Hisser to your new repo:

```bash
# Process documentation
cp scrimmage-team.md <new-repo>/
cp Backlog-API-guide.md <new-repo>/
cp CLAUDE.md <new-repo>/    # Will customize in step 2

# Backlog system
cp backlog_db.py <new-repo>/
cp test_backlog_db.py <new-repo>/

# Worktree management
cp worktree_setup.py <new-repo>/

# Project configuration
cp .gitignore <new-repo>/    # Customize for your stack
cp pyproject.toml <new-repo>/    # Customize linter/tool config

# Deploy scripts (if using AWS CDK or similar)
cp branch_deploy.sh <new-repo>/
cp branch_teardown.sh <new-repo>/

# Tools
cp -r tools/ <new-repo>/tools/

# Documentation (generic)
mkdir -p <new-repo>/docs
cp docs/scrimmage-team-portability.md <new-repo>/docs/
cp docs/diagrams-howto.md <new-repo>/docs/
# AWS-specific docs (customize if using AWS, skip otherwise)
cp docs/aws-credentials-setup.md <new-repo>/docs/
cp docs/assume-role-verification.md <new-repo>/docs/
cp docs/deactivate-static-keys-runbook.md <new-repo>/docs/
cp docs/delete-static-keys-runbook.md <new-repo>/docs/

# CI/CD templates (customize heavily)
cp -r .github/workflows/ <new-repo>/.github/workflows/

# Claude Code configuration
cp -r .claude/ <new-repo>/.claude/

# Knowledge base structure
mkdir -p <new-repo>/notes/plans
cp notes/backend-engineer.md <new-repo>/notes/    # Keep Key Behaviours section, clear project-specific content
cp notes/frontend-engineer.md <new-repo>/notes/   # Keep Key Behaviours section, clear project-specific content
# ... copy all role notes, then clear project-specific content (preserve Key Behaviours sections)
```

### 2. Customize CLAUDE.md

Edit `<new-repo>/CLAUDE.md`:

1. **Tech Stack** — Replace with your stack (Node.js, Go, Terraform, etc.)
2. **Repo Structure** — Update monorepo paths or directory layout
3. **Worktree Config** — Update `symlinks` and `deps` for your project:
   - `symlinks`: Files shared across worktrees (e.g., `backlog.db`, `notes`, config files)
   - `deps`: Directories with dependency install commands (e.g., `npm ci`, `pip install -r requirements.txt`)
4. **Playwright / Chromium** — Remove if not using Playwright, or update paths
5. **Local Verification** — Update with your linter, type checker, test runner commands
6. **Environment** — Update AWS section with your cloud provider and credential setup
7. **Non-Prod Frontend Serving** — Replace with your deployment model (CloudFront, Vercel, etc.)
8. **Deployed Resources** — Remove Hisser resources; add your resource IDs as you deploy

### 3. Clear Knowledge Base

The `notes/` directory structure is generic, but most of the content is Hisser-specific:

**IMPORTANT:** Each role note file (e.g., `notes/backend-engineer.md`, `notes/frontend-engineer.md`) begins with a "Key Behaviours" section that is **generic and reusable**. Preserve these sections when copying to a new project.

```bash
# For each role note file, preserve the Key Behaviours section
# and clear only the project-specific content below it.
# Example for backend-engineer.md:
#   Keep: "## Key Behaviours" section
#   Clear: Everything below the Key Behaviours section

# Alternatively, manually edit each file to remove Hisser-specific content
# while keeping the Key Behaviours section intact.

# Start fresh with known issues
echo "# Known Issues" > notes/known-issues.md

# Clear old plan files
rm -rf notes/plans/*
```

### 4. Customize Deploy Scripts

If using `branch_deploy.sh` and `branch_teardown.sh`:

1. **CDK context** — Update stack names, region, account ID
2. **VITE_BASE** — Remove if not using Vite; replace with your frontend build env vars
3. **CloudFormation output parsing** — Update keys to match your stack outputs
4. **E2E test env vars** — Update to match your test user setup (Cognito → your auth)
5. **Merge guards** — Review protected directories (`notes/`, `tools/`, `.claude/`)

If **not using AWS CDK**, replace these scripts entirely with your deployment tooling (Terraform, Pulumi, etc.).

### 5. Customize CI/CD Workflows

Edit `.github/workflows/deploy.yml`:

1. **AWS credentials** — Update role ARN, region, account ID (or replace with GCP/Azure)
2. **CDK commands** — Replace with your IaC tool (`terraform apply`, `pulumi up`, etc.)
3. **Build steps** — Update frontend/backend build commands for your stack
4. **Environment variables** — Update `VITE_BASE`, Cognito IDs, etc. to match your app

Edit `.github/workflows/ci.yml`:

1. **Linting** — Update with your linters (`eslint`, `ruff`, `golangci-lint`, etc.)
2. **Type checking** — Update with your type checker (`tsc`, `mypy`, etc.)
3. **Unit tests** — Update with your test runner (`pytest`, `jest`, `go test`, etc.)

### 6. Customize Tools

- **`tools/assume-deploy-role.sh`** — Update IAM role ARN and success messages (or remove if not using AWS STS)
- **`tools/get-aws-creds.sh`** — Wrapper for assume-role; no changes needed if using `assume-deploy-role.sh`
- **`tools/check_key_status.sh`** — Update default IAM username (or remove)
- **`tools/generate_sm_state.py`** — Review CloudFormation parsing; may need updates for non-AWS
- **`tools/cfn_output.py`** — Keep if using AWS CloudFormation; remove otherwise
- **`tools/memory_monitor.sh`** — Generic; no changes needed
- **`tools/oom_protect.sh`** — Generic; no changes needed
- **`tools/chat-monitor/`** — Generic; no changes needed
- **`tools/scrimmage-board/`** — Generic; no changes needed
- **`tools/tmux-launcher/`** — Review window layout; customize for your project

### 7. Update README.md

Replace Hisser's README with your project's README:

```bash
cat > README.md <<'EOF'
# Your Project Name

Your project description here.

See `scrimmage-team.md` for team process and `CLAUDE.md` for project config.
EOF
```

### 8. Initialize Backlog

The backlog database is created automatically when first accessed:

```bash
# Will create backlog.db on first import
python3 -c "from backlog_db import get_backlog_db; get_backlog_db(agent='Setup').add('Bootstrap project', item_type='task')"
```

### 9. Test the Setup

1. **Create a worktree:**
   ```bash
   python3 worktree_setup.py create test-agent demo-feature
   ```

2. **Verify symlinks:**
   ```bash
   ls -l <worktree-path>/backlog.db    # Should be a symlink
   ls -l <worktree-path>/notes         # Should be a symlink
   ```

3. **Check backlog access:**
   ```bash
   cd <worktree-path>
   python3 -c "from backlog_db import get_backlog_db; print(get_backlog_db().list_items())"
   ```

4. **Clean up test worktree:**
   ```bash
   python3 worktree_setup.py teardown test-agent demo-feature --force
   ```

---

## Customization Cheat Sheet

### Minimal Customization (2-4 hours)

For a simple project with similar stack to Hisser (React, Python, AWS CDK):

1. Update `CLAUDE.md` Tech Stack, Repo Structure, Deployed Resources
2. Update `CLAUDE.md` Worktree Config (`symlinks`, `deps`)
3. Clear project-specific content from `notes/*.md` (preserve Key Behaviours sections)
4. Update `branch_deploy.sh` stack names and env vars
5. Update `.github/workflows/deploy.yml` stack names and AWS config

### Moderate Customization (1-2 days)

For a project with different tech stack (e.g., Next.js, Go, GCP):

1. All minimal customizations above
2. Replace deploy scripts (`branch_deploy.sh` → Terraform/Pulumi equivalent)
3. Rewrite `.github/workflows/deploy.yml` for your cloud provider
4. Update `tools/generate_sm_state.py` to parse your infrastructure output
5. Update `scrimmage-team.md` § Local Verification Pipeline with your commands
6. Review team roles in `scrimmage-team.md` and adjust for your domain

### Extensive Customization (3-5 days)

For a project with radically different architecture (e.g., monolith, microservices, Kubernetes):

1. All moderate customizations above
2. Rethink deploy pipeline — may need multi-stage deploy, canary releases, etc.
3. Adapt worktree strategy — microservices may need different worktree layouts
4. Extend backlog schema — may need epics, sprints, components, etc. (see `backlog_db.py`)
5. Create project-specific tools (e.g., Kubernetes deploy helper, service mesh config)
6. Write custom CI/CD stages for your deployment model

---

## AWS STS Credential Tooling (Reusable Component)

The Hisser project includes a complete AWS STS (Security Token Service) credential management system that enables secure, MFA-protected temporary credentials for local development and multi-agent deployments. This tooling is **highly reusable** for any AWS-based project.

### Overview

**Problem:** Long-lived static IAM access keys are a security risk. If leaked, they provide unlimited access until manually revoked.

**Solution:** The STS credential tooling implements a zero-trust approach:
1. Minimal IAM user with **only** `sts:AssumeRole` permission (no direct AWS service access)
2. Virtual MFA device requirement (authenticator app on your phone)
3. Helper scripts to obtain time-limited temporary credentials (1-12 hours)
4. Shared credential file pattern for multi-agent/multi-shell scenarios

### Components

The STS credential tooling consists of three bash scripts that work together:

#### 1. `tools/assume-deploy-role.sh` — Core AssumeRole Script

**What it does:**
- Fetches your MFA device ARN automatically via `aws iam list-mfa-devices`
- Prompts for a 6-digit MFA token from your authenticator app
- Calls `aws sts assume-role` with MFA authentication
- Exports temporary credentials as environment variables:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_SESSION_TOKEN`
- Prints expiration time and usage examples

**Usage:**
```bash
source tools/assume-deploy-role.sh           # 1 hour session (default)
source tools/assume-deploy-role.sh 43200     # 12 hour session
```

**IMPORTANT:** Must be `source`d (not executed) so environment variables propagate to the current shell.

**Key design decisions:**
- Uses `python3` for JSON parsing (not `jq`) because Python is already a project dependency
- Handles errors gracefully with helpful troubleshooting messages
- No `set -euo pipefail` because the script is sourced (would affect caller's shell)
- Session name includes `$(whoami)` and timestamp for CloudTrail audit trail

**Hisser-specific configuration:**
```bash
ROLE_ARN="arn:aws:iam::368331614770:role/Hisser-dev-Developer"
```

**To customize for your project:**
1. Change `ROLE_ARN` to your IAM role ARN
2. Update success message with your role name (line 117-118)
3. Update session name prefix if desired (line 31)

#### 2. `tools/get-aws-creds.sh` — Convenience Wrapper (NEW)

**What it does:**
- Clears any stale AWS session tokens from environment (`unset AWS_*`)
- Calls `assume-deploy-role.sh` to get fresh credentials
- Saves credentials to `/tmp/aws-session-creds.sh` for sharing across shells/agents
- Sets file permissions to `600` (readable only by current user)

**Why this is critical for multi-agent deployments:**

When multiple agents need AWS access (e.g., Scrimmage Master + Cloud Engineer + Integration Engineer), each agent runs in a separate shell/process. Environment variables don't cross process boundaries. The `/tmp/aws-session-creds.sh` pattern solves this:

1. **One agent** runs `source tools/get-aws-creds.sh` and enters MFA token
2. Credentials are saved to `/tmp/aws-session-creds.sh`
3. **Other agents** run `source /tmp/aws-session-creds.sh` (no MFA prompt needed)
4. All agents share the same temporary credentials until expiration

**Usage:**
```bash
# First agent (enters MFA token, saves credentials)
source tools/get-aws-creds.sh

# Other agents (reuse saved credentials)
source /tmp/aws-session-creds.sh
```

**The shared credential file pattern:**

The generated `/tmp/aws-session-creds.sh` file contains:
```bash
# AWS temporary credentials — auto-generated by tools/get-aws-creds.sh
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
# Credentials expire at: 2026-02-14T23:30:00Z
```

**Security notes:**
- File permissions are `600` (owner-read-write only)
- Credentials stored in `/tmp` are automatically cleared on reboot
- Expiration timestamp included as comment for visibility
- Stale tokens are explicitly cleared before obtaining new ones to prevent "ExpiredToken" errors

**To customize for your project:**
- No changes needed if using `assume-deploy-role.sh`
- Optional: Change `/tmp/aws-session-creds.sh` path if `/tmp` is not writable

#### 3. `tools/check_key_status.sh` — IAM Key Status Checker

**What it does:**
- Lists all access keys for a specified IAM user
- Shows key ID, status (Active/Inactive), and creation date
- Displays current AWS identity (IAM user vs assumed role)
- Color-coded output (red for Active keys, green for Inactive)

**Usage:**
```bash
./tools/check_key_status.sh                          # Default user
./tools/check_key_status.sh my-iam-username          # Specific user
```

**Use cases:**
- Verify IAM access key deactivation after migrating to STS credentials
- Audit which keys are still active in your AWS account
- Confirm you're using temporary credentials (shows "assumed-role" ARN)

**Hisser-specific configuration:**
```bash
USERNAME="${1:-st1-limited-permissions-user}"
```

**To customize for your project:**
1. Change default username (line 25) to your IAM user
2. Optionally update color-coded status logic if needed

### Integration with Deploy Scripts

The `branch_deploy.sh` script enforces MFA-protected temporary credentials:

**Credential check logic (lines ~50-100 in branch_deploy.sh):**
```bash
if [[ -z "${AWS_SESSION_TOKEN:-}" ]]; then
  echo "[ERROR] Static credentials not allowed"
  echo "[ERROR] REQUIRED: source tools/assume-deploy-role.sh"
  exit 1
fi
```

**Override (not recommended):**
```bash
HISSER_ALLOW_STATIC=1 ./branch_deploy.sh <worktree>   # Bypasses credential check
```

This enforcement ensures all deployments use MFA-protected credentials by default.

### How to Adapt for a New Project

#### Minimal Changes (Same AWS Setup)

If your new project uses AWS with a similar IAM role setup:

1. **Update `tools/assume-deploy-role.sh`:**
   - Line 30: Change `ROLE_ARN` to your IAM role ARN
   - Line 117-118: Update success message with your role name

2. **Update `tools/check_key_status.sh`:**
   - Line 25: Change default username to your IAM user

3. **Create IAM resources in your AWS account:**
   - IAM role with appropriate permissions (e.g., `MyProject-dev-Developer`)
   - Role trust policy allowing your IAM users to assume it with MFA
   - Minimal IAM users with only `sts:AssumeRole` permission

4. **Update documentation:**
   - Copy and customize `docs/aws-credentials-setup.md` with your role names
   - Update `CLAUDE.md` Environment section with your credential setup

#### Moderate Changes (Different AWS Account/Region)

If deploying to a different AWS account or using different role naming conventions:

1. All minimal changes above
2. **Update `branch_deploy.sh` credential enforcement:**
   - Search for "assume-deploy-role.sh" references
   - Update error messages with your role name
3. **Update `.github/workflows/deploy.yml`:**
   - Change AWS OIDC role ARN for GitHub Actions
   - Update region if different from `eu-west-1`
4. **Update IAM role maximum session duration:**
   - Default is 12 hours (43200 seconds)
   - Configurable in IAM role settings
   - Update script comments if you change this

#### Extensive Changes (Non-AWS or Different Auth)

If using GCP, Azure, or a different authentication mechanism:

1. **Replace the entire STS tooling** with your cloud provider's equivalent:
   - **GCP:** Use `gcloud auth application-default login` or service account impersonation
   - **Azure:** Use `az login` with managed identities or service principals
   - **Multi-cloud:** Consider using a credential manager like HashiCorp Vault

2. **Keep the shared credential file pattern:**
   - The `/tmp/<project>-session-creds.sh` pattern is cloud-agnostic
   - Adapt to export your cloud provider's environment variables
   - Example for GCP:
     ```bash
     # /tmp/myproject-gcp-creds.sh
     export GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcp-service-account-key.json"
     export GOOGLE_CLOUD_PROJECT="my-project-id"
     ```

3. **Update deploy scripts** to check for your cloud provider's credentials

### Workflow Examples

#### Single-Agent Deployment
```bash
# Agent obtains credentials
source tools/assume-deploy-role.sh
# Enter MFA token: 123456

# Agent deploys
./branch_deploy.sh ../worktrees/my-feature
```

#### Multi-Agent Deployment (Scrimmage Team)
```bash
# Scrimmage Master obtains and shares credentials
source tools/get-aws-creds.sh
# Enter MFA token: 123456
# Credentials saved to: /tmp/aws-session-creds.sh

# Other agents can now source the shared credentials
# (in their own shells/tmux windows)

# Cloud Engineer (in separate tmux window)
source /tmp/aws-session-creds.sh
cd infra && npx cdk deploy --all

# Integration Engineer (in separate tmux window)
source /tmp/aws-session-creds.sh
./branch_deploy.sh ../worktrees/test-feature
```

No additional MFA prompts needed — all agents share the same temporary credentials.

#### Credential Expiration Handling
```bash
# After 1 hour (or your configured duration), AWS commands fail:
# An error occurred (ExpiredToken) when calling the ... operation

# Solution: Re-run get-aws-creds.sh
source tools/get-aws-creds.sh
# Enter new MFA token: 789012

# All agents source the updated file
source /tmp/aws-session-creds.sh
```

### Security Benefits

1. **MFA Protection** — Stolen credentials are useless without the MFA device
2. **Time-Limited Access** — Credentials auto-expire (1-12 hours), reducing blast radius
3. **Audit Trail** — All `AssumeRole` operations logged in AWS CloudTrail
4. **Zero Standing Privileges** — IAM users have no direct AWS service permissions
5. **No Long-Lived Secrets** — Static access keys restricted to assume-only permissions

### Testing the Setup

After customizing the scripts for your project:

1. **Test assume-role script:**
   ```bash
   source tools/assume-deploy-role.sh
   aws sts get-caller-identity
   # Should show assumed-role ARN, not IAM user ARN
   ```

2. **Test credential sharing:**
   ```bash
   # Terminal 1
   source tools/get-aws-creds.sh

   # Terminal 2
   source /tmp/aws-session-creds.sh
   aws sts get-caller-identity
   # Should show same session as Terminal 1
   ```

3. **Test credential enforcement:**
   ```bash
   unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
   ./branch_deploy.sh ../worktrees/test
   # Should fail with "[ERROR] Static credentials not allowed"
   ```

4. **Test key status checker:**
   ```bash
   ./tools/check_key_status.sh your-iam-username
   # Should show your access keys and current identity
   ```

### Files to Copy for a New Project

**Core STS tooling (copy these):**
```bash
cp tools/assume-deploy-role.sh <new-repo>/tools/
cp tools/get-aws-creds.sh <new-repo>/tools/          # If using multi-agent pattern
cp tools/check_key_status.sh <new-repo>/tools/
cp tools/test_assume_role_components.sh <new-repo>/tools/  # Optional: test harness
```

**Documentation (customize these):**
```bash
cp docs/aws-credentials-setup.md <new-repo>/docs/
cp docs/assume-role-verification.md <new-repo>/docs/
cp docs/deactivate-static-keys-runbook.md <new-repo>/docs/
cp docs/delete-static-keys-runbook.md <new-repo>/docs/
```

Then customize as described in the sections above.

### Common Pitfalls

**1. Running script without `source`**

**Wrong:**
```bash
./tools/assume-deploy-role.sh
# Runs in a subshell — env vars don't propagate
```

**Correct:**
```bash
source tools/assume-deploy-role.sh
# Runs in current shell — env vars are set
```

**2. Stale AWS_SESSION_TOKEN in environment**

**Symptom:** "ExpiredToken" or "No MFA device configured" errors even after running the script.

**Fix:** `get-aws-creds.sh` explicitly clears stale tokens first. Use it instead of `assume-deploy-role.sh` directly, or manually unset:
```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
source tools/assume-deploy-role.sh
```

**3. Forgetting to update role ARN**

**Symptom:** "AccessDenied: User is not authorized to perform: sts:AssumeRole" errors.

**Fix:** Update `ROLE_ARN` in `assume-deploy-role.sh` to match your AWS account and role name.

**4. Credentials not shared across agents**

**Symptom:** Each agent prompts for MFA separately.

**Fix:** Use `get-aws-creds.sh` (which saves to `/tmp/aws-session-creds.sh`) instead of `assume-deploy-role.sh` directly. Other agents should `source /tmp/aws-session-creds.sh`.

### Related Documentation

- **Full setup guide:** `docs/aws-credentials-setup.md` — Step-by-step MFA configuration and credential setup
- **Verification steps:** `docs/assume-role-verification.md` — How to verify your assume-role setup works
- **Credential migration:** `docs/deactivate-static-keys-runbook.md` — Deactivating old static IAM keys
- **Cleanup:** `docs/delete-static-keys-runbook.md` — Deleting deactivated keys

---

## Framework Dependencies

The scrimmage team framework assumes:

1. **Git** — Worktree management requires git 2.30+
2. **Python 3.10+** — For `backlog_db.py`, `worktree_setup.py`, tools
3. **SQLite 3** — For backlog database (included with Python)
4. **Bash 4+** — For deploy scripts and tools
5. **tmux** (optional) — For chat monitor and scrimmage board tools
6. **Claude Code CLI** — Agents run via Claude Code
7. **GitHub Actions** (optional) — For CI/CD; can use other CI platforms

The framework does **not** require:

- AWS — Scripts are AWS-focused but adaptable to GCP, Azure, etc.
- CDK — Deploy scripts use CDK, but you can replace with Terraform, Pulumi, etc.
- React/TypeScript — Frontend stack is project-specific
- DynamoDB — Backend storage is project-specific
- Playwright — E2E testing is project-specific

---

## Common Pitfalls

### 1. Forgetting to Update CLAUDE.md Worktree Config

**Symptom:** Worktree creation fails with "npm: command not found" or symlinks are missing.

**Fix:** Update the `symlinks` and `deps` sections in `CLAUDE.md` to match your project's shared files and dependency install commands.

### 2. Hardcoded Hisser-Specific Paths in Deploy Scripts

**Symptom:** Deploy fails with "stack not found" or "bucket does not exist".

**Fix:** Search for "hisser" (case-insensitive) in `branch_deploy.sh`, `branch_teardown.sh`, and `.github/workflows/deploy.yml`. Replace with your project's stack names and resource names.

### 3. Stale Notes Content

**Symptom:** Agents reference Hisser-specific patterns (DynamoDB, Cognito, API Gateway S3 proxy).

**Fix:** Clear all `notes/*.md` content before starting your project. The file structure is generic, but the content is Hisser-specific.

### 4. CI/CD Env Vars for Old Resources

**Symptom:** GitHub Actions deploy fails with "invalid Cognito client ID".

**Fix:** Update all environment variables in `.github/workflows/deploy.yml` to match your project's resources. Remove Hisser-specific vars like `HISSER_COGNITO_CLIENT_ID`.

### 5. Backlog DB Location

**Symptom:** Each worktree creates its own `backlog.db` instead of sharing one.

**Fix:** Ensure `backlog.db` is in the `symlinks` list in `CLAUDE.md` Worktree Config. The worktree setup script creates symlinks automatically based on this config.

---

## Framework Evolution

As you use the scrimmage team framework in your project, you may discover generic improvements that should be upstreamed:

1. **Backlog enhancements** — New fields, queries, or validation logic in `backlog_db.py`
2. **Worktree improvements** — Better symlink handling, dependency caching in `worktree_setup.py`
3. **Tool additions** — New monitoring, deploy verification, or debugging tools
4. **Process refinements** — Better Definition of Done, handoff protocol, context management

Consider contributing these back to the original Hisser repository (or a dedicated scrimmage-team-framework repo) so other projects can benefit.

---

## Further Reading

- **`scrimmage-team.md`** — Core process document (agent workflow, Definition of Done, communication)
- **`Backlog-API-guide.md`** — Full API reference for the backlog database
- **`CLAUDE.md`** — Project-specific config template
- **`worktree_setup.py`** — Implementation of worktree creation/teardown
- **`backlog_db.py`** — Implementation of the backlog database

---

## Questions?

If you're adapting this framework for a new project and hit a roadblock:

1. Check the **Common Pitfalls** section above
2. Review the **Customization Cheat Sheet** to see if you missed a step
3. Search `notes/known-issues.md` in Hisser for related issues
4. Read the source code — `backlog_db.py`, `worktree_setup.py`, and `branch_deploy.sh` are well-commented

Happy slithering!
