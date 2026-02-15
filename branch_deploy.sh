#!/usr/bin/env bash
# =============================================================================
# Branch Deploy — Deploy a feature branch to a staging environment
# =============================================================================
#
# Deploys infrastructure and application code from a git worktree to a
# temporary staging environment. Supports dry-run, merge-back, and cleanup.
#
# Usage:
#   ./branch_deploy.sh <worktree-path> [options]
#
# Options:
#   --merge       After deploy, merge the feature branch back to master
#   --cleanup     After deploy (and optional merge), tear down the stage
#   --hotswap     Use CDK hotswap for faster Lambda-only deploys
#   --e2e         Run e2e smoke tests after deploy
#   --dry-run     Show what would be done without executing
#   --allow-deletions  Allow CDK to delete resources (normally blocked)
#
# Examples:
#   ./branch_deploy.sh ../worktrees/barry-login-feature
#   ./branch_deploy.sh ../worktrees/barry-login-feature --merge --cleanup
#   ./branch_deploy.sh ../worktrees/barry-login-feature --dry-run
#
# =============================================================================

set -euo pipefail

# ─── Colors & helpers ───────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; }
die()   { fail "$@"; exit 1; }

# ─── Arg parsing ────────────────────────────────────────────────────────────
WORKTREE_PATH=""
DO_MERGE=false
DO_CLEANUP=false
HOTSWAP=false
RUN_E2E=false
DRY_RUN=false
ALLOW_DELETIONS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --merge)           DO_MERGE=true; shift ;;
    --cleanup)         DO_CLEANUP=true; shift ;;
    --hotswap)         HOTSWAP=true; shift ;;
    --e2e)             RUN_E2E=true; shift ;;
    --dry-run)         DRY_RUN=true; shift ;;
    --allow-deletions) ALLOW_DELETIONS=true; shift ;;
    -*)                die "Unknown option: $1" ;;
    *)
      if [[ -z "$WORKTREE_PATH" ]]; then
        WORKTREE_PATH="$1"; shift
      else
        die "Unexpected argument: $1"
      fi
      ;;
  esac
done

[[ -n "$WORKTREE_PATH" ]] || die "Usage: $0 <worktree-path> [--merge] [--cleanup] [--hotswap] [--e2e] [--dry-run] [--allow-deletions]"
[[ -d "$WORKTREE_PATH" ]] || die "Worktree path does not exist: $WORKTREE_PATH"

# Resolve absolute path
WORKTREE_PATH="$(cd "$WORKTREE_PATH" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Stage name derivation ──────────────────────────────────────────────────
# Derive stage name from the branch (not the path) using worktree_setup.py
BRANCH_NAME=$(git -C "$WORKTREE_PATH" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
if [[ -n "$BRANCH_NAME" ]] && command -v python3 &>/dev/null && [[ -f "$SCRIPT_DIR/worktree_setup.py" ]]; then
  STAGE_NAME=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
from worktree_setup import derive_stage_name
print(derive_stage_name('$BRANCH_NAME'))
" 2>/dev/null) || STAGE_NAME=$(basename "$WORKTREE_PATH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')
else
  STAGE_NAME=$(basename "$WORKTREE_PATH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')
fi

info "Stage name: $STAGE_NAME"
info "Worktree:   $WORKTREE_PATH"
info "Options:    merge=$DO_MERGE cleanup=$DO_CLEANUP hotswap=$HOTSWAP e2e=$RUN_E2E dry_run=$DRY_RUN"

# ─── Dry-run wrappers ───────────────────────────────────────────────────────
run() {
  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} $*"
  else
    "$@"
  fi
}

run_in_dir() {
  local dir="$1"; shift
  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} (in $dir) $*"
  else
    (cd "$dir" && "$@")
  fi
}

# ─── AWS credential check ───────────────────────────────────────────────────
check_aws_credentials() {
  info "Checking AWS credentials..."

  if [[ -n "${AWS_SESSION_TOKEN:-}" ]]; then
    ok "Using temporary credentials (AWS_SESSION_TOKEN present)"
    return 0
  fi

  # Static credentials detected
  if [[ -n "${AWS_ACCESS_KEY_ID:-}" ]] || aws configure get aws_access_key_id &>/dev/null; then
    if [[ "${ALLOW_STATIC_CREDS:-}" == "1" ]]; then
      warn "Using static credentials (ALLOW_STATIC_CREDS=1 override)"
      return 0
    fi
    fail "Static IAM credentials are not allowed for deployment."
    fail ""
    fail "This deployment requires temporary credentials with MFA."
    fail "To deploy, obtain temporary credentials with:"
    fail ""
    fail "  source tools/assume-deploy-role.sh"
    fail ""
    fail "Then re-run this script."
    warn "Emergency override: Set ALLOW_STATIC_CREDS=1 to bypass this check"
    exit 1
  fi

  die "No AWS credentials found. Run: source tools/assume-deploy-role.sh"
}

