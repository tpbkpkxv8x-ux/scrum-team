#!/usr/bin/env bash
# =============================================================================
# Branch Teardown — Destroy a staging environment and clean up worktree
# =============================================================================
#
# Tears down cloud resources deployed by branch_deploy.sh and optionally
# removes the git worktree.
#
# Usage:
#   ./branch_teardown.sh <worktree-path> [--remove-worktree]
#
# Options:
#   --remove-worktree  Also remove the git worktree after destroying stacks
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
REMOVE_WORKTREE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove-worktree) REMOVE_WORKTREE=true; shift ;;
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

[[ -n "$WORKTREE_PATH" ]] || die "Usage: $0 <worktree-path> [--remove-worktree]"
[[ -d "$WORKTREE_PATH" ]] || die "Worktree path does not exist: $WORKTREE_PATH"

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

info "Tearing down stage: $STAGE_NAME"
info "Worktree: $WORKTREE_PATH"

# ─── AWS credential check ───────────────────────────────────────────────────
if [[ -z "${AWS_SESSION_TOKEN:-}" ]]; then
  if [[ "${ALLOW_STATIC_CREDS:-}" != "1" ]]; then
    die "Temporary AWS credentials required. Run: source tools/assume-deploy-role.sh"
  fi
  warn "Using static credentials (ALLOW_STATIC_CREDS=1 override)"
fi

# ─── Destroy stacks ─────────────────────────────────────────────────────────
info "═══ Destroying cloud resources ═══"
# TODO: List your stacks in reverse dependency order and destroy them.
# Example for CDK:
#   cd "$WORKTREE_PATH/infra"
#   npx cdk destroy FrontendStack-$STAGE_NAME --force
#   npx cdk destroy BackendStack-$STAGE_NAME --force
#   npx cdk destroy DatabaseStack-$STAGE_NAME --force
warn "Stack destruction not implemented — add your teardown commands"

# ─── Remove worktree (optional) ─────────────────────────────────────────────
if $REMOVE_WORKTREE; then
  info "═══ Removing git worktree ═══"
  BRANCH_NAME=$(git -C "$WORKTREE_PATH" rev-parse --abbrev-ref HEAD 2>/dev/null || true)

  # Check if branch is merged
  if [[ -n "$BRANCH_NAME" ]] && [[ "$BRANCH_NAME" != "master" ]] && [[ "$BRANCH_NAME" != "main" ]]; then
    if git -C "$SCRIPT_DIR" branch --merged master | grep -q "$BRANCH_NAME"; then
      info "Branch $BRANCH_NAME is merged into master"
    else
      warn "Branch $BRANCH_NAME is NOT merged into master"
      warn "Use 'python3 worktree_setup.py teardown <agent> <desc> --force' to remove unmerged worktrees"
    fi
  fi

  # Use worktree_setup.py if available
  if [[ -f "$SCRIPT_DIR/worktree_setup.py" ]]; then
    info "Use worktree_setup.py to remove the worktree:"
    info "  python3 $SCRIPT_DIR/worktree_setup.py teardown <agent-name> <branch-desc>"
  else
    git -C "$SCRIPT_DIR" worktree remove "$WORKTREE_PATH" --force
    if [[ -n "$BRANCH_NAME" ]]; then
      git -C "$SCRIPT_DIR" branch -d "$BRANCH_NAME" 2>/dev/null || true
    fi
  fi
  ok "Worktree removed"
fi

ok "Teardown complete for stage: $STAGE_NAME"
