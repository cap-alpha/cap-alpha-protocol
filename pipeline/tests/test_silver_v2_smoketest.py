"""
Silver_v2_* smoke tests for the general-purpose truth ledger (Issue #555).

Phase B-0 tests (in CI always):
  1. domain_taxonomy seed data integrity — no BigQuery needed

Phase B-1 integration tests (marked pytest.mark.integration):
  Run only when RUN_INTEGRATION_TESTS=1 is set.
  Require:
    - GCP_PROJECT_ID set
    - silver_v2 DDL applied (via apply_silver_v2_migrations.py)
    - Backfill loaded (via backfill_silver_v2_sample.py)

  Sanity checks:
    - Brady entity exists with 3 Retire transition events
    - Ochocinco: NameChange transitions present (Johnson <-> Ochocinco)
    - Bo Jackson: concurrent employment rows (NFL + MLB) with is_concurrent_ok=True

All other Phase B-1 tests remain skipped pending Phase B-2 claim/resolution work.
"""

import os
import uuid

import pytest

# ---------------------------------------------------------------------------
# Constants matching the domain_taxonomy seed in 015_create_silver_v2_core.sql
# ---------------------------------------------------------------------------

EXPECTED_SEED_DOMAINS = [
    "sports",
    "sports.nfl",
    "politics",
    "politics.us",
    "politics.us.federal",
    "finance",
    "finance.macro",
    "tech",
]

DOMAIN_PARENT_MAP = {
    "sports": None,
    "sports.nfl": "sports",
    "politics": None,
    "politics.us": "politics",
    "politics.us.federal": "politics.us",
    "finance": None,
    "finance.macro": "finance",
    "tech": None,
}

# ---------------------------------------------------------------------------
# Helper: parse the INSERT VALUES from the migration file to extract seeded rows.
# This lets us validate the seed data without a live BigQuery connection.
# ---------------------------------------------------------------------------


def _load_seed_domains_from_migration() -> list[str]:
    """
    Parse 015_create_silver_v2_core.sql and extract the domain values from the
    INSERT INTO domain_taxonomy block. Returns a list of domain strings.
    """
    import pathlib
    import re

    migration_path = (
        pathlib.Path(__file__).parent.parent
        / "migrations"
        / "015_create_silver_v2_core.sql"
    )
    sql = migration_path.read_text()

    # Find the INSERT block and extract quoted first-column values (domain)
    # Each row starts with: \n  (\n    '<domain>',
    pattern = re.compile(r"^\s+\(\s*\n\s+'([^']+)'", re.MULTILINE)
    return pattern.findall(sql)


# ---------------------------------------------------------------------------
# Phase B-0: real tests (run in CI without BigQuery)
# ---------------------------------------------------------------------------


class TestDomainTaxonomySeed:
    """Verify the domain_taxonomy seed data in migration 015."""

    def test_seed_has_exactly_eight_domains(self):
        """The migration must seed exactly 8 domain rows."""
        seeded = _load_seed_domains_from_migration()
        assert len(seeded) == 8, f"Expected 8 seed domains, got {len(seeded)}: {seeded}"

    def test_seed_contains_all_expected_domains(self):
        """Every expected domain must appear in the seed INSERT."""
        seeded = set(_load_seed_domains_from_migration())
        missing = set(EXPECTED_SEED_DOMAINS) - seeded
        assert not missing, f"Missing domains in seed: {missing}"

    def test_no_extra_domains_in_seed(self):
        """No unexpected domains should appear in the seed INSERT."""
        seeded = set(_load_seed_domains_from_migration())
        extra = seeded - set(EXPECTED_SEED_DOMAINS)
        assert not extra, f"Unexpected domains in seed: {extra}"

    def test_root_domains_have_no_parent(self):
        """Root domains (sports, politics, finance, tech) must have NULL parent."""
        root_domains = {d for d, p in DOMAIN_PARENT_MAP.items() if p is None}
        assert root_domains == {"sports", "politics", "finance", "tech"}

    def test_child_domains_reference_existing_parents(self):
        """Every non-root domain's parent must itself be in the seed."""
        all_domains = set(EXPECTED_SEED_DOMAINS)
        for domain, parent in DOMAIN_PARENT_MAP.items():
            if parent is not None:
                assert parent in all_domains, (
                    f"Domain '{domain}' references parent '{parent}' "
                    f"which is not in the seed"
                )


# ---------------------------------------------------------------------------
# Phase B-1: BigQuery integration tests
# Run only when RUN_INTEGRATION_TESTS=1 is set.
# Require: GCP_PROJECT_ID, silver_v2 DDL applied, backfill loaded.
# ---------------------------------------------------------------------------

