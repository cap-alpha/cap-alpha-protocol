"""
Micro-batch ETL Trigger — SP18.5-2

Provides vendor-agnostic delta detection for high-frequency data updates.
Core idea: hash each entity's canonical fields on every poll; only write
entities whose hash changed since the last run to Bronze (and downstream).

Usage
-----
Any vendor ingestor (Bronze writer) should call this instead of doing a full
WRITE_TRUNCATE on every run:

    from src.microbatch_trigger import MicrobatchTrigger

    trigger = MicrobatchTrigger(db, table_prefix="sportsdataio_players")
    changed_df = trigger.detect_changes(current_df, key_col="PlayerID", hash_cols=["Name", "Team", "Status"])
    if not changed_df.empty:
        db.append_dataframe_to_table(changed_df, "bronze_sportsdataio_players")
        trigger.commit_hashes(changed_df, key_col="PlayerID")
        run_silver_transformation()   # only when data actually changed

Architecture
-----------
Change tracking table: bronze_entity_hashes
  entity_namespace  STRING NOT NULL  -- e.g. "sportsdataio_players"
  entity_key        STRING NOT NULL  -- vendor-native primary key
  content_hash      STRING NOT NULL  -- SHA-256 of canonical fields
  last_seen_ts      TIMESTAMP NOT NULL
  PK: (entity_namespace, entity_key)

The table uses MERGE (upsert) so it remains a current-state snapshot — one row
per entity, updated in place.  This is safe: it only tracks "what version did
we last write?" — the actual immutable history lives in Bronze append tables.
"""

import hashlib
import json
import logging
from typing import List, Optional

import pandas as pd

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

_HASH_TABLE = "bronze_entity_hashes"


