"""
Unit tests for team_batcher.py (Issue #181)

Tests team mention extraction, article batching, and prompt assembly.
No LLM calls are made.
"""

import pytest

from src.team_batcher import (
    ArticleRecord,
    NFL_TEAMS,
    annotate_team_mentions,
    batch_articles_by_team,
    build_batched_prompt,
    extract_team_mentions,
)


# ---------------------------------------------------------------------------
# extract_team_mentions
# ---------------------------------------------------------------------------


class TestExtractTeamMentions:
    def test_full_team_name(self):
        assert extract_team_mentions("The Chicago Bears drafted Caleb Williams.") == {"CHI"}

    def test_short_name_only(self):
        assert extract_team_mentions("Bears fans are excited.") == {"CHI"}

    def test_multiple_teams(self):
        result = extract_team_mentions("Chiefs beat the Eagles 28-17.")
        assert result == {"KC", "PHI"}

    def test_case_insensitive(self):
        assert extract_team_mentions("PATRIOTS signed a new quarterback.") == {"NE"}

    def test_abbreviation_match(self):
        assert "BAL" in extract_team_mentions("Ravens QB Lamar Jackson throws for 300 yards.")

    def test_no_team_returns_empty(self):
        assert extract_team_mentions("Today is a beautiful day.") == set()

    def test_all_32_teams_covered(self):
        # Every abbreviated team should appear in at least one entry in NFL_TEAMS values
        all_abbrs = set(NFL_TEAMS.values())
        assert len(all_abbrs) == 32, f"Expected 32 teams, got {len(all_abbrs)}: {all_abbrs}"

    def test_legacy_alias(self):
        assert extract_team_mentions("Oakland Raiders moved to Las Vegas.") == {"LV"}

    def test_49ers_numeric_alias(self):
        assert extract_team_mentions("The 49ers are Super Bowl contenders.") == {"SF"}

    def test_city_name_in_longer_phrase(self):
        result = extract_team_mentions("Green Bay Packers will win the NFC North.")
        assert "GB" in result

    def test_multiple_mentions_same_team_deduped(self):
        result = extract_team_mentions("Chiefs win. Chiefs are great. Kansas City Chiefs.")
        assert result == {"KC"}


# ---------------------------------------------------------------------------
# batch_articles_by_team
# ---------------------------------------------------------------------------


def _make_article(content_hash: str, text: str, date: str = "", pundit: str = "") -> ArticleRecord:
    return ArticleRecord(
        content_hash=content_hash,
        raw_text=text,
        published_date=date,
        pundit_name=pundit,
    )


class TestBatchArticlesByTeam:
    def test_single_article_single_team(self):
        articles = [_make_article("h1", "The Bears traded their quarterback.")]
        batches = batch_articles_by_team(articles)
        assert "CHI" in batches
        assert len(batches["CHI"]) == 1
        assert len(batches["CHI"][0]) == 1

    def test_multi_team_article_appears_in_both(self):
        articles = [_make_article("h1", "Chiefs beat Eagles 28-17.")]
        batches = batch_articles_by_team(articles)
        assert "KC" in batches
        assert "PHI" in batches

    def test_splits_into_sub_batches_when_over_limit(self):
        articles = [
            _make_article(f"h{i}", "Bears offensive coordinator speaks.", date=f"2026-04-{i:02d}")
            for i in range(1, 8)  # 7 articles about Bears
        ]
        batches = batch_articles_by_team(articles, max_per_batch=3)
        assert "CHI" in batches
        chi_batches = batches["CHI"]
        # 7 articles split into 3 batches: [3, 3, 1]
        assert len(chi_batches) == 3
        assert len(chi_batches[0]) == 3
        assert len(chi_batches[1]) == 3
        assert len(chi_batches[2]) == 1

    def test_sorted_by_date(self):
        articles = [
            _make_article("h3", "Bears fire coordinator.", date="2026-04-20"),
            _make_article("h1", "Bears hire new coach.", date="2026-04-01"),
            _make_article("h2", "Bears sign free agent.", date="2026-04-10"),
        ]
        batches = batch_articles_by_team(articles)
        chi_batch = batches["CHI"][0]
        dates = [a.published_date for a in chi_batch]
        assert dates == sorted(dates)

    def test_no_team_article_not_batched(self):
        articles = [_make_article("h1", "The weather today is sunny.")]
        batches = batch_articles_by_team(articles)
        assert len(batches) == 0

    def test_empty_input(self):
        batches = batch_articles_by_team([])
        assert batches == {}

    def test_pre_annotated_teams_used(self):
        article = ArticleRecord(
            content_hash="h1",
            raw_text="Some generic text with no team name.",
            teams_mentioned={"DAL"},  # pre-annotated
        )
        batches = batch_articles_by_team([article])
        assert "DAL" in batches