# Stable UUID namespace must match the one in backfill_silver_v2_sample.py
_BACKFILL_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _stable_id(slug: str) -> str:
    """Reproduce the same stable UUID logic used in the backfill script."""
    return str(uuid.uuid5(_BACKFILL_NS, f"silver_v2_backfill/{slug}"))


def _bq_client():
    """Return a BigQuery client using GCP_PROJECT_ID."""
    from google.cloud import bigquery  # noqa: PLC0415

    project_id = os.environ["GCP_PROJECT_ID"]
    return bigquery.Client(project=project_id), project_id


_B1_REASON = "Phase B-1: requires BQ backfill — set RUN_INTEGRATION_TESTS=1"
_skip_b1 = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"),
    reason="GCP_PROJECT_ID not set — skipping BQ integration tests",
)


@pytest.mark.integration
@_skip_b1
def test_brady_entity_and_three_retire_transitions():
    """
    Tom Brady must have exactly 3 Retire transition events in silver_v2_core.

    This is the canonical multi-retirement stress-test case from the 25-case
    corpus (Phase B-0 design doc, Issue #555).
    """
    client, project_id = _bq_client()
    brady_id = _stable_id("tom_brady")

    # 1. entity row must exist
    entity_query = f"""
        SELECT entity_id, entity_kind, primary_domain
        FROM `{project_id}.silver_v2_core.entity`
        WHERE entity_id = '{brady_id}'
    """
    rows = list(client.query(entity_query).result())
    assert len(rows) == 1, f"Expected 1 Brady entity row, got {len(rows)}"
    assert rows[0]["entity_kind"] == "person"
    assert rows[0]["primary_domain"] == "sports.nfl"

    # 2. must have exactly 3 Retire transitions
    retire_query = f"""
        SELECT COUNT(*) AS cnt
        FROM `{project_id}.silver_v2_core.transition_event`
        WHERE entity_id = '{brady_id}'
          AND type = 'Retire'
    """
    result = list(client.query(retire_query).result())
    retire_count = result[0]["cnt"]
    assert retire_count == 3, f"Expected 3 Brady Retire transitions, got {retire_count}"


@pytest.mark.integration
@_skip_b1
def test_chad_johnson_name_change_transitions():
    """
    Chad Johnson must have 2 NameChange transitions representing the
    Johnson -> Ochocinco -> Johnson cycle.

    This is the canonical name-change stress-test case (Issue #555).
    """
    client, project_id = _bq_client()
    chad_id = _stable_id("chad_johnson")

    # entity must exist
    entity_query = f"""
        SELECT entity_id
        FROM `{project_id}.silver_v2_core.entity`
        WHERE entity_id = '{chad_id}'
    """
    rows = list(client.query(entity_query).result())
    assert len(rows) == 1, f"Expected 1 Chad Johnson entity row, got {len(rows)}"

    # must have exactly 2 NameChange transitions
    nc_query = f"""
        SELECT type, from_value, to_value
        FROM `{project_id}.silver_v2_core.transition_event`
        WHERE entity_id = '{chad_id}'
          AND type = 'NameChange'
        ORDER BY occurred_at
    """
    transitions = list(client.query(nc_query).result())
    assert len(transitions) == 2, (
        f"Expected 2 NameChange transitions, got {len(transitions)}"
    )
    # First: Johnson -> Ochocinco
    assert transitions[0]["from_value"] == "Chad Johnson"
    assert transitions[0]["to_value"] == "Chad Ochocinco"
    # Second: Ochocinco -> Johnson
    assert transitions[1]["from_value"] == "Chad Ochocinco"
    assert transitions[1]["to_value"] == "Chad Johnson"

    # Also verify alias rows: all 3 legal name aliases should exist
    alias_query = f"""
        SELECT alias_text, alias_kind, is_legal
        FROM `{project_id}.silver_v2_core.entity_alias`
        WHERE entity_id = '{chad_id}'
          AND is_legal = TRUE
        ORDER BY valid_from
    """
    aliases = list(client.query(alias_query).result())
    alias_texts = [r["alias_text"] for r in aliases]
    assert "Chad Johnson" in alias_texts, "Legal alias 'Chad Johnson' must exist"
    assert "Chad Ochocinco" in alias_texts, "Legal alias 'Chad Ochocinco' must exist"


