#!/usr/bin/env bash
# =============================================================================
# coverage_agent.sh — weekly test coverage gap detector
#
# Finds Python source files changed in the last 7 days that have no
# corresponding test file.  Sends a Telegram summary so gaps don't silently
# accumulate.  Runs Sunday after market close (see crontab).
#
# No API calls — pure bash/git.  Fast and zero-cost to run.
# =============================================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${REPO_DIR}/logs/coverage_agent.log"
HB_DIR="${REPO_DIR}/logs/heartbeats"
HB="${HB_DIR}/coverage_agent.last_ok"
TODAY=$(TZ=Asia/Kolkata date '+%Y-%m-%d')

mkdir -p "$HB_DIR" "$(dirname "$LOG")"

log() { echo "[$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST')] $*" | tee -a "$LOG"; }

# ── Guard: already ran this week ─────────────────────────────────────────────
if [[ -f "$HB" ]]; then
    LAST=$(cat "$HB" 2>/dev/null | cut -c1-10)
    # Skip if ran within the last 6 days
    LAST_EPOCH=$(date -d "$LAST" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    AGE_DAYS=$(( (NOW_EPOCH - LAST_EPOCH) / 86400 ))
    if [[ $AGE_DAYS -lt 6 ]]; then
        log "Coverage agent ran ${AGE_DAYS}d ago — skipping"
        exit 0
    fi
fi

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

cd "$REPO_DIR"

# ── Find changed Python source files (last 7 days, non-test) ─────────────────
CHANGED_FILES=$(git log \
    --since="7 days ago" \
    --name-only \
    --diff-filter=AM \
    --pretty="" \
    -- '*.py' \
    | grep -v "^tests/" \
    | grep -v "conftest\.py" \
    | grep -v "^scripts/" \
    | sort -u 2>/dev/null || true)

if [[ -z "$CHANGED_FILES" ]]; then
    log "No source files changed in last 7 days — nothing to check"
    echo "$TODAY" > "$HB"
    exit 0
fi

# ── Check each changed file for test coverage ────────────────────────────────
GAPS=()
COVERED=()

while IFS= read -r src_file; do
    [[ -z "$src_file" ]] && continue
    [[ ! -f "$src_file" ]]  && continue   # deleted file — skip

    # Derive expected test file name:
    #   signals/extractor.py  → tests/test_extractor.py
    #   learning/channel_scores.py → tests/test_channel_scores.py
    module=$(basename "$src_file" .py)
    test_file="tests/test_${module}.py"

    if [[ -f "$test_file" ]]; then
        COVERED+=("  ✓ ${src_file} → ${test_file}")
    else
        GAPS+=("  ✗ ${src_file}  (no ${test_file})")
    fi
done <<< "$CHANGED_FILES"

# ── Write heartbeat ──────────────────────────────────────────────────────────
echo "$TODAY" > "$HB"

# ── Build report ─────────────────────────────────────────────────────────────
TOTAL_CHANGED=$(echo "$CHANGED_FILES" | grep -c . || echo 0)
GAP_COUNT=${#GAPS[@]}
COVERED_COUNT=${#COVERED[@]}

log "Coverage check: ${TOTAL_CHANGED} changed files, ${GAP_COUNT} gaps, ${COVERED_COUNT} covered"

if [[ $GAP_COUNT -eq 0 ]]; then
    MSG="[COVERAGE] <b>All changed files have tests</b>
${COVERED_COUNT} file(s) changed — all covered
${TODAY}"
else
    GAP_TEXT=$(printf '%s\n' "${GAPS[@]}")
    COVERED_TEXT=""
    if [[ $COVERED_COUNT -gt 0 ]]; then
        COVERED_TEXT=$'\n'"Covered (${COVERED_COUNT}):"$'\n'"$(printf '%s\n' "${COVERED[@]}")"
    fi

    MSG="[COVERAGE] <b>${GAP_COUNT} file(s) without tests</b>
${TODAY}

Gaps (${GAP_COUNT}):
${GAP_TEXT}${COVERED_TEXT}

Run <code>make test</code> or add tests for the above."
fi

send_telegram "$MSG"
log "Coverage report sent"
