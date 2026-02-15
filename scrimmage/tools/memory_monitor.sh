#!/usr/bin/env bash
# Memory pressure monitor for multi-agent scrimmage sessions.
# Runs in a tmux pane and warns when memory usage gets high.
#
# Usage: ./scrimmage/tools/memory_monitor.sh [--interval SECS] [--warn PCT] [--critical PCT]
#
# Thresholds:
#   --warn     : yellow warning threshold (default: 70%)
#   --critical : red critical threshold (default: 85%)
#   --interval : check interval in seconds (default: 10)

set -euo pipefail

INTERVAL=10
WARN_PCT=70
CRIT_PCT=85
FLASH=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval)  INTERVAL="$2"; shift 2 ;;
        --warn)      WARN_PCT="$2"; shift 2 ;;
        --critical)  CRIT_PCT="$2"; shift 2 ;;
        --no-flash)  FLASH=false; shift ;;
        *)           echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ANSI colors
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

get_memory_stats() {
    local mem_total mem_available mem_used swap_total swap_free swap_used
    mem_total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
    mem_available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    swap_total=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
    swap_free=$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)

    mem_used=$((mem_total - mem_available))
    swap_used=$((swap_total - swap_free))

    echo "$mem_total $mem_available $mem_used $swap_total $swap_free $swap_used"
}

kb_to_gb() {
    awk "BEGIN {printf \"%.1f\", $1 / 1048576}"
}

kb_to_mb() {
    awk "BEGIN {printf \"%.0f\", $1 / 1024}"
}

top_memory_consumers() {
    # Show top 5 memory-consuming process trees (by RSS)
    ps -eo pid,rss,comm --sort=-rss 2>/dev/null | head -6 | tail -5 | while read pid rss comm; do
        if [[ "$rss" =~ ^[0-9]+$ ]] && [ "$rss" -gt 0 ]; then
            echo "    PID $pid  $(kb_to_mb "$rss") MB  $comm"
        fi
    done
}

# iTerm2 background flash via proprietary escape sequences.
# Works inside tmux (uses DCS passthrough) and bare iTerm2.
iterm2_set_bg() {
    local hex="$1"  # e.g. "ff0000" or "default"
    local osc="\033]1337;SetColors=bg=${hex}\a"
    if [[ -n "${TMUX:-}" ]]; then
        # tmux DCS passthrough
        printf "\033Ptmux;\033%b\033\\\\" "$osc"
    else
        printf "%b" "$osc"
    fi
}

flash_red() {
    [[ "$FLASH" = true ]] || return 0
    iterm2_set_bg "ff0000"
    sleep 0.3
    iterm2_set_bg "330000"  # dark red — keeps urgency visible
}

flash_reset() {
    [[ "$FLASH" = true ]] || return 0
    iterm2_set_bg "default"
}

# Reset background on exit so we don't leave the terminal red
trap 'flash_reset; exit' INT TERM EXIT

prev_level=""

echo -e "${BOLD}${CYAN}Memory Monitor${RESET} — checking every ${INTERVAL}s (warn: ${WARN_PCT}%, critical: ${CRIT_PCT}%)"
echo ""

while true; do
    read -r mem_total mem_available mem_used swap_total swap_free swap_used <<< "$(get_memory_stats)"

    if [ "$mem_total" -eq 0 ]; then
        sleep "$INTERVAL"
        continue
    fi

    pct_used=$((mem_used * 100 / mem_total))
    pct_swap=0
    if [ "$swap_total" -gt 0 ]; then
        pct_swap=$((swap_used * 100 / swap_total))
    fi

    timestamp=$(date '+%H:%M:%S')

    if [ "$pct_used" -ge "$CRIT_PCT" ]; then
        level="CRITICAL"
        color="$RED"
    elif [ "$pct_used" -ge "$WARN_PCT" ]; then
        level="WARNING"
        color="$YELLOW"
    else
        level="OK"
        color="$GREEN"
    fi

    # Always show status line
    printf "\r${BOLD}${color}[%s]${RESET} RAM: %s/%s GB (%d%%) | Swap: %s/%s MB (%d%%)    " \
        "$timestamp" \
        "$(kb_to_gb "$mem_used")" "$(kb_to_gb "$mem_total")" "$pct_used" \
        "$(kb_to_mb "$swap_used")" "$(kb_to_mb "$swap_total")" "$pct_swap"

    # On level change, update iTerm2 background and print detailed info
    if [ "$level" != "$prev_level" ]; then
        if [ "$level" = "CRITICAL" ]; then
            flash_red
        elif [ "$level" = "OK" ]; then
            flash_reset
        elif [ "$level" = "WARNING" ]; then
            flash_reset  # clear any red from prior critical state
        fi

        if [ "$level" != "OK" ]; then
            echo ""
            echo -e "${BOLD}${color}*** MEMORY ${level} — ${pct_used}% used ***${RESET}"
            echo -e "  Available: $(kb_to_gb "$mem_available") GB | Swap used: $(kb_to_mb "$swap_used") MB / $(kb_to_mb "$swap_total") MB"
            echo "  Top consumers:"
            top_memory_consumers
            if [ "$level" = "CRITICAL" ]; then
                echo -e "${RED}${BOLD}  Consider shutting down idle agents to free memory!${RESET}"
            fi
            echo ""
        fi
    fi

    prev_level="$level"
    sleep "$INTERVAL"
done
