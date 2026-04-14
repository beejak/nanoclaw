"""
Telegram bridge: listens to all channels discovered in the user's account
and writes messages into the SQLite DB for signal analysis.

Runs as a systemd service. Monitored channels are loaded from the
monitored_channels DB table (populated by `python main.py discover`).
"""
import asyncio
import logging
import signal
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from pyrogram import Client, filters
from pyrogram.types import Message

from config import db, TG_API_ID, TG_API_HASH, TG_SESSION, DB_PATH
from bridge.discover import get_active_ids, _init_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bridge] %(message)s"
)
log = logging.getLogger(__name__)

# Load monitored set at startup (refresh requires service restart)
_init_table()
MONITORED: set[int] = get_active_ids()
log.info("Loaded %d monitored channels from DB", len(MONITORED))

app = Client(TG_SESSION, api_id=TG_API_ID, api_hash=TG_API_HASH)


def write_to_db(chat_id, chat_name, msg_id, sender_id, sender_name, text, ts):
    jid    = f"tg:{chat_id}"
    ts_iso = ts.isoformat()
    with db() as conn:
        conn.execute("""
            INSERT INTO chats (jid, name, last_message_time, channel, is_group)
            VALUES (?, ?, ?, 'telegram', 1)
            ON CONFLICT(jid) DO UPDATE SET
                name = excluded.name,
                last_message_time = MAX(last_message_time, excluded.last_message_time)
        """, (jid, chat_name, ts_iso))
        conn.execute("""
            INSERT OR REPLACE INTO messages
              (id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
            VALUES (?,?,?,?,?,?,0,0)
        """, (f"tg_{chat_id}_{msg_id}", jid, str(sender_id), sender_name, text, ts_iso))
        # conn.commit() is implicit on __exit__ of the with-block; explicit here
        # only to flush immediately so the bridge liveness check can see the row.
        conn.commit()


@app.on_message(filters.text)
async def on_message(client: Client, msg: Message) -> None:
    chat_id = msg.chat.id
    if MONITORED and chat_id not in MONITORED:
        return

    chat_name   = msg.chat.title or str(chat_id)
    sender_id   = msg.from_user.id         if msg.from_user else chat_id
    sender_name = msg.from_user.first_name if msg.from_user else chat_name
    text        = msg.text or ""
    ts          = msg.date or datetime.now(timezone.utc)

    if not text.strip():
        return

    try:
        write_to_db(chat_id, chat_name, msg_id=msg.id,
                    sender_id=sender_id, sender_name=sender_name, text=text, ts=ts)
        log.info("[%s] %s: %s", chat_name, sender_name, text[:80])
    except Exception as e:
        log.error("DB write failed: %s", e)


LIVENESS_CHECK_INTERVAL = 60    # seconds between liveness checks
LIVENESS_MAX_SILENCE    = 600   # exit if no DB write in this many seconds (10 min)
                                 # systemd Restart=on-failure brings it back cleanly


async def _liveness_monitor():
    """
    Periodically checks that the bridge is actually writing messages.
    Only active during market hours (9:00–15:45 IST) when channels are
    expected to be posting. Outside those hours channels are quiet so
    silence is normal — no restart needed.
    If no message written in LIVENESS_MAX_SILENCE seconds during market hours,
    exits with code 1 so systemd restarts the process fresh — no zombie state.
    """
    import sqlite3 as _sqlite3
    from datetime import datetime as _dt, timezone as _tz
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
    while True:
        await asyncio.sleep(LIVENESS_CHECK_INTERVAL)
        try:
            now_ist = _dt.now(_IST)
            # Only check liveness during market hours 9:00–15:45 IST
            ist_mins = now_ist.hour * 60 + now_ist.minute
            if not (540 <= ist_mins <= 945):   # 9:00 AM – 15:45 PM
                continue
            conn = _sqlite3.connect(DB_PATH, timeout=3)
            row  = conn.execute("SELECT MAX(timestamp) FROM messages").fetchone()
            conn.close()
            if row and row[0]:
                last = _dt.fromisoformat(row[0].replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=_tz.utc)
                silence = (_dt.now(_tz.utc) - last).total_seconds()
                if silence > LIVENESS_MAX_SILENCE:
                    log.warning(
                        "Liveness: no DB write for %.0f s during market hours — exiting for clean restart",
                        silence
                    )
                    raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as e:
            log.debug("Liveness check error: %s", e)


async def main():
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, None)
    await app.start()
    log.info("Bridge running — monitoring %d channels", len(MONITORED) if MONITORED else 0)
    # Run liveness monitor as a background task
    liveness_task = asyncio.ensure_future(_liveness_monitor())
    await stop
    liveness_task.cancel()
    try:
        await app.stop()
    except RuntimeError as e:
        log.warning("Bridge stop (ignorable asyncio loop error): %s", e)
    log.info("Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
