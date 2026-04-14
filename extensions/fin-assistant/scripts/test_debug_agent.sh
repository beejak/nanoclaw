#!/usr/bin/env bash
# =============================================================================
# test_debug_agent.sh — AI-powered test failure diagnosis
#
# Called by run_tests.sh when pytest reports failures or errors.
# Uses claude -p (haiku, non-interactive) to turn the raw pytest output
# into structured: assertion → likely cause → suggested fix (file:line).
#
# Outputs plain text to stdout.  run_tests.sh uses this as the Telegram body.
# Usage: ./test_debug_agent.sh <report_file>
# =============================================================================
set -uo pipefail

REPORT_FILE="${1:-}"
if [[ -z "$REPORT_FILE" || ! -f "$REPORT_FILE" ]]; then
    echo "(debug agent: report file not found)"
    exit 1
fi

# Keep only the failure-relevant sections to avoid bloating the prompt.
# --tb=line means each failure is short: FAILED line + 1-line traceback.
FAILURE_SECTION=$(awk '
    /^(FAILED|ERROR) / { in_fail=1 }
    in_fail { print; lines++ }
    lines > 120 { exit }
' "$REPORT_FILE")

SUMMARY_LINE=$(grep -E '^\d+ (passed|failed)' "$REPORT_FILE" | tail -1 || echo "")

PROMPT="You are diagnosing pytest failures for a live trading bot.

Summary: ${SUMMARY_LINE}

Failures:
${FAILURE_SECTION}

For each FAILED or ERROR test output a compact diagnosis. Format exactly:

FAIL: <TestClass::test_name>
  Assert: <exact assertion message, ≤1 line>
  Cause:  <root cause, 1 sentence>
  Fix:    <file:line — what to change>

Rules:
- Do NOT include tracebacks or code snippets.
- Max 4 lines per failure.
- If all tests passed, output: CLEAN — no failures."

# Run claude non-interactively with haiku (cheap + fast for structured output).
# Timeout after 30s so cron doesn't stall.
timeout 30 claude --model haiku -p "$PROMPT" 2>/dev/null \
    || echo "(debug agent: diagnosis timed out or unavailable)"
