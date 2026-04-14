"""
Daily AMC Bulk/Block Deal Report.

Fetches today's AMC activity from NSE bulk/block deal endpoints,
generates a Telegram summary and a PDF one-pager.

Usage:
  python main.py amc-report              # send to Telegram + save PDF
  python main.py amc-report --dry-run    # print only, no send, save PDF
  python main.py amc-report --amc "HDFC MF"  # single AMC only
"""
import html
import logging
import os
from datetime import datetime

from config import IST, OWNER_CHAT_ID
from enrichers.amc_bulk_deals import fetch, summarise
from bot import send

log = logging.getLogger(__name__)

PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "store")


# ── Telegram report ───────────────────────────────────────────────────────────

def _tg_report(summary: dict, date_str: str) -> str:
    lines = [f"<b>AMC BULK/BLOCK DEALS — {date_str}</b>", ""]

    if not summary:
        lines.append("<i>No AMC bulk/block deals recorded today.</i>")
        return "\n".join(lines)

    for amc, data in sorted(summary.items()):
        buys  = data["buys"]
        sells = data["sells"]
        bv    = data["buy_value_cr"]
        sv    = data["sell_value_cr"]

        lines.append(f"<b>{html.escape(amc)}</b>")
        if buys:
            lines.append(f"  ▲ Bought  ₹{bv:.1f} Cr")
            for r in buys[:5]:
                vstr = f"  ₹{r['value_cr']:.1f} Cr" if r["value_cr"] else ""
                lines.append(f"    • {html.escape(r['symbol'])}  {int(r['qty']):,} @ ₹{r['price']:,.1f}{vstr}  [{r['deal_type']}]")
        if sells:
            lines.append(f"  ▼ Sold    ₹{sv:.1f} Cr")
            for r in sells[:5]:
                vstr = f"  ₹{r['value_cr']:.1f} Cr" if r["value_cr"] else ""
                lines.append(f"    • {html.escape(r['symbol'])}  {int(r['qty']):,} @ ₹{r['price']:,.1f}{vstr}  [{r['deal_type']}]")
        lines.append("")

    return "\n".join(lines)


# ── PDF report ────────────────────────────────────────────────────────────────

def _build_pdf(summary: dict, date_str: str) -> str | None:
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_fill_color(30, 30, 30)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, f"AMC Bulk/Block Deals  --  {date_str}", fill=True, ln=True)
        pdf.ln(4)

        if not summary:
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 8, "No AMC bulk/block deals recorded today.", ln=True)
        else:
            for amc, data in sorted(summary.items()):
                buys  = data["buys"]
                sells = data["sells"]
                bv    = data["buy_value_cr"]
                sv    = data["sell_value_cr"]

                # AMC header bar
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_fill_color(50, 100, 180)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(0, 8, f"  {amc}", fill=True, ln=True)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(1)

                col_w = [55, 35, 30, 28, 28, 22]  # Symbol, Qty, Price, Value Cr, Type, Deal

                def _header_row():
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.set_fill_color(220, 230, 245)
                    for txt, w in zip(["Symbol", "Qty", "Price (Rs)", "Value (Cr)", "B/S", "Type"], col_w):
                        pdf.cell(w, 6, txt, border=1, fill=True)
                    pdf.ln()

                def _data_row(r, is_buy: bool):
                    pdf.set_font("Helvetica", "", 8)
                    fill_col = (230, 255, 230) if is_buy else (255, 230, 230)
                    pdf.set_fill_color(*fill_col)
                    vals = [
                        r["symbol"],
                        f"{int(r['qty']):,}",
                        f"{r['price']:,.1f}",
                        f"{r['value_cr']:.1f}" if r["value_cr"] else "-",
                        "BUY" if is_buy else "SELL",
                        r["deal_type"],
                    ]
                    for v, w in zip(vals, col_w):
                        pdf.cell(w, 5, str(v), border=1, fill=True)
                    pdf.ln()

                all_rows = [(r, True) for r in buys] + [(r, False) for r in sells]
                if all_rows:
                    _header_row()
                    for r, is_buy in all_rows:
                        _data_row(r, is_buy)

                # Summary line
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(60, 60, 60)
                parts = []
                if buys:  parts.append(f"Bought Rs{bv:.1f} Cr")
                if sells: parts.append(f"Sold Rs{sv:.1f} Cr")
                pdf.cell(0, 5, "  " + "   |   ".join(parts), ln=True)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(3)

        # Footer
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 5, f"Generated by nanoclaw | Source: NSE Bulk/Block Deal API | {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}",
                 ln=True, align="C")

        os.makedirs(PDF_DIR, exist_ok=True)
        fname = f"amc_deals_{date_str.replace(' ', '_').replace(',', '')}.pdf"
        path  = os.path.join(PDF_DIR, fname)
        pdf.output(path)
        log.info("PDF saved: %s", path)
        return path

    except Exception as e:
        log.warning("PDF generation failed: %s", e)
        return None


# ── Entry point ───────────────────────────────────────────────────────────────

def run(dry_run: bool = False, filter_amc: str | None = None) -> None:
    date_str = datetime.now(IST).strftime("%d %b %Y")
    log.info("AMC report: fetching deals (filter=%s)", filter_amc or "all")

    records = fetch(filter_amc=filter_amc)
    summary = summarise(records)

    tg_text = _tg_report(summary, date_str)
    pdf_path = _build_pdf(summary, date_str)

    if dry_run:
        print(tg_text)
        if pdf_path:
            print(f"\nPDF saved: {pdf_path}")
        return

    send(tg_text, chat_id=OWNER_CHAT_ID)

    if pdf_path:
        try:
            import requests as _req
            from config import TG_TOKEN
            with open(pdf_path, "rb") as f:
                _req.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument",
                    data={"chat_id": OWNER_CHAT_ID, "caption": f"AMC Deals PDF — {date_str}"},
                    files={"document": f},
                    timeout=30,
                )
            log.info("PDF sent to Telegram")
        except Exception as e:
            log.warning("PDF Telegram send failed: %s", e)
