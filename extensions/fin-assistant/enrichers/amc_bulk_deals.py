"""
AMC Bulk/Block Deal Tracker.

Fetches today's bulk and block deals from NSE, filters for known AMC
(mutual fund) buyers/sellers, and returns structured records.

AMC name matching is fuzzy — covers the common fund house names seen
in NSE's client name field.
"""
import logging
from datetime import date

log = logging.getLogger(__name__)

# ── Known AMC name fragments (NSE uses variations) ───────────────────────────

AMC_NAMES: dict[str, str] = {
    # fragment (upper) → canonical label
    "HDFC MUTUAL":      "HDFC MF",
    "HDFC AMC":         "HDFC MF",
    "SBI MUTUAL":       "SBI MF",
    "SBI MAGNUM":       "SBI MF",
    "SBI MF":           "SBI MF",
    "ICICI PRUDENTIAL": "ICICI Pru MF",
    "ICICI PRU":        "ICICI Pru MF",
    "NIPPON INDIA":     "Nippon MF",
    "NIPPON MUTUAL":    "Nippon MF",
    "RELIANCE MUTUAL":  "Nippon MF",   # legacy name
    "KOTAK MUTUAL":     "Kotak MF",
    "KOTAK AMC":        "Kotak MF",
    "AXIS MUTUAL":      "Axis MF",
    "AXIS AMC":         "Axis MF",
    "MIRAE ASSET":      "Mirae MF",
    "DSP MUTUAL":       "DSP MF",
    "DSP BLACKROCK":    "DSP MF",
    "ADITYA BIRLA":     "Aditya Birla MF",
    "BIRLA SUN LIFE":   "Aditya Birla MF",
    "FRANKLIN TEMPLETON": "Franklin MF",
    "FRANKLIN INDIA":   "Franklin MF",
    "UTI MUTUAL":       "UTI MF",
    "UTI AMC":          "UTI MF",
    "TATA MUTUAL":      "Tata MF",
    "TATA AMC":         "Tata MF",
    "INVESCO MUTUAL":   "Invesco MF",
    "L&T MUTUAL":       "L&T MF",
    "EDELWEISS MUTUAL": "Edelweiss MF",
    "SUNDARAM MUTUAL":  "Sundaram MF",
    "QUANTUM MUTUAL":   "Quantum MF",
    "MOTILAL OSWAL MUTUAL": "Motilal MF",
    "MOTILAL OSWAL AMC":    "Motilal MF",
    "WHITEOAK":         "WhiteOak MF",
    "NAVI MUTUAL":      "Navi MF",
    "QUANT MUTUAL":     "Quant MF",
    "PPFAS MUTUAL":     "Parag Parikh MF",
    "PARAG PARIKH":     "Parag Parikh MF",
    "BAJAJ FINSERV MUTUAL": "Bajaj Finserv MF",
}


def _match_amc(client: str) -> str | None:
    """Return canonical AMC label if client name matches, else None."""
    up = (client or "").upper()
    for frag, label in AMC_NAMES.items():
        if frag in up:
            return label
    return None


def fetch(filter_amc: str | None = None) -> list[dict]:
    """
    Fetch today's bulk + block deals and return only AMC activity.

    filter_amc: if given (e.g. "HDFC MF"), return only that AMC's deals.
    Returns list of dicts: {amc, symbol, type (BUY/SELL), qty, price, value_cr, date, deal_type}
    """
    from nse import client as nse
    nse.init()

    records = []
    for deal_type, rows in (("BULK", nse.bulk_deals()), ("BLOCK", nse.block_deals())):
        for r in rows:
            amc = _match_amc(r.get("client", ""))
            if not amc:
                continue
            if filter_amc and amc.upper() != filter_amc.upper():
                continue
            qty   = r.get("qty") or 0
            price = r.get("price") or 0
            try:
                qty   = float(str(qty).replace(",", ""))
                price = float(str(price).replace(",", ""))
            except Exception:
                qty = price = 0
            value_cr = round(qty * price / 1e7, 2) if qty and price else None
            records.append({
                "amc":        amc,
                "symbol":     (r.get("symbol") or "").upper(),
                "type":       (r.get("type") or "").upper(),
                "qty":        int(qty),
                "price":      price,
                "value_cr":   value_cr,
                "date":       r.get("date") or str(date.today()),
                "deal_type":  deal_type,
            })

    log.info("AMC deals fetched: %d records (filter=%s)", len(records), filter_amc or "all")
    return records


def summarise(records: list[dict]) -> dict[str, dict]:
    """
    Group by AMC → {buys: [...], sells: [...], buy_value_cr, sell_value_cr}
    """
    out: dict[str, dict] = {}
    for r in records:
        amc = r["amc"]
        if amc not in out:
            out[amc] = {"buys": [], "sells": [], "buy_value_cr": 0.0, "sell_value_cr": 0.0}
        if r["type"] == "BUY":
            out[amc]["buys"].append(r)
            out[amc]["buy_value_cr"] += r["value_cr"] or 0
        else:
            out[amc]["sells"].append(r)
            out[amc]["sell_value_cr"] += r["value_cr"] or 0
    return out
