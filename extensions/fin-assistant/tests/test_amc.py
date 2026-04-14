"""
AGENDA: AMC bulk/block deal matching accuracy.

Tests the fuzzy AMC name matching that powers the daily AMC report.
Wrong matches = wrong channel getting attributed deals.
"""
import pytest
from enrichers.amc_bulk_deals import _match_amc


class TestAmcNameMatching:

    # ── Known fund houses must match ─────────────────────────────────────────

    def test_hdfc_mutual_fund(self):
        assert _match_amc("HDFC Mutual Fund") == "HDFC MF"

    def test_hdfc_amc_short(self):
        # "HDFC AMC" fragment maps to label "HDFC MF"
        assert _match_amc("HDFC AMC") == "HDFC MF"

    def test_sbi_mutual_fund(self):
        assert _match_amc("SBI Mutual Fund") == "SBI MF"

    def test_sbi_mf_short(self):
        assert _match_amc("SBI MF") == "SBI MF"

    def test_nippon_india(self):
        result = _match_amc("Nippon India Mutual Fund")
        assert result is not None
        assert "Nippon" in result

    def test_icici_prudential(self):
        result = _match_amc("ICICI Prudential Asset Management")
        assert result is not None
        assert "ICICI" in result

    def test_axis_mf(self):
        result = _match_amc("Axis Mutual Fund")
        assert result is not None
        assert "Axis" in result

    def test_kotak_mf(self):
        # Fragment used in AMC_NAMES is "KOTAK MUTUAL" or "KOTAK AMC"
        result = _match_amc("Kotak Mutual Fund")
        assert result is not None
        assert "Kotak" in result

    # ── Non-AMC clients must return None ─────────────────────────────────────

    def test_non_amc_client_returns_none(self):
        assert _match_amc("Rakesh Jhunjhunwala") is None

    def test_corporate_name_returns_none(self):
        assert _match_amc("Reliance Industries Limited") is None

    def test_empty_string_returns_none(self):
        assert _match_amc("") is None

    def test_random_text_returns_none(self):
        assert _match_amc("Some Random Investor Pvt Ltd") is None

    # ── Case insensitivity ───────────────────────────────────────────────────

    def test_match_is_case_insensitive(self):
        upper = _match_amc("HDFC MUTUAL FUND")
        lower = _match_amc("hdfc mutual fund")
        assert upper == lower
        assert upper is not None
