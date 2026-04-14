#!/usr/bin/env bash
# =============================================================================
# run_tests.sh — automated test runner
#
# Fires on WSL2 wake (@reboot via startup.sh) and via a 30-min cron.
# Guards:
#   1. Already ran today → skip
#   2. Market hours (9:00–15:45 IST) → defer (don't add load during live trading)
#
# On completion: writes heartbeat + sends Telegram summary.
# =============================================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HB_DIR="${REPO_DIR}/logs/heartbeats"
LOG="${REPO_DIR}/logs/tests.log"
REPORT="${REPO_DIR}/logs/test_report.txt"
PYTHON=/usr/bin/python3

mkdir -p "$HB_DIR" "$(dirname "$LOG")"

log() { echo "[$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST')] $*" | tee -a "$LOG"; }

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

# ── Guard 1: already ran today ───────────────────────────────────────────────
HB="${HB_DIR}/tests.last_ok"
TODAY=$(TZ=Asia/Kolkata date '+%Y-%m-%d')
if [[ -f "$HB" ]]; then
    LAST=$(cat "$HB" 2>/dev/null | cut -c1-10)
    if [[ "$LAST" == "$TODAY" ]]; then
        log "Tests already ran today — skipping"
        exit 0
    fi
fi

# ── Guard 2: defer during market hours (9:00–15:45 IST) ─────────────────────
IST_HOUR=$(TZ=Asia/Kolkata date '+%H')
IST_MIN=$(TZ=Asia/Kolkata date '+%M')
IST_TIME=$(( IST_HOUR * 60 + IST_MIN ))
WEEKDAY=$(date '+%u')

if [[ $WEEKDAY -le 5 && $IST_TIME -ge 540 && $IST_TIME -le 945 ]]; then
    log "Market hours (${IST_HOUR}:${IST_MIN} IST) — deferring tests until close"
    exit 0
fi

# ── Run tests ────────────────────────────────────────────────────────────────
log "=== Running test suite ==="
cd "$REPO_DIR"

# Ensure test dependencies are installed
$PYTHON -m pytest --version > /dev/null 2>&1 || {
    log "pytest not found — installing dev dependencies"
    make install-dev >> "$LOG" 2>&1
}

# Run with machine-readable output
make test-report >> "$LOG" 2>&1
EXIT_CODE=$?

# ── Parse results ────────────────────────────────────────────────────────────
PASSED=$(grep -oP '\d+(?= passed)' "$REPORT" | tail -1 || echo 0)
FAILED=$(grep -oP '\d+(?= failed)' "$REPORT" | tail -1 || echo 0)
ERRORS=$(grep -oP '\d+(?= error)'  "$REPORT" | tail -1 || echo 0)

# Collect failure diagnosis via AI debug agent
FAIL_LINES=""
if [[ "${FAILED:-0}" -gt 0 || "${ERRORS:-0}" -gt 0 ]]; then
    # Try the AI agent first (haiku, ~5s); fall back to raw FAILED lines
    DIAGNOSIS=$(bash "${REPO_DIR}/scripts/test_debug_agent.sh" "$REPORT" 2>/dev/null)
    if [[ -n "$DIAGNOSIS" && "$DIAGNOSIS" != *"debug agent:"* ]]; then
        FAIL_LINES="$DIAGNOSIS"
    else
        FAIL_LINES=$(grep -E "^FAILED|^ERROR" "$REPORT" 2>/dev/null | head -10 \
            | sed 's/^/  /' || echo "  (see logs/test_report.txt)")
    fi
fi

# ── Write heartbeat ──────────────────────────────────────────────────────────
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "$(TZ=Asia/Kolkata date --iso-8601=seconds)" > "$HB"
fi

# ── Telegram notification ────────────────────────────────────────────────────
if [[ "${FAILED:-0}" -eq 0 && "${ERRORS:-0}" -eq 0 ]]; then
    STATUS="[OK] All tests passed"
    MSG="[TESTS] <b>${STATUS}</b>
${PASSED} passed  |  $(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M IST')"
else
    STATUS="[FAIL] Tests failed"
    MSG="[TESTS] <b>${STATUS}</b>
${PASSED} passed  |  ${FAILED} failed  |  ${ERRORS} errors
$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M IST')

${FAIL_LINES}"
fi

send_telegram "$MSG"
log "$STATUS — passed=${PASSED} failed=${FAILED} errors=${ERRORS}"
log "=== Test run complete ==="

exit $EXIT_CODE