check_aws_credentials

# =============================================================================
# DEPLOYMENT PHASES
# =============================================================================

# ─── Phase 1: Deploy infrastructure ─────────────────────────────────────────
info "═══ Phase 1: Deploy infrastructure ═══"
# TODO: Deploy your infrastructure stacks here.
# Example for CDK:
#   run_in_dir "$WORKTREE_PATH/infra" npx cdk deploy --all \
#     --context stageName="$STAGE_NAME" \
#     --require-approval never \
#     ${HOTSWAP:+--hotswap} \
#     ${ALLOW_DELETIONS:---no-allow-deletions}
warn "Phase 1 not implemented — add your infrastructure deploy commands"

# ─── Phase 2: Build application with stack outputs ──────────────────────────
info "═══ Phase 2: Build application ═══"
# TODO: Extract stack outputs, rebuild frontend with real config.
# Example:
#   API_URL=$(python3 tools/cfn_output.py MyStack-$STAGE_NAME ApiEndpoint)
#   cd "$WORKTREE_PATH/frontend" && VITE_API_URL=$API_URL npm run build
warn "Phase 2 not implemented — add your application build commands"

# ─── Phase 3: Deploy application assets ─────────────────────────────────────
info "═══ Phase 3: Deploy application assets ═══"
# TODO: Deploy frontend stack / upload assets.
# Example:
#   run_in_dir "$WORKTREE_PATH/infra" npx cdk deploy FrontendStack-$STAGE_NAME
#   aws s3 sync "$WORKTREE_PATH/frontend/dist" "s3://$BUCKET_NAME/"
warn "Phase 3 not implemented — add your asset deploy commands"

# ─── Smoke tests ────────────────────────────────────────────────────────────
if $RUN_E2E; then
  info "═══ Running smoke tests ═══"
  if [[ -x "$WORKTREE_PATH/e2e/run_smoke.sh" ]]; then
    run "$WORKTREE_PATH/e2e/run_smoke.sh" "$STAGE_NAME"
  else
    warn "No e2e/run_smoke.sh found — skipping smoke tests"
  fi
fi

ok "Deploy complete for stage: $STAGE_NAME"

# ─── Merge (optional) ───────────────────────────────────────────────────────
merge_branch() {
  info "═══ Merging feature branch to master ═══"

  local feature_branch
  feature_branch=$(git -C "$WORKTREE_PATH" rev-parse --abbrev-ref HEAD)

  if [[ "$feature_branch" == "master" || "$feature_branch" == "main" ]]; then
    die "Cannot merge: worktree is on $feature_branch (expected a feature branch)"
  fi

  # Safety: check for deletions of protected paths
  local deletions
  deletions=$(git -C "$WORKTREE_PATH" diff --name-status master..."$feature_branch" | grep "^D" | awk '{print $2}' || true)
  if [[ -n "$deletions" ]]; then
    local protected_deletions=""
    while IFS= read -r file; do
      case "$file" in
        notes/*|tools/*|.claude/*) protected_deletions+="  $file"$'\n' ;;
      esac
    done <<< "$deletions"
    if [[ -n "$protected_deletions" ]]; then
      fail "Merge blocked — feature branch deletes protected files:"
      echo "$protected_deletions"
      die "Review these deletions. Use --allow-deletions to override."
    fi
  fi

  # Do the merge from the main repo
  run git -C "$SCRIPT_DIR" fetch origin master
  run git -C "$SCRIPT_DIR" checkout master
  run git -C "$SCRIPT_DIR" pull origin master
  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} git merge $feature_branch"
  else
    git -C "$SCRIPT_DIR" merge "$feature_branch" || die "Merge failed — resolve conflicts manually"
    git -C "$SCRIPT_DIR" push origin master || die "Push failed"
  fi
  ok "Merged $feature_branch into master and pushed"
}

if $DO_MERGE; then
  merge_branch
fi

# ─── Cleanup (optional) ─────────────────────────────────────────────────────
if $DO_CLEANUP; then
  info "═══ Cleaning up stage ═══"
  if [[ -x "$SCRIPT_DIR/branch_teardown.sh" ]]; then
    run "$SCRIPT_DIR/branch_teardown.sh" "$WORKTREE_PATH"
  else
    warn "No branch_teardown.sh found — skipping cleanup"
  fi
fi

ok "All done!"
