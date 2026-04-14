"""
AGENDA: Signal grading correctness.

Covers the grade_signal() function for both options (directional) and
stocks/indices (price-based). Every production bug found to date has a
regression test here.
"""
import json
import pytest
from reports.eod import grade_signal


def _sig(instrument, direction="BUY", entry=None, sl=None, targets=None):
    return {
        "instrument": instrument,
        "direction":  direction,
        "entry":      entry,
        "sl":         sl,
        "targets":    json.dumps(targets or []),
    }


def _q(ltp, high=None, low=None, pct=0.0):
    return {
        "ltp":  ltp,
        "high": high or ltp,
        "low":  low  or ltp,
        "pct":  pct,
    }


# ===========================================================================
# OPTIONS — directional grading against underlying
# ===========================================================================

class TestOptionGrading:
    """
    Regression suite for the options grading bug:
    options were compared against underlying price (e.g. 23800 >= 100 → always TGT_HIT).
    Now graded directionally: underlying ±0.5% threshold.
    """

    def test_buy_call_underlying_up_is_hit(self):
        result, note = grade_signal(
            _sig("NIFTY 23700CE", "BUY", entry=74, sl=45, targets=[100]),
            _q(23850, high=24000, low=23600, pct=1.0),
        )
        assert result == "TGT1_HIT"
        assert "directional correct" in note

    def test_buy_call_underlying_down_is_sl(self):
        result, note = grade_signal(
            _sig("NIFTY 23700CE", "BUY", entry=74),
            _q(23550, high=23700, low=23400, pct=-1.1),
        )
        assert result == "SL_HIT"
        assert "directional wrong" in note

    def test_buy_call_neutral_move_is_open(self):
        """Underlying moved only 0.3% — below threshold, no grade."""
        result, _ = grade_signal(
            _sig("NIFTY 23700CE", "BUY", entry=74),
            _q(23800, pct=0.3),
        )
        assert result == "OPEN"

    def test_buy_put_underlying_down_is_hit(self):
        result, _ = grade_signal(
            _sig("NIFTY 23800PE", "BUY", entry=130, sl=110),
            _q(23500, pct=-1.2),
        )
        assert result == "TGT1_HIT"

    def test_buy_put_underlying_up_is_sl(self):
        result, _ = grade_signal(
            _sig("NIFTY 23800PE", "BUY", entry=130),
            _q(24100, pct=1.5),
        )
        assert result == "SL_HIT"

    def test_sell_call_underlying_down_is_hit(self):
        result, _ = grade_signal(
            _sig("NIFTY 24000CE", "SELL", entry=205),
            _q(23400, pct=-1.8),
        )
        assert result == "TGT1_HIT"

    def test_sell_put_underlying_up_is_hit(self):
        result, _ = grade_signal(
            _sig("BANKNIFTY 50000PE", "SELL"),
            _q(51500, pct=0.9),
        )
        assert result == "TGT1_HIT"

    def test_option_no_direction_is_open(self):
        """No direction on an option — cannot grade, stays OPEN."""
        result, note = grade_signal(
            _sig("NIFTY 23700CE", direction=""),
            _q(23800, pct=1.0),
        )
        assert result == "OPEN"
        assert "no direction" in note

    def test_option_no_nse_data_is_open(self):
        result, note = grade_signal(_sig("NIFTY 23700CE", "BUY"), None)
        assert result == "OPEN"
        assert "no NSE data" in note

    def test_stock_option_graded_directionally(self):
        """Stock options (HDFCBANK 1600CE) use the same directional logic."""
        result, _ = grade_signal(
            _sig("HDFCBANK 1600CE", "BUY"),
            _q(1650, pct=1.5),
        )
        assert result == "TGT1_HIT"

    def test_regression_underlying_price_never_auto_hits_premium_target(self):
        """
        Regression: old code did `high (24000) >= target (100)` → always TGT1_HIT.
        With directional grading, a neutral day must not be a hit.
        """
        result, _ = grade_signal(
            _sig("NIFTY 23700CE", "BUY", targets=[100]),
            _q(23800, high=24000, low=23600, pct=0.1),  # tiny move
        )
        assert result == "OPEN", \
            "Option with tiny underlying move must not auto-hit via premium target comparison"


# ===========================================================================
# STOCKS & INDICES — price-based grading
# ===========================================================================

class TestStockGrading:
    """Standard entry/SL/target grading for stocks and plain indices."""

    def test_buy_target1_hit(self):
        result, note = grade_signal(
            _sig("HDFCBANK", "BUY", entry=1620, sl=1590, targets=[1650, 1680]),
            _q(1655, high=1660, low=1600),
        )
        assert result == "TGT1_HIT"
        assert "1650" in note

    def test_buy_target2_hit(self):
        result, _ = grade_signal(
            _sig("HDFCBANK", "BUY", entry=1620, targets=[1650, 1680]),
            _q(1685, high=1690, low=1620),
        )
        assert result == "TGT2_HIT"

    def test_buy_sl_hit(self):
        result, note = grade_signal(
            _sig("HDFCBANK", "BUY", entry=1620, sl=1590),
            _q(1570, high=1610, low=1580),
        )
        assert result == "SL_HIT"
        assert "1580" in note

    def test_buy_open_between_sl_and_target(self):
        result, _ = grade_signal(
            _sig("HDFCBANK", "BUY", entry=1620, sl=1590, targets=[1660]),
            _q(1635, high=1645, low=1600),
        )
        assert result == "OPEN"

    def test_sell_target_hit(self):
        result, _ = grade_signal(
            _sig("WIPRO", "SELL", entry=220, sl=228, targets=[210, 205]),
            _q(207, high=222, low=205),
        )
        assert result == "TGT2_HIT"

    def test_sell_sl_hit(self):
        result, _ = grade_signal(
            _sig("WIPRO", "SELL", entry=220, sl=228),
            _q(230, high=230, low=218),
        )
        assert result == "SL_HIT"

    def test_no_entry_no_sl_no_targets_stays_open(self):
        """Signal with no levels at all should stay OPEN, not crash."""
        result, _ = grade_signal(
            _sig("NIFTY", "BUY"),
            _q(23800),
        )
        assert result == "OPEN"

    def test_no_nse_data_stays_open(self):
        result, note = grade_signal(_sig("RELIANCE", "BUY", entry=1250), None)
        assert result == "OPEN"
        assert "no NSE data" in note

    def test_undirected_stock_signal(self):
        """No direction — should not raise, stays OPEN."""
        result, _ = grade_signal(
            _sig("INFY", direction=""),
            _q(1400),
        )
        assert result == "OPEN"
