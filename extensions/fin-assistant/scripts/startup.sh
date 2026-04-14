#!/usr/bin/env bash
# =============================================================================
# startup.sh — fires on WSL2 wake (@reboot cron) to recover missed jobs
#
# Handles:
#   - Bridge restart (WSL2 network stack resets on every wake)
#   - NSE symbol refresh  (7:30 AM IST) — missed while laptop was off overnight
#   - Weekly scorecard    (Mon 8:00 AM IST) — missed if Monday morning wakeup
#   - Preopen             (8:45 AM IST) — belt-and-suspenders before watchdog fires
#
# Crontab entry (added automatically by install.sh):
#   @reboot sleep 20 && cd /root/fin-assistant && bash scripts/startup.sh >> logs/startup.log 2>&1
# =============================================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HB_DIR="${REPO_DIR}/logs/heartbeats"
PYTHON=/usr/bin/python3

mkdir -p "$HB_DIR" "${REPO_DIR}/logs"

log() { echo "[$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST')] $*"; }

# Load credentials
if [[ -f "${REPO_DIR}/.env" ]]; then
    set -a
    source <(grep -E '^(BOT_TOKEN|OWNER_CHAT_ID)=' "${REPO_DIR}/.env")
    set +a
fi

send_telegram() {
    local msg="$1"
    [[ -z "${BOT_TOKEN:-}" || -z "${OWNER_CHAT_ID:-}" ]] && return
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${OWNER_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="$msg" > /dev/null 2>&1 || true
}

ran_today() {
    local job="$1"
    local hb="${HB_DIR}/${job}.last_ok"
    [[ ! -f "$hb" ]] && return 1
    local last_ok
    last_ok=$(cat "$hb" 2>/dev/null | cut -c1-10)
    [[ ! "$last_ok" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && return 1
    local today
    today=$(TZ=Asia/Kolkata date '+%Y-%m-%d')
    [[ "$last_ok" == "$today" ]]
}

IST_HOUR=$(TZ=Asia/Kolkata date '+%H')
IST_MIN=$(TZ=Asia/Kolkata date '+%M')
IST_TIME=$(( IST_HOUR * 60 + IST_MIN ))
WEEKDAY=$(date '+%u')   # 1=Mon ... 7=Sun

log "=== Startup (IST ${IST_HOUR}:${IST_MIN}, weekday=${WEEKDAY}) ==="

ACTIONS=()

# ── Bridge restart ────────────────────────────────────────────────────────────
# WSL2 resets the network stack on every wake/sleep cycle.
# Always restart so Pyrogram gets a fresh connection instead of a stale zombie.
if systemctl is-active --quiet fin-bridge 2>/dev/null; then
    log "Bridge active — restarting for clean wake connection"
    systemctl restart fin-bridge 2>/dev/null \
        && ACTIONS+=("bridge restarted (clean wake)") \
        || log "Bridge restart failed"
else
    log "Bridge inactive — starting"
    systemctl start fin-bridge 2>/dev/null \
        && ACTIONS+=("bridge started") \
        || log "Bridge start failed"
fi
sleep 5   # let bridge establish session before running scripts that need DB

# ── NSE symbol refresh (weekdays, 7:30 AM IST = 450 min) ─────────────────────
if [[ $WEEKDAY -le 5 && $IST_TIME -ge 450 ]] && ! ran_today "nse_symbols"; then
    log "NSE symbol refresh missed — running"
    if bash "${REPO_DIR}/scripts/cron_guard.sh" nse_symbols \
            "$PYTHON" scripts/refresh_nse_symbols.py \
            >> "${REPO_DIR}/logs/nse_symbols.log" 2>&1; then
        ACTIONS+=("nse_symbols refresh OK")
    else
        log "nse_symbols refresh FAILED"
    fi
fi

# ── Weekly scorecard (Monday, 8:00 AM IST = 480 min) ─────────────────────────
if [[ $WEEKDAY -eq 1 && $IST_TIME -ge 480 ]] && ! ran_today "weekly"; then
    log "Weekly scorecard missed — running"
    if bash "${REPO_DIR}/scripts/cron_guard.sh" weekly_startup \
            "$PYTHON" main.py weekly \
            >> "${REPO_DIR}/logs/cron.log" 2>&1; then
        ACTIONS+=("weekly scorecard OK")
    else
        log "weekly scorecard FAILED"
    fi
fi

# ── Preopen (weekdays, 8:45–9:30 AM IST = 525–570 min) ───────────────────────
# Watchdog also covers preopen; this fires first on wakeup before watchdog slot.
if [[ $WEEKDAY -le 5 && $IST_TIME -ge 525 && $IST_TIME -le 570 ]] \
        && ! ran_today "preopen"; then
    log "Preopen missed — running"
    if bash "${REPO_DIR}/scripts/cron_guard.sh" preopen_startup \
            "$PYTHON" main.py preopen \
            >> "${REPO_DIR}/logs/cron.log" 2>&1; then
        ACTIONS+=("preopen OK")
    else
        log "preopen FAILED"
    fi
fi

# ── Tests (background — don't block startup) ─────────────────────────────────
# run_tests.sh has its own market-hours gate and "ran today" guard
bash "${REPO_DIR}/scripts/run_tests.sh" >> "${REPO_DIR}/logs/tests.log" 2>&1 &

# ── Report ────────────────────────────────────────────────────────────────────
if [[ ${#ACTIONS[@]} -gt 0 ]]; then
    MSG="[STARTUP] WSL2 wake recovery"$'\n'
    for a in "${ACTIONS[@]}"; do
        MSG+="[OK] ${a}"$'\n'
    done
    send_telegram "$MSG"
    log "Actions: ${ACTIONS[*]}"
else
    log "Nothing to recover — all jobs on track"
fi

log "=== Startup done ==="
