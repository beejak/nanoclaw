<div align="center">

<img src="assets/nanoclaw-logo.png" alt="NanoClaw" width="320">

# NanoClaw - Financial Assistant

**Self-hosted AI agent framework with a built-in Indian stock market signal aggregator**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)](https://python.org)
[![Node.js](https://img.shields.io/badge/node-20%2B-339933?logo=node.js&logoColor=white)](https://nodejs.org)
[![Platform](https://img.shields.io/badge/platform-WSL2%20%7C%20Linux-lightgrey?logo=linux)](https://docs.microsoft.com/en-us/windows/wsl/)
[![Docker](https://img.shields.io/badge/docker-required-2496ed?logo=docker&logoColor=white)](https://docker.com)
[![Telegram](https://img.shields.io/badge/telegram-MTProto-26a5e4?logo=telegram)](https://core.telegram.org/mtproto)
[![NSE](https://img.shields.io/badge/data-NSE%20India-orange)](https://nseindia.com)
[![Discord](https://img.shields.io/discord/1470188214710046894?label=discord&logo=discord&logoColor=white)](https://discord.gg/VDdww8qS42)

[Quick Install](#one-click-install) - [Architecture](#architecture) - [Features](#what-it-does) - [Setup](#financial-assistant-setup) - [Docs](#table-of-contents)

</div>

---

> [!WARNING]
> **DISCLAIMER -- READ BEFORE USING**
>
> The financial assistant in this repository is a **personal research tool** built to explore what can be done with public data and self-hosted automation. It is **not financial advice**. Nothing it outputs constitutes a recommendation to buy, sell, or hold any security. Data is sourced from public APIs and Telegram channels you personally subscribe to. Signal extraction from unstructured text is imperfect by design. Market data may be delayed or inaccurate. **The authors accept no liability for any trading decisions, financial losses, or actions taken based on this software's output.** Use it to understand your own information environment -- not to make investment decisions.

---

## What It Does

This repository is a fork of [NanoClaw](https://github.com/qwibitai/nanoclaw) -- a lightweight AI agent framework that runs Claude securely inside Docker containers. On top of it, a fully functional Indian stock market signal assistant has been built and included as a working example.

<table>
<tr>
<td width="50%">

**NanoClaw** `src/`

AI agent runtime. Connects Claude to your messaging apps (WhatsApp, Telegram, Slack, Discord). Each agent runs in an isolated container with its own memory. Handles scheduling, multi-channel routing, and credential security.

Requires a Claude subscription.

</td>
<td width="50%">

**Financial Assistant** `extensions/fin-assistant/`

Pure Python. Connects to your personal Telegram account via MTProto, discovers every channel you follow, extracts trading signals from their messages, cross-validates each against live NSE data, and delivers structured briefings to a Telegram bot.

**No AI subscription required.**

</td>
</tr>
</table>

The two components are fully independent. Run one, the other, or both.

---

## One-Click Install

```bash
git clone https://github.com/beejak/nanoclaw.git && cd nanoclaw && ./install.sh
```

The installer handles everything -- dependencies, credentials, database, services, schedule, and an optional Google Drive backup connection. It asks for input only when needed, with exact instructions for each step.

**Before you run it, have these ready:**

| What | Where to get it | Cost |
|---|---|---|
| Telegram API ID + Hash | [my.telegram.org/apps](https://my.telegram.org/apps) -> Create Application | Free |
| Telegram bot token | [@BotFather](https://t.me/BotFather) -> `/newbot` | Free |
| Google account | [google.com](https://google.com) -- for Drive backups | Free (optional) |
| Claude subscription | [claude.ai/pricing](https://claude.ai/pricing) -- for NanoClaw agents only | Paid (optional) |

> **Time:** ~10 minutes on a fresh WSL2 machine.

---

## Table of Contents

<details>
<summary>Expand</summary>

1. [Architecture](#architecture)
2. [Subscriptions & Cost](#subscriptions--cost)
3. [NanoClaw Setup](#nanoclaw-setup)
4. [Financial Assistant Setup](#financial-assistant-setup)
   - [Credentials](#1-credentials)
   - [Install](#2-install)
   - [Channel Discovery](#3-channel-discovery)
   - [Backfill History](#4-backfill-history)
   - [Start the Bridge](#5-start-the-bridge)
   - [Scheduled Reports](#6-scheduled-reports)
5. [Service Reference](#service-reference)
6. [Signal Pipeline](#signal-pipeline)
   - [Extraction](#extraction)
   - [Enrichment](#enrichment)
   - [Learning Loop](#learning-loop)
   - [Global Market Context](#global-market-context)
7. [Report Schedule](#report-schedule)
8. [Manual Commands](#manual-commands)
9. [Channel Management](#channel-management)
10. [Health Monitoring](#health-monitoring)
11. [Backup & Recovery](#backup--recovery)
12. [Database Schema](#database-schema)
13. [Failover & Redundancy](#failover--redundancy)
14. [Limitations](#limitations)
15. [Contributing](#contributing)
16. [License](#license)

</details>

---

## Architecture

```
+----------------------------------------------------------------------+
|                           Your Machine (WSL2 / Linux)                |
|                                                                      |
|  +-------------------------------------------------------------+    |
|  |  NanoClaw  (Node.js - systemd - Docker)                     |    |
|  |                                                             |    |
|  |  WhatsApp -+                                                |    |
|  |  Telegram -+-> SQLite --> Polling loop --> Docker          |    |
|  |  Slack    -+              (per-group)       container       |    |
|  |  Discord  -+                                |               |    |
|  |                                             v               |    |
|  |                                       Claude Agent SDK      |    |
|  |                                             |               |    |
|  |                                             v               |    |
|  |                                       Response --> Router   |    |
|  +-------------------------------------------------------------+    |
|                                                                      |
|  +-------------------------------------------------------------+    |
|  |  Financial Assistant  (Python - systemd - cron)             |    |
|  |                                                             |    |
|  |  Your Telegram account                                      |    |
|  |    |  Pyrogram (MTProto)                                    |    |
|  |    v                                                        |    |
|  |  bridge/tg_bridge.py <---- monitors all your channels 24/7 |    |
|  |    |                                                        |    |
|  |    v                                                        |    |
|  |  store/messages.db  (SQLite)                                |    |
|  |    |                                                        |    |
|  |    +-- signals/extractor.py   <- regex signal extraction     |    |
|  |    +-- enrichers/             <- NSE - yfinance - OI - FII   |    |
|  |    +-- learning/              <- channel scores - regime     |    |
|  |    +-- reports/               <- pre-open - hourly - EOD     |    |
|  |                   |                                         |    |
|  |                   v                                         |    |
|  |             Telegram bot --> your phone                     |    |
|  +-------------------------------------------------------------+    |
|                                                                      |
|  +-------------------------------------------------------------+    |
|  |  External data  (all public, no API keys required)          |    |
|  |                                                             |    |
|  |  NSE India API ---- live quotes - OI - FII/DII - events     |    |
|  |  yfinance      ---- TA - global indices - fallback quotes   |    |
|  |  ForexFactory  ---- high-impact macro event calendar        |    |
|  +-------------------------------------------------------------+    |
+----------------------------------------------------------------------+
```

---

## Subscriptions & Cost

| Component | Requirement | Cost |
|---|---|---|
| Financial Assistant | None | **Free** |
| Financial Assistant | Telegram account + bot | **Free** |
| Financial Assistant | NSE / yfinance / ForexFactory data | **Free** |
| NanoClaw agents | Claude Pro or higher | Paid - [claude.ai/pricing](https://claude.ai/pricing) |
| NanoClaw agents | Anthropic API (direct calls) | Pay-per-use - [anthropic.com/pricing](https://www.anthropic.com/pricing) |
| NanoClaw agents | Docker Desktop | Free (personal use) |

> NanoClaw supports any Anthropic API-compatible endpoint. Point it at a local Ollama instance or any hosted open-source model by setting `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` in `.env`.

---

## NanoClaw Setup

### Install

```bash
git clone https://github.com/beejak/nanoclaw.git
cd nanoclaw
claude        # opens Claude Code
```

Inside Claude Code, run:

```
/setup
```

Claude handles Node.js dependencies, Docker authentication, container builds, and service registration automatically. Commands starting with `/` are [Claude Code skills](https://code.claude.com/docs/en/skills) -- type them inside the `claude` prompt, not your terminal.

### Start - Stop - Restart

```bash
# Foreground (dev)
npm start

# Background service
systemctl start   nanoclaw
systemctl stop    nanoclaw
systemctl restart nanoclaw
systemctl status  nanoclaw
journalctl -u nanoclaw -f          # live logs
```

### Docker

NanoClaw runs each Claude agent in an isolated Docker container.

```bash
docker ps                                                    # running containers
docker logs <container-id>                                   # agent output
docker ps --filter label=nanoclaw -q | xargs docker stop    # stop all agents
docker container prune                                       # clean stopped
docker pull ghcr.io/anthropics/claude-code:latest            # update image

# Start Docker if not running
sudo service docker start          # Linux / WSL2
open -a Docker                     # macOS
```

---

## Financial Assistant Setup

> If you ran `./install.sh` -- this is already done. Use this section as a reference.

All commands run from `extensions/fin-assistant/`.

```bash
cd extensions/fin-assistant
```

### 1. Credentials

```bash
cp .env.example .env
nano .env
```

| Variable | How to get it |
|---|---|
| `TG_API_ID` | [my.telegram.org/apps](https://my.telegram.org/apps) -> log in -> Create Application -> copy **App api_id** |
| `TG_API_HASH` | Same page -> copy **App api_hash** |
| `TG_SESSION` | Any local path (no extension) -- e.g. `/home/you/tg_session` |
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) -> `/newbot` -> copy the token |
| `OWNER_CHAT_ID` | Send `/start` to your bot, then: `curl https://api.telegram.org/bot<TOKEN>/getUpdates` |

> `.env` is git-ignored and never committed. See [Security](#security) for credential handling.

### 2. Install

```bash
sudo ./scripts/setup.sh
```

Installs system packages, Python dependencies, SQLite schema, systemd service, and crontab.

**Python dependencies:**

```
pyrogram==2.0.106   MTProto Telegram client
tgcrypto            C-level crypto acceleration for Pyrogram
requests            NSE API calls
python-dotenv       .env loader
yfinance >=1.2.0     Yahoo Finance -- TA enrichment + fallback quotes
pandas >=2.0.0       Data processing
pandas-ta >=0.3.14b  RSI(14), SMA(20), ADX indicators
```

### 3. Channel Discovery

The assistant has no hardcoded channels. It scans your Telegram account and monitors everything you already follow.

```bash
python3 main.py discover --dry   # preview -- nothing saved
python3 main.py discover         # save to database
python3 main.py channels         # list all with status
```

```
Status   Type         ID                Members  Name
--------------------------------------------------------------------
ON       CHANNEL      -1001234567890    12500    BankNifty Calls
ON       SUPERGROUP   -1009876543210    4300     Nifty Options
...
171 active / 171 total
```

Mute noise channels:

```bash
python3 main.py disable -1001234567890
python3 main.py enable  -1001234567890
python3 main.py discover               # re-run after joining new channels
systemctl restart fin-bridge           # pick up changes
```

### 4. Backfill History

```bash
python3 main.py fetch 7       # last 7 days, 500 msg/channel
python3 main.py fetch 14 200  # last 14 days, 200 msg/channel
```

First run triggers a Pyrogram login -- enter your phone number and the OTP Telegram sends. Session saved locally and reused automatically.

### 5. Start the Bridge

The bridge is a 24/7 listener that writes every incoming message from your monitored channels to the database.

```bash
systemctl start   fin-bridge
systemctl stop    fin-bridge
systemctl restart fin-bridge        # required after channel changes
systemctl status  fin-bridge
tail -f logs/bridge.log
journalctl -u fin-bridge -f
```

### 6. Scheduled Reports

Installed automatically by `setup.sh`. All times IST, Mon-Fri.

| Time | Report | Contents |
|---|---|---|
| 8:30 AM | Stack health check | 9-component status + Telegram alert |
| 8:45 AM | Pre-open briefing | GIFT Nifty gap - India VIX - global markets - macro events - FII/DII - overnight signals - mute recommendations |
| 9:45 AM | First hourly scan | New signals - NSE live - TA - OI velocity - confluence - macro flags |
| 10:45 AM - 3:15 PM | Hourly scans | As above -- new signals only, deduped |
| 3:45 PM | EOD grader | Every signal graded: TGT hit / SL hit / Open - channel scorecard |
| Mon 8:00 AM | Weekly scorecard | 30-day hit rate per channel - mute recommendations |
| 11:30 PM (daily) | Backup | DB + .env + session -> local + Google Drive |

```bash
crontab -l                                               # verify schedule
crontab extensions/fin-assistant/systemd/crontab.txt     # reinstall if needed
tail -f extensions/fin-assistant/logs/cron.log           # live output
```

---

## Service Reference

| Service | Role | Start | Stop | Logs |
|---|---|---|---|---|
| `nanoclaw` | AI agent runtime | `systemctl start nanoclaw` | `systemctl stop nanoclaw` | `journalctl -u nanoclaw -f` |
| `fin-bridge` | Telegram message collector | `systemctl start fin-bridge` | `systemctl stop fin-bridge` | `tail -f logs/bridge.log` |
| Docker | Container runtime for NanoClaw | `sudo service docker start` | `sudo service docker stop` | `journalctl -u docker -f` |
| Cron | Report + backup scheduler | `crontab crontab.txt` | `crontab -r` | `tail -f logs/cron.log` |

```bash
# Check everything at once
systemctl status nanoclaw fin-bridge docker
```

---

## Signal Pipeline

### Extraction

Messages are scanned with a regex-based extractor that looks for BUY/SELL/CE/PE patterns and parses instrument, entry price, stop-loss, and targets from free-text.

A large noise filter (`NOISE` frozenset) prevents common English words from being misread as NSE ticker symbols. Option strike codes (`12500CE`, `2360PE`) are filtered separately before any NSE lookup.

### Enrichment

Every extracted signal is cross-validated before being sent:

| Layer | Source | What it adds |
|---|---|---|
| **Live price** | NSE India public API | Entry still valid? SL already hit? |
| **Technical analysis** | yfinance + pandas-ta | RSI(14) - SMA(20) - 52-week percentile - trend - ADX |
| **OI velocity** | NSE option chain (hourly snapshot) | Strike buildup / unwinding this hour |
| **Confluence** | `signal_log` table | 2+ channels calling same instrument -> elevated alert |
| **Corporate events** | NSE corporate actions | Earnings / dividend / split within 5 days |
| **FII/DII flows** | NSE provisional data | Institutional net buy/sell direction |
| **Bulk & block deals** | NSE deal API | Trades >= Rs.10cr -- institutional accumulation/distribution |
| **GIFT Nifty gap** | NSE all-indices API | Pre-market gap vs previous close |
| **Global markets** | yfinance (free) | S&P 500 - Nasdaq - Nikkei - Hang Seng - Crude - Gold - DXY - US 10Y |
| **Macro calendar** | ForexFactory (free) | High-impact USD/INR events in next 48h, times converted to IST |

### Learning Loop

The system learns from its own outcomes. After every EOD grading run, three memory tables are updated:

```
Signal logged -> EOD graded -> Learning tables updated -> Next day's reports use updated scores
```

| Table | What is learned | How it's used |
|---|---|---|
| `channel_scores` | 30-day hit rate per channel | Hourly: channels sorted HIGH->MED->LOW; mute suggestions in pre-open |
| `instrument_stats` | BUY/SELL success rate per instrument | Hourly: historical base rate shown on each signal |
| `market_regime` | Daily: VIX label - FII flow direction - index trend | Pre-open: yesterday's regime; hourly: context header |

Confidence bands for channel scores: **HIGH** >=60% - **MED** 40-59% - **LOW** <40% - auto-mute suggested below 25% with >=10 closed signals.

### Global Market Context

Pre-open and hourly reports include an overnight global snapshot:

| Ticker | Why it matters for Indian markets |
|---|---|
| S&P 500 `^GSPC` | Strongest single global correlate with Nifty open |
| Nasdaq `^IXIC` | Leads IT sector stocks |
| Nikkei 225 `^N225` | Asian session direction |
| Hang Seng `^HSI` | China proxy -- affects metals and EM sentiment |
| Crude WTI `CL=F` | Inflation - OMC stocks - rupee pressure |
| Gold `GC=F` | Risk-off gauge |
| DXY `DX-Y.NYB` | Dollar strength -> FII outflows from India |
| US 10Y `^TNX` | Elevated yields -> risk-off -> FII exits EM |

---

## Report Schedule

### Pre-open (8:45 AM IST)

```
[PRE-OPEN] PRE-OPEN BRIEFING  Mon 07 Apr 2026  08:45 IST

Yesterday's regime: [-] BEARISH  -  High volatility  -  FII selling (-2,840cr)

[=] GIFT NIFTY  22,450  Gap -180 pts (-0.79%)
[!!!] India VIX   25.52   HIGH -- expect volatility

[DATA] Previous close
[-] NIFTY 50    22,713  (-0.82%)   52W H 26,373  L 21,743
[-] BANK NIFTY  51,549  (-1.10%)   52W H 61,764  L 49,156

[GLOBAL] GLOBAL MARKETS
  [-] S&P 500      5,074  (-4.84%)
  [-] Nasdaq      15,587  (-5.97%)
  [-] Nikkei 225  30,216  (-7.83%)
  [+] Crude WTI     111   (+6.51%)  [!] oil spike
  [+] DXY           103   (+0.18%)  [WARN] USD strength -> FII outflow risk

[DATE] MACRO EVENTS (next 48h, high impact)
  [WARN] US US  Non-Farm Payrolls  [Mon 18:00 IST]  fcst 65K  prev -92K

[WARN] Low-accuracy channels (2) -- consider muting:
  - Some Channel  18% hit rate (34 closed signals, 30d)
```

### Hourly signal scan

```
[LIVE] SIGNAL SCAN  10:45 IST  (3 new)

[+] NIFTY 50    22,890  (+0.78%)   PCR 1.32BULL  RR:25,000  SS:22,500
[-] BANKNIFTY   51,200  (-0.30%)
[!!] VIX 19.4
[UP] Regime: [-] BEARISH  -  High volatility  -  FII selling
[WARN] US US  Non-Farm Payrolls  [Mon 18:00 IST]

>> BestCallsChannel  (2)  *63% [HIGH]
  [+] RELIANCE  @ 2,890  SL 2,850  TGT 2,950/3,000  [10:32]
  + NSE Rs.2,904  ^0.5%  [OK]
  + TA: RSI 58  above SMA20  52W 74th pct  UPTREND
  + [+] BUY hist: 61% hit (28 signals, 30d)

  [-] NIFTY  CE  SL 22,400  TGT 22,200  [10:38]
  + NIFTY 22,890  (+0.78%)

>> NoisyChannel  (1)  v21% [LOW]  [WARN] consider muting
  [+] INFY  @ 1,450  SL 1,420  TGT 1,500  [10:41]
  + NSE Rs.1,461  ^0.8%  [OK]
  + [-] BUY hist: 21% hit (19 signals, 30d)
```

---

## Manual Commands

```bash
# Run from extensions/fin-assistant/

# Reports (send to Telegram)
python3 main.py preopen
python3 main.py hourly
python3 main.py eod
python3 main.py weekly
python3 main.py oi-snapshot

# Dry run (print to terminal, no Telegram)
python3 main.py preopen  --dry-run
python3 main.py hourly   --dry-run
python3 main.py eod      --dry-run

# Channel management
python3 main.py discover           # re-scan Telegram for channels
python3 main.py channels           # list all with ON/OFF status
python3 main.py disable <id>       # mute a channel
python3 main.py enable  <id>       # unmute a channel

# History
python3 main.py fetch 7            # backfill last 7 days

# Health
python3 scripts/healthcheck.py             # check + alert on failure
python3 scripts/healthcheck.py --report    # full status to Telegram
python3 scripts/healthcheck.py --quiet     # log only

# Backup
bash scripts/backup.sh                     # backup to ~/fa-backups/
bash scripts/setup-gdrive.sh              # connect Google Drive (one-time)
```

---

## Channel Management

The `monitored_channels` table is the single source of truth. The bridge reads it at startup.

```bash
python3 main.py channels           # list all
python3 main.py disable <id>       # mute without deleting history
python3 main.py enable  <id>       # unmute
python3 main.py discover           # re-scan after joining new channels
systemctl restart fin-bridge       # always restart after any change
```

**Direct SQL queries:**

```sql
-- Most active channels by message volume
SELECT c.name, COUNT(*) AS msgs
FROM messages m JOIN chats c ON m.chat_jid = c.jid
GROUP BY c.name ORDER BY msgs DESC LIMIT 20;

-- 30-day hit rate leaderboard
SELECT channel,
       COUNT(*)  AS total,
       SUM(CASE WHEN result LIKE 'TGT%' THEN 1 ELSE 0 END) AS hits,
       ROUND(100.0 * SUM(CASE WHEN result LIKE 'TGT%' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN result != 'OPEN' THEN 1 ELSE 0 END), 0), 1) AS hit_pct
FROM signal_log
WHERE date >= DATE('now', '-30 days')
GROUP BY channel
HAVING total >= 5
ORDER BY hit_pct DESC;

-- Mute a channel by name
UPDATE monitored_channels SET active = 0 WHERE name LIKE '%ChannelName%';
```

---

## Health Monitoring

The health check runs every 15 minutes during market hours and every 2 hours overnight. It sends a Telegram alert immediately on any failure, and attempts auto-recovery where possible.

```bash
python3 scripts/healthcheck.py --quiet     # silent run (cron mode)
python3 scripts/healthcheck.py --report    # send full status to bot
tail -f logs/healthcheck.log               # live output
```

**Checks performed:**

| Check | Auto-recovery |
|---|---|
| Disk space (warn < 500 MB) | -- |
| SQLite accessible + tables present | -- |
| `fin-bridge` service active | `systemctl restart fin-bridge` -> re-check |
| Bridge message freshness (market hours) | -- |
| NSE API reachable | -- |
| yfinance fallback reachable | -- |
| ForexFactory calendar reachable | -- |
| Telegram bot token valid | -- |
| Logs directory writable | -- |

A full stack status report is also sent at **8:30 AM IST every weekday** -- 15 minutes before the pre-open briefing -- so you know the system is healthy before the market opens.

---

## Backup & Recovery

### Automated daily backup

Every night at **11:30 PM IST** the backup script runs automatically.

**What is backed up:**

| File | Why |
|---|---|
| `store/messages.db` | All messages, signals, grades, and learning data |
| `.env` | Your credentials |
| `*.session` | Pyrogram session -- avoids re-authenticating |

Source code is not backed up -- it lives on GitHub.

### Google Drive (recommended)

Set up once, runs forever:

```bash
bash extensions/fin-assistant/scripts/setup-gdrive.sh
```

Walks you through rclone's OAuth flow -- log in via browser, no manual token creation needed.

**Retention:**
- Local: last **7** backups in `~/fa-backups/`
- Remote: last **30** backups in Google Drive -> `fin-assistant-backups/`

### Manual backup

```bash
bash extensions/fin-assistant/scripts/backup.sh             # to ~/fa-backups/
bash extensions/fin-assistant/scripts/backup.sh /your/path  # custom dir
```

### Restore on a new machine

```bash
# 1. Clone and start the installer
git clone https://github.com/beejak/nanoclaw.git && cd nanoclaw && ./install.sh

# 2. At Step 8 (before .env is written), restore your archive instead:
tar -xzf fa-backup-YYYYMMDD_HHMM.tar.gz
# This extracts DB, .env, and session to their original absolute paths

# 3. Continue from Step 9
```

If you lost the session file, re-authenticate at Step 10 of the installer.

---

## Database Schema

Located at `extensions/fin-assistant/store/messages.db`.

| Table | Contents |
|---|---|
| `monitored_channels` | All Telegram groups/channels with active toggle |
| `chats` | Chat metadata keyed by `tg:<chat_id>` |
| `messages` | Raw message content from all active channels |
| `signal_log` | Extracted signals + EOD grades (TGT1/2/3\_HIT - SL\_HIT - OPEN) |
| `oi_snapshots` | Hourly OI per strike -- NIFTY - BANKNIFTY - FINNIFTY |
| `fii_dii_daily` | FII/DII net flows by day |
| `bulk_deals` | Institutional bulk/block trades >= Rs.10cr |
| `corporate_events` | Earnings, dividends, splits |
| `channel_scores` | Rolling 30-day hit rate per channel (learning) |
| `instrument_stats` | Per-instrument BUY/SELL success rate (learning) |
| `market_regime` | Daily VIX - FII flow - index trend snapshot (memory) |

Full schema: [`extensions/fin-assistant/db/schema.sql`](extensions/fin-assistant/db/schema.sql)

---

## Failover & Redundancy

| Component | Primary | Fallback | Behaviour on failure |
|---|---|---|---|
| Equity quotes | NSE India API | yfinance `.NS` suffix | Silent fallback, warning logged |
| Index data | NSE allIndices | yfinance `^NSEI`, `^NSEBANK` | Silent fallback, warning logged |
| Macro calendar | ForexFactory JSON | -- | Section skipped gracefully |
| Telegram bridge | systemd `Restart=always` | healthcheck auto-restart | Alert sent + restart attempted |
| TA enrichment | yfinance per symbol | -- | Per-symbol skip on error |

The `fin-bridge` service is configured with `Restart=always` and `RestartSec=5` in systemd, providing automatic recovery from crashes independent of the health check.

---

## Limitations

**The system can:**
- Discover and monitor every Telegram channel you personally subscribe to
- Extract BUY/SELL/CE/PE signals from free-text messages
- Cross-validate against live NSE prices
- Grade each signal at EOD against the day's high/low
- Track channel accuracy over time and surface low-performers
- Show global market context and high-impact macro events
- Run entirely on public data with no paid subscriptions

**The system cannot:**
- Predict price direction
- Execute trades or connect to broker APIs
- Read channels you haven't joined
- Process image-based signals (charts, screenshots)
- Guarantee extraction accuracy from unstructured natural language
- Provide real-time tick data (snapshot-based, not streaming)
- Learn to extract signals in new formats without code changes

---

## Contributing

**NanoClaw core** -- upstream changes only. See [CONTRIBUTING.md](CONTRIBUTING.md). Security fixes and bug fixes accepted; new capabilities go in skills.

**Financial Assistant** -- PRs welcome against this fork:

- Additional exchange support (BSE, MCX)
- Improved signal extraction patterns
- New enrichment sources
- Additional report formats or delivery channels

**Do not commit:**
- `.env` or any file containing credentials
- `*.session` Pyrogram session files
- `store/*.db` database files
- `logs/` output files

---

## Security

- All credentials live in `.env`, which is git-ignored
- Pyrogram session files (`.session`) are git-ignored
- The database (`store/`) is git-ignored
- No credentials are ever passed to Docker containers (NanoClaw routes API calls through [OneCLI Agent Vault](https://github.com/onecli/onecli))
- The health check audits the full stack for credential exposure on every run

To rotate credentials: update `.env`, revoke the old bot token via @BotFather, and restart services.

---

## License

[MIT](LICENSE) -- see license file for details.

The financial assistant extension is provided as-is for personal research purposes. See the disclaimer at the top of this file.

---

<div align="center">

**[^ back to top](#nanoclaw--financial-assistant)**

Made with Python, Node.js, and public data - Not affiliated with NSE India or Telegram

</div>