class MicrobatchTrigger:
    """
    Detects which entities changed since the last micro-batch run.

    Parameters
    ----------
    db : DBManager
        Open database connection.
    table_prefix : str
        Logical namespace for the entity type being tracked
        (e.g. "sportsdataio_players", "spotrac_contracts").
        Scopes the hash rows so multiple sources can share the same tracking table.
    """

    def __init__(self, db: DBManager, table_prefix: str):
        self.db = db
        self.namespace = table_prefix
        self._ensure_hash_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_changes(
        self,
        current_df: pd.DataFrame,
        key_col: str,
        hash_cols: List[str],
    ) -> pd.DataFrame:
        """
        Returns only the rows from current_df that are new or changed
        since the last committed run.

        Parameters
        ----------
        current_df : DataFrame
            Full snapshot from the vendor API (all entities).
        key_col : str
            Column that uniquely identifies each entity (vendor primary key).
        hash_cols : list of str
            Columns whose values determine whether a record "changed".
            Include all mutable fields you want to track.

        Returns
        -------
        DataFrame
            Subset of current_df where the entity is new or its hash changed.
            Adds a `_content_hash` column with the computed hash.
        """
        if current_df is None or current_df.empty:
            logger.info(f"[{self.namespace}] detect_changes: empty input, nothing to do.")
            return pd.DataFrame()

        # Compute content hash for each row
        df = current_df.copy()
        df["_content_hash"] = df.apply(
            lambda row: self._hash_row(row, hash_cols), axis=1
        )

        # Load known hashes from BigQuery
        known = self._load_known_hashes()

        if known.empty:
            logger.info(
                f"[{self.namespace}] No prior hashes found — treating all {len(df)} rows as new."
            )
            return df

        # Merge to find changed/new rows
        merged = df.merge(
            known[["entity_key", "content_hash"]].rename(
                columns={"content_hash": "_known_hash"}
            ),
            left_on=key_col,
            right_on="entity_key",
            how="left",
        )

        changed = merged[
            merged["_known_hash"].isna()  # new entity
            | (merged["_content_hash"] != merged["_known_hash"])  # changed entity
        ].drop(columns=["entity_key", "_known_hash"], errors="ignore")

        logger.info(
            f"[{self.namespace}] {len(changed)} changed / {len(df)} total entities in this batch."
        )
        return changed

    def commit_hashes(
        self,
        written_df: pd.DataFrame,
        key_col: str,
    ) -> None:
        """
        Updates bronze_entity_hashes with the hashes of the rows that were
        successfully written to Bronze.  Call this AFTER a successful Bronze write.

        Parameters
        ----------
        written_df : DataFrame
            The DataFrame returned by detect_changes() (must contain `_content_hash`).
        key_col : str
            Column identifying each entity (same as passed to detect_changes).
        """
        if written_df is None or written_df.empty:
            return

        if "_content_hash" not in written_df.columns:
            raise ValueError(
                "written_df must contain '_content_hash' column. "
                "Pass the DataFrame returned by detect_changes()."
            )

        hashes_df = pd.DataFrame(
            {
                "entity_namespace": self.namespace,
                "entity_key": written_df[key_col].astype(str),
                "content_hash": written_df["_content_hash"],
                "last_seen_ts": pd.Timestamp.utcnow(),
            }
        )

        # Upsert into the hash tracking table via BigQuery MERGE
        self._upsert_hashes(hashes_df)
        logger.info(
            f"[{self.namespace}] Committed {len(hashes_df)} entity hashes to {_HASH_TABLE}."
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _hash_row(self, row: pd.Series, hash_cols: List[str]) -> str:
        canonical = "|".join(
            str(row.get(c, "")) for c in sorted(hash_cols)
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _ensure_hash_table(self) -> None:
        """Creates bronze_entity_hashes if it doesn't exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.db.project_id}.{self.db.dataset_id}.{_HASH_TABLE}`
        (
          entity_namespace  STRING    NOT NULL OPTIONS(description="Source + entity type namespace"),
          entity_key        STRING    NOT NULL OPTIONS(description="Vendor primary key for the entity"),
          content_hash      STRING    NOT NULL OPTIONS(description="SHA-256 of canonical mutable fields"),
          last_seen_ts      TIMESTAMP NOT NULL OPTIONS(description="When this hash was last written to Bronze")
        )
        CLUSTER BY entity_namespace, entity_key
        OPTIONS (description = "Micro-batch change tracker: one row per entity, current hash only.");
        """
        try:
            self.db.execute(ddl)
        except Exception as e:
            # Table likely already exists — tolerate
            logger.debug(f"_ensure_hash_table: {e}")

    def _load_known_hashes(self) -> pd.DataFrame:
        """Returns all known hashes for this namespace."""
        try:
            return self.db.fetch_df(
                f"""
                SELECT entity_key, content_hash
                FROM `{self.db.project_id}.{self.db.dataset_id}.{_HASH_TABLE}`
                WHERE entity_namespace = '{self.namespace}'
                """
            )
        except Exception as e:
            logger.warning(f"[{self.namespace}] Could not load known hashes: {e}")
            return pd.DataFrame(columns=["entity_key", "content_hash"])

    def _upsert_hashes(self, hashes_df: pd.DataFrame) -> None:
        """Upserts the new hashes into the tracking table."""
        full_stg = f"{self.db.project_id}.{self.db.dataset_id}.{_HASH_TABLE}_stg"
        full_tgt = f"{self.db.project_id}.{self.db.dataset_id}.{_HASH_TABLE}"

        self.db.append_dataframe_to_table(hashes_df, f"{_HASH_TABLE}_stg")

        merge_sql = f"""
        MERGE `{full_tgt}` T
        USING `{full_stg}` S
          ON T.entity_namespace = S.entity_namespace
         AND T.entity_key = S.entity_key
        WHEN MATCHED THEN UPDATE SET
          T.content_hash  = S.content_hash,
          T.last_seen_ts  = S.last_seen_ts
        WHEN NOT MATCHED THEN INSERT
          (entity_namespace, entity_key, content_hash, last_seen_ts)
          VALUES (S.entity_namespace, S.entity_key, S.content_hash, S.last_seen_ts);
        """
        self.db.execute(merge_sql)
        self.db.execute(f"DROP TABLE IF EXISTS `{full_stg}`;")
