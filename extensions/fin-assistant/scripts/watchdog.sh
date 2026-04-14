#!/usr/bin/env bash
# =============================================================================
# watchdog.sh -- cron-based failover for critical jobs
#
# Runs every 30 minutes during market day.
# Checks heartbeat files written by cron_guard.sh after each successful run.
# If a critical job missed its window or its heartbeat shows a past date,
# re-runs it once and alerts via Telegram on what it did.
#
# This is completely independent of cron_guard -- it acts as a second layer
# that catches anything cron_guard missed or could not recover.
#
# Crontab entry (added automatically by install.sh):
#   */30 2-11 * * 1-5 cd /root/fin-assistant && bash scripts/watchdog.sh >> logs/watchdog.log 2>&1
# =============================================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HB_DIR="${REPO_DIR}/logs/heartbeats"
LOG="${REPO_DIR}/logs/watchdog.log"
PYTHON=/usr/bin/python3

mkdir -p "${HB_DIR}"

# Load credentials
if [[ -f "${REPO_DIR}/.env" ]]; then
    set -a
    source <(grep -E '^(BOT_TOKEN|OWNER_CHAT_ID)=' "${REPO_DIR}/.env")
    set +a
fi

log() { echo "[$(date '+%H:%M:%S')] $*"; }

send_telegram() {
    local msg="$1"
    [[ -z "${BOT_TOKEN:-}" || -z "${OWNER_CHAT_ID:-}" ]] && return
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${OWNER_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="$msg" > /dev/null 2>&1 || true
}

# Returns 0 if job ran successfully today, 1 if not
ran_today() {
    local job="$1"
    local hb="${HB_DIR}/${job}.last_ok"
    [[ ! -f "$hb" ]] && return 1
    local last_ok
    last_ok=$(cat "$hb" 2>/dev/null | cut -c1-10)   # first 10 chars = YYYY-MM-DD
    # Validate format before comparing to avoid corrupt files passing the check
    if [[ ! "$last_ok" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        return 1
    fi
    local today
    today=$(TZ=Asia/Kolkata date '+%Y-%m-%d')   # IST — consistent with scheduler.py
    [[ "$last_ok" == "$today" ]]
}

run_job() {
    local job="$1"
    shift
    log "Re-running: ${job}"
    bash "${REPO_DIR}/scripts/cron_guard.sh" "${job}_watchdog" "$@"
    return $?
}

# Current IST hour/minute (UTC+5:30)
IST_HOUR=$(TZ=Asia/Kolkata date '+%H')
IST_MIN=$(TZ=Asia/Kolkata date '+%M')
IST_TIME=$(( IST_HOUR * 60 + IST_MIN ))  # minutes since midnight IST
WEEKDAY=$(date '+%u')   # 1=Mon ... 5=Fri ... 7=Sun

log "=== Watchdog starting (IST ${IST_HOUR}:${IST_MIN} weekday=${WEEKDAY}) ==="

# NSE public holidays 2026 — equity/cash segment (weekday closures only)
# Update annually when NSE publishes the next year's circular.
NSE_HOLIDAYS_2026=(
    "2026-01-26"   # Republic Day
    "2026-03-03"   # Holi
    "2026-03-26"   # Shri Ram Navami
    "2026-03-31"   # Shri Mahavir Jayanti
    "2026-04-03"   # Good Friday
    "2026-04-14"   # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01"   # Maharashtra Day
    "2026-05-28"   # Bakri Id (Eid ul-Adha)
    "2026-06-26"   # Muharram
    "2026-09-14"   # Ganesh Chaturthi
    "2026-10-02"   # Mahatma Gandhi Jayanti
    "2026-10-20"   # Dussehra
    "2026-11-10"   # Diwali — Balipratipada
    "2026-11-24"   # Prakash Gurpurb (Guru Nanak Jayanti)
    "2026-12-25"   # Christmas
)

is_market_open() {
    local today
    today=$(TZ=Asia/Kolkata date '+%Y-%m-%d')
    for h in "${NSE_HOLIDAYS_2026[@]}"; do
        [[ "$h" == "$today" ]] && return 1   # holiday → market closed
    done
    return 0   # open
}

# Only act on weekdays and non-holidays
if [[ $WEEKDAY -ge 6 ]]; then
    log "Weekend -- nothing to watch"
    exit 0
fi
if ! is_market_open; then
    log "NSE holiday -- nothing to watch"
    exit 0
fi

ACTIONS=()
FAILURES=()

# ── Bridge self-heal (laptop sleep / WSL2 network drop) ───────────────────────
# During market hours, if the last DB message is >90 min old the bridge has
# likely gone dead after a sleep/wake cycle.  Fix: stop → fetch backfill →
# restart → fire scanner immediately so we don't wait for the next cron slot.
BRIDGE_STALE_MINS=15
if [[ $IST_TIME -ge 555 && $IST_TIME -le 930 ]]; then   # 09:15–15:30 IST
    LAST_MSG_AGO=$(${PYTHON} -c "
import sqlite3, sys
sys.path.insert(0, '${REPO_DIR}')
from config import DB_PATH
from datetime import datetime, timezone
try:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    row  = conn.execute('SELECT MAX(timestamp) FROM messages').fetchone()
    conn.close()
    if not row or not row[0]:
        print(9999)
    else:
        last = datetime.fromisoformat(row[0].replace('Z','+00:00'))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        diff = (datetime.now(timezone.utc) - last).total_seconds() / 60
        print(int(diff))
except Exception as e:
    print(9999)
" 2>/dev/null || echo 9999)

    # Also detect zombie state: bridge service active but HandlerTasks not in log
    # (reconnected after network drop but never started message handlers)
    BRIDGE_ZOMBIE=0
    if systemctl is-active --quiet fin-bridge; then
        HANDLER_STARTED=$(grep "HandlerTasks" "${REPO_DIR}/logs/bridge.log" 2>/dev/null | tail -1 | cut -c1-19 || echo "")
        LAST_RESTART=$(systemctl show fin-bridge --property=ActiveEnterTimestamp --value 2>/dev/null | cut -c1-19 || echo "")
        if [[ -n "$HANDLER_STARTED" && -n "$LAST_RESTART" ]]; then
            # If last HandlerTasks log line is BEFORE the last service start → zombie
            if [[ "$HANDLER_STARTED" < "$LAST_RESTART" ]]; then
                BRIDGE_ZOMBIE=1
                log "Bridge zombie detected (connected but HandlerTasks not running)"
            fi
        fi
    fi

    if [[ "${LAST_MSG_AGO}" -ge "${BRIDGE_STALE_MINS}" || "${BRIDGE_ZOMBIE}" -eq 1 ]]; then
        REASON="stale ${LAST_MSG_AGO} min"
        [[ "${BRIDGE_ZOMBIE}" -eq 1 ]] && REASON="zombie (no HandlerTasks)"
        log "Bridge self-healing (${REASON}) — stop → fetch → restart → scan"
        systemctl stop fin-bridge 2>/dev/null || true
        sleep 3
        ${PYTHON} bridge/fetch.py 1 500 >> "${REPO_DIR}/logs/bridge_fetch.log" 2>&1 \
            && log "Fetch OK" || log "Fetch failed (continuing)"
        systemctl start fin-bridge 2>/dev/null || true
        sleep 5
        # Fire all three scanner modes to catch up on missed signals
        ${PYTHON} main.py hourly            >> "${REPO_DIR}/logs/cron.log"         2>&1 &
        ${PYTHON} main.py hourly --mode stocks   >> "${REPO_DIR}/logs/cron_stocks.log"  2>&1 &
        ${PYTHON} main.py hourly --mode futures  >> "${REPO_DIR}/logs/cron_futures.log" 2>&1 &
        wait
        ACTIONS+=("bridge self-heal: ${REASON}")
    fi
fi

# ── preopen: should run at 8:45 AM IST ───────────────────────────────────────
# Check after 9:00 AM (540 min)
if [[ $IST_TIME -ge 540 ]] && ! ran_today "preopen"; then
    log "preopen missed -- re-running"
    if run_job "preopen" "${PYTHON}" main.py preopen; then
        ACTIONS+=("preopen re-run OK")
    else
        FAILURES+=("preopen re-run FAILED")
    fi
fi

# ── hourly indices: 9:45–15:15 IST ───────────────────────────────────────────
# Check after 10:45 AM (645 min) -- if no heartbeat at all today
if [[ $IST_TIME -ge 645 ]] && ! ran_today "hourly_indices"; then
    log "hourly indices missed -- re-running"
    if run_job "hourly_indices" "${PYTHON}" main.py hourly; then
        ACTIONS+=("hourly indices re-run OK")
    else
        FAILURES+=("hourly indices re-run FAILED")
    fi
fi

# ── hourly stocks: 9:50–15:20 IST ────────────────────────────────────────────
if [[ $IST_TIME -ge 650 ]] && ! ran_today "hourly_stocks"; then
    log "hourly stocks missed -- re-running"
    if run_job "hourly_stocks" "${PYTHON}" main.py hourly --mode stocks; then
        ACTIONS+=("hourly stocks re-run OK")
    else
        FAILURES+=("hourly stocks re-run FAILED")
    fi
fi

# ── hourly futures: 9:55–15:25 IST ───────────────────────────────────────────
if [[ $IST_TIME -ge 655 ]] && ! ran_today "hourly_futures"; then
    log "hourly futures missed -- re-running"
    if run_job "hourly_futures" "${PYTHON}" main.py hourly --mode futures; then
        ACTIONS+=("hourly futures re-run OK")
    else
        FAILURES+=("hourly futures re-run FAILED")
    fi
fi

# ── eod: should run at 3:45 PM IST (945 min) ─────────────────────────────────
# Check after 4:15 PM (975 min)
if [[ $IST_TIME -ge 975 ]] && ! ran_today "eod"; then
    log "eod missed -- re-running"
    if run_job "eod" "${PYTHON}" main.py eod; then
        ACTIONS+=("eod re-run OK")
    else
        FAILURES+=("eod re-run FAILED")
    fi
fi

# ── amc_report: primary at 4:15 PM IST (975 min), check after 5:15 PM (1035) ─
# Cron retries at 5:15/6:15/7:15 PM handle normal delays; watchdog is last resort
if [[ $IST_TIME -ge 1035 ]] && ! ran_today "amc_report"; then
    log "amc_report missed -- re-running"
    if run_job "amc_report" "${PYTHON}" main.py amc-report; then
        ACTIONS+=("amc_report re-run OK")
    else
        FAILURES+=("amc_report re-run FAILED")
    fi
fi

# ── Report ────────────────────────────────────────────────────────────────────
if [[ ${#ACTIONS[@]} -eq 0 && ${#FAILURES[@]} -eq 0 ]]; then
    log "All jobs on track -- nothing to do"
    exit 0
fi

MSG="[WATCHDOG] Recovered missed cron jobs"$'\n'
for a in "${ACTIONS[@]}"; do
    MSG+="[OK] ${a}"$'\n'
    log "${a}"
done
for f in "${FAILURES[@]}"; do
    MSG+="[FAIL] ${f}"$'\n'
    log "${f}"
done

send_telegram "$MSG"
log "=== Watchdog done ==="

[[ ${#FAILURES[@]} -gt 0 ]] && exit 1 || exit 0
