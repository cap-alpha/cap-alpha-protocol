-- Migration: 029_add_post_event_flag
-- Issue: #996 — Filter post-event articles from extraction (root cause for #993 contamination)
-- Description: Add is_post_event BOOL flag to bronze_layer.raw_pundit_media so the
--   ingestion heuristic can tag articles that describe events already completed (e.g.
--   "Seahawks select X at pick 5" published after the draft ended).  The extractor
--   excludes is_post_event = TRUE rows so they are never fed to the LLM.
--
-- Includes a one-time backfill UPDATE that retroactively marks existing rows that
-- match the known post-event URL / title patterns.  Safe to re-run (idempotent).

-- ── 1. Add column ──────────────────────────────────────────────────────────────
-- BigQuery rejects `ADD COLUMN ... DEFAULT` on an existing table. Per the BQ
-- error guidance, split into three statements: add the column, set its DEFAULT
-- for future inserts, then backfill existing rows so the column is effectively
-- FALSE-by-default before the heuristic UPDATEs below flip qualifying rows to TRUE.
ALTER TABLE `{project_id}.nfl_dead_money.raw_pundit_media`
  ADD COLUMN IF NOT EXISTS is_post_event BOOL
    OPTIONS(description="TRUE when heuristic detects a post-event article (e.g. draft tracker, live grades). Rows with is_post_event=TRUE are excluded from LLM extraction.");

ALTER TABLE `{project_id}.nfl_dead_money.raw_pundit_media`
  ALTER COLUMN is_post_event SET DEFAULT FALSE;

UPDATE `{project_id}.nfl_dead_money.raw_pundit_media`
SET    is_post_event = FALSE
WHERE  is_post_event IS NULL;

-- ── 2. Backfill: URL-pattern heuristics ───────────────────────────────────────
--
--  Patterns that reliably indicate post-event reporting:
--    • draft-tracker          — live draft tracker embeds (PFT, The Athletic, etc.)
--    • live-draft-grades      — draft-grade articles published during/after event
--    • live-draft             — generic live-blog slug
--    • -nfl-draft-pick-<N>-   — Athletic pick-by-pick articles (e.g. "chiefs-nfl-draft-pick-5-2026")
--    • draft-results          — post-draft summary pages
--    • -selected-by-          — Athletic player-selection slug
--
UPDATE `{project_id}.nfl_dead_money.raw_pundit_media`
SET    is_post_event = TRUE
WHERE  is_post_event IS DISTINCT FROM TRUE
  AND (
        REGEXP_CONTAINS(LOWER(source_url), r'draft-tracker')
     OR REGEXP_CONTAINS(LOWER(source_url), r'live-draft-grades')
     OR REGEXP_CONTAINS(LOWER(source_url), r'live-draft')
     OR REGEXP_CONTAINS(LOWER(source_url), r'-nfl-draft-pick-\d+')
     OR REGEXP_CONTAINS(LOWER(source_url), r'draft-results')
     OR REGEXP_CONTAINS(LOWER(source_url), r'-selected-by-')
  );

-- ── 3. Backfill: title-pattern heuristics ─────────────────────────────────────
--
--  Titles of the form "<Team> selects/drafts/picks <Player>" are reports of fact.
--  The REGEXP matches the 32 NFL franchise cities/nicknames followed by a verb.
--  Deliberately conservative — only exact post-event verb forms trigger.
--
UPDATE `{project_id}.nfl_dead_money.raw_pundit_media`
SET    is_post_event = TRUE
WHERE  is_post_event IS DISTINCT FROM TRUE
  AND  title IS NOT NULL
  AND  REGEXP_CONTAINS(
         LOWER(title),
         r'^(arizona|atlanta|baltimore|buffalo|carolina|chicago|cincinnati|cleveland|dallas|denver|detroit|green bay|houston|indianapolis|jacksonville|kansas city|las vegas|los angeles|miami|minnesota|new england|new orleans|new york|philadelphia|pittsburgh|san francisco|seattle|tampa bay|tennessee|washington)'
         r'\s+(cardinals?|falcons?|ravens?|bills?|panthers?|bears?|bengals?|browns?|cowboys?|broncos?|lions?|packers?|texans?|colts?|jaguars?|chiefs?|raiders?|rams?|chargers?|dolphins?|vikings?|patriots?|saints?|giants?|jets?|eagles?|steelers?|49ers?|seahawks?|buccaneers?|titans?|commanders?)?'
         r'\s*(selects?|drafts?|picks?|takes?|chooses?|chose)\s+'
       );

-- ── 4. Backfill: published-after-event date guard ─────────────────────────────
--
--  Known event windows (UTC close).  Articles published AFTER the event closes
--  that were ingested from known post-event source IDs are tagged.
--
--  2025 NFL Draft: April 24-26 2025 → closed 2025-04-27 00:00 UTC
--  2026 NFL Draft: April 23-25 2026 → closed 2026-04-26 00:00 UTC
--
--  Source IDs associated with draft tracker / live-blog content:
--    pft_staff, athletic_nfl_staff
--
UPDATE `{project_id}.nfl_dead_money.raw_pundit_media`
SET    is_post_event = TRUE
WHERE  is_post_event IS DISTINCT FROM TRUE
  AND  source_id IN ('pft_staff', 'athletic_nfl_staff')
  AND (
        (published_at >= TIMESTAMP '2025-04-27 00:00:00 UTC'
         AND published_at <  TIMESTAMP '2025-05-15 00:00:00 UTC')
     OR (published_at >= TIMESTAMP '2026-04-26 00:00:00 UTC'
         AND published_at <  TIMESTAMP '2026-05-15 00:00:00 UTC')
  );

-- ── Verification queries (copy-paste into BigQuery console to confirm) ─────────
--
-- Count flagged rows:
--   SELECT COUNT(*) AS flagged
--   FROM `{project_id}.nfl_dead_money.raw_pundit_media`
--   WHERE is_post_event = TRUE;
--
-- Before/after breakdown by source:
--   SELECT source_id,
--          COUNTIF(is_post_event = TRUE)  AS post_event,
--          COUNTIF(is_post_event = FALSE OR is_post_event IS NULL) AS clean
--   FROM `{project_id}.nfl_dead_money.raw_pundit_media`
--   GROUP BY source_id
--   ORDER BY post_event DESC;
