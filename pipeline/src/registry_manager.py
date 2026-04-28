"""
Adaptive Pundit Registry Manager (Issue #119)

Manages pundit and source registries in BigQuery:
- Seed from static media_sources.yaml (one-time migration)
- CRUD for pundits and sources with append-only audit log
- Auto-discovery: surface recurring unmatched authors as candidates
- Adaptive polling cadence based on observed posting frequency

BigQuery tables (created by migration 012):
  nfl_dead_money.pundit_registry
  nfl_dead_money.source_registry
  nfl_dead_money.registry_audit_log

Design decisions (see issue #119):
  - Standard BQ rows with updated_at versioning (not BigLake Iceberg)
  - Discovery threshold: 3+ unmatched articles from same author in 30 days
  - Cadence tiers: daily|twice_weekly|weekly|biweekly|monthly
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

# Cadence thresholds (posts_per_month → cadence tier)
_CADENCE_TIERS = [
    (15.0, "daily"),
    (7.0, "twice_weekly"),
    (3.0, "weekly"),
    (1.0, "biweekly"),
    (0.0, "monthly"),
]

DISCOVERY_MIN_APPEARANCES = 3
DISCOVERY_WINDOW_DAYS = 30


def compute_cadence_tier(posts_per_month: float) -> str:
    """Map a posting frequency to a cadence tier string.

    Tiers (posts/month → cadence):
      >=15  → daily
      >=7   → twice_weekly
      >=3   → weekly
      >=1   → biweekly
      <1    → monthly
    """
    for threshold, tier in _CADENCE_TIERS:
        if posts_per_month >= threshold:
            return tier
    return "monthly"


class RegistryManager:
    """Manages the adaptive pundit and source registries in BigQuery."""

    def __init__(self, db: DBManager):
        self.db = db
        self.project_id = db.project_id
        self.dataset = "nfl_dead_money"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _table(self, name: str) -> str:
        return f"`{self.project_id}.{self.dataset}.{name}`"

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Append an audit entry to registry_audit_log."""
        row = {
            "log_id": str(uuid.uuid4()),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "old_value": json.dumps(old_value) if old_value is not None else None,
            "new_value": json.dumps(new_value) if new_value is not None else None,
            "reason": reason,
            "logged_at": self._now(),
        }
        df = pd.DataFrame([row])
        try:
            self.db.append_dataframe_to_table(df, "registry_audit_log")
        except Exception as e:
            logger.warning(f"Audit log write failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Seed from YAML
    # ------------------------------------------------------------------

    def seed_from_yaml(self, config: dict, overwrite: bool = False) -> dict:
        """Migrate media_sources.yaml config into BigQuery registry tables.

        Args:
            config: Parsed YAML dict (same shape as media_sources.yaml).
            overwrite: If True, DELETE existing rows before inserting.
                       If False (default), skip sources/pundits already present.

        Returns:
            Summary dict with counts of sources/pundits inserted/skipped.
        """
        now = self._now()
        sources_inserted = 0
        pundits_inserted = 0
        sources_skipped = 0
        pundits_skipped = 0

        # Existing IDs (for skip logic)
        existing_sources: set[str] = set()
        existing_pundits: set[str] = set()
        if not overwrite:
            try:
                df = self.db.fetch_df(
                    f"SELECT source_id FROM {self._table('source_registry')}"
                )
                if not df.empty:
                    existing_sources = set(df["source_id"].tolist())
            except Exception:
                pass
            try:
                df = self.db.fetch_df(
                    f"SELECT pundit_id FROM {self._table('pundit_registry')}"
                )
                if not df.empty:
                    existing_pundits = set(df["pundit_id"].tolist())
            except Exception:
                pass

        if overwrite:
            try:
                self.db.execute(
                    f"DELETE FROM {self._table('source_registry')} WHERE TRUE"
                )
                self.db.execute(
                    f"DELETE FROM {self._table('pundit_registry')} WHERE TRUE"
                )
            except Exception as e:
                logger.warning(f"Could not clear existing registry rows: {e}")

        source_rows = []
        pundit_rows = []

        for source in config.get("sources", []):
            source_id = source["id"]
            sport = source.get("sport", "NFL")

            if source_id in existing_sources and not overwrite:
                sources_skipped += 1
            else:
                source_rows.append(
                    {
                        "source_id": source_id,
                        "source_name": source.get("name", source_id),
                        "source_type": source.get("type", "rss"),
                        "url": source.get("url", ""),
                        "sport": sport,
                        "enabled": source.get("enabled", True),
                        "scrape_full_text": source.get("scrape_full_text", False),
                        "keyword_filter": source.get("keyword_filter", []),
                        "default_pundit_id": (
                            source["default_pundit"]["id"]
                            if source.get("default_pundit")
                            else None
                        ),
                        "polling_cadence": "daily",
                        "last_fetched_at": None,
                        "last_item_count": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                sources_inserted += 1

            # Default pundit for the source (if any)
            default_pundit = source.get("default_pundit")
            if default_pundit:
                pid = default_pundit["id"]
                if pid not in existing_pundits and not overwrite:
                    pundit_rows.append(
                        {
                            "pundit_id": pid,
                            "pundit_name": default_pundit.get("name", pid),
                            "sport": sport,
                            "source_ids": [source_id],
                            "match_authors": [],
                            "enabled": source.get("enabled", True),
                            "is_source_default": True,
                            "polling_cadence": "daily",
                            "last_seen_at": None,
                            "posts_per_month": None,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                    existing_pundits.add(pid)
                    pundits_inserted += 1
                elif pid in existing_pundits:
                    pundits_skipped += 1

            # Per-author pundits
            for pundit in source.get("pundits", []):
                pid = pundit["id"]
                if pid in existing_pundits and not overwrite:
                    pundits_skipped += 1
                    continue
                pundit_rows.append(
                    {
                        "pundit_id": pid,
                        "pundit_name": pundit.get("name", pid),
                        "sport": sport,
                        "source_ids": [source_id],
                        "match_authors": pundit.get("match_authors", []),
                        "enabled": source.get("enabled", True),
                        "is_source_default": False,
                        "polling_cadence": "daily",
                        "last_seen_at": None,
                        "posts_per_month": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                existing_pundits.add(pid)
                pundits_inserted += 1

        if source_rows:
            df = pd.DataFrame(source_rows)
            for col in ["last_fetched_at", "default_pundit_id"]:
                if col in df.columns:
                    df[col] = df[col].where(df[col].notna(), None)
            self.db.append_dataframe_to_table(df, "source_registry")

        if pundit_rows:
            df = pd.DataFrame(pundit_rows)
            for col in ["last_seen_at", "posts_per_month"]:
                if col in df.columns:
                    df[col] = df[col].where(df[col].notna(), None)
            self.db.append_dataframe_to_table(df, "pundit_registry")

        summary = {
            "sources_inserted": sources_inserted,
            "sources_skipped": sources_skipped,
            "pundits_inserted": pundits_inserted,
            "pundits_skipped": pundits_skipped,
        }
        logger.info(f"Registry seeded from YAML: {summary}")
        return summary

    # ------------------------------------------------------------------
    # Config export (YAML-compatible dict)
    # ------------------------------------------------------------------

    def get_source_config(self) -> dict:
        """Return a config dict compatible with media_sources.yaml structure.

        Used by the ingestor as a BQ-backed replacement for the YAML file.
        Falls back gracefully if the registry tables are empty or unavailable.
        """
        sources_df = self.db.fetch_df(
            f"""
            SELECT *
            FROM {self._table("source_registry")}
            WHERE enabled = TRUE
            ORDER BY source_id
            """
        )
        if sources_df.empty:
            return {"sources": [], "defaults": {}}

        pundits_df = self.db.fetch_df(
            f"""
            SELECT *
            FROM {self._table("pundit_registry")}
            ORDER BY pundit_id
            """
        )

        # Index pundits by source_id for fast lookup
        pundits_by_source: dict[str, list[dict]] = {}
        default_by_source: dict[str, dict] = {}
        if not pundits_df.empty:
            for _, row in pundits_df.iterrows():
                for sid in row.get("source_ids") or []:
                    if row.get("is_source_default"):
                        default_by_source[sid] = {
                            "id": row["pundit_id"],
                            "name": row["pundit_name"],
                        }
                    else:
                        pundits_by_source.setdefault(sid, []).append(
                            {
                                "id": row["pundit_id"],
                                "name": row["pundit_name"],
                                "match_authors": list(row.get("match_authors") or []),
                            }
                        )

        sources = []
        for _, row in sources_df.iterrows():
            sid = row["source_id"]
            source: dict = {
                "id": sid,
                "name": row["source_name"],
                "type": row["source_type"],
                "url": row["url"],
                "sport": row.get("sport", "NFL"),
                "enabled": bool(row.get("enabled", True)),
                "pundits": pundits_by_source.get(sid, []),
            }
            if row.get("scrape_full_text"):
                source["scrape_full_text"] = True
            kf = row.get("keyword_filter")
            if kf:
                source["keyword_filter"] = list(kf)
            if sid in default_by_source:
                source["default_pundit"] = default_by_source[sid]
            sources.append(source)

        return {"sources": sources, "defaults": {}}

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    def find_discovery_candidates(
        self,
        min_appearances: int = DISCOVERY_MIN_APPEARANCES,
        window_days: int = DISCOVERY_WINDOW_DAYS,
    ) -> list[dict]:
        """Find recurring unmatched authors in raw_pundit_media.

        Scans the last `window_days` of ingested content for authors that:
        - Were NOT matched to any tracked pundit (matched_pundit_id IS NULL)
        - Appear at least `min_appearances` times
        - Are distinct from existing pundit names

        Returns a list of candidate dicts with keys:
          author, source_id, appearances, first_seen, last_seen
        """
        query = f"""
            SELECT
                author,
                source_id,
                COUNT(*)                AS appearances,
                MIN(ingested_at)        AS first_seen,
                MAX(ingested_at)        AS last_seen
            FROM {self._table("raw_pundit_media")}
            WHERE
                matched_pundit_id IS NULL
                AND author IS NOT NULL
                AND TRIM(author) != ''
                AND ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_days} DAY)
            GROUP BY author, source_id
            HAVING COUNT(*) >= {min_appearances}
            ORDER BY appearances DESC
        """
        try:
            df = self.db.fetch_df(query)
        except Exception as e:
            logger.warning(f"Discovery query failed: {e}")
            return []

        if df.empty:
            return []

        candidates = df.to_dict(orient="records")
        logger.info(
            f"Discovery: found {len(candidates)} candidate(s) "
            f"(threshold={min_appearances}, window={window_days}d)"
        )
        for c in candidates:
            self._log(
                entity_type="candidate",
                entity_id=str(c.get("author", "unknown")),
                action="candidate_discovered",
                new_value={
                    "source_id": c.get("source_id"),
                    "appearances": int(c.get("appearances", 0)),
                },
                reason=f"Appeared {c.get('appearances')} times unmatched in last {window_days} days",
            )
        return candidates

    # ------------------------------------------------------------------
    # Cadence management
    # ------------------------------------------------------------------

    def refresh_cadences(self, window_days: int = 30) -> int:
        """Recompute and update polling cadence for all tracked pundits.

        Queries raw_pundit_media for each pundit's recent post count,
        derives posts_per_month, maps to a cadence tier, and updates
        the pundit_registry row if the tier has changed.

        Returns the number of pundits whose cadence was updated.
        """
        freq_query = f"""
            SELECT
                matched_pundit_id                           AS pundit_id,
                COUNT(*)  * (30.0 / {window_days})          AS posts_per_month
            FROM {self._table("raw_pundit_media")}
            WHERE
                matched_pundit_id IS NOT NULL
                AND ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_days} DAY)
            GROUP BY matched_pundit_id
        """
        registry_query = f"""
            SELECT pundit_id, polling_cadence, posts_per_month
            FROM {self._table("pundit_registry")}
            WHERE enabled = TRUE
        """
        try:
            freq_df = self.db.fetch_df(freq_query)
            reg_df = self.db.fetch_df(registry_query)
        except Exception as e:
            logger.warning(f"Cadence refresh query failed: {e}")
            return 0

        if freq_df.empty or reg_df.empty:
            return 0

        freq_map = {
            row["pundit_id"]: float(row["posts_per_month"])
            for _, row in freq_df.iterrows()
        }

        updated = 0
        now = self._now()
        update_rows = []

        for _, reg_row in reg_df.iterrows():
            pid = reg_row["pundit_id"]
            ppm = freq_map.get(pid, 0.0)
            new_cadence = compute_cadence_tier(ppm)
            old_cadence = reg_row.get("polling_cadence", "daily")

            update_rows.append(
                {
                    "pundit_id": pid,
                    "posts_per_month": ppm,
                    "polling_cadence": new_cadence,
                    "updated_at": now,
                }
            )

            if new_cadence != old_cadence:
                self._log(
                    entity_type="pundit",
                    entity_id=pid,
                    action="cadence_change",
                    old_value={"polling_cadence": old_cadence},
                    new_value={"polling_cadence": new_cadence, "posts_per_month": ppm},
                    reason=f"Observed {ppm:.1f} posts/month in last {window_days} days",
                )
                updated += 1

        if update_rows:
            df = pd.DataFrame(update_rows)
            # Upsert: merge new cadence data into pundit_registry via a temp table join
            self.db.append_dataframe_to_table(df, "_cadence_update_tmp")
            self.db.execute(
                f"""
                UPDATE {self._table("pundit_registry")} pr
                SET
                    pr.posts_per_month  = t.posts_per_month,
                    pr.polling_cadence  = t.polling_cadence,
                    pr.updated_at       = t.updated_at
                FROM `{self.project_id}.{self.dataset}._cadence_update_tmp` t
                WHERE pr.pundit_id = t.pundit_id
                """
            )
            try:
                self.db.execute(
                    f"DROP TABLE IF EXISTS `{self.project_id}.{self.dataset}._cadence_update_tmp`"
                )
            except Exception:
                pass

        logger.info(
            f"Cadence refresh: {updated} pundit(s) updated out of {len(update_rows)}"
        )
        return updated

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def enable_pundit(self, pundit_id: str, reason: str = "") -> None:
        """Enable a pundit and log the change."""
        self.db.execute(
            f"""
            UPDATE {self._table("pundit_registry")}
            SET enabled = TRUE, updated_at = CURRENT_TIMESTAMP()
            WHERE pundit_id = '{pundit_id}'
            """
        )
        self._log("pundit", pundit_id, "enable", reason=reason or "Manually enabled")

    def disable_pundit(self, pundit_id: str, reason: str = "") -> None:
        """Disable a pundit without deleting it (never retire)."""
        self.db.execute(
            f"""
            UPDATE {self._table("pundit_registry")}
            SET enabled = FALSE, updated_at = CURRENT_TIMESTAMP()
            WHERE pundit_id = '{pundit_id}'
            """
        )
        self._log("pundit", pundit_id, "disable", reason=reason or "Manually disabled")

    def update_last_seen(self, pundit_id: str, seen_at: datetime) -> None:
        """Record the most recent content timestamp for a pundit."""
        ts = seen_at.isoformat()
        self.db.execute(
            f"""
            UPDATE {self._table("pundit_registry")}
            SET last_seen_at = '{ts}', updated_at = CURRENT_TIMESTAMP()
            WHERE pundit_id = '{pundit_id}'
              AND (last_seen_at IS NULL OR last_seen_at < '{ts}')
            """
        )

    def update_source_fetch_stats(
        self, source_id: str, item_count: int, fetched_at: Optional[datetime] = None
    ) -> None:
        """Update fetch statistics after a successful source poll."""
        ts = (fetched_at or self._now()).isoformat()
        self.db.execute(
            f"""
            UPDATE {self._table("source_registry")}
            SET
                last_fetched_at  = '{ts}',
                last_item_count  = {item_count},
                updated_at       = CURRENT_TIMESTAMP()
            WHERE source_id = '{source_id}'
            """
        )
