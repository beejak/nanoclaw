# nanoclaw / fin-assistant

A self-hosted, fault-tolerant market intelligence platform for Indian equities. Connects to your personal Telegram account via MTProto, harvests trading signals from every group and channel you subscribe to, validates each call against live NSE data, and delivers structured briefings to your private bot — hourly during market hours, with a full EOD accuracy report, intraday price alerts the moment a target or stop-loss is hit, and a daily AMC institutional activity report.

No hardcoded channel lists. No subscriptions. No external APIs beyond NSE/Yahoo Finance. Works entirely with what you are already subscribed to.

---

## Architecture

```
Your Telegram account
        │
        │  Pyrogram · MTProto (personal account, not a bot)
        ▼
bridge/tg_bridge.py ─────── live message listener (systemd: fin-bridge)
        │
        │  writes to SQLite
        ▼
store/messages.db ──────────────────────────────────────────────────
        │
        ├── signals/extractor.py  ── regex + heuristic signal parser
        │     modes: indices | stocks | futures
        │     guards: STOCK_OPT_RE filter, sub-15k strike check, within-scan dedup
        ├── enrichers/            ── NSE live, TA, OI velocity, events, AMC deals
        │
        │  reads/writes
        ▼
main.py [mode] ─────────── analysis engine + Telegram reporter
        │
        ├── preopen      8:45 AM   GIFT Nifty gap · VIX · FII/DII · overnight signals
        ├── hourly        9:45–3:15  New signals · NSE live · TA · OI · confluence
        ├── eod           3:45 PM   Grade every call: TGT hit / SL hit / open · scorecard
        ├── weekly        Mon 8 AM  Hit rate per channel · mute recommendations
        ├── amc-report    4:15 PM   AMC bulk/block deal report + PDF
        └── backtest               P&L analysis on historical signal_log

scripts/price_monitor.py ── intraday daemon (every 5 min via cron)
        └── alerts the moment any open signal hits its target or SL

bot_listen.py ─────────────── Telegram query listener (systemd: fin-listen)
        └── ask nanoclaw anything from your phone; responds with live data
```

---

## Resilience — five independent recovery layers

The scheduler is built in concentric rings. Each layer operates completely independently; a failure at any level automatically escalates to the next.

```
Layer 0 · startup.sh  (@reboot — WSL2 cold start)
  Fires 20 seconds after every WSL2 instance start.
  Restarts fin-bridge for a clean MTProto connection after network reset.
  Runs any overnight jobs missed while the machine was suspended:
    NSE symbol refresh (if past 7:30 AM IST and not done today)
    Weekly scorecard  (if Monday past 8:00 AM IST)
    Pre-open briefing (if 8:45–9:30 AM IST window is current)
  Runs the test suite in background.
  Sends a Telegram recovery summary of all actions taken.

Layer 1 · cron_guard.sh
  Wraps every cron job. On failure: retry 3× with 60 s backoff.
  On success: write heartbeat to logs/heartbeats/<job>.last_ok.
  After 3 failures: schedule a one-off recovery attempt via atd,
  then alert Telegram with log tail and manual override hint.

Layer 2 · watchdog.sh  (cron: every 30 min, 7:30 AM – 5:30 PM IST)
  Reads heartbeat files. If any critical job missed its window,
  re-runs it via cron_guard and sends a recovery alert.
  Covers: preopen · hourly_indices · hourly_stocks · hourly_futures
          · eod · amc_report (checked after 5:15 PM IST)
  Completely independent of cron_guard — separate cron entry.

Layer 3 · atd fallback
  Scheduled by cron_guard as a last resort when all 3 retries fail.
  One-shot execution 10 minutes after the failure is declared.

Layer 4 · fin-scheduler  (systemd: Restart=always)
  Persistent Python process. Checks the clock every 30 s.
  Fires any job 5 minutes after its scheduled slot if the heartbeat
  shows cron never ran it. Survives crashes via systemd auto-restart.
  Sends [FAILSAFE] Telegram alerts when it acts.
```

