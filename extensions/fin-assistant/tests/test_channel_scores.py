"""
AGENDA: Channel scoring accuracy.

Tests the learning loop that drives channel confidence ratings and
mute suggestions. Bad scoring = wrong signals surfaced to the user.
"""
import pytest
from tests.conftest import make_signal
from learning import channel_scores as ch_scores


def _insert_signals(db_file, signals):
    import sqlite3
    conn = sqlite3.connect(str(db_file))
    for s in signals:
        conn.execute("""
            INSERT OR REPLACE INTO signal_log
              (id, date, channel, instrument, direction, entry, sl,
               targets, raw_text, sent_at, result, result_note, graded_at)
            VALUES (:id,:date,:channel,:instrument,:direction,:entry,:sl,
                    :targets,:raw_text,:sent_at,:result,:result_note,:graded_at)
        """, s)
    conn.commit()
    conn.close()


class TestHitRateCalculation:

    def test_all_hits(self, test_db):
        _insert_signals(test_db, [
            make_signal("NIFTY", result="TGT1_HIT", channel="Chan A"),
            make_signal("NIFTY", result="TGT1_HIT", channel="Chan A"),
            make_signal("NIFTY", result="TGT1_HIT", channel="Chan A"),
        ])
        scores = ch_scores.update()
        assert scores["Chan A"]["hit_rate"] == 100.0
        assert scores["Chan A"]["confidence"] == "HIGH"

    def test_mixed_hits_and_sl(self, test_db):
        _insert_signals(test_db, [
            make_signal("NIFTY", result="TGT1_HIT", channel="Chan B"),
            make_signal("NIFTY", result="TGT1_HIT", channel="Chan B"),
            make_signal("NIFTY", result="SL_HIT",   channel="Chan B"),
            make_signal("NIFTY", result="SL_HIT",   channel="Chan B"),
        ])
        scores = ch_scores.update()
        assert scores["Chan B"]["hit_rate"] == 50.0
        assert scores["Chan B"]["confidence"] == "MED"

    def test_open_signals_excluded_from_rate(self, test_db):
        """OPEN signals must not dilute the hit rate — only closed trades count."""
        _insert_signals(test_db, [
            make_signal("NIFTY", result="TGT1_HIT", channel="Chan C"),
            make_signal("NIFTY", result="OPEN",     channel="Chan C"),
            make_signal("NIFTY", result="OPEN",     channel="Chan C"),
            make_signal("NIFTY", result="OPEN",     channel="Chan C"),
        ])
        scores = ch_scores.update()
        # Channel appears because it has 1 closed signal; rate = 1/1 = 100%
        assert "Chan C" in scores
        assert scores["Chan C"]["hit_rate"] == 100.0, \
            "3 OPEN signals must not dilute the 1 TGT1_HIT result"

    def test_all_open_signals_channel_not_in_scores(self, test_db):
        """Channel with only OPEN signals has no closed data — absent from scores."""
        _insert_signals(test_db, [
            make_signal("NIFTY", result="OPEN", channel="Chan D"),
            make_signal("NIFTY", result="OPEN", channel="Chan D"),
        ])
        scores = ch_scores.update()
        assert "Chan D" not in scores, \
            "All-OPEN channel must not appear in scores — no closed signals to rate"


class TestConfidenceBands:

    def test_high_confidence_at_60_pct(self, test_db):
        signals = (
            [make_signal("NIFTY", result="TGT1_HIT", channel="High") for _ in range(3)] +
            [make_signal("NIFTY", result="SL_HIT",   channel="High") for _ in range(2)]
        )
        _insert_signals(test_db, signals)
        scores = ch_scores.update()
        assert scores["High"]["confidence"] == "HIGH"  # 60%

    def test_med_confidence_at_50_pct(self, test_db):
        signals = (
            [make_signal("NIFTY", result="TGT1_HIT", channel="Med") for _ in range(1)] +
            [make_signal("NIFTY", result="SL_HIT",   channel="Med") for _ in range(1)]
        )
        _insert_signals(test_db, signals)
        scores = ch_scores.update()
        assert scores["Med"]["confidence"] == "MED"   # 50%

    def test_low_confidence_below_40_pct(self, test_db):
        _insert_signals(test_db, [
            make_signal("NIFTY", result="TGT1_HIT", channel="Low"),
            make_signal("NIFTY", result="SL_HIT",   channel="Low"),
            make_signal("NIFTY", result="SL_HIT",   channel="Low"),
            make_signal("NIFTY", result="SL_HIT",   channel="Low"),
        ])
        scores = ch_scores.update()
        assert scores["Low"]["confidence"] == "LOW"   # 25%


class TestMuteSuggestion:

    def test_suggest_mute_below_25pct_with_10_signals(self, test_db):
        # Use list comprehension — list multiplication replicates the same dict reference
        signals = (
            [make_signal("NIFTY", result="TGT1_HIT", channel="Bad") for _ in range(2)] +
            [make_signal("NIFTY", result="SL_HIT",   channel="Bad") for _ in range(8)]
        )
        _insert_signals(test_db, signals)
        scores = ch_scores.update()
        assert scores["Bad"]["suggest_mute"] is True   # 20% < 25%, 10 closed signals

    def test_no_mute_below_25pct_fewer_than_10_signals(self, test_db):
        """Insufficient data — do not suggest mute prematurely."""
        signals = [make_signal("NIFTY", result="SL_HIT", channel="New") for _ in range(2)]
        _insert_signals(test_db, signals)
        scores = ch_scores.update()
        assert scores["New"]["suggest_mute"] is False

    def test_no_mute_above_threshold(self, test_db):
        signals = (
            [make_signal("NIFTY", result="TGT1_HIT", channel="Ok") for _ in range(5)] +
            [make_signal("NIFTY", result="SL_HIT",   channel="Ok") for _ in range(5)]
        )
        _insert_signals(test_db, signals)
        scores = ch_scores.update()
        assert scores["Ok"]["suggest_mute"] is False   # 50% ≥ 25%