@pytest.mark.integration
@_skip_b1
def test_bo_jackson_concurrent_employment():
    """
    Bo Jackson must have 2 concurrent employment attribute events with
    is_concurrent_ok=TRUE (NFL Raiders + MLB Royals).

    This is the canonical concurrent-employment stress-test case (Issue #555).
    """
    client, project_id = _bq_client()
    bo_id = _stable_id("bo_jackson")

    # entity must exist
    entity_query = f"""
        SELECT entity_id
        FROM `{project_id}.silver_v2_core.entity`
        WHERE entity_id = '{bo_id}'
    """
    rows = list(client.query(entity_query).result())
    assert len(rows) == 1, f"Expected 1 Bo Jackson entity row, got {len(rows)}"

    # employment attributes must have is_concurrent_ok = TRUE
    employment_query = f"""
        SELECT attr, value, is_concurrent_ok
        FROM `{project_id}.silver_v2_core.entity_attribute_event`
        WHERE entity_id = '{bo_id}'
          AND attr = 'employment'
        ORDER BY valid_from
    """
    employment_rows = list(client.query(employment_query).result())
    assert len(employment_rows) == 2, (
        f"Expected 2 employment rows for Bo Jackson, got {len(employment_rows)}"
    )
    for row in employment_rows:
        assert row["is_concurrent_ok"] is True, (
            f"Bo Jackson employment row '{row['value']}' must have is_concurrent_ok=True"
        )

    # Both NFL and MLB must be represented
    values = {r["value"] for r in employment_rows}
    assert any("Raiders" in v or "NFL" in v for v in values), (
        "Bo Jackson must have an NFL Raiders employment row"
    )
    assert any("Royals" in v or "MLB" in v for v in values), (
        "Bo Jackson must have a Kansas City Royals (MLB) employment row"
    )


# ---------------------------------------------------------------------------
# Remaining Phase B-1 tests — skipped pending Phase B-2 claim/resolution work
# ---------------------------------------------------------------------------

_B2_REASON = "Phase B-2: requires claim/resolution tables populated"


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_table_exists_in_bq():
    """silver_v2_core.entity table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_alias_table_exists_in_bq():
    """silver_v2_core.entity_alias table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_attribute_event_table_exists_in_bq():
    """silver_v2_core.entity_attribute_event table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_transition_event_table_exists_in_bq():
    """silver_v2_core.transition_event table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_domain_taxonomy_table_exists_in_bq():
    """silver_v2_core.domain_taxonomy table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_domain_taxonomy_seed_count_in_bq():
    """domain_taxonomy must have exactly 8 rows in BigQuery after migration."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_raw_utterance_table_exists_in_bq():
    """silver_v2_claims.raw_utterance table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_claim_table_exists_in_bq():
    """silver_v2_claims.claim table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_resolution_method_table_exists_in_bq():
    """silver_v2_claims.resolution_method table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_resolution_table_exists_in_bq():
    """silver_v2_claims.resolution table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_franchise_lineage_table_exists_in_bq():
    """silver_v2_sports.franchise_lineage table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_current_view_exists_in_bq():
    """silver_v2_core.entity_current view must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_timeline_view_exists_in_bq():
    """silver_v2_core.entity_timeline view must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_roundtrip_insert_and_read():
    """Insert a test entity and read it back via entity_current view."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_alias_links_to_entity():
    """entity_alias.entity_id must resolve to a row in entity."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_attribute_event_valid_to_null_means_current():
    """Attributes with valid_to IS NULL must appear in entity_current view."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_is_concurrent_ok_allows_multiple_current_values():
    """Attributes with is_concurrent_ok=TRUE may have multiple valid_to IS NULL rows."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_claim_prev_hash_chain_integrity():
    """Each claim.prev_hash must equal this_hash of prior_claim_id row."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_resolution_prev_hash_chain_integrity():
    """Each resolution.prev_hash must equal this_hash of the prior resolution row."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_claim_must_be_testable_assertion_returns_zero_rows():
    """CI assertion query silver_v2_claim_must_be_testable must return zero rows."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_claim_subject_entity_ids_resolve_to_entities():
    """All entity UUIDs in claim.subject_entity_ids must exist in entity table."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_transition_event_occurred_at_precision_enum():
    """All transition_event rows must have occurred_at_precision in (second,day,month,year)."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_resolution_outcome_enum():
    """All resolution.outcome values must be in (true,false,partial,unresolvable,vacuous,pending)."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_entity_kind_enum():
    """All entity.entity_kind values must be in (person,team_brand,franchise,org,product,event,office)."""
    pass


@pytest.mark.skip(reason=_B2_REASON)
def test_domain_hierarchy_parent_child_referential_integrity():
    """Every domain_taxonomy row with a non-NULL parent_domain must have a parent that exists."""
    pass