If every automated layer is down, send `/run_preopen` (or any `/run_*`) command to your bot — the `fin-bot-listener` service handles it instantly from your phone.

---

## Signal quality

The extractor has three modes and several guards to prevent garbage signals polluting channel scores:

| Guard | What it prevents |
|---|---|
| `STOCK_OPT_RE` check | Stock option strikes (e.g. GODREJCP 1040CE) mis-attributed to NIFTY |
| Sub-15k strike filter | NIFTY strikes < 15,000 rejected (commodity/stock option leakage) |
| Strike range thresholds | SENSEX ≥ 60k, BANKNIFTY ≥ 30k, NIFTY 15k–30k |
| Within-scan dedup | Same channel + instrument + direction in one 65-min window → keep only most recent |

### Option grading

Options are graded **directionally against the underlying**, not by comparing the premium target to the underlying price (which would always produce a hit):

| Signal | Result condition |
|---|---|
| BUY CE | TGT1_HIT if underlying closes ≥ +0.5%; SL_HIT if ≤ −0.5% |
| BUY PE | TGT1_HIT if underlying closes ≤ −0.5%; SL_HIT if ≥ +0.5% |
| SELL CE | TGT1_HIT if underlying closes ≤ −0.5%; SL_HIT if ≥ +0.5% |
| SELL PE | TGT1_HIT if underlying closes ≥ +0.5%; SL_HIT if ≤ −0.5% |
| Any | OPEN if underlying moves < 0.5% in either direction |

Plain equity and futures signals use high/low vs target/SL as before.

---

## Telegram query mode

Send any question to your bot from Telegram. `bot_listen.py` (systemd: `fin-listen`) handles it in real time.

```
/q RELIANCE          live quote + TA + 30-day signal history + upcoming events
/q NIFTY             index snapshot
can I hold RIL long term?   → live data + Claude CLI synthesis
which stocks is HDFCAMC buying?  → real NSE bulk/block deal data (no LLM)
give me 2 large cap stocks near 52W low  → Claude CLI with web-search
```

**Routing logic:**
- Known NSE symbol detected → full stock/index snapshot
- AMC / bulk-deal keywords → live NSE deal data (no LLM at all)
- Research/screening question (4+ words) → Claude CLI synthesis
- Short unrecognised input → help message

---

## AMC bulk/block deal report

Runs daily at 4:15 PM IST after market close. Retries hourly (5:15, 6:15, 7:15 PM) if missed. Covers 25+ AMC fund houses:

HDFC MF · SBI MF · ICICI Pru MF · Nippon MF · Kotak MF · Axis MF · Mirae MF · DSP MF · Aditya Birla MF · Franklin MF · UTI MF · Tata MF · Motilal MF · Parag Parikh MF · Quant MF · WhiteOak MF · and more.

Data source: NSE bulk/block deal CSV archives (no session warmup required).

```bash
python main.py amc-report                  # all AMCs
python main.py amc-report --amc "SBI MF"   # single AMC
python main.py amc-report --dry-run        # print + save PDF, no Telegram send
```

Output: Telegram message with buys/sells per AMC + PDF document sent to your bot.

---

## Testing

The test suite is pytest-based and covers every critical subsystem that has caused or could cause production errors.

```
tests/
  conftest.py              shared fixtures: isolated SQLite DB, mocked NSE, captured bot.send
  test_extractor.py        27 tests — signal extraction (indices, stocks, futures, helpers)
  test_grading.py          20 tests — EOD grading: options (directional), stocks, edge cases
  test_channel_scores.py   10 tests — hit rate, confidence bands, mute suggestion logic
  test_amc.py              13 tests — AMC fuzzy name matching
                         ─────────
                           70 tests total
```

**Run the suite:**

```bash
make test              # full suite
make test-grading      # grading logic only
make test-extract      # signal extraction only
make test-scores       # channel scoring only
make test-amc          # AMC matching only
make test-report       # full suite + write logs/test_report.txt
make ci                # lint + typecheck + tests
```

**Test isolation:** every test gets a fresh in-memory SQLite DB with the full production schema, NSE client mocked (no HTTP calls), and `bot.send` captured (no Telegram messages). Tests run in ~3 s.

