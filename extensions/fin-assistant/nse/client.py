"""
NSE India API client.
- Session warmup on init() (homepage + live-equity page) to acquire cookies
- Global rate limiter: ≥0.5 s between API requests; 429 → Retry-After backoff
- Retries on 401/403 with full session re-init
- Automatic fallback to yfinance for equity quotes when NSE is unreachable
- Bulk/block deals: JSON API is geo-blocked; CSV archive used as primary source
"""
import re
import time
import threading
import logging
import requests
from datetime import datetime

log = logging.getLogger(__name__)

# ── Rate limiter ───────────────────────────────────────────────────────────
_rl_lock          = threading.Lock()
_rl_last_req: float = 0.0
MIN_REQ_INTERVAL  = 0.5   # seconds — NSE recommends ≥500 ms between requests

# ── yfinance fallback ──────────────────────────────────────────────────────

def _yf_quote(symbol: str) -> dict | None:
    """
    Fallback equity quote via yfinance when NSE is unavailable.
    NSE symbol → Yahoo Finance ticker by appending .NS
    """
    try:
        import yfinance as yf
        t  = yf.Ticker(f"{symbol.upper()}.NS")
        fi = t.fast_info
        ltp = fi.last_price
        if ltp is None:
            return None
        hi = getattr(fi, "day_high", None) or ltp
        lo = getattr(fi, "day_low",  None) or ltp
        prev = getattr(fi, "previous_close", None) or ltp
        pct  = round((ltp - prev) / prev * 100, 2) if prev else 0
        wh   = getattr(fi, "year_high", None)
        wl   = getattr(fi, "year_low",  None)
        log.debug("yfinance fallback OK for %s: ltp=%s", symbol, ltp)
        return {
            "symbol": symbol.upper(),
            "ltp":   ltp,
            "pct":   pct,
            "high":  hi,
            "low":   lo,
            "close": prev,
            "wh52":  wh,
            "wl52":  wl,
            "_source": "yfinance",
        }
    except Exception as e:
        log.debug("yfinance fallback %s: %s", symbol, e)
        return None


def _yf_indices() -> dict:
    """
    Fallback index snapshot via yfinance when NSE allIndices is unavailable.
    Returns dict in same format as all_indices() for keys we care about.
    """
    try:
        import yfinance as yf
        mapping = {
            "NIFTY 50":    "^NSEI",
            "NIFTY BANK":  "^NSEBANK",
        }
        result = {}
        for label, sym in mapping.items():
            fi = yf.Ticker(sym).fast_info
            if fi.last_price:
                prev = fi.previous_close or fi.last_price
                pct  = round((fi.last_price - prev) / prev * 100, 2) if prev else 0
                result[label] = {
                    "index":         label,
                    "last":          fi.last_price,
                    "percentChange": pct,
                    "_source":       "yfinance",
                }
        log.debug("yfinance index fallback: %d indices", len(result))
        return result
    except Exception as e:
        log.debug("yfinance index fallback: %s", e)
        return {}

BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",   # no 'br' — brotlipy not installed
    "Referer":         "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}

_sess: requests.Session | None = None

# Pages that prime the NSE session cookie before JSON API calls
_WARMUP_PAGES = [
    "/",                                   # homepage — sets _abck, bm_sz cookies
    "/market-data/live-equity-market",     # sets deeper auth tokens
]


def _warmup():
    """GET the warmup pages to seed session cookies. Silently skips on error."""
    for page in _WARMUP_PAGES:
        try:
            _sess.get(BASE + page, timeout=10)
            time.sleep(MIN_REQ_INTERVAL)
        except Exception as e:
            log.debug("NSE warmup %s: %s", page, e)


def init():
    global _sess
    _sess = requests.Session()
    _sess.headers.update(HEADERS)
    _warmup()


def _throttled_get(url: str, **kwargs) -> requests.Response:
    """GET with global rate limit — enforces MIN_REQ_INTERVAL between any call."""
    global _rl_last_req
    with _rl_lock:
        gap = MIN_REQ_INTERVAL - (time.monotonic() - _rl_last_req)
        if gap > 0:
            time.sleep(gap)
        _rl_last_req = time.monotonic()
    return _sess.get(url, **kwargs)


def get(path: str, retries: int = 3) -> dict | list | None:
    global _sess
    if _sess is None:
        init()
    for attempt in range(retries):
        try:
            r = _throttled_get(BASE + path, timeout=15)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                log.warning("NSE rate-limited on %s — waiting %ds", path, wait)
                time.sleep(wait)
                continue
            if r.status_code in (401, 403):
                log.warning("NSE %d on %s — reinit session (attempt %d)",
                            r.status_code, path, attempt + 1)
                init()
                continue
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "")
                if "json" in ct or r.text.lstrip()[:1] in ("{", "["):
                    return r.json()
                log.warning("NSE non-JSON on %s (ct=%s)", path, ct[:40])
                return None
        except Exception as e:
            log.warning("NSE %s attempt %d: %s", path, attempt + 1, e)
            time.sleep(2)
    return None


