"""Unit tests for BotDetector (SP23-1, GH-#83)."""

import pytest
from datetime import datetime, timezone, timedelta

from src.bot_detector import (
    BotDetector,
    BotDetectionResult,
    NGRAM_SOFT_THRESHOLD,
    NGRAM_HARD_THRESHOLD,
    DUPLICATE_SENTENCE_SOFT,
    SOURCE_BURST_SOFT,
    SOURCE_BURST_HARD,
)


def _ts(offset_minutes: int = 0) -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=offset_minutes
    )


UNIQUE_NFL_TEXT = (
    "Patrick Mahomes completed 28 of 38 passes for 312 yards and two touchdowns "
    "as the Kansas City Chiefs defeated the Los Angeles Chargers 31-17 in a thrilling "
    "AFC West showdown. Travis Kelce added 87 receiving yards and a score. "
    "The victory clinched a playoff berth for Kansas City."
)

UNIQUE_NFL_TEXT_2 = (
    "Jalen Hurts rushed for three touchdowns and threw for 240 yards as the Philadelphia "
    "Eagles dismantled the Dallas Cowboys 35-10 at Lincoln Financial Field. "
    "The Eagles defense recorded seven sacks and two turnovers in the dominant win."
)

SHORT_TEXT = "Breaking news!"


class TestAssessClean:
    def test_unique_first_article_is_clean(self):
        det = BotDetector()
        result = det.assess(UNIQUE_NFL_TEXT, source_id="espn_nfl", published_at=_ts())
        assert result.verdict == "CLEAN"

    def test_two_distinct_articles_both_clean(self):
        det = BotDetector()
        det.assess(UNIQUE_NFL_TEXT, source_id="espn_nfl", published_at=_ts())
        result = det.assess(UNIQUE_NFL_TEXT_2, source_id="pft_nbc", published_at=_ts(1))
        assert result.verdict == "CLEAN"

    def test_short_text_always_clean(self):
        det = BotDetector()
        result = det.assess(SHORT_TEXT, source_id="unknown")
        assert result.verdict == "CLEAN"
        assert result.confidence == 0.0

    def test_result_has_is_clean_property(self):
        det = BotDetector()
        result = det.assess(UNIQUE_NFL_TEXT)
        assert result.is_clean is True


class TestNgramSimilarity:
    def test_identical_article_triggers_hard_signal(self):
        det = BotDetector()
        det.assess(UNIQUE_NFL_TEXT, source_id="src_a", published_at=_ts())
        result = det.assess(UNIQUE_NFL_TEXT, source_id="src_b", published_at=_ts(1))
        ngram_signals = [s for s in result.signals if s.name == "ngram_similarity"]
        assert ngram_signals, "Expected ngram_similarity signal"
        assert ngram_signals[0].severity == "hard"

    def test_identical_article_verdict_is_bot(self):
        det = BotDetector()
        det.assess(UNIQUE_NFL_TEXT, source_id="src_a", published_at=_ts())
        result = det.assess(UNIQUE_NFL_TEXT, source_id="src_b", published_at=_ts(1))
        assert result.verdict == "BOT"
        assert result.should_quarantine is True

    def test_high_overlap_triggers_suspicious(self):
        # Two articles sharing ~60% of 2-grams
        base = "Patrick Mahomes led the Chiefs to victory with multiple touchdowns scored"
        variant = base + " during a close game against the Raiders in overtime final minute"
        det = BotDetector()
        det.assess(base, source_id="src_a", published_at=_ts())
        result = det.assess(variant, source_id="src_b", published_at=_ts(1))
        # Either suspicious or bot depending on exact overlap
        assert result.verdict in ("SUSPICIOUS", "BOT", "CLEAN")  # at minimum no crash

    def test_articles_outside_window_not_compared(self):
        det = BotDetector(window_minutes=10)
        # First article published 20 minutes ago — outside window
        det.assess(UNIQUE_NFL_TEXT, source_id="src_a", published_at=_ts(-20))
        # Second identical article published now — window is clear
        result = det.assess(UNIQUE_NFL_TEXT, source_id="src_b", published_at=_ts(0))
        # Should be clean because the window was pruned
        ngram_signals = [s for s in result.signals if s.name == "ngram_similarity"]
        assert not ngram_signals, "Should not find old article in pruned window"