### Autonomous test pipeline

| Component | What it does |
|---|---|
| `scripts/run_tests.sh` | Cron every 30 min; skips if already ran today; defers during market hours (9:00–15:45 IST); sends Telegram on pass or fail |
| `scripts/test_debug_agent.sh` | Called on failure; uses `claude haiku -p` to diagnose each failing test (assertion → root cause → file:line fix) and injects the diagnosis into the Telegram alert |
| `scripts/coverage_agent.sh` | Weekly (Sunday 8 PM IST); finds `.py` files changed in the last 7 days with no corresponding `tests/test_<module>.py`; sends Telegram gap list |

### Claude Code skills

| Skill | How to invoke | What it does |
|---|---|---|
| `/test` | Claude Code session | Run suite + structured pass/fail report with coverage gap check |
| `/debug` | Claude Code session | Deep diagnosis: reads source files, traces logic path, proposes minimal diffs (no auto-apply) |

---

## Tested and verified

### Production test harness (current)

70 pytest tests across signal extraction, EOD grading, channel scoring, and AMC matching. Covers every production bug that has been found and fixed:

| Test class | Key regressions covered |
|---|---|
| `TestIndexOptions` | HAL 3700CE / HCLTECH 1400CE / HEROMOTOCO 5200CE extracted as NIFTY (day-1 bug) |
| `TestOptionGrading` | Option premium target vs underlying price always-hit bug; all directional combos |
| `TestHitRateCalculation` | OPEN signals diluting hit rate; all-OPEN channel appearing in scores |
| `TestMuteSuggestion` | Premature mute suggestion with < 10 data points |

Run: `make test` (no network access, no production DB touched)

### Resilience stress test (historical)

54 / 54 tests on the 4-layer cron recovery chain. Full findings: [`TEST_REPORT.md`](TEST_REPORT.md)

---

## Setup

### Requirements