# ── Market status ──────────────────────────────────────────────────────────

def market_status() -> str:
    data = get("/api/marketStatus")
    if not data:
        return "UNKNOWN"
    for m in data.get("marketState", []):
        if m.get("market") == "Capital Market":
            return m.get("marketStatus", "UNKNOWN")
    return "UNKNOWN"


def is_market_open() -> bool:
    return market_status() == "Open"


# ── Indices ────────────────────────────────────────────────────────────────

def all_indices() -> dict:
    """Return dict keyed by index name. Falls back to yfinance on NSE failure."""
    data = get("/api/allIndices")
    if data:
        return {d["index"]: d for d in data.get("data", [])}
    log.warning("NSE allIndices unavailable — using yfinance fallback")
    return _yf_indices()


def sensex() -> dict | None:
    """Return Sensex snapshot via yfinance (BSE index, not on NSE API)."""
    try:
        import yfinance as yf
        fi   = yf.Ticker("^BSESN").fast_info
        ltp  = fi.last_price
        if not ltp:
            return None
        prev = fi.previous_close or ltp
        pct  = round((ltp - prev) / prev * 100, 2) if prev else 0
        return {"index": "SENSEX", "last": ltp, "percentChange": pct}
    except Exception as e:
        log.debug("Sensex yfinance: %s", e)
        return None


def gift_nifty() -> dict | None:
    """Return GIFT NIFTY data (pre-market indicator)."""
    idx = all_indices()
    return idx.get("GIFT NIFTY")


def india_vix() -> float | None:
    idx = all_indices()
    v = idx.get("India VIX") or idx.get("INDIA VIX")
    return v.get("last") if v else None


# ── Equity quotes ──────────────────────────────────────────────────────────

def quote(symbol: str) -> dict | None:
    """Equity quote from NSE. Falls back to yfinance if NSE is unreachable."""
    data = get(f"/api/quote-equity?symbol={symbol.upper()}")
    if data:
        try:
            pi  = data["priceInfo"]
            hl  = pi.get("intraDayHighLow") or {}
            whl = pi.get("weekHighLow") or {}
            return {
                "symbol": symbol.upper(),
                "ltp":    pi.get("lastPrice"),
                "pct":    pi.get("pChange"),
                "high":   hl.get("max"),
                "low":    hl.get("min"),
                "close":  pi.get("close") or pi.get("previousClose"),
                "wh52":   whl.get("max"),
                "wl52":   whl.get("min"),
            }
        except Exception as e:
            log.warning("Quote parse %s: %s", symbol, e)

    log.warning("NSE quote unavailable for %s — using yfinance fallback", symbol)
    return _yf_quote(symbol)


# ── Option chain ───────────────────────────────────────────────────────────

def option_chain(symbol: str) -> dict | None:
    """
    Returns processed option chain for nearest expiry.
    symbol: NIFTY | BANKNIFTY | FINNIFTY
    """
    data = get(f"/api/option-chain-indices?symbol={symbol.upper()}")
    if not data:
        return None
    try:
        records  = data["records"]["data"]
        expiries = data["records"]["expiryDates"]
        expiry   = expiries[0] if expiries else None
        atm_price = data["records"].get("underlyingValue", 0)

        tce = tpe = 0
        max_ce = max_pe = {"oi": 0, "strike": 0}
        strikes = []

        for r in records:
            if r.get("expiryDate") != expiry:
                continue
            sp   = r.get("strikePrice", 0)
            ce   = r.get("CE") or {}
            pe   = r.get("PE") or {}
            co   = ce.get("openInterest", 0) or 0
            po   = pe.get("openInterest", 0) or 0
            cchg = ce.get("changeinOpenInterest", 0) or 0
            pchg = pe.get("changeinOpenInterest", 0) or 0
            tce += co; tpe += po
            if co > max_ce["oi"]: max_ce = {"oi": co, "strike": sp}
            if po > max_pe["oi"]: max_pe = {"oi": po, "strike": sp}
            strikes.append({
                "strike": sp,
                "ce_oi": co, "ce_chg_oi": cchg, "ce_ltp": ce.get("lastPrice"),
                "pe_oi": po, "pe_chg_oi": pchg, "pe_ltp": pe.get("lastPrice"),
            })

        pcr  = round(tpe / tce, 2) if tce else 0
        bias = "BULLISH" if pcr > 1.2 else ("BEARISH" if pcr < 0.8 else "NEUTRAL")
        return {
            "symbol":    symbol.upper(),
            "expiry":    expiry,
            "atm":       atm_price,
            "pcr":       pcr,
            "bias":      bias,
            "max_ce":    max_ce["strike"],
            "max_pe":    max_pe["strike"],
            "total_ce":  tce,
            "total_pe":  tpe,
            "strikes":   strikes,
        }
    except Exception as e:
        log.warning("OC parse %s: %s", symbol, e)
        return None


