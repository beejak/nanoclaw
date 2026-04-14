"""
AGENDA: Signal extraction correctness.

Covers every extraction path that has caused a production bug or is
business-critical. Each test is named to describe the scenario so
failures read as plain English in CI output.
"""
import pytest
from signals.extractor import extract, is_option, base_symbol


# ===========================================================================
# INDEX OPTIONS
# ===========================================================================

class TestIndexOptions:
    """NIFTY / BANKNIFTY / SENSEX option extraction."""

    def test_nifty_call_with_entry(self):
        sig = extract("BUY NIFTY 23700CE @ 74 SL 45 TGT 100/120", mode="indices")
        assert sig is not None
        assert sig["instrument"] == "NIFTY 23700CE"
        assert sig["direction"] == "BUY"
        assert sig["entry"] == 74.0
        assert sig["sl"] == 45.0

    def test_nifty_put_with_entry(self):
        sig = extract("BUY 23800PE @ 130 SL 110", mode="indices")
        assert sig is not None
        assert sig["instrument"] == "NIFTY 23800PE"
        assert sig["direction"] == "BUY"

    def test_banknifty_call(self):
        sig = extract("BUY BANKNIFTY 55000CE @ 1050 SL 700", mode="indices")
        assert sig is not None
        assert sig["instrument"] == "BANKNIFTY 55000CE"

    def test_sensex_call(self):
        sig = extract("BUY SENSEX 77000CE @ 530", mode="indices")
        assert sig is not None
        assert sig["instrument"] == "SENSEX 77000CE"

    def test_strike_below_15000_rejected(self):
        """Regression: NIFTY 1400CE was logged as a real signal from misextraction."""
        sig = extract("BUY 1400CE @ 50 SL 45", mode="indices")
        assert sig is None, "Strike < 15000 must be rejected as non-NIFTY"

    def test_strike_3700_rejected(self):
        """Regression: HAL 3700CE was extracted as NIFTY 3700CE."""
        sig = extract("BUY 3700CE @ 157", mode="indices")
        assert sig is None, "Strike < 15000 must be rejected"

    def test_strike_5200_rejected(self):
        """Regression: HEROMOTOCO 5200CE was extracted as NIFTY 5200CE."""
        sig = extract("BUY 5200CE @ 155", mode="indices")
        assert sig is None, "Strike < 15000 must be rejected"

    def test_stock_option_not_attributed_to_nifty(self):
        """Regression: 'HAL 3700 CE' was logged as NIFTY 3700CE (day-1 bug)."""
        sig = extract("💛 HAL 3700 CE (apr)\nBUY ABOVE 157\nSL 147", mode="indices")
        assert sig is None, "Stock option preceding CE/PE must not become NIFTY option"

    def test_hcltech_option_not_nifty(self):
        """Regression: 'HCLTECH 1400 CE' was logged as NIFTY 1400CE."""
        sig = extract("HCLTECH 1400 CE BUY @ 50 SL 45.8", mode="indices")
        assert sig is None, "HCLTECH 1400CE is a stock option — should not be NIFTY"

    def test_sell_direction_extracted(self):
        sig = extract("SELL NIFTY 24000CE @ 205", mode="indices")
        assert sig is not None
        assert sig["direction"] == "SELL"

    def test_at_least_one_target_extracted(self):
        """Extractor captures the first target; multiple targets via slash notation
        is a known limitation of _common() — covered separately in backlog."""
        sig = extract("BUY NIFTY 23700CE TGT 100 SL 80", mode="indices")
        assert sig is not None
        assert len(sig["targets"]) >= 1
        assert sig["targets"][0] == 100.0


# ===========================================================================
# STOCK SIGNALS
# ===========================================================================

class TestStockSignals:
    """Individual NSE stock extraction."""

    def test_basic_stock_buy(self, test_db):
        sig = extract("BUY HDFCBANK @ 1620 SL 1590 TGT 1660", mode="stocks")
        assert sig is not None
        assert sig["instrument"] == "HDFCBANK"
        assert sig["direction"] == "BUY"
        assert sig["entry"] == 1620.0
        assert sig["sl"] == 1590.0

    def test_stock_sell(self, test_db):
        sig = extract("SELL WIPRO @ 220", mode="stocks")
        assert sig is not None
        assert sig["instrument"] == "WIPRO"
        assert sig["direction"] == "SELL"

    def test_stock_option_extracted(self, test_db):
        sig = extract("BUY HDFCBANK 1600CE @ 50 SL 40", mode="stocks")
        assert sig is not None
        assert sig["instrument"] == "HDFCBANK 1600CE"

    def test_hcltech_option_extracted_in_stocks_mode(self, test_db):
        """HCLTECH 1400CE should extract correctly in stocks mode."""
        sig = extract("HCLTECH 1400 CE BUY @ 50 SL 45.8", mode="stocks")
        assert sig is not None
        assert sig["instrument"] == "HCLTECH 1400CE"
        assert sig["direction"] == "BUY"

    def test_hal_option_extracted_in_stocks_mode(self, test_db):
        """HAL 3700CE should extract correctly in stocks mode."""
        sig = extract("💛 HAL 3700 CE BUY ABOVE 157 SL 147", mode="stocks")
        assert sig is not None
        assert sig["instrument"] == "HAL 3700CE"

    def test_noise_words_not_tickers(self, test_db):
        """Common English words must never be treated as stock tickers."""
        for word in ("YOUR", "HIGH", "OPEN", "CLOSE", "TREND", "RISK"):
            sig = extract(f"{word} stop loss hit today", mode="stocks")
            if sig is not None:
                assert sig["instrument"] != word, \
                    f"Noise word '{word}' must not be extracted as a ticker"

    def test_index_excluded_from_stocks_mode(self, test_db):
        """NIFTY/BANKNIFTY must not be extracted as stocks."""
        sig = extract("BUY NIFTY @ 23800", mode="stocks")
        assert sig is None or sig["instrument"] not in ("NIFTY", "BANKNIFTY", "SENSEX")


# ===========================================================================
# FUTURES
# ===========================================================================

class TestFutures:
    """Futures signal extraction."""

    def test_nifty_futures(self):
        sig = extract("BUY NIFTY FUT @ 23850 SL 23700", mode="futures")
        assert sig is not None
        assert "FUT" in sig["instrument"]

    def test_stock_futures(self, test_db):
        sig = extract("BUY INFY FUT @ 1400", mode="futures")
        assert sig is not None
        assert sig["instrument"] == "INFY FUT"


# ===========================================================================
# HELPERS
# ===========================================================================

class TestHelpers:
    """base_symbol and is_option utility functions."""

    def test_base_symbol_plain_stock(self):
        assert base_symbol("HDFCBANK") == "HDFCBANK"

    def test_base_symbol_option(self):
        assert base_symbol("NIFTY 23700CE") == "NIFTY"

    def test_base_symbol_future(self):
        assert base_symbol("INFY FUT") == "INFY"

    def test_is_option_index(self):
        assert is_option("NIFTY 23700CE") is True

    def test_is_option_stock(self):
        assert is_option("HDFCBANK 1600CE") is True

    def test_is_option_plain_stock(self):
        assert is_option("HDFCBANK") is False

    def test_is_option_future(self):
        assert is_option("NIFTY FUT") is False
