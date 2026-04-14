Run the fin-assistant test suite and give me a structured report.

Steps:
1. Run `cd /root/fin-assistant && make test-report` and capture the output
2. Parse the output for: total passed, total failed, total errors, total skipped
3. If there are failures or errors, for each one:
   - State which test file and test name failed
   - Show the exact assertion or error message (not the full traceback unless needed)
   - Diagnose the likely root cause in one sentence
   - Suggest the exact fix (file:line if possible)
4. If all tests pass, confirm the count and note any warnings
5. Check if any test file is missing coverage for recent code changes by reviewing git log for changed .py files vs test files

Output format:
```
TEST RESULTS  <date>
──────────────────────────────
  Passed : N
  Failed : N
  Errors : N
  Skipped: N

[FAILURES]
  test_grading.py::TestOptionGrading::test_buy_call_underlying_up_is_hit
    → AssertionError: expected TGT1_HIT, got OPEN
    → Likely cause: pct field missing from index quote dict
    → Fix: eod.py:118 — add "pct": nifty.get("percentChange") to index q dict

[COVERAGE GAPS]
  reports/eod.py modified but no new tests added — consider test_grading.py

[STATUS] PASS / FAIL
```

If tests cannot run (import error, missing dependency), diagnose the setup issue first.