def oi_velocity(oc: dict, top_n: int = 5) -> list[dict]:
    """
    Return top N strikes with largest absolute OI change (buildup + unwinding).
    Requires option_chain() output.
    """
    if not oc or not oc.get("strikes"):
        return []
    rows = []
    for s in oc["strikes"]:
        for side, oi, chg in (("CE", s["ce_oi"], s["ce_chg_oi"]),
                               ("PE", s["pe_oi"], s["pe_chg_oi"])):
            if chg and abs(chg) > 0:
                rows.append({
                    "strike": s["strike"], "type": side,
                    "oi": oi, "chg": chg,
                    "ltp": s[f"{side.lower()}_ltp"],
                    "pct_chg": round(chg / (oi - chg) * 100, 1) if (oi - chg) != 0 else None,
                })
    rows.sort(key=lambda x: abs(x["chg"]), reverse=True)
    return rows[:top_n]


# ── FII / DII ──────────────────────────────────────────────────────────────

def fii_dii() -> dict | None:
    data = get("/api/fiidiiTradeReact")
    if not data:
        return None
    try:
        result = {}
        def _f(v) -> float:
            try:
                return float(str(v).replace(",", "")) if v is not None else 0.0
            except (ValueError, TypeError):
                return 0.0

        for row in data:
            cat = row.get("category", "").strip().upper()
            if "FII" in cat or "FPI" in cat:
                result["fii_buy"]  = _f(row.get("buyValue"))
                result["fii_sell"] = _f(row.get("sellValue"))
                result["fii_net"]  = _f(row.get("netValue"))
            elif "DII" in cat:
                result["dii_buy"]  = _f(row.get("buyValue"))
                result["dii_sell"] = _f(row.get("sellValue"))
                result["dii_net"]  = _f(row.get("netValue"))
        return result if result else None
    except Exception as e:
        log.warning("FII/DII parse: %s", e)
        return None


# ── Bulk & block deals ─────────────────────────────────────────────────────
# NSE /api/bulk-deal-archives and /api/block-deal-archives return 404 from WSL2
# (confirmed geo-blocked — tested with full session warmup, 2026-04-14).
# The public CSV archives work from any IP without session warmup.

_BULK_CSV  = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
_BLOCK_CSV = "https://nsearchives.nseindia.com/content/equities/block.csv"


def _parse_deal_csv(url: str) -> list[dict]:
    """Download and parse NSE bulk/block deal CSV. Returns [] on any error."""
    try:
        r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
        if r.status_code != 200 or not r.text.strip():
            return []
        import io, csv
        reader = csv.DictReader(io.StringIO(r.text))
        out = []
        for row in reader:
            # CSV columns: Date, Symbol, Security Name, Client Name, Buy/Sell,
            #              Quantity Traded, Trade Price / Wght. Avg. Price, Remarks
            qty   = row.get("Quantity Traded", "0").replace(",", "")
            price = row.get("Trade Price / Wght. Avg. Price", "0").replace(",", "")
            out.append({
                "date":   row.get("Date", "").strip(),
                "symbol": row.get("Symbol", "").strip().upper(),
                "client": row.get("Client Name", "").strip(),
                "type":   row.get("Buy/Sell", "").strip().upper(),
                "qty":    int(float(qty))   if qty   else 0,
                "price":  float(price)      if price else 0.0,
            })
        return out
    except Exception as e:
        log.warning("Deal CSV %s: %s", url, e)
        return []


def bulk_deals() -> list[dict]:
    return _parse_deal_csv(_BULK_CSV)


def block_deals() -> list[dict]:
    return _parse_deal_csv(_BLOCK_CSV)


# ── Corporate actions ──────────────────────────────────────────────────────

def corporate_actions(symbol: str) -> list[dict]:
    data = get(f"/api/corporateActions?index=equities&symbol={symbol.upper()}")
    out  = []
    if not data:
        return out
    for row in (data if isinstance(data, list) else []):
        out.append({
            "symbol":  row.get("symbol"),
            "ex_date": row.get("exDate"),
            "purpose": row.get("purpose"),
        })
    return out