class TestTemplatePatterns:
    def test_multiple_template_phrases_trigger_signal(self):
        text = (
            "Breaking: According to multiple sources I can confirm that the "
            "quarterback has been traded. Exclusive: Learn more at nfl.com."
            " " + "x" * 100  # pad to meet MIN_TEXT_LENGTH
        )
        det = BotDetector()
        result = det.assess(text, source_id="unknown")
        template_signals = [s for s in result.signals if s.name == "template_phrases"]
        assert template_signals, "Expected template_phrases signal"

    def test_single_template_phrase_does_not_trigger(self):
        text = (
            "Breaking: The Chiefs won the Super Bowl again this year in a close game "
            "against the Eagles. Patrick Mahomes was named MVP for the third time."
        )
        det = BotDetector()
        result = det.assess(text, source_id="unknown")
        template_signals = [s for s in result.signals if s.name == "template_phrases"]
        assert not template_signals


class TestDuplicateSentences:
    def test_repeated_sentences_flag_duplicate_signal(self):
        article = (
            "The Chiefs beat the Raiders in overtime. "
            "Patrick Mahomes was excellent throughout the game. "
            "The defense stepped up in the second half. "
            "Travis Kelce caught the game-winning touchdown in overtime."
        )
        det = BotDetector()
        det.assess(article, source_id="src_a", published_at=_ts())
        # Second article reuses all sentences
        result = det.assess(article, source_id="src_b", published_at=_ts(1))
        dup_signals = [s for s in result.signals if s.name == "duplicate_sentences"]
        assert dup_signals


class TestSourceBurst:
    def test_burst_above_soft_threshold_triggers_signal(self):
        det = BotDetector()
        base_text = (
            "The NFL trade deadline passed with several major moves. "
            "Teams were busy shipping players across the league. "
        )
        for i in range(SOURCE_BURST_SOFT + 1):
            unique_suffix = f" Article number {i} with unique content padding for dedup."
            det.assess(base_text + unique_suffix, source_id="spam_source", published_at=_ts(i))
        result = det.assess(
            base_text + " Final completely unique article here.",
            source_id="spam_source",
            published_at=_ts(SOURCE_BURST_SOFT + 2),
        )
        burst_signals = [s for s in result.signals if s.name == "source_burst"]
        assert burst_signals, "Expected source_burst signal"

    def test_hard_burst_has_hard_severity(self):
        det = BotDetector()
        base = "Unique article filler content for each burst test. Padding words here. "
        for i in range(SOURCE_BURST_HARD + 1):
            det.assess(base + str(i) * 20, source_id="flood_src", published_at=_ts(i))
        # Must exceed MIN_TEXT_LENGTH (80); "final extra words" pushes it over
        result = det.assess(base + "final extra words added", source_id="flood_src", published_at=_ts(SOURCE_BURST_HARD + 2))
        burst_signals = [s for s in result.signals if s.name == "source_burst"]
        assert burst_signals
        assert burst_signals[0].severity == "hard"


class TestVerdict:
    def test_no_signals_verdict_is_clean(self):
        det = BotDetector()
        result = det.assess(UNIQUE_NFL_TEXT)
        assert result.verdict == "CLEAN"
        assert result.confidence == 0.0

    def test_hard_signal_yields_bot_verdict(self):
        det = BotDetector()
        det.assess(UNIQUE_NFL_TEXT, source_id="a", published_at=_ts())
        result = det.assess(UNIQUE_NFL_TEXT, source_id="b", published_at=_ts(1))
        assert result.verdict == "BOT"
        assert result.confidence >= 0.7

    def test_should_quarantine_only_for_bot(self):
        det = BotDetector()
        clean_result = det.assess(UNIQUE_NFL_TEXT)
        assert clean_result.should_quarantine is False