# ---------------------------------------------------------------------------
# build_batched_prompt
# ---------------------------------------------------------------------------


class TestBuildBatchedPrompt:
    def _make_articles(self, n: int) -> list[ArticleRecord]:
        return [
            ArticleRecord(
                content_hash=f"h{i}",
                raw_text=f"Bears will take Caleb Williams at pick {i}.",
                pundit_name=f"Pundit {i}",
                source_name="ESPN",
                published_date="2026-04-20",
                title=f"Draft Preview {i}",
            )
            for i in range(1, n + 1)
        ]

    def test_prompt_contains_team_name(self):
        articles = self._make_articles(2)
        prompt = build_batched_prompt("CHI", articles)
        assert "Chicago Bears" in prompt

    def test_prompt_contains_pundit_names(self):
        articles = self._make_articles(2)
        prompt = build_batched_prompt("CHI", articles)
        assert "Pundit 1" in prompt
        assert "Pundit 2" in prompt

    def test_prompt_contains_article_count(self):
        articles = self._make_articles(3)
        prompt = build_batched_prompt("CHI", articles)
        assert "3 article" in prompt

    def test_prompt_contains_target_team(self):
        articles = self._make_articles(1)
        prompt = build_batched_prompt("DAL", articles)
        assert '"DAL"' in prompt

    def test_prompt_truncates_long_article(self):
        long_text = "x" * 5000
        article = ArticleRecord(
            content_hash="h1",
            raw_text=long_text,
            pundit_name="Big Pundit",
        )
        prompt = build_batched_prompt("SF", [article])
        # Truncated text + "..." should be present
        assert "..." in prompt
        # Should not contain all 5000 chars
        assert len(prompt) < len(long_text) + 2000

    def test_prompt_includes_current_date(self):
        articles = self._make_articles(1)
        prompt = build_batched_prompt("KC", articles, current_date="2026-04-24")
        assert "2026-04-24" in prompt

    def test_prompt_is_valid_json_template(self):
        articles = self._make_articles(1)
        prompt = build_batched_prompt("NE", articles)
        # Should contain JSON schema keys
        assert "extracted_claim" in prompt
        assert "pundit_name" in prompt
        assert "consensus_note" in prompt

    def test_unknown_team_abbr_uses_abbr_as_name(self):
        articles = self._make_articles(1)
        prompt = build_batched_prompt("XYZ", articles)
        assert "XYZ" in prompt


# ---------------------------------------------------------------------------
# annotate_team_mentions
# ---------------------------------------------------------------------------


class TestAnnotateTeamMentions:
    def test_annotates_in_place(self):
        articles = [
            ArticleRecord(content_hash="h1", raw_text="Eagles signed a receiver."),
            ArticleRecord(content_hash="h2", raw_text="No teams mentioned here."),
        ]
        result = annotate_team_mentions(articles)
        assert result is articles  # same list returned
        assert articles[0].teams_mentioned == {"PHI"}
        assert articles[1].teams_mentioned == set()

    def test_skips_already_annotated(self):
        article = ArticleRecord(
            content_hash="h1",
            raw_text="Bears are great.",
            teams_mentioned={"KC"},  # already set — should not overwrite
        )
        annotate_team_mentions([article])
        assert article.teams_mentioned == {"KC"}
