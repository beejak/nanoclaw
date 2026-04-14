"""
Shared fixtures for fin-assistant test suite.

Every test gets:
  - An isolated in-memory SQLite DB with the full production schema
  - config.DB_PATH patched to the test DB
  - nse.client functions mocked (no real HTTP calls)
  - bot.send captured (no real Telegram messages)
"""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# DB schema — mirrors production exactly; update when schema changes
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_log (
    id          TEXT PRIMARY KEY,
    date        TEXT NOT NULL,
    channel     TEXT NOT NULL,
    instrument  TEXT NOT NULL,
    direction   TEXT,
    entry       REAL,
    sl          REAL,
    targets     TEXT,
    raw_text    TEXT,
    sent_at     TEXT NOT NULL,
    result      TEXT DEFAULT 'OPEN',
    result_note TEXT,
    graded_at   TEXT,
    intraday_alerts TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS channel_scores (
    channel      TEXT PRIMARY KEY,
    total        INTEGER DEFAULT 0,
    hits         INTEGER DEFAULT 0,
    sl_hits      INTEGER DEFAULT 0,
    hit_rate     REAL,
    confidence   TEXT DEFAULT 'UNKNOWN',
    suggest_mute INTEGER DEFAULT 0,
    updated_at   TEXT
);
CREATE TABLE IF NOT EXISTS instrument_stats (
    instrument   TEXT NOT NULL,
    direction    TEXT NOT NULL,
    total        INTEGER DEFAULT 0,
    hits         INTEGER DEFAULT 0,
    sl_hits      INTEGER DEFAULT 0,
    hit_rate     REAL,
    updated_at   TEXT,
    PRIMARY KEY (instrument, direction)
);
CREATE TABLE IF NOT EXISTS chats (
    jid              TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    last_message_time TEXT,
    channel          TEXT DEFAULT 'telegram',
    is_group         INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS messages (
    id             TEXT PRIMARY KEY,
    chat_jid       TEXT NOT NULL,
    sender         TEXT,
    sender_name    TEXT,
    content        TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    is_from_me     INTEGER DEFAULT 0,
    is_bot_message INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nse_symbols (
    symbol     TEXT PRIMARY KEY,
    name       TEXT,
    isin       TEXT,
    series     TEXT,
    type       TEXT DEFAULT 'equity',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS market_regime (
    date         TEXT PRIMARY KEY,
    vix          REAL,
    vix_label    TEXT,
    fii_net_5d   REAL,
    flow_label   TEXT,
    nifty_close  REAL,
    nifty_5d_pct REAL,
    trend_label  TEXT,
    regime_text  TEXT,
    recorded_at  TEXT
);
CREATE TABLE IF NOT EXISTS monitored_channels (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    type           TEXT,
    members_count  INTEGER DEFAULT 0,
    discovered_at  TEXT NOT NULL,
    last_seen      TEXT,
    active         INTEGER DEFAULT 1
);
"""

_SEED_SYMBOLS = [
    ("RELIANCE", "Reliance Industries Ltd"),
    ("HDFCBANK", "HDFC Bank Ltd"),
    ("INFY", "Infosys Ltd"),
    ("TCS", "Tata Consultancy Services"),
    ("WIPRO", "Wipro Ltd"),
    ("BAJFINANCE", "Bajaj Finance Ltd"),
    ("TITAN", "Titan Company Ltd"),
    ("HCLTECH", "HCL Technologies Ltd"),
    ("HAL", "Hindustan Aeronautics Ltd"),
    ("HEROMOTOCO", "Hero MotoCorp Ltd"),
]


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """
    Isolated SQLite DB with production schema + seed NSE symbols.
    Patches config.DB_PATH so all code under test writes here.
    """
    db_file = tmp_path / "test_messages.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(_SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO nse_symbols (symbol, name) VALUES (?, ?)",
        [(s, n) for s, n in _SEED_SYMBOLS],
    )
    conn.commit()
    conn.close()

    import config
    monkeypatch.setattr(config, "DB_PATH", db_file)

    # Re-patch db() so it always connects to our test file
    import contextlib

    @contextlib.contextmanager
    def _test_db_ctx(timeout=15.0):
        c = sqlite3.connect(str(db_file), timeout=timeout)
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    monkeypatch.setattr(config, "db", _test_db_ctx)
    return db_file


@pytest.fixture
def mock_nse():
    """Mock all nse.client functions — no real HTTP calls."""
    with patch("nse.client.quote") as mock_quote, \
         patch("nse.client.all_indices") as mock_indices, \
         patch("nse.client.init") as mock_init, \
         patch("nse.client.india_vix") as mock_vix:

        mock_init.return_value = None
        mock_vix.return_value = 14.5
        mock_indices.return_value = {
            "NIFTY 50":   {"last": 23800, "high": 24000, "low": 23600,
                           "percentChange": 0.8, "pct": 0.8},
            "NIFTY BANK": {"last": 51200, "high": 51800, "low": 50900,
                           "percentChange": 1.1, "pct": 1.1},
            "SENSEX":     {"last": 77500, "high": 78000, "low": 77000,
                           "percentChange": 0.6, "pct": 0.6},
        }
        mock_quote.return_value = {
            "ltp": 1640, "high": 1660, "low": 1600,
            "open": 1620, "pct": 1.2,
        }

        yield {
            "quote":       mock_quote,
            "all_indices": mock_indices,
            "init":        mock_init,
            "vix":         mock_vix,
        }


@pytest.fixture
def mock_send():
    """Capture bot.send calls — no real Telegram messages sent."""
    sent = []
    with patch("bot.send", side_effect=lambda msg, **kw: sent.append(msg)):
        yield sent


_signal_counter = [0]


def make_signal(instrument, direction="BUY", entry=None, sl=None,
                targets=None, channel="Test Channel",
                result="OPEN", date="2026-04-13"):
    """Helper: build a signal_log row dict with a guaranteed unique id."""
    _signal_counter[0] += 1
    return {
        "id":           f"test_{_signal_counter[0]:06d}_{instrument}_{direction}",
        "date":         date,
        "channel":      channel,
        "instrument":   instrument,
        "direction":    direction,
        "entry":        entry,
        "sl":           sl,
        "targets":      json.dumps(targets or []),
        "raw_text":     f"BUY {instrument}",
        "sent_at":      f"{date}T09:45:00",
        "result":       result,
        "result_note":  None,
        "graded_at":    None,
    }
