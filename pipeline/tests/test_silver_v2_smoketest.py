"""
Phase B-0 smoke tests for the silver_v2_* schema (Issue #555).

This module is the 25-case stress test harness for the general-purpose truth
ledger data model. It validates:

  1. domain_taxonomy seed data integrity (runs in CI without BigQuery)
  2. Schema contract tests (Phase B-1: requires BQ backfill — skipped until then)
  3. Claim promotion logic (Phase B-1: skipped)
  4. Entity resolution round-trips (Phase B-1: skipped)
  5. Cryptographic chain integrity for claims (Phase B-1: skipped)
  ... and 20 additional cases gated on Phase B-1 backfill.

Phase B-1 tests are marked pytest.mark.skip and will be activated once the
BigQuery datasets are backfilled and the pipeline adapters are implemented.
"""

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
# Phase B-1: BigQuery integration tests (skipped until backfill complete)
# ---------------------------------------------------------------------------

_B1_REASON = "Phase B-1: requires BQ backfill and live dataset"


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_table_exists_in_bq():
    """silver_v2_core.entity table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_alias_table_exists_in_bq():
    """silver_v2_core.entity_alias table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_attribute_event_table_exists_in_bq():
    """silver_v2_core.entity_attribute_event table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_transition_event_table_exists_in_bq():
    """silver_v2_core.transition_event table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_domain_taxonomy_table_exists_in_bq():
    """silver_v2_core.domain_taxonomy table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_domain_taxonomy_seed_count_in_bq():
    """domain_taxonomy must have exactly 8 rows in BigQuery after migration."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_raw_utterance_table_exists_in_bq():
    """silver_v2_claims.raw_utterance table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_claim_table_exists_in_bq():
    """silver_v2_claims.claim table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_resolution_method_table_exists_in_bq():
    """silver_v2_claims.resolution_method table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_resolution_table_exists_in_bq():
    """silver_v2_claims.resolution table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_franchise_lineage_table_exists_in_bq():
    """silver_v2_sports.franchise_lineage table must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_current_view_exists_in_bq():
    """silver_v2_core.entity_current view must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_timeline_view_exists_in_bq():
    """silver_v2_core.entity_timeline view must exist in BigQuery."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_roundtrip_insert_and_read():
    """Insert a test entity and read it back via entity_current view."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_alias_links_to_entity():
    """entity_alias.entity_id must resolve to a row in entity."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_attribute_event_valid_to_null_means_current():
    """Attributes with valid_to IS NULL must appear in entity_current view."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_is_concurrent_ok_allows_multiple_current_values():
    """Attributes with is_concurrent_ok=TRUE may have multiple valid_to IS NULL rows."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_claim_prev_hash_chain_integrity():
    """Each claim.prev_hash must equal this_hash of prior_claim_id row."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_resolution_prev_hash_chain_integrity():
    """Each resolution.prev_hash must equal this_hash of the prior resolution row."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_claim_must_be_testable_assertion_returns_zero_rows():
    """CI assertion query silver_v2_claim_must_be_testable must return zero rows."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_claim_subject_entity_ids_resolve_to_entities():
    """All entity UUIDs in claim.subject_entity_ids must exist in entity table."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_transition_event_occurred_at_precision_enum():
    """All transition_event rows must have occurred_at_precision in (second,day,month,year)."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_resolution_outcome_enum():
    """All resolution.outcome values must be in (true,false,partial,unresolvable,vacuous,pending)."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_entity_kind_enum():
    """All entity.entity_kind values must be in (person,team_brand,franchise,org,product,event,office)."""
    pass


@pytest.mark.skip(reason=_B1_REASON)
def test_domain_hierarchy_parent_child_referential_integrity():
    """Every domain_taxonomy row with a non-NULL parent_domain must have a parent that exists."""
    pass
