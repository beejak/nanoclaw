Deep-diagnose failing tests in fin-assistant and propose concrete fixes.

Steps:
1. Read `logs/test_report.txt` (the latest test run output).
   - If it doesn't exist or is older than 10 minutes, run `make test-report` first.

2. For each FAILED or ERROR test:
   a. Extract the exact assertion message and the line in the test file that failed.
   b. Read the *source file under test* (not just the test file) — the module the
      test is exercising (e.g. `signals/extractor.py`, `reports/eod.py`).
   c. Trace through the logic to find the root cause.  Be specific: name the
      function, the line number, and what condition is violated.
   d. Propose the minimal code change to fix it.  Show the old line and the new
      line (no whole-function rewrites).

3. If zero failures: confirm the count and check for any pytest warnings.

4. Coverage check: run `git log --since="3 days ago" --name-only --diff-filter=AM -- '*.py'`
   and list any changed source files that have no corresponding `tests/test_<module>.py`.

Output format:
```
DEBUG REPORT  <date>
──────────────────────────────────────────────────────
FAIL #1  tests/test_grading.py::TestOptionGrading::test_buy_call_underlying_up_is_hit
  Assertion : assert result == "TGT1_HIT", got "OPEN"
  Root cause: reports/eod.py:118 — q dict for NIFTY index missing "pct" key;
              grade_signal() gets pct=0 so neutral branch taken.
  Fix       : eod.py:118
              - "last": nifty["last"], "high": nifty["high"]
              + "last": nifty["last"], "high": nifty["high"], "pct": nifty.get("percentChange", 0)

FAIL #2  ...

──────────────────────────────────────────────────────
COVERAGE GAPS
  reports/amc.py changed — no tests/test_amc_report.py found

──────────────────────────────────────────────────────
[STATUS] N failures · N gaps
```

Do NOT auto-apply any fixes.  Output the diagnosis only so the user can review
before changing production code.
