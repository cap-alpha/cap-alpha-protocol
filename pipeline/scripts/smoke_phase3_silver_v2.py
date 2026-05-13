#!/usr/bin/env python3
"""
Phase 3 DuckDB smoke test — validates write_silver_v2_claims, write_claim_entity_links,
write_claim_state_history against a local DuckDB database.

Usage:
    DB_BACKEND=duckdb python3 pipeline/scripts/smoke_phase3_silver_v2.py

Exit codes:
    0 — all assertions passed
    1 — assertion failure (reason printed to stderr)

Prerequisites:
    DB_BACKEND=duckdb python3 pipeline/scripts/init_local_db.py
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Adjust sys.path so we can import from pipeline/src/
_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PIPELINE_DIR))
sys.path.insert(0, str(_PIPELINE_DIR / "src"))

# Force DuckDB backend
os.environ["DB_BACKEND"] = "duckdb"
# Ensure GCP_PROJECT_ID is NOT set so we exercise the DuckDB path
os.environ.pop("GCP_PROJECT_ID", None)

import duckdb  # noqa: E402 — imported after env setup

from src.assertion_extractor import (
    write_silver_v2_claims,
    write_claim_entity_links,
    write_claim_state_history,
)
from src.db_manager import get_db_manager

DOMAIN = "sports.nfl"
# Use a unique speaker_entity_id per run so we can isolate this run's rows
SPEAKER_ENTITY_ID = "smoke-speaker-" + uuid.uuid4().hex[:8]

_FAIL = False
_failures: list[str] = []


def fail(msg: str) -> None:
    global _FAIL
    _FAIL = True
    _failures.append(msg)
    print(f"  FAIL: {msg}", file=sys.stderr)


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  OK: {label}")
    else:
        fail(label)


def main() -> int:
    db_path = os.environ.get(
        "DUCKDB_PATH",
        str(_PIPELINE_DIR / "data" / "local.duckdb"),
    )
    if not Path(db_path).exists():
        print(
            f"FATAL: DuckDB file not found: {db_path}\n"
            "Run: DB_BACKEND=duckdb python3 pipeline/scripts/init_local_db.py",
            file=sys.stderr,
        )
        return 1

    # Use DuckDBManager for the write functions
    db = get_db_manager()

    # Use a raw DuckDB connection for seed/verify queries (bypasses search_path issues)
    conn = duckdb.connect(db_path)

    # ------------------------------------------------------------------
    # STEP 1: Seed silver_v2_core.entity with a known entity
    # ------------------------------------------------------------------
    print("\n=== Seeding silver_v2_core.entity ===")
    known_entity_id = "entity-smoke-" + uuid.uuid4().hex[:8]
    known_entity_name = "Patrick Mahomes"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    conn.execute(
        """
        INSERT INTO silver_v2_core.entity
            (entity_id, entity_kind, primary_domain, created_at)
        VALUES (?, 'person', 'sports.nfl', ?::TIMESTAMP)
        """,
        [known_entity_id, now_str],
    )

    alias_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO silver_v2_core.entity_alias
            (alias_id, entity_id, alias_text, alias_kind,
             valid_from, is_legal, confidence)
        VALUES (?, ?, ?, 'preferred_name', ?::TIMESTAMP, true, 1.0)
        """,
        [alias_id, known_entity_id, known_entity_name.lower(), now_str],
    )
    print(f"  Seeded entity {known_entity_id} with alias '{known_entity_name.lower()}'")

    # ------------------------------------------------------------------
    # STEP 2: Build 3 fake utterances
    # ------------------------------------------------------------------
    source_doc_id = "smoke-doc-" + uuid.uuid4().hex[:8]
    uttered_at = datetime.now(timezone.utc)

    # Utterance 1: has a known subject entity (Patrick Mahomes)
    u1_id = str(uuid.uuid4())
    u1 = {
        "text": "Patrick Mahomes will win MVP this season.",
        "extracted_claim": "Patrick Mahomes will win MVP this season.",
        "speech_act_type": "assertion",
        "testability_score": 0.85,
        "target_player": known_entity_name,
        "predicate": "will_win_award",
        "predicate_args": {"award": "MVP", "season": "2024"},
        "claim_category": "performance",
    }

    # Utterance 2: has an unknown entity (will create placeholder + queue row)
    u2_id = str(uuid.uuid4())
    u2 = {
        "text": "Zyx Qarambo will be cut before Week 5.",
        "extracted_claim": "Zyx Qarambo will be cut before Week 5.",
        "speech_act_type": "assertion",
        "testability_score": 0.80,
        "target_player": "Zyx Qarambo",
        "predicate": "will_be_released",
        "predicate_args": {"before": "Week 5"},
        "claim_category": "roster",
    }

    # Utterance 3: multiple subjects
    u3_id = str(uuid.uuid4())
    u3 = {
        "text": "The Kansas City Chiefs and Denver Broncos will meet in the playoffs.",
        "extracted_claim": "Kansas City Chiefs and Denver Broncos will meet in playoffs.",
        "speech_act_type": "assertion",
        "testability_score": 0.75,
        "target_team": "Kansas City Chiefs",
        "subject": "Denver Broncos",
        "predicate": "will_play",
        "predicate_args": {"stage": "playoffs"},
        "claim_category": "game",
    }

    utterances = [u1, u2, u3]
    utterance_id_map = {
        u1["text"][:4000]: u1_id,
        u2["text"][:4000]: u2_id,
        u3["text"][:4000]: u3_id,
    }

    # ------------------------------------------------------------------
    # STEP 3: Write claims + entity links + state history
    # ------------------------------------------------------------------
    print("\n=== Writing claims via write_silver_v2_claims ===")
    n_written = write_silver_v2_claims(
        utterances=utterances,
        utterance_id_map=utterance_id_map,
        source_doc_id=source_doc_id,
        speaker_entity_id=SPEAKER_ENTITY_ID,
        uttered_at=uttered_at,
        domain=DOMAIN,
        db=db,
        threshold=0.5,  # low threshold so all 3 utterances pass
    )
    print(f"  write_silver_v2_claims returned {n_written}")
    check("write_silver_v2_claims returns 3", n_written == 3)

    # ------------------------------------------------------------------
    # STEP 4: Verify DuckDB state using raw connection
    # ------------------------------------------------------------------
    print("\n=== Verifying silver_v2_claims.claim ===")
    claim_rows = conn.execute(
        "SELECT claim_id FROM silver_v2_claims.claim WHERE speaker_entity_id = ?",
        [SPEAKER_ENTITY_ID],
    ).fetchall()
    claim_ids = [r[0] for r in claim_rows]
    print(f"  silver_v2_claims.claim rows for this doc: {len(claim_ids)}")
    check("claim has 3 rows", len(claim_ids) == 3)

    print("\n=== Verifying silver_v2_claims.claim_entity_link ===")
    if claim_ids:
        placeholders = ", ".join("?" * len(claim_ids))
        link_rows = conn.execute(
            f"SELECT claim_id, entity_id, entity_role FROM silver_v2_claims.claim_entity_link WHERE claim_id IN ({placeholders})",
            claim_ids,
        ).fetchall()
        print(f"  claim_entity_link rows: {len(link_rows)}")
        check("claim_entity_link has at least 3 rows", len(link_rows) >= 3)

        subject_rows = [r for r in link_rows if r[2] == "subject"]
        check(
            "claim_entity_link has subject-role rows",
            len(subject_rows) >= 1,
        )
        print(f"  subject-role link rows: {len(subject_rows)}")
    else:
        fail("no claim rows found — cannot check entity links")
        link_rows = []

    print("\n=== Verifying silver_v2_claims.claim_state_history ===")
    if claim_ids:
        history_rows = conn.execute(
            f"SELECT claim_id, state, effective_source FROM silver_v2_claims.claim_state_history WHERE claim_id IN ({placeholders})",
            claim_ids,
        ).fetchall()
        print(f"  claim_state_history rows: {len(history_rows)}")
        check("claim_state_history has 3 rows", len(history_rows) == 3)

        pending = [r for r in history_rows if r[1] == "PENDING"]
        check("all state_history rows are PENDING", len(pending) == 3)

        ingestion = [r for r in history_rows if r[2] == "ingestion"]
        check(
            "all state_history rows have effective_source=ingestion",
            len(ingestion) == 3,
        )
    else:
        fail("no claim rows found — cannot check state history")

    print("\n=== Verifying silver_v2_claims.entity_resolution_queue ===")
    queue_rows = conn.execute(
        "SELECT queue_id, raw_entity_string, status FROM silver_v2_claims.entity_resolution_queue WHERE status = 'PENDING'"
    ).fetchall()
    print(f"  entity_resolution_queue PENDING rows: {len(queue_rows)}")
    check("entity_resolution_queue has at least 1 row", len(queue_rows) >= 1)

    zyx_rows = [r for r in queue_rows if "Zyx" in (r[1] or "")]
    check("unknown entity 'Zyx Qarambo' is in resolution queue", len(zyx_rows) >= 1)

    print("\n=== Verifying placeholder entity in silver_v2_core.entity ===")
    placeholder_rows = conn.execute(
        "SELECT entity_id, entity_kind FROM silver_v2_core.entity WHERE entity_kind = 'unresolved'"
    ).fetchall()
    print(f"  unresolved placeholder entities: {len(placeholder_rows)}")
    check("at least 1 unresolved placeholder entity created", len(placeholder_rows) >= 1)

    conn.close()

    # ------------------------------------------------------------------
    # STEP 5: Print copy-pasteable verification queries
    # ------------------------------------------------------------------
    print("\n=== Verification queries (copy-paste into DuckDB CLI) ===")
    if claim_ids:
        ids_literal = ", ".join(f"'{c}'" for c in claim_ids)
        print(f"""
-- Expected: 3 rows
SELECT COUNT(*) AS claim_count FROM silver_v2_claims.claim
WHERE speaker_entity_id = '{SPEAKER_ENTITY_ID}';

-- Expected: >= 3 rows, at least 1 with entity_role='subject'
SELECT entity_role, COUNT(*) AS cnt
FROM silver_v2_claims.claim_entity_link
WHERE claim_id IN ({ids_literal})
GROUP BY entity_role;

-- Expected: 3 rows with state='PENDING', effective_source='ingestion'
SELECT state, effective_source, COUNT(*) AS cnt
FROM silver_v2_claims.claim_state_history
WHERE claim_id IN ({ids_literal})
GROUP BY state, effective_source;

-- Expected: >= 1 row with raw_entity_string containing 'Zyx Qarambo'
SELECT raw_entity_string, status
FROM silver_v2_claims.entity_resolution_queue
WHERE status = 'PENDING';

-- Expected: >= 1 row with entity_kind='unresolved'
SELECT entity_id, entity_kind FROM silver_v2_core.entity
WHERE entity_kind = 'unresolved';
""")

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------
    print("=== Summary ===")
    if _FAIL:
        print(f"FAILED — {len(_failures)} assertion(s) failed:", file=sys.stderr)
        for msg in _failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    else:
        print("All assertions PASSED — Phase 3 writes validate against DuckDB.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
