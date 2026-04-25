"""
Local RAG Pipeline Orchestration (Issue #182)

Wires together the full extraction flow:
  1. Fetch unprocessed media from BigQuery
  2. Annotate each article with mentioned NFL teams (team_batcher)
  3. Group articles by team into batches of ≤5 (reduces LLM round-trips 3-5x)
  4. Build a batched extraction prompt per team-group
  5. Send to configured LLM provider (Ollama local by default)
  6. Map returned predictions back to source articles → ingest to ledger
  7. Mark processed

Controlled entirely by pipeline/config/llm_config.yaml:

    batching:
      enabled: true
      max_articles_per_batch: 5
      article_truncate_chars: 1500

When batching.enabled = false, falls back to the existing per-article
extraction in assertion_extractor.run_extraction().
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from src.assertion_extractor import (
    PunditPrediction,
    _deduplicate_claims,
    get_unprocessed_media,
    mark_as_processed,
)
from src.cryptographic_ledger import ingest_batch
from src.db_manager import DBManager
from src.llm_provider import LLMProvider, get_provider_with_fallback, load_llm_config
from src.team_batcher import (
    BATCH_PROMPT_VERSION,
    ArticleRecord,
    annotate_team_mentions,
    batch_articles_by_team,
    build_batched_prompt,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_article(row: pd.Series) -> ArticleRecord:
    """Convert a raw_pundit_media row into an ArticleRecord for team batching."""
    pub = ""
    if pd.notna(row.get("published_at")):
        try:
            pub = pd.Timestamp(row["published_at"]).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ArticleRecord(
        content_hash=str(row["content_hash"]),
        raw_text=str(row.get("raw_text", "")),
        title=str(row.get("title", "")),
        pundit_name=str(row.get("matched_pundit_name") or row.get("author") or ""),
        source_name=str(row.get("source_id", "")),
        published_date=pub,
    )


def _build_pundit_predictions(
    predictions: list[dict],
    source_article: ArticleRecord,
    pundit_id: str,
    source_url: str,
    prompt_version: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> list[PunditPrediction]:
    """Convert raw LLM prediction dicts to PunditPrediction objects."""
    result = []
    for pred in predictions:
        claim = pred.get("extracted_claim", "").strip()
        if not claim:
            continue
        raw_player = pred.get("target_player_name") or pred.get("target_player")
        player_name = None
        if raw_player:
            player_name = (
                "MULTI"
                if ("," in raw_player and len(raw_player.split(",")) > 1)
                else raw_player
            )

        result.append(
            PunditPrediction(
                pundit_id=pundit_id,
                pundit_name=source_article.pundit_name or pundit_id,
                source_url=source_url,
                raw_assertion_text=source_article.raw_text[:2000],
                extracted_claim=claim,
                claim_category=pred.get("claim_category", "other"),
                season_year=pred.get("season_year"),
                target_player_id=None,
                target_player_name=player_name,
                target_team=pred.get("target_team"),
                sport="NFL",
                prompt_version=prompt_version,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Team-batched extraction runner
# ---------------------------------------------------------------------------


def run_batched_extraction(
    limit: int = 100,
    dry_run: bool = False,
    sport: str = "NFL",
    include_unmatched: bool = False,
    db: Optional[DBManager] = None,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """
    Team-batched extraction entry point.

    Differences from assertion_extractor.run_extraction():
    - Groups articles by team before extraction (3-5x fewer LLM calls)
    - Multi-article prompts give the model cross-article consensus context
    - Returns the same summary dict shape for drop-in compatibility

    Configure via pipeline/config/llm_config.yaml:
        batching.enabled: true
        batching.max_articles_per_batch: 5
    """
    config = load_llm_config()
    batch_config = config.get("batching", {})
    max_per_batch = batch_config.get("max_articles_per_batch", 5)

    close_db = db is None
    if db is None:
        db = DBManager()

    if provider is None and not dry_run:
        provider = get_provider_with_fallback("extraction", config)

    provider_model = getattr(provider, "model", "dry-run") if provider else "dry-run"
    provider_type = (
        type(provider).__name__.replace("Provider", "").lower()
        if provider
        else "dry-run"
    )
    summary = {
        "total_articles": 0,
        "total_batches": 0,
        "predictions_extracted": 0,
        "predictions_ingested": 0,
        "errors": 0,
        "skipped_no_predictions": 0,
        "provider": provider_model,
        "mode": "batched",
    }

    try:
        media_df = get_unprocessed_media(
            db, limit=limit, include_unmatched=include_unmatched
        )
        if media_df.empty:
            logger.info("No unprocessed media found.")
            return summary

        summary["total_articles"] = len(media_df)
        logger.info(f"[batched] {len(media_df)} articles → annotating team mentions…")

        # Convert to ArticleRecord and annotate
        row_lookup: dict[str, pd.Series] = {}
        articles: list[ArticleRecord] = []
        for _, row in media_df.iterrows():
            art = _row_to_article(row)
            articles.append(art)
            row_lookup[art.content_hash] = row

        annotate_team_mentions(articles)

        # Group by team into sub-batches
        team_batches = batch_articles_by_team(articles, max_per_batch=max_per_batch)

        # Track which hashes were processed (to mark later)
        processed_hashes: set[str] = set()
        all_predictions: list[PunditPrediction] = []

        logger.info(
            f"[batched] {sum(len(bs) for bs in team_batches.values())} team-batches "
            f"across {len(team_batches)} teams"
        )

        for team_abbr, sub_batches in team_batches.items():
            for batch in sub_batches:
                summary["total_batches"] += 1

                if dry_run:
                    pundits = ", ".join({a.pundit_name for a in batch if a.pundit_name})
                    logger.info(
                        f"DRY RUN: team={team_abbr} batch_size={len(batch)} pundits=[{pundits}]"
                    )
                    for art in batch:
                        processed_hashes.add(art.content_hash)
                    continue

                prompt = build_batched_prompt(
                    team_abbr=team_abbr,
                    articles=batch,
                    sport=sport,
                    current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                )

                try:
                    raw_predictions = provider.extract_predictions(prompt)
                    filtered = [
                        p
                        for p in raw_predictions
                        if p.get("extracted_claim", "").strip()
                    ]

                    current_year = datetime.now().year
                    temporal_ok = [
                        p
                        for p in filtered
                        if not (
                            isinstance(p.get("season_year"), (int, float))
                            and int(p.get("season_year")) < current_year
                        )
                    ]
                    deduped = _deduplicate_claims(temporal_ok)
                except Exception as e:
                    logger.warning(
                        f"[batched] Extraction error for team={team_abbr}: {e}"
                    )
                    summary["errors"] += 1
                    for art in batch:
                        processed_hashes.add(art.content_hash)
                    continue

                if not deduped:
                    summary["skipped_no_predictions"] += len(batch)
                    for art in batch:
                        processed_hashes.add(art.content_hash)
                    continue

                summary["predictions_extracted"] += len(deduped)

                # Attribute predictions to individual articles (best-effort by pundit name)
                # If the model attributed the prediction, use that; otherwise use first article
                for pred in deduped:
                    pred_pundit = pred.get("pundit_name", "").lower()
                    source_art = batch[0]  # default to first article in batch
                    for art in batch:
                        if pred_pundit and art.pundit_name.lower() == pred_pundit:
                            source_art = art
                            break

                    src_row = row_lookup.get(source_art.content_hash)
                    pundit_id = (
                        str(src_row.get("matched_pundit_id") or "unknown")
                        if src_row is not None
                        else "unknown"
                    )
                    source_url = (
                        str(src_row.get("source_url", ""))
                        if src_row is not None
                        else ""
                    )

                    preds = _build_pundit_predictions(
                        [pred],
                        source_art,
                        pundit_id,
                        source_url,
                        prompt_version=BATCH_PROMPT_VERSION,
                        llm_provider=provider_type,
                        llm_model=provider_model,
                    )
                    all_predictions.extend(preds)

                for art in batch:
                    processed_hashes.add(art.content_hash)

        # Ingest all predictions
        if all_predictions and not dry_run:
            hashes = ingest_batch(all_predictions, db)
            summary["predictions_ingested"] = len(hashes)

        # Mark all processed
        if not dry_run:
            mark_as_processed(list(processed_hashes), db)

        logger.info(
            f"[batched] Done: {summary['total_batches']} batches, "
            f"{summary['predictions_extracted']} extracted, "
            f"{summary['predictions_ingested']} ingested, "
            f"{summary['errors']} errors"
        )

    finally:
        if close_db:
            db.close()

    return summary


# ---------------------------------------------------------------------------
# Pipeline entry point (reads config, dispatches to batched or per-article)
# ---------------------------------------------------------------------------


def run_extraction_with_config(
    limit: int = 100,
    dry_run: bool = False,
    sport: str = "NFL",
    include_unmatched: bool = False,
    db: Optional[DBManager] = None,
) -> dict:
    """
    Config-driven extraction entry point.

    Reads pipeline/config/llm_config.yaml and routes to either:
    - Team-batched extraction (if batching.enabled = true)
    - Standard per-article extraction (default)

    This is the recommended entrypoint for run_daily.py.
    """
    config = load_llm_config()
    batching_enabled = config.get("batching", {}).get("enabled", False)

    if batching_enabled:
        logger.info("[local_rag] batching.enabled=true → using team-batched extraction")
        return run_batched_extraction(
            limit=limit,
            dry_run=dry_run,
            sport=sport,
            include_unmatched=include_unmatched,
            db=db,
        )

    # Fall back to per-article extraction
    from src.assertion_extractor import run_extraction

    logger.info("[local_rag] batching.enabled=false → per-article extraction")
    return run_extraction(
        limit=limit,
        dry_run=dry_run,
        sport=sport,
        include_unmatched=include_unmatched,
        db=db,
    )