- Ubuntu / Debian / WSL2 (tested on Ubuntu 22.04 and WSL2)
- Python 3.11+
- A personal Telegram account (MTProto — not a bot token)
- A Telegram bot for receiving reports (create one via [@BotFather](https://t.me/BotFather))
- `atd` running (`apt-get install at`)

### 1. Clone and install

```bash
git clone https://github.com/beejak/nanoclaw.git
cd nanoclaw/extensions/fin-assistant
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
nano .env
```

| Variable | Where to get it |
|---|---|
| `TG_API_ID` / `TG_API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `TG_SESSION` | Local path for the Pyrogram session file (no extension) |
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `OWNER_CHAT_ID` | Send `/start` to your bot, then check `getUpdates` via the Bot API |

### 3. Discover your channels (one-time; re-run after joining new ones)

```bash
python main.py discover --dry    # preview what will be found
python main.py discover          # save to DB
python main.py channels          # verify the list
```

Selectively mute irrelevant sources:

```bash
python main.py disable -1001234567890   # stop monitoring a channel
python main.py enable  -1001234567890   # re-enable it
```

### 4. Install cron jobs and systemd services

```bash
# Cron (all scheduled jobs: reports, watchdog, price monitor, AMC report, tests)
crontab systemd/crontab.txt

# Core bridge (listens to your Telegram channels)
cp scripts/fin-bridge.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now fin-bridge

# Failsafe scheduler (Layer 4)
cp scripts/fin-scheduler.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now fin-scheduler

# Telegram query listener (respond to your messages)
cp scripts/fin-listen.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now fin-listen
```

### 5. Backfill and verify

```bash
python main.py fetch 7           # backfill last 7 days of history
python main.py hourly --dry-run  # print a scan without sending to Telegram
python main.py amc-report --dry-run
make test                        # verify test suite is green before going live
```

---

## Schedule (Mon–Fri, IST)

| Time | Job | What it does |
|---|---|---|
| @reboot (WSL2 start) | startup.sh | Bridge restart + catch-up for any missed overnight jobs |
| 7:30 AM (daily) | refresh_nse_symbols | Download EQUITY_L.csv from NSE archives, upsert nse_symbols |
| 8:00 AM (Mon) | weekly | Channel hit-rate scorecard, mute recommendations |
| 8:30 AM | healthcheck --report | Full stack status to Telegram before market opens |
| 8:45 AM | preopen | GIFT Nifty gap · VIX · FII/DII · overnight signal digest |
| 9:45 – 3:15 PM | hourly × 7 (indices + stocks + futures) | New signals · NSE live · TA · OI · confluence · leaderboard |
| 3:45 PM | eod | Grade every open call: target hit / SL hit / still open |
| 4:15 PM | amc-report | AMC bulk/block deals + PDF (retries hourly if missed) |
| Every 5 min (9:15–3:30) | price_monitor | Alert the moment a target or SL is breached |
| Every 15 min (9:00–3:45) | healthcheck | Bridge alive · NSE reachable · DB writable · disk OK |
| Every 30 min (7:30–5:30) | watchdog | Re-run any job that missed its heartbeat window |
| Every 30 min (any time) | run_tests.sh | Test suite; skips if already ran today; defers during market hours |
| Sunday 8:00 PM | coverage_agent.sh | Check for recently changed .py files with no tests |
| 11:30 PM | backup | DB + session + .env → tar.gz, optional upload to Google Drive |

---

## Market holidays

All jobs automatically skip NSE market holidays. The 2026 NSE equity holiday list is maintained in `config.py` (`NSE_HOLIDAYS`) and mirrored in `watchdog.sh`. Both use IST date for comparison.

**2026 NSE trading holidays:**

| Date | Day | Holiday |
|---|---|---|
| 26 Jan | Mon | Republic Day |
| 03 Mar | Tue | Holi |
| 26 Mar | Thu | Shri Ram Navami |
| 31 Mar | Tue | Shri Mahavir Jayanti |
| 03 Apr | Fri | Good Friday |
| 14 Apr | Tue | Dr. Baba Saheb Ambedkar Jayanti |
| 01 May | Fri | Maharashtra Day |
| 28 May | Thu | Bakri Id (Eid ul-Adha) |
| 26 Jun | Fri | Muharram |
| 14 Sep | Mon | Ganesh Chaturthi |
| 02 Oct | Fri | Mahatma Gandhi Jayanti |
| 20 Oct | Tue | Dussehra |
| 10 Nov | Tue | Diwali — Balipratipada |
| 24 Nov | Tue | Prakash Gurpurb Sri Guru Nanak Jayanti |
| 25 Dec | Fri | Christmas |

---

## Per-signal enrichment

Every extracted trading call is automatically enriched before appearing in any report:

| Enrichment | What it adds |
|---|---|
| **NSE live price** | Is the entry still valid? Has the SL already been hit? |
| **Technical state** | RSI(14), SMA(20) position, 52-week percentile, trend direction |
| **OI velocity** | Which strikes are seeing large buildup or unwinding this hour |
| **Confluence** | Same stock called by 2+ independent channels → elevated alert |
| **Event flag** | Earnings / dividend / split within 5 calendar days |

---

## Hourly report format

The hourly report is structured for fast readability:

```
INDEX SCAN  10:45 IST  (3 new)
NIFTY 23,124 (+0.7%)  BNIFTY 52,716 (+0.2%)  SENSEX 74,617 (+0.7%)
VIX 24.7 - ELEVATED  <- expect whipsaws

Verdict: SPLIT on NIFTY (5 BUY vs 4 SELL)

[CONFLUENCE ALERT] Multiple channels agree
[-] NIFTY  SELL  x4 channels  avg SL 23160
[+] NIFTY 22700PE  BUY  x2 channels  entry 50  SL 35

WATCHLIST  top actionable signals
  ▲ NIFTY 23100CE  @ 45  SL 5  TGT 120  R:R 1.7
  ▼ NIFTY  SL 23160

Channel Leaderboard
  █████ BNOptions         100% (5 sig)
  █████ NIFTY STOCK TALKS 100% (6 sig)
```

---

## Intraday price alerts

`scripts/price_monitor.py` runs every 5 minutes during market hours. For every open signal:

- **BUY** — alert if `day_high >= target` or `day_low <= stop_loss`
- **SELL** — alert if `day_low <= target` or `day_high >= stop_loss`

Each event fires exactly once per signal per session (persisted in `signal_log.intraday_alerts`).

---

## Bot commands

Send these to your bot at any time. Only messages from `OWNER_CHAT_ID` are processed.

| Command | What it does |
|---|---|
| `/q SYMBOL` | Live quote + TA + 30-day signal history + events |
| `/q NIFTY` | Index snapshot |
| `/run_preopen` | Run the pre-open briefing immediately |
| `/run_hourly` | Run an hourly signal scan immediately |
| `/run_eod` | Run the EOD grader immediately |
| `/run_weekly` | Run the weekly scorecard immediately |
| `/health` | Run a full healthcheck and report to Telegram |
| `/help` | Show available commands |

Natural language queries also work — just ask anything about a stock or market.

---

## Backtest

```bash
python main.py backtest --days 30              # all channels, last 30 days
python main.py backtest --channel "BNOptions"  # single channel
python main.py backtest --direction BUY        # buys only
python main.py backtest --instrument NIFTY     # partial match on instrument
python main.py backtest --min-confidence HIGH  # only HIGH-rated channels
python main.py backtest --send                 # send report to Telegram
```

---

## Channel management

```bash
python main.py channels          # list all with status (ON/OFF)
python main.py disable <id>      # mute without deleting history
python main.py enable  <id>      # unmute
python main.py discover          # re-scan after joining new channels
systemctl restart fin-bridge     # pick up channel list changes

# Join curated channels from CHANNEL_SCOUT.md
python3 scripts/join_scout_channels.py
python3 scripts/join_scout_channels.py --dry-run
```

---

## Manual commands

```bash
# Reports
python main.py preopen                      # pre-open briefing
python main.py hourly                       # hourly signal scan (indices)
python main.py hourly --mode stocks         # stocks mode
python main.py hourly --mode futures        # futures mode
python main.py eod                          # EOD grader
python main.py weekly                       # weekly scorecard
python main.py amc-report                   # AMC bulk/block deals + PDF
python main.py amc-report --amc "HDFC MF"  # single AMC
python main.py oi-snapshot                  # manual OI snapshot

# Add --dry-run to any report to print instead of sending to Telegram

# Logs
tail -f logs/bridge.log
tail -f logs/cron.log
tail -f logs/price_monitor.log
tail -f logs/amc_report.log
tail -f logs/watchdog.log
tail -f logs/tests.log
tail -f logs/coverage_agent.log
journalctl -fu fin-listen        # query bot listener
```

---

## Database schema

| Table | Contents |
|---|---|
| `monitored_channels` | All Telegram groups/channels with active on/off toggle |
| `messages` | Raw messages from all active channels |
| `signal_log` | Extracted signals, EOD grades, intraday alert history |
| `channel_scores` | Per-channel hit rate, confidence band, mute suggestion |
| `instrument_stats` | Per-instrument hit rate by direction |
| `oi_snapshots` | Hourly OI per strike (NIFTY / BANKNIFTY / FINNIFTY) |
| `fii_dii_daily` | FII/DII provisional net flows per day |
| `bulk_deals` | Institutional bulk and block trades >= Rs. 10 cr |
| `corporate_events` | Earnings, dividends, splits |
| `nse_symbols` | NSE equity symbol allowlist (refreshed daily from NSE archives) |
| `market_regime` | Daily VIX label, FII flow label, trend label, regime text |

Full schema: [`db/schema.sql`](db/schema.sql)

---

## Backup and restore

```bash
# Create backup (DB + .env + session file)
./scripts/backup.sh ~/backups

# Restore on a new machine
tar -xzf fin-assistant-backup-*.tar.gz -C ~
cd fin-assistant && pip install -r requirements.txt
# Restore .env manually; copy the .session file to the path in TG_SESSION
systemctl start fin-bridge fin-listen
```

---

## Disclaimer

Personal research tool only. Not financial advice. Trade at your own risk.
