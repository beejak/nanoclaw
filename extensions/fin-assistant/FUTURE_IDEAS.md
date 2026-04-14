# Future Ideas

Captured from session discussions. Ordered by impact, not effort.

---

## 1. Close the feedback loop (channel scoring → auto-mute)

`learning/channel_scores.py` computes hit rates and sets `suggest_mute = True` when
hit rate < 25% over ≥ 10 closed signals. The weekly report surfaces this.
Nobody acts on it automatically.

What's missing: a threshold rule (e.g. `suggest_mute` for 4 consecutive weeks)
that calls `bridge/discover.py:disable_channel()` and sends a Telegram notice.
One function, wired into the weekly job.

Without this, the EOD grader collects data forever but the system never gets smarter.
This is the highest-leverage gap in the entire codebase.

**Status:** `suggest_mute` flag is computed and stored. Auto-disable not yet wired.

---

## 2. Log rotation

`logs/cron.log`, `logs/bridge.log`, `logs/price_monitor.log` grow unbounded.
A logrotate config — 20 lines — prevents an eventual disk-full outage.
The healthcheck already alerts at 500 MB free; rotation prevents ever getting there.

---

## 3. Backtesting

Replay `signal_log` entries against historical NSE OHLC data (available via
`yfinance` for daily, NSE for intraday). Compute actual hit rates independent
of the live grader. Useful for:
- Validating the grader's logic against ground truth
- Bootstrapping channel scores before 4 weeks of live data accumulates
- Finding the signal types (BUY/SELL, large/small cap, options/equity) that
  actually work across all channels

**Status:** `python main.py backtest` exists. Deep OHLC replay not yet built.
Scheduled for review ~2026-04-27 after 3 weeks of live graded data.

---

## 4. Confidence tiers on hourly alerts

The hourly report already has confluence (2+ channels calling same stock).
Add a simple tier: HIGH (confluence + channel score > 60%), MEDIUM, LOW.
Surface it in the Telegram message so the reader can triage instantly.
No new data needed — everything is already in the DB.

---

## 5. Options OI as independent signals

Unusual strike OI buildup (already tracked in `oi_snapshots`) is currently
context-only. Large sudden buildup at a specific strike often precedes a move.
A simple threshold alert (e.g. OI at strike X doubled in one hour) would
generate signals independent of any Telegram channel — pure market structure.

---

## 6. Image OCR for signal images

Many channels send signals as screenshots rather than text. `bridge/tg_bridge.py`
captures text only; photo messages are skipped.

Plan: download photo attachments, run Tesseract OCR, pass the text through the
extractor as normal. Requires `pytesseract` + `Pillow` and a Tesseract install.

**Status:** Deferred. This is the only remaining item from the original pending list.

---

## 7. New data sources

Beyond the current Telegram channel scraping:
- NSE/BSE official feeds (FII/DII, bulk deals already covered; intraday OI direct feed)
- Additional Telegram channels (channel scout runs daily, curated list in CHANNEL_SCOUT.md)
- RSS feeds from financial news sites (ET Markets, Mint, Moneycontrol)
- X.com (formerly Twitter) — public financial commentary, SEBI announcements

**Status:** Planned for discussion ~2026-04-24.

---

## 8. Nanoclaw scheduler migration (Option A)

Replace the bash cron + watchdog + systemd stack with nanoclaw's native task
scheduler. Plan: shadow run (both systems in parallel, compare outputs) → hard
cutover → rollback plan.

**Status:** Planned for ~2026-04-17. Rollback plan is documented.

---

## 9. CI/CD pipeline

GitHub Actions on every push to `extensions/fin-assistant/`:
- `ruff check` (lint)
- `mypy` (type check)
- `pytest` (70 tests)
- Telegram notification on failure

**Status:** Planned for ~2026-04-18 weekend. Extractor + grading tests first.

---

## 10. Self-learning / Hermes integration

Loop 1 (no model): behavioural rules derived from graded signal history →
auto-adjust weights in channel scoring.

Loop 2 (RAG): vector store of graded signals; similarity search to surface
historically analogous setups when a new signal arrives.

