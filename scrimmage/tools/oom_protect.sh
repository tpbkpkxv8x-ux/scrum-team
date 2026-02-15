#!/usr/bin/env bash
# OOM protection for Claude Code agent processes.
# Lowers oom_score_adj so the OOM killer prefers other targets.
#
# Must be run as root:
#   sudo ./scrimmage/tools/oom_protect.sh
#
# Options:
#   --score N    : oom_score_adj value (default: -500, range: -1000 to 1000)
#                  -1000 = never kill, -500 = strongly prefer not to kill
#   --watch      : keep running, protecting new claude processes as they spawn
#   --interval N : seconds between scans in watch mode (default: 5)
#   --dry-run    : show what would be changed without writing

set -euo pipefail

SCORE=-500
WATCH=false
INTERVAL=5
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --score)    SCORE="$2"; shift 2 ;;
        --watch)    WATCH=true; shift ;;
        --interval) INTERVAL="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--score N] [--watch] [--interval N] [--dry-run]"
            echo ""
            echo "  --score N    oom_score_adj value (default: -500)"
            echo "  --watch      continuously protect new processes"
            echo "  --interval N scan interval in watch mode (default: 5s)"
            echo "  --dry-run    show changes without applying"
            exit 0
            ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [[ "$SCORE" -lt -1000 || "$SCORE" -gt 1000 ]]; then
    echo "Error: --score must be between -1000 and 1000"
    exit 1
fi

if [[ "$(id -u)" -ne 0 && "$DRY_RUN" = false ]]; then
    echo "Error: must be run as root (oom_score_adj requires root for negative values)"
    exit 1
fi

# Check if the container has CAP_SYS_RESOURCE (needed for negative oom_score_adj)
check_capability() {
    if [[ "$SCORE" -ge 0 ]]; then
        return 0  # positive values don't need the capability
    fi
    # Try writing to our own process first as a capability test
    local self_adj="/proc/$$/oom_score_adj"
    local original
    original=$(cat "$self_adj" 2>/dev/null) || return 1
    if ! echo "$SCORE" > "$self_adj" 2>/dev/null; then
        return 1
    fi
    # Restore original value
    echo "$original" > "$self_adj" 2>/dev/null
    return 0
}

if [[ "$DRY_RUN" = false ]] && ! check_capability; then
    echo "ERROR: Cannot set negative oom_score_adj — container lacks CAP_SYS_RESOURCE."
    echo ""
    echo "Fix: add the capability when launching the container:"
    echo "  docker run --cap-add=SYS_RESOURCE ..."
    echo ""
    echo "Or in docker-compose.yml:"
    echo "  cap_add:"
    echo "    - SYS_RESOURCE"
    echo ""
    echo "Alternatively, use a non-negative score (--score 0) to reset processes to default."
    exit 1
fi

# Track which PIDs we've already protected (avoid redundant writes)
declare -A PROTECTED_PIDS

protect_processes() {
    local count=0

    # Find all claude/node processes related to Claude Code agents
    # Match: claude, node (claude code runs as node), python3 (agent subprocesses)
    while IFS= read -r line; do
        local pid comm
        pid=$(echo "$line" | awk '{print $1}')
        comm=$(echo "$line" | awk '{print $2}')

        # Skip if already protected
        if [[ -n "${PROTECTED_PIDS[$pid]:-}" ]]; then
            continue
        fi

        # Verify process still exists
        if [[ ! -f "/proc/$pid/oom_score_adj" ]]; then
            continue
        fi

        local current
        current=$(cat "/proc/$pid/oom_score_adj" 2>/dev/null) || continue

        if [[ "$current" -eq "$SCORE" ]]; then
            PROTECTED_PIDS[$pid]=1
            continue
        fi

        if [[ "$DRY_RUN" = true ]]; then
            echo "[dry-run] PID $pid ($comm): oom_score_adj $current -> $SCORE"
        else
            echo "$SCORE" > "/proc/$pid/oom_score_adj" 2>/dev/null && {
                echo "Protected PID $pid ($comm): oom_score_adj $current -> $SCORE"
                PROTECTED_PIDS[$pid]=1
                ((count++))
            } || {
                echo "Warning: failed to protect PID $pid ($comm)"
            }
        fi
    done < <(ps -eo pid,comm --no-headers | grep -E '(claude|node|anthropic)' | awk '{print $1, $2}')

    # Also protect tmux server and any python3 processes in the workspace
    while IFS= read -r line; do
        local pid cmdline
        pid=$(echo "$line" | awk '{print $1}')

        if [[ -n "${PROTECTED_PIDS[$pid]:-}" ]]; then
            continue
        fi

        if [[ ! -f "/proc/$pid/oom_score_adj" ]]; then
            continue
        fi

        # Check if this python3 is running something in our workspace
        cmdline=$(cat "/proc/$pid/cmdline" 2>/dev/null | tr '\0' ' ') || continue
        if [[ "$cmdline" != *"/workspace/"* && "$cmdline" != *"backlog"* ]]; then
            continue
        fi

        local current
        current=$(cat "/proc/$pid/oom_score_adj" 2>/dev/null) || continue

        if [[ "$current" -eq "$SCORE" ]]; then
            PROTECTED_PIDS[$pid]=1
            continue
        fi

        if [[ "$DRY_RUN" = true ]]; then
            echo "[dry-run] PID $pid (python3-workspace): oom_score_adj $current -> $SCORE"
        else
            echo "$SCORE" > "/proc/$pid/oom_score_adj" 2>/dev/null && {
                echo "Protected PID $pid (python3-workspace): oom_score_adj $current -> $SCORE"
                PROTECTED_PIDS[$pid]=1
                ((count++))
            } || true
        fi
    done < <(ps -eo pid,comm --no-headers | grep python3 | awk '{print $1, $2}')

    # Clean up stale PIDs from tracking
    for pid in "${!PROTECTED_PIDS[@]}"; do
        if [[ ! -d "/proc/$pid" ]]; then
            unset "PROTECTED_PIDS[$pid]"
        fi
    done

    if [[ $count -gt 0 ]]; then
        echo "--- Protected $count new process(es) (score=$SCORE, total tracked: ${#PROTECTED_PIDS[@]})"
    fi
}

echo "OOM Protector — score=$SCORE, watch=$WATCH, interval=${INTERVAL}s"
echo ""

protect_processes

if [[ "$WATCH" = true ]]; then
    echo ""
    echo "Watching for new processes every ${INTERVAL}s... (Ctrl+C to stop)"
    while true; do
        sleep "$INTERVAL"
        protect_processes
    done
fi
