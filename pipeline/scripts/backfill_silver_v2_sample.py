"""
backfill_silver_v2_sample.py — Phase B-1 sample backfill for silver_v2 tables.

Seeds 10 well-known NFL players (plus Bo Jackson's dual-sport complexity) into
the silver_v2_core tables.  Ground-truth facts are hard-coded — this is a
curated dataset, not inferred from scraped articles.

Usage:
    # Dry-run (default — prints rows without writing):
    python pipeline/scripts/backfill_silver_v2_sample.py --dry-run

    # Actually insert into BigQuery:
    python pipeline/scripts/backfill_silver_v2_sample.py

Prerequisites:
    GCP_PROJECT_ID env var must be set.
    Application Default Credentials or GCP_SERVICE_ACCOUNT_JSON must be available.

UUIDv7 note:
    The uuid7 package is not in requirements.txt.  We fall back to uuid.uuid4()
    which provides uniqueness without time-ordering; the entity_id field is
    stable across reruns because we deterministically derive it via uuid.uuid5()
    from a known namespace + player name slug (ensuring idempotent backfills).
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable UUID namespace for this backfill corpus.
# Any uuid5(BACKFILL_NS, slug) will always return the same UUID for the same
# slug, making reruns fully idempotent.
# ---------------------------------------------------------------------------
BACKFILL_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # RFC 4122 DNS ns


def stable_id(slug: str) -> str:
    """Return a stable UUID string derived from slug (idempotent across runs)."""
    return str(uuid.uuid5(BACKFILL_NS, f"silver_v2_backfill/{slug}"))


NOW = datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Player catalogue — hard-coded ground truth
# ---------------------------------------------------------------------------

# Each entry drives row generation for entity, entity_alias,
# entity_attribute_event, and transition_event tables.

PLAYERS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # 1. Tom Brady
    # ------------------------------------------------------------------
    {
        "slug": "tom_brady",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1977-08-03",
        "external_ids": {"pfr_slug": "BradTo00", "wikidata": "Q9685"},
        "aliases": [
            {
                "text": "Tom Brady",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1977-08-03T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "QB",
                "valid_from": "2000-04-16T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "2023-02-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "team",
                "value": "retired",
                "valid_from": "2023-02-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            # Brady 3-retirement stress-test cases
            {
                "type": "Retire",
                "from_value": "TB",
                "to_value": None,
                "occurred_at": "2022-02-01T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "Unretire",
                "from_value": None,
                "to_value": "TB",
                "occurred_at": "2022-03-13T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "Retire",
                "from_value": "TB",
                "to_value": None,
                "occurred_at": "2023-02-01T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 2. Chad Johnson / Ochocinco
    # ------------------------------------------------------------------
    {
        "slug": "chad_johnson",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1978-01-09",
        "external_ids": {"pfr_slug": "JohnCh01"},
        "aliases": [
            {
                "text": "Chad Johnson",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1978-01-09T00:00:00+00:00",
                "valid_to": "2008-08-29T00:00:00+00:00",
            },
            {
                "text": "Chad Ochocinco",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "2008-08-29T00:00:00+00:00",
                "valid_to": "2012-07-23T00:00:00+00:00",
            },
            {
                "text": "Chad Johnson",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "2012-07-23T00:00:00+00:00",
            },
            # Nickname Ochocinco (85 in Spanish) persists throughout career
            {
                "text": "Ochocinco",
                "kind": "nickname",
                "is_legal": False,
                "valid_from": "2008-08-29T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "WR",
                "valid_from": "2001-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "2012-01-01T00:00:00+00:00",
                "evidence_type": "inferred",
            },
            {
                "attr": "team",
                "value": "retired",
                "valid_from": "2012-01-01T00:00:00+00:00",
                "evidence_type": "inferred",
            },
        ],
        "transitions": [
            # Name change stress-test cases
            {
                "type": "NameChange",
                "from_value": "Chad Johnson",
                "to_value": "Chad Ochocinco",
                "occurred_at": "2008-08-29T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "NameChange",
                "from_value": "Chad Ochocinco",
                "to_value": "Chad Johnson",
                "occurred_at": "2012-07-23T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 3. Bo Jackson — concurrent NFL + MLB employment
    # ------------------------------------------------------------------
    {
        "slug": "bo_jackson",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1962-11-30",
        "external_ids": {"pfr_slug": "JackBo00"},
        "aliases": [
            {
                "text": "Bo Jackson",
                "kind": "preferred_name",
                "is_legal": False,
                "valid_from": "1962-11-30T00:00:00+00:00",
            },
            {
                "text": "Vincent Edward Jackson",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1962-11-30T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "RB",
                "valid_from": "1987-09-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            # Concurrent employment: NFL Raiders + MLB Royals
            # is_concurrent_ok=True for employment attribute
            {
                "attr": "employment",
                "value": "LA Raiders (NFL)",
                "valid_from": "1987-09-01T00:00:00+00:00",
                "valid_to": "1991-04-01T00:00:00+00:00",
                "evidence_type": "public_announce",
                "is_concurrent_ok": True,
            },
            {
                "attr": "employment",
                "value": "Kansas City Royals (MLB)",
                "valid_from": "1986-06-01T00:00:00+00:00",
                "valid_to": "1994-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
                "is_concurrent_ok": True,
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "1994-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Draft",
                "from_value": None,
                "to_value": "LA Raiders",
                "occurred_at": "1987-09-01T00:00:00+00:00",
                "precision": "day",
                "payload": {"round": 7, "pick": 183, "league": "NFL"},
            },
        ],
    },
    # ------------------------------------------------------------------
    # 4. Brett Favre — 3 retirements
    # ------------------------------------------------------------------
    {
        "slug": "brett_favre",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1969-10-10",
        "external_ids": {"pfr_slug": "FavrBr00"},
        "aliases": [
            {
                "text": "Brett Favre",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1969-10-10T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "QB",
                "valid_from": "1991-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "2010-06-09T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "team",
                "value": "retired",
                "valid_from": "2010-06-09T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Retire",
                "from_value": "GB",
                "to_value": None,
                "occurred_at": "2008-03-04T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "Unretire",
                "from_value": None,
                "to_value": "NYJ",
                "occurred_at": "2008-08-18T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "Retire",
                "from_value": "MIN",
                "to_value": None,
                "occurred_at": "2009-02-01T00:00:00+00:00",
                "precision": "month",
            },
            {
                "type": "Unretire",
                "from_value": None,
                "to_value": "MIN",
                "occurred_at": "2009-08-18T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "Retire",
                "from_value": "MIN",
                "to_value": None,
                "occurred_at": "2010-06-09T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 5. Julian Edelman
    # ------------------------------------------------------------------
    {
        "slug": "julian_edelman",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1986-05-22",
        "external_ids": {"pfr_slug": "EdelJu00"},
        "aliases": [
            {
                "text": "Julian Edelman",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1986-05-22T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "WR",
                "valid_from": "2009-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "2021-04-12T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "team",
                "value": "retired",
                "valid_from": "2021-04-12T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Retire",
                "from_value": "NE",
                "to_value": None,
                "occurred_at": "2021-04-12T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 6. Kurt Warner
    # ------------------------------------------------------------------
    {
        "slug": "kurt_warner",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1971-06-22",
        "external_ids": {"pfr_slug": "WarnKu00"},
        "aliases": [
            {
                "text": "Kurt Warner",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1971-06-22T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "QB",
                "valid_from": "1998-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "2010-01-29T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "team",
                "value": "retired",
                "valid_from": "2010-01-29T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Retire",
                "from_value": "ARI",
                "to_value": None,
                "occurred_at": "2010-01-29T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 7. Michael Vick — incarceration + reinstatement
    # ------------------------------------------------------------------
    {
        "slug": "michael_vick",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1980-06-26",
        "external_ids": {"pfr_slug": "VickMi00"},
        "aliases": [
            {
                "text": "Michael Vick",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1980-06-26T00:00:00+00:00",
            },
            {
                "text": "Mike Vick",
                "kind": "preferred_name",
                "is_legal": False,
                "valid_from": "2001-01-01T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "QB",
                "valid_from": "2001-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "retired",
                "valid_from": "2017-01-01T00:00:00+00:00",
                "evidence_type": "inferred",
            },
            {
                "attr": "team",
                "value": "retired",
                "valid_from": "2017-01-01T00:00:00+00:00",
                "evidence_type": "inferred",
            },
        ],
        "transitions": [
            # Incarceration + Release stress-test cases
            {
                "type": "Suspend",
                "from_value": "ATL",
                "to_value": None,
                "occurred_at": "2007-08-24T00:00:00+00:00",
                "precision": "day",
                "payload": {"reason": "NFL personal conduct policy violation"},
            },
            {
                "type": "Incarcerate",
                "from_value": None,
                "to_value": "FCI Leavenworth",
                "occurred_at": "2007-11-19T00:00:00+00:00",
                "precision": "day",
                "payload": {"charge": "dogfighting conspiracy", "sentence_months": 23},
            },
            {
                "type": "Release",
                "from_value": "FCI Leavenworth",
                "to_value": None,
                "occurred_at": "2009-05-20T00:00:00+00:00",
                "precision": "day",
            },
            {
                "type": "Reinstate",
                "from_value": None,
                "to_value": "PHI",
                "occurred_at": "2009-07-27T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 8. Josh Gordon — repeated suspensions
    # ------------------------------------------------------------------
    {
        "slug": "josh_gordon",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1991-04-13",
        "external_ids": {"pfr_slug": "GordJo02"},
        "aliases": [
            {
                "text": "Josh Gordon",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1991-04-13T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "WR",
                "valid_from": "2012-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "suspended",
                "valid_from": "2023-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "team",
                "value": "suspended",
                "valid_from": "2023-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Suspend",
                "from_value": "CLE",
                "to_value": None,
                "occurred_at": "2014-06-09T00:00:00+00:00",
                "precision": "day",
                "payload": {"reason": "substance abuse policy"},
            },
            {
                "type": "Reinstate",
                "from_value": None,
                "to_value": "CLE",
                "occurred_at": "2015-09-26T00:00:00+00:00",
                "precision": "day",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 9. Deion Sanders
    # ------------------------------------------------------------------
    {
        "slug": "deion_sanders",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1967-08-09",
        "external_ids": {"pfr_slug": "SandDe00"},
        "aliases": [
            {
                "text": "Deion Sanders",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1967-08-09T00:00:00+00:00",
            },
            {
                "text": "Prime Time",
                "kind": "nickname",
                "is_legal": False,
                "valid_from": "1989-01-01T00:00:00+00:00",
            },
            {
                "text": "Neon Deion",
                "kind": "nickname",
                "is_legal": False,
                "valid_from": "1989-01-01T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "CB",
                "valid_from": "1989-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            # Concurrent employment: NFL + MLB (Atlanta Braves / Cincinnati Reds)
            {
                "attr": "employment",
                "value": "NFL (various teams)",
                "valid_from": "1989-01-01T00:00:00+00:00",
                "valid_to": "2005-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
                "is_concurrent_ok": True,
            },
            {
                "attr": "employment",
                "value": "MLB (Atlanta Braves / Cincinnati Reds / San Francisco Giants)",
                "valid_from": "1989-01-01T00:00:00+00:00",
                "valid_to": "2001-01-01T00:00:00+00:00",
                "evidence_type": "public_announce",
                "is_concurrent_ok": True,
            },
            {
                "attr": "status",
                "value": "coach",
                "valid_from": "2021-09-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Retire",
                "from_value": "BAL",
                "to_value": None,
                "occurred_at": "2006-01-01T00:00:00+00:00",
                "precision": "year",
            },
        ],
    },
    # ------------------------------------------------------------------
    # 10. Kyler Murray
    # ------------------------------------------------------------------
    {
        "slug": "kyler_murray",
        "entity_kind": "person",
        "primary_domain": "sports.nfl",
        "birth_date": "1997-08-07",
        "external_ids": {"pfr_slug": "MurrKy00"},
        "aliases": [
            {
                "text": "Kyler Murray",
                "kind": "legal_name",
                "is_legal": True,
                "valid_from": "1997-08-07T00:00:00+00:00",
            },
        ],
        "attributes": [
            {
                "attr": "position",
                "value": "QB",
                "valid_from": "2019-04-26T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "status",
                "value": "active",
                "valid_from": "2019-09-01T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
            {
                "attr": "team",
                "value": "ARI",
                "valid_from": "2019-04-26T00:00:00+00:00",
                "evidence_type": "public_announce",
            },
        ],
        "transitions": [
            {
                "type": "Draft",
                "from_value": None,
                "to_value": "ARI",
                "occurred_at": "2019-04-26T00:00:00+00:00",
                "precision": "day",
                "payload": {"round": 1, "pick": 1, "league": "NFL"},
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _ts(iso_str: str) -> "bigquery.ScalarQueryParameter":  # type: ignore[name-defined]
    """Parse ISO timestamp string for use as a BQ TIMESTAMP value."""
    return datetime.fromisoformat(iso_str)


def build_entity_rows(player: dict) -> list[dict]:
    return [
        {
            "entity_id": stable_id(player["slug"]),
            "entity_kind": player["entity_kind"],
            "primary_domain": player["primary_domain"],
            "birth_or_founded": player.get("birth_date"),  # DATE string
            "death_or_dissolved": None,
            "external_ids": json.dumps(player.get("external_ids", {})),
            "created_at": NOW,
            "notes": None,
        }
    ]


def build_alias_rows(player: dict) -> list[dict]:
    entity_id = stable_id(player["slug"])
    rows = []
    for alias in player.get("aliases", []):
        rows.append(
            {
                "alias_id": stable_id(f"{player['slug']}/alias/{alias['text']}"),
                "entity_id": entity_id,
                "alias_text": alias["text"],
                "alias_kind": alias["kind"],
                "valid_from": alias["valid_from"],
                "valid_to": alias.get("valid_to"),
                "is_legal": alias["is_legal"],
                "source_event_id": None,
                "confidence": 1.0,
                "language": "en",
            }
        )
    return rows


def build_attribute_rows(player: dict) -> list[dict]:
    entity_id = stable_id(player["slug"])
    rows = []
    for i, attr in enumerate(player.get("attributes", [])):
        rows.append(
            {
                "event_id": stable_id(f"{player['slug']}/attr/{attr['attr']}/{i}"),
                "entity_id": entity_id,
                "domain": player["primary_domain"],
                "attr": attr["attr"],
                "value": attr["value"],
                "value_json": None,
                "valid_from": attr["valid_from"],
                "valid_to": attr.get("valid_to"),
                "evidence_type": attr.get("evidence_type", "public_announce"),
                "source_claim_id": None,
                "source_doc_id": None,
                "extraction_confidence": 1.0,
                "corroboration_count": 1,
                "is_concurrent_ok": attr.get("is_concurrent_ok", False),
                "superseded_by": None,
                "created_at": NOW,
            }
        )
    return rows


def build_transition_rows(player: dict) -> list[dict]:
    entity_id = stable_id(player["slug"])
    rows = []
    for i, tr in enumerate(player.get("transitions", [])):
        rows.append(
            {
                "event_id": stable_id(f"{player['slug']}/transition/{tr['type']}/{i}"),
                "entity_id": entity_id,
                "domain": player["primary_domain"],
                "type": tr["type"],
                "from_value": tr.get("from_value"),
                "to_value": tr.get("to_value"),
                "occurred_at": tr["occurred_at"],
                "occurred_at_precision": tr.get("precision", "day"),
                "payload": json.dumps(tr["payload"]) if tr.get("payload") else None,
                "source_claim_id": None,
                "source_doc_id": None,
                "confidence": 1.0,
                "created_at": NOW,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# BigQuery insert helpers
# ---------------------------------------------------------------------------

_BQ_TABLES = {
    "entity": "silver_v2_core.entity",
    "entity_alias": "silver_v2_core.entity_alias",
    "entity_attribute_event": "silver_v2_core.entity_attribute_event",
    "transition_event": "silver_v2_core.transition_event",
}


def _insert_rows(client, project_id: str, table_key: str, rows: list[dict]) -> None:
    if not rows:
        return
    table_ref = f"{project_id}.{_BQ_TABLES[table_key]}"
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"BQ insert errors for {table_ref}: {errors}")
    log.info("  Inserted %d row(s) into %s", len(rows), table_ref)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(dry_run: bool = True) -> None:
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        log.error("GCP_PROJECT_ID environment variable is not set.")
        sys.exit(1)

    log.info("Target project: %s | dry_run=%s", project_id, dry_run)

    if not dry_run:
        from google.cloud import bigquery as _bq  # noqa: PLC0415

        client = _bq.Client(project=project_id)
    else:
        client = None  # type: ignore[assignment]

    all_entities: list[dict] = []
    all_aliases: list[dict] = []
    all_attrs: list[dict] = []
    all_transitions: list[dict] = []

    for player in PLAYERS:
        entity_rows = build_entity_rows(player)
        alias_rows = build_alias_rows(player)
        attr_rows = build_attribute_rows(player)
        transition_rows = build_transition_rows(player)

        all_entities.extend(entity_rows)
        all_aliases.extend(alias_rows)
        all_attrs.extend(attr_rows)
        all_transitions.extend(transition_rows)

        log.info(
            "[%s] entity=%d alias=%d attr=%d transition=%d",
            player["slug"],
            len(entity_rows),
            len(alias_rows),
            len(attr_rows),
            len(transition_rows),
        )

    total = len(all_entities) + len(all_aliases) + len(all_attrs) + len(all_transitions)
    log.info(
        "Total rows: entity=%d alias=%d attr=%d transition=%d (total=%d)",
        len(all_entities),
        len(all_aliases),
        len(all_attrs),
        len(all_transitions),
        total,
    )

    if dry_run:
        log.info("DRY-RUN — no writes performed.")
        # Print sample rows for inspection
        import pprint  # noqa: PLC0415

        print("\n--- Sample entity rows ---")
        pprint.pprint(all_entities[:3])
        print("\n--- Sample alias rows ---")
        pprint.pprint(all_aliases[:3])
        print("\n--- Sample attribute rows ---")
        pprint.pprint(all_attrs[:3])
        print("\n--- Sample transition rows ---")
        pprint.pprint(all_transitions[:3])
        return

    log.info("Inserting entity rows...")
    _insert_rows(client, project_id, "entity", all_entities)

    log.info("Inserting entity_alias rows...")
    _insert_rows(client, project_id, "entity_alias", all_aliases)

    log.info("Inserting entity_attribute_event rows...")
    _insert_rows(client, project_id, "entity_attribute_event", all_attrs)

    log.info("Inserting transition_event rows...")
    _insert_rows(client, project_id, "transition_event", all_transitions)

    log.info("Backfill complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill 10 sample players into silver_v2 tables"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print rows without writing to BigQuery (default: True for safety)",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Actually insert rows into BigQuery",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