Loop 3 (fine-tuning): Hermes model via Together.ai, trained on the graded
signal corpus to generate trade context summaries.

**Status:** Architecture discussed. No model runtime currently available (needs
Together.ai key or local GPU). Fold into nanoclaw scheduler discussion ~2026-04-17.

---

## 11. Web dashboard

A lightweight read-only Flask page:
- Today's open signals with live NSE LTP
- Channel scorecard (hit rate, last 30 days)
- Heartbeat status for all recovery layers
- DB message count, last bridge write time

Currently everything is Telegram-only. One screen to look at during market
hours would be more comfortable than polling the bot.

---

## 12. P&L tracker

If signals are actually acted on, track actual entry/exit against the signal
and compute real returns per channel. Separate from the grader (which uses
day high/low, not actual fill prices). Would require manual or broker-API
trade logging.

---

## 13. DB migration system

Schema changes are currently handled with `ALTER TABLE IF NOT EXISTS` scattered
across multiple files. A single `db/migrate.py` with versioned migrations would
make schema evolution safe and auditable. Low urgency for a solo project.

---

## Not worth doing

- WhatsApp group scraping: brittle, ToS violation, Telegram coverage is sufficient
- Grafana/Prometheus: overkill for a single-user system; the healthcheck + Telegram covers it
- Containerisation: adds operational complexity with no benefit on a single machine
- Mocking the database in tests: caused a prod incident (mocked tests passed, migration failed) — keep the real SQLite fixture

---

## Lessons Learned

Operational mistakes and production bugs recorded so they don't repeat.

### 1. Stop cron before touching the Telegram session

`healthcheck.py` runs every 15 minutes via cron and auto-restarts `fin-bridge`
if it detects the service is down. If you stop `fin-bridge` without stopping
cron first, the healthcheck will restart it within 15 minutes (or less), causing
`database is locked` errors in any tool that tries to open the Pyrogram session.

**Correct shutdown sequence when you need exclusive session access:**
```bash
systemctl stop cron                  # 1. stop healthcheck from restarting bridge
systemctl stop fin-bridge            # 2. stop the service
pkill -9 -f tg_bridge.py             # 3. kill any surviving process
sleep 2                              # 4. let OS release file locks
# ... do your work ...
systemctl start fin-bridge           # 5. bring bridge back
systemctl start cron                 # 6. restore healthcheck
```

### 2. `discover` resets channel filter on each run

`bridge/discover.py` upserts every channel in your Telegram account back into
`monitored_channels` with `active=1`. Running it after a cleanup pass re-adds
all the junk you just removed.

**Fix in place:** the `join_scout_channels.py` script does a targeted upsert
for only the channels it just joined, rather than calling the full discover.
If you ever run `python main.py discover` manually, re-run the trading channel
filter script afterwards.

### 3. Option grading must be directional, not price-comparison

Day 1: `grade_signal("NIFTY 23700CE", q={"high": 24000, "target": 100})` checked
`high (24,000) >= target (100)` — always true regardless of outcome. This caused
100% false hit rates for every option channel in the weekly scorecard.

**Fix in place:** `is_option()` detection routes options to directional grading
using the underlying's `pct` move. Premium targets are ignored entirely for options.

### 4. WSL2 sleep/wake does not trigger @reboot

Cron entries run on cold WSL2 instance start, not on Windows sleep/resume.
After a laptop suspend/resume, cron misses its pre-market window until the watchdog
catches up (up to 30 min lag). The `startup.sh` (@reboot) mitigates cold-start
misses but cannot help with wake-from-sleep.

**Workaround:** Windows Task Scheduler on wake event (not yet implemented).
Accepted for now — watchdog catches up with < 30 min lag.

### 5. List multiplication replicates the same dict reference

`[make_signal("NIFTY")] * 4` calls `make_signal` once and replicates the same
dict four times. Combined with `INSERT OR REPLACE`, only 1 row lands in the DB.
Always use `[make_signal("NIFTY") for _ in range(4)]` in tests.
