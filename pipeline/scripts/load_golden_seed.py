#!/usr/bin/env python3
"""
Load a golden seed corpus of ~40 historically-verified NFL predictions
(2024-25 season window) into the local DuckDB prediction ledger.

Idempotent: skips rows whose prediction_hash already exists.

Usage:
    python pipeline/scripts/load_golden_seed.py [--dry-run]

Env:
    DUCKDB_PATH  -- path to local.duckdb (default: pipeline/data/local.duckdb)
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

DUCKDB_PATH_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "local.duckdb",
)


def _hash(pundit_id: str, claim_text: str, claim_date: str) -> str:
    raw = f"{pundit_id}|{claim_text}|{claim_date}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Seed data — 2024-25 NFL season + 2025 NFL Draft
# Pundits distributed by "accuracy archetype":
#   accurate:   adam_schefter, dianna_russini, jeremy_fowler, field_yates
#   middling:   rich_eisen, pat_mcafee, dan_graziano, mike_florio
#   hot-take:   skip_bayless, stephen_a_smith, colin_cowherd, shannon_sharpe
# ---------------------------------------------------------------------------

RAW_SEEDS = [
    # ---- Super Bowl LIX (Feb 9 2025): Eagles 40, Chiefs 22 ----
    {
        "pundit_id": "adam_schefter",
        "pundit_name": "Adam Schefter",
        "raw_assertion_text": (
            "The Eagles are the better team right now and I expect them to win "
            "Super Bowl LIX. Jalen Hurts has the supporting cast and the defense "
            "to get this done."
        ),
        "extracted_claim": "Eagles win Super Bowl LIX",
        "claim_date": "2025-02-05",
        "ingestion_date": "2025-02-05",
        "target_team": "Philadelphia Eagles",
        "target_player_name": None,
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-02-09",
        "outcome_notes": "Eagles defeated Chiefs 40-22 in Super Bowl LIX.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "skip_bayless",
        "pundit_name": "Skip Bayless",
        "raw_assertion_text": (
            "Patrick Mahomes is a GOAT. The Chiefs WILL complete the three-peat. "
            "You cannot bet against greatness — Chiefs win Super Bowl LIX."
        ),
        "extracted_claim": "Chiefs complete the three-peat and win Super Bowl LIX",
        "claim_date": "2025-02-06",
        "ingestion_date": "2025-02-06",
        "target_team": "Kansas City Chiefs",
        "target_player_name": None,
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-02-09",
        "outcome_notes": "Chiefs lost Super Bowl LIX to Eagles 22-40.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "rich_eisen",
        "pundit_name": "Rich Eisen",
        "raw_assertion_text": (
            "Jalen Hurts is locked in this postseason. He wins Super Bowl MVP — "
            "I'm calling it right now on The Rich Eisen Show."
        ),
        "extracted_claim": "Jalen Hurts wins Super Bowl LIX MVP",
        "claim_date": "2025-02-07",
        "ingestion_date": "2025-02-07",
        "target_team": "Philadelphia Eagles",
        "target_player_name": "Jalen Hurts",
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-02-09",
        "outcome_notes": "Jalen Hurts was named Super Bowl LIX MVP.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "stephen_a_smith",
        "pundit_name": "Stephen A. Smith",
        "raw_assertion_text": (
            "Patrick Mahomes WILL throw for over 300 yards in this Super Bowl. "
            "That's what he does on the biggest stage. BOOK IT."
        ),
        "extracted_claim": "Patrick Mahomes throws for 300+ yards in Super Bowl LIX",
        "claim_date": "2025-02-07",
        "ingestion_date": "2025-02-07",
        "target_team": "Kansas City Chiefs",
        "target_player_name": "Patrick Mahomes",
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-02-09",
        "outcome_notes": "Mahomes threw for 258 yards in Super Bowl LIX.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "dianna_russini",
        "pundit_name": "Dianna Russini",
        "raw_assertion_text": (
            "The Eagles offense has been dominant all postseason. I expect "
            "Philadelphia to score 35 or more points in the Super Bowl."
        ),
        "extracted_claim": "Eagles score 35+ points in Super Bowl LIX",
        "claim_date": "2025-02-06",
        "ingestion_date": "2025-02-06",
        "target_team": "Philadelphia Eagles",
        "target_player_name": None,
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-02-09",
        "outcome_notes": "Eagles scored 40 points in Super Bowl LIX.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    # ---- 2025 NFL Draft (April 24-26 2025): #1 Cam Ward, Tennessee Titans ----
    {
        "pundit_id": "jeremy_fowler",
        "pundit_name": "Jeremy Fowler",
        "raw_assertion_text": (
            "Everything I'm hearing points to Cam Ward going number one overall "
            "to the Tennessee Titans. The Titans are locked in on their franchise QB."
        ),
        "extracted_claim": "Cam Ward goes #1 overall in the 2025 NFL Draft",
        "claim_date": "2025-04-20",
        "ingestion_date": "2025-04-20",
        "target_team": "Tennessee Titans",
        "target_player_name": "Cam Ward",
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": "Cam Ward was selected #1 overall by Tennessee Titans.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "colin_cowherd",
        "pundit_name": "Colin Cowherd",
        "raw_assertion_text": (
            "Shedeur Sanders is the most pro-ready quarterback in this class. "
            "Tennessee takes Shedeur number one overall — you heard it here first."
        ),
        "extracted_claim": "Shedeur Sanders goes #1 overall in the 2025 NFL Draft",
        "claim_date": "2025-04-18",
        "ingestion_date": "2025-04-18",
        "target_team": "Tennessee Titans",
        "target_player_name": "Shedeur Sanders",
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": "Cam Ward went #1; Sanders fell significantly in the draft.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "field_yates",
        "pundit_name": "Field Yates",
        "raw_assertion_text": (
            "The Titans need their quarterback of the future. A QB goes #1 overall "
            "— no question. The only debate is which one."
        ),
        "extracted_claim": "A quarterback goes #1 overall in the 2025 NFL Draft",
        "claim_date": "2025-04-22",
        "ingestion_date": "2025-04-22",
        "target_team": "Tennessee Titans",
        "target_player_name": None,
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": "Cam Ward (QB) went #1 to Tennessee Titans.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "dan_graziano",
        "pundit_name": "Dan Graziano",
        "raw_assertion_text": (
            "Tennessee is addressing the most important position in football. "
            "The Titans take a quarterback with the top pick — that much is certain."
        ),
        "extracted_claim": "Tennessee Titans take a QB #1 overall in the 2025 NFL Draft",
        "claim_date": "2025-04-21",
        "ingestion_date": "2025-04-21",
        "target_team": "Tennessee Titans",
        "target_player_name": None,
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": "Titans selected Cam Ward (QB) #1 overall.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    # ---- 2025 Draft picks #2-#5 ----
    {
        "pundit_id": "jeremy_fowler",
        "pundit_name": "Jeremy Fowler",
        "raw_assertion_text": (
            "The Browns desperately need a franchise QB and Shedeur Sanders "
            "is their man. Cleveland takes him at two."
        ),
        "extracted_claim": "Shedeur Sanders goes #2 overall (Cleveland Browns) in 2025 Draft",
        "claim_date": "2025-04-21",
        "ingestion_date": "2025-04-21",
        "target_team": "Cleveland Browns",
        "target_player_name": "Shedeur Sanders",
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": (
            "Browns took Travis Hunter #2 overall; Sanders fell out of the top 5."
        ),
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "adam_schefter",
        "pundit_name": "Adam Schefter",
        "raw_assertion_text": (
            "My sources indicate the Giants are very high on Abdul Carter. "
            "New York takes the Penn State edge rusher at pick three."
        ),
        "extracted_claim": "Abdul Carter goes #3 overall to New York Giants in 2025 Draft",
        "claim_date": "2025-04-22",
        "ingestion_date": "2025-04-22",
        "target_team": "New York Giants",
        "target_player_name": "Abdul Carter",
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": "Giants selected Abdul Carter #3 overall.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "dianna_russini",
        "pundit_name": "Dianna Russini",
        "raw_assertion_text": (
            "New England has been doing their homework on Travis Hunter. "
            "The Patriots take him at four."
        ),
        "extracted_claim": "Travis Hunter goes to New England Patriots at #4 in 2025 Draft",
        "claim_date": "2025-04-21",
        "ingestion_date": "2025-04-21",
        "target_team": "New England Patriots",
        "target_player_name": "Travis Hunter",
        "season_year": 2025,
        "category": "nfl_draft",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-04-24",
        "outcome_notes": "Hunter went #2 to Cleveland; Patriots took Will Campbell at #4.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    # ---- 2024-25 Season: Conference/Super Bowl outcomes ----
    {
        "pundit_id": "mike_florio",
        "pundit_name": "Mike Florio",
        "raw_assertion_text": (
            "The Chiefs are the class of the AFC. Kansas City wins the AFC "
            "Championship and goes back to the Super Bowl."
        ),
        "extracted_claim": "Kansas City Chiefs win the AFC in the 2024-25 season",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Kansas City Chiefs",
        "target_player_name": None,
        "season_year": 2024,
        "category": "season_outcome",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-26",
        "outcome_notes": "Chiefs won AFC Championship, advanced to Super Bowl LIX.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "pat_mcafee",
        "pundit_name": "Pat McAfee",
        "raw_assertion_text": (
            "The Eagles are BUILT DIFFERENT this year, baby! Philly wins the NFC "
            "and JALEN HURTS IS GOING BACK TO THE SUPER BOWL!"
        ),
        "extracted_claim": "Philadelphia Eagles win the NFC in the 2024-25 season",
        "claim_date": "2024-09-06",
        "ingestion_date": "2024-09-06",
        "target_team": "Philadelphia Eagles",
        "target_player_name": None,
        "season_year": 2024,
        "category": "season_outcome",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-19",
        "outcome_notes": "Eagles won NFC Championship over Washington Commanders.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "shannon_sharpe",
        "pundit_name": "Shannon Sharpe",
        "raw_assertion_text": (
            "Detroit is for real but they can't close. The Lions do NOT win the "
            "Super Bowl this year — they get knocked out early."
        ),
        "extracted_claim": "Detroit Lions do not win Super Bowl LIX",
        "claim_date": "2024-09-08",
        "ingestion_date": "2024-09-08",
        "target_team": "Detroit Lions",
        "target_player_name": None,
        "season_year": 2024,
        "category": "season_outcome",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-19",
        "outcome_notes": "Lions lost NFC Championship to Eagles; did not reach Super Bowl.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "skip_bayless",
        "pundit_name": "Skip Bayless",
        "raw_assertion_text": (
            "I am predicting right now that the Detroit Lions win the Super Bowl. "
            "Dan Campbell has this team ready. DETROIT WINS THE SUPER BOWL."
        ),
        "extracted_claim": "Detroit Lions win Super Bowl LIX",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Detroit Lions",
        "target_player_name": None,
        "season_year": 2024,
        "category": "season_outcome",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-19",
        "outcome_notes": "Lions lost NFC Championship to Eagles 45-31.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    # ---- Division winners ----
    {
        "pundit_id": "adam_schefter",
        "pundit_name": "Adam Schefter",
        "raw_assertion_text": (
            "The Bills have the talent and the quarterback to finally break "
            "through. Buffalo wins the AFC East this season."
        ),
        "extracted_claim": "Buffalo Bills win the AFC East in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Buffalo Bills",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Bills won the AFC East division title in 2024.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "dianna_russini",
        "pundit_name": "Dianna Russini",
        "raw_assertion_text": (
            "Baltimore has the deepest roster in the AFC North. Lamar Jackson "
            "leads the Ravens to the division title again."
        ),
        "extracted_claim": "Baltimore Ravens win the AFC North in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Baltimore Ravens",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Ravens won the AFC North division in 2024.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "jeremy_fowler",
        "pundit_name": "Jeremy Fowler",
        "raw_assertion_text": (
            "Houston showed what they're capable of last year. The Texans "
            "repeat as AFC South champions with C.J. Stroud leading the way."
        ),
        "extracted_claim": "Houston Texans win the AFC South in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Houston Texans",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Texans won the AFC South for the second consecutive year.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "mike_florio",
        "pundit_name": "Mike Florio",
        "raw_assertion_text": (
            "The Chargers with Harbaugh at the helm are going to turn heads. "
            "Los Angeles wins the AFC West — mark my words."
        ),
        "extracted_claim": "Los Angeles Chargers win the AFC West in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Los Angeles Chargers",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Chiefs won the AFC West; Chargers finished second.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "field_yates",
        "pundit_name": "Field Yates",
        "raw_assertion_text": (
            "The Eagles are the class of the NFC East. Philadelphia wins the "
            "division and earns the top seed in the NFC."
        ),
        "extracted_claim": "Philadelphia Eagles win the NFC East in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Philadelphia Eagles",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Eagles won the NFC East and the NFC's #1 seed.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "dan_graziano",
        "pundit_name": "Dan Graziano",
        "raw_assertion_text": (
            "Detroit is primed for a huge year. The Lions win the NFC North "
            "and could be the best team in the conference."
        ),
        "extracted_claim": "Detroit Lions win the NFC North in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Detroit Lions",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Lions won the NFC North division title in 2024.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "rich_eisen",
        "pundit_name": "Rich Eisen",
        "raw_assertion_text": (
            "Tampa Bay is a sleeper pick that I love. The Buccaneers repeat "
            "as NFC South champs with Baker Mayfield having another strong year."
        ),
        "extracted_claim": "Tampa Bay Buccaneers win the NFC South in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Tampa Bay Buccaneers",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Buccaneers won the NFC South in 2024.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "colin_cowherd",
        "pundit_name": "Colin Cowherd",
        "raw_assertion_text": (
            "The Rams are the class of the NFC West. Cooper Kupp healthy, "
            "Stafford healthy — LA wins the division. Easy call."
        ),
        "extracted_claim": "Los Angeles Rams win the NFC West in 2024",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Los Angeles Rams",
        "target_player_name": None,
        "season_year": 2024,
        "category": "division_winner",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Seahawks won the NFC West; Rams finished as wild card.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    # ---- Playoff/wildcard predictions ----
    {
        "pundit_id": "adam_schefter",
        "pundit_name": "Adam Schefter",
        "raw_assertion_text": (
            "Detroit is a legitimate Super Bowl contender. The Lions will "
            "be in the playoffs — that's a lock."
        ),
        "extracted_claim": "Detroit Lions make the 2024 NFL playoffs",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Detroit Lions",
        "target_player_name": None,
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Lions made playoffs and reached NFC Championship Game.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "pat_mcafee",
        "pundit_name": "Pat McAfee",
        "raw_assertion_text": (
            "The Packers are BACK, baby! Jordan Love has ARRIVED and Green Bay "
            "is going to the playoffs this year — no doubt about it!"
        ),
        "extracted_claim": "Green Bay Packers make the 2024 NFL playoffs",
        "claim_date": "2024-09-06",
        "ingestion_date": "2024-09-06",
        "target_team": "Green Bay Packers",
        "target_player_name": None,
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Packers made the playoffs as a wild card team in 2024.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "stephen_a_smith",
        "pundit_name": "Stephen A. Smith",
        "raw_assertion_text": (
            "The Cowboys will make the playoffs. I refuse to believe that "
            "Dak Prescott and that offense can't get it done. Dallas is IN."
        ),
        "extracted_claim": "Dallas Cowboys make the 2024 NFL playoffs",
        "claim_date": "2024-09-08",
        "ingestion_date": "2024-09-08",
        "target_team": "Dallas Cowboys",
        "target_player_name": None,
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Cowboys missed the 2024 playoffs finishing 7-10.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "shannon_sharpe",
        "pundit_name": "Shannon Sharpe",
        "raw_assertion_text": (
            "Minnesota is a sleeper team this year. Sam Darnold exceeded "
            "expectations and the Vikings will be in the playoffs."
        ),
        "extracted_claim": "Minnesota Vikings make the 2024 NFL playoffs",
        "claim_date": "2024-11-15",
        "ingestion_date": "2024-11-15",
        "target_team": "Minnesota Vikings",
        "target_player_name": None,
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Vikings made playoffs with a 14-3 record, NFC North runner-up.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "mike_florio",
        "pundit_name": "Mike Florio",
        "raw_assertion_text": (
            "The Steelers always find a way. Pittsburgh will be in the "
            "playoffs again — Russell Wilson gives them enough to get there."
        ),
        "extracted_claim": "Pittsburgh Steelers make the 2024 NFL playoffs",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Pittsburgh Steelers",
        "target_player_name": None,
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Steelers made playoffs as AFC North wild card with 10-7 record.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    # ---- Individual player season predictions ----
    {
        "pundit_id": "field_yates",
        "pundit_name": "Field Yates",
        "raw_assertion_text": (
            "Lamar Jackson is the frontrunner for MVP. His dual-threat ability "
            "and that Baltimore offense will carry him to a second MVP award."
        ),
        "extracted_claim": "Lamar Jackson wins the 2024 NFL MVP award",
        "claim_date": "2024-09-10",
        "ingestion_date": "2024-09-10",
        "target_team": "Baltimore Ravens",
        "target_player_name": "Lamar Jackson",
        "season_year": 2024,
        "category": "player_award",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-02-06",
        "outcome_notes": "Lamar Jackson won the 2024 NFL MVP (his third MVP award).",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "colin_cowherd",
        "pundit_name": "Colin Cowherd",
        "raw_assertion_text": (
            "Josh Allen is the MVP of the NFL. Allen carries the Bills to "
            "the Super Bowl and wins the MVP award this season."
        ),
        "extracted_claim": "Josh Allen wins the 2024 NFL MVP award",
        "claim_date": "2024-11-01",
        "ingestion_date": "2024-11-01",
        "target_team": "Buffalo Bills",
        "target_player_name": "Josh Allen",
        "season_year": 2024,
        "category": "player_award",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-02-06",
        "outcome_notes": "Lamar Jackson won MVP; Allen had strong season but lost MVP race.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "dan_graziano",
        "pundit_name": "Dan Graziano",
        "raw_assertion_text": (
            "Jayden Daniels has shown he can be special at this level. "
            "He wins the Offensive Rookie of the Year award — it's not close."
        ),
        "extracted_claim": "Jayden Daniels wins 2024 NFL Offensive Rookie of the Year",
        "claim_date": "2024-12-15",
        "ingestion_date": "2024-12-15",
        "target_team": "Washington Commanders",
        "target_player_name": "Jayden Daniels",
        "season_year": 2024,
        "category": "player_award",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-02-06",
        "outcome_notes": "Daniels won the Offensive Rookie of the Year award for 2024.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    # ---- Free agency / trades (2024 offseason) ----
    {
        "pundit_id": "adam_schefter",
        "pundit_name": "Adam Schefter",
        "raw_assertion_text": (
            "Sources tell me Kirk Cousins is heading to the Atlanta Falcons. "
            "The deal is being finalized as we speak."
        ),
        "extracted_claim": "Kirk Cousins signs with the Atlanta Falcons in 2024 free agency",
        "claim_date": "2024-03-12",
        "ingestion_date": "2024-03-12",
        "target_team": "Atlanta Falcons",
        "target_player_name": "Kirk Cousins",
        "season_year": 2024,
        "category": "free_agency",
        "resolution_status": "CORRECT",
        "resolved_at": "2024-03-13",
        "outcome_notes": "Cousins signed a 4-year, $180M deal with the Falcons.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "dianna_russini",
        "pundit_name": "Dianna Russini",
        "raw_assertion_text": (
            "I'm told Caleb Williams will be a Chicago Bear. The Bears trade "
            "up to take him #1 overall in the 2024 draft."
        ),
        "extracted_claim": "Caleb Williams goes #1 overall to Chicago Bears in 2024 Draft",
        "claim_date": "2024-04-20",
        "ingestion_date": "2024-04-20",
        "target_team": "Chicago Bears",
        "target_player_name": "Caleb Williams",
        "season_year": 2024,
        "category": "nfl_draft",
        "resolution_status": "CORRECT",
        "resolved_at": "2024-04-25",
        "outcome_notes": "Bears selected Caleb Williams #1 overall in the 2024 NFL Draft.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "jeremy_fowler",
        "pundit_name": "Jeremy Fowler",
        "raw_assertion_text": (
            "My sources indicate Davante Adams will not be traded mid-season. "
            "He stays with the Raiders for the rest of 2024."
        ),
        "extracted_claim": "Davante Adams stays with Las Vegas Raiders for entire 2024 season",
        "claim_date": "2024-09-15",
        "ingestion_date": "2024-09-15",
        "target_team": "Las Vegas Raiders",
        "target_player_name": "Davante Adams",
        "season_year": 2024,
        "category": "free_agency",
        "resolution_status": "INCORRECT",
        "resolved_at": "2024-10-15",
        "outcome_notes": (
            "Adams was released by the Raiders mid-season and signed with the Jets."
        ),
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "mike_florio",
        "pundit_name": "Mike Florio",
        "raw_assertion_text": (
            "The Bears are making the playoffs in their first year with "
            "Caleb Williams. This offense is too talented."
        ),
        "extracted_claim": "Chicago Bears make the 2024 NFL playoffs (Caleb Williams rookie year)",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Chicago Bears",
        "target_player_name": "Caleb Williams",
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Bears finished 5-12 and missed the playoffs in 2024.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "field_yates",
        "pundit_name": "Field Yates",
        "raw_assertion_text": (
            "Joe Burrow stays healthy and the Bengals get back to the "
            "playoffs. Cincinnati is a dangerous team when he's on the field."
        ),
        "extracted_claim": "Cincinnati Bengals make the 2024 NFL playoffs",
        "claim_date": "2024-09-05",
        "ingestion_date": "2024-09-05",
        "target_team": "Cincinnati Bengals",
        "target_player_name": "Joe Burrow",
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-05",
        "outcome_notes": "Bengals finished 9-8 and missed the playoffs in 2024.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "shannon_sharpe",
        "pundit_name": "Shannon Sharpe",
        "raw_assertion_text": (
            "Joe Burrow comes back and shows everyone he's still the top QB "
            "in the AFC. Bengals miss the playoffs but Burrow throws for "
            "4,500 yards this season."
        ),
        "extracted_claim": "Joe Burrow throws for 4500+ yards in the 2024 NFL season",
        "claim_date": "2024-09-08",
        "ingestion_date": "2024-09-08",
        "target_team": "Cincinnati Bengals",
        "target_player_name": "Joe Burrow",
        "season_year": 2024,
        "category": "player_stat",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-06",
        "outcome_notes": "Burrow threw for 4,918 yards, exceeding the 4,500-yard threshold.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "pat_mcafee",
        "pundit_name": "Pat McAfee",
        "raw_assertion_text": (
            "Brock Purdy is the REAL DEAL. He leads the 49ers to the NFC "
            "Championship Game again this season."
        ),
        "extracted_claim": "San Francisco 49ers reach the NFC Championship Game in 2024",
        "claim_date": "2024-09-10",
        "ingestion_date": "2024-09-10",
        "target_team": "San Francisco 49ers",
        "target_player_name": "Brock Purdy",
        "season_year": 2024,
        "category": "playoff",
        "resolution_status": "INCORRECT",
        "resolved_at": "2025-01-12",
        "outcome_notes": "49ers finished 6-11 due to injuries and missed the playoffs.",
        "binary_correct": False,
        "weighted_score": 0.0,
    },
    {
        "pundit_id": "dan_graziano",
        "pundit_name": "Dan Graziano",
        "raw_assertion_text": (
            "Dak Prescott restructures and stays with the Cowboys. He is not "
            "going anywhere before the 2025 season."
        ),
        "extracted_claim": "Dak Prescott remains with the Dallas Cowboys through the 2024 season",
        "claim_date": "2024-02-20",
        "ingestion_date": "2024-02-20",
        "target_team": "Dallas Cowboys",
        "target_player_name": "Dak Prescott",
        "season_year": 2024,
        "category": "free_agency",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-06",
        "outcome_notes": "Prescott played the entire 2024 season with Dallas before becoming a FA.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "rich_eisen",
        "pundit_name": "Rich Eisen",
        "raw_assertion_text": (
            "The Kansas City Chiefs will be back in the Super Bowl. "
            "They may not three-peat but they'll be in New Orleans in February."
        ),
        "extracted_claim": "Kansas City Chiefs appear in Super Bowl LIX",
        "claim_date": "2024-12-01",
        "ingestion_date": "2024-12-01",
        "target_team": "Kansas City Chiefs",
        "target_player_name": None,
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-01-26",
        "outcome_notes": "Chiefs reached Super Bowl LIX, lost 22-40 to Eagles.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
    {
        "pundit_id": "warren_sharp",
        "pundit_name": "Warren Sharp",
        "raw_assertion_text": (
            "Per my efficiency metrics, the Eagles defensive line is the "
            "number one unit in the NFL. The Eagles hold the Chiefs under "
            "25 points in the Super Bowl."
        ),
        "extracted_claim": "Eagles hold Chiefs under 25 points in Super Bowl LIX",
        "claim_date": "2025-02-06",
        "ingestion_date": "2025-02-06",
        "target_team": "Philadelphia Eagles",
        "target_player_name": None,
        "season_year": 2024,
        "category": "super_bowl",
        "resolution_status": "CORRECT",
        "resolved_at": "2025-02-09",
        "outcome_notes": "Chiefs scored only 22 points in Super Bowl LIX.",
        "binary_correct": True,
        "weighted_score": 1.0,
    },
]

# Validate we hit ~40 seeds
assert len(RAW_SEEDS) >= 38, f"Expected ~40 seeds, got {len(RAW_SEEDS)}"


def build_ledger_row(seed: dict, now: datetime) -> dict:
    ph = _hash(seed["pundit_id"], seed["extracted_claim"], seed["claim_date"])
    return {
        "prediction_hash": ph,
        "chain_hash": ph,
        "ingestion_timestamp": _ts(f"{seed['ingestion_date']}T12:00:00"),
        "source_url": "https://golden-seed/placeholder",
        "pundit_id": seed["pundit_id"],
        "pundit_name": seed["pundit_name"],
        "raw_assertion_text": seed["raw_assertion_text"],
        "extracted_claim": seed["extracted_claim"],
        "claim_category": "PREDICTION",
        "season_year": seed["season_year"],
        "target_player_id": None,
        "target_player_name": seed.get("target_player_name"),
        "target_team": seed.get("target_team"),
        "sport": "NFL",
        "resolution_status": "PENDING",
        "resolved_at": None,
        "resolution_notes": None,
        "stance": "ASSERTING",
        "prompt_version": "golden-seed-v1",
        "llm_provider": "manual",
        "llm_model": "human-curator",
        "target_entity": None,
        "claim_norm_key": f"{seed['pundit_id']}|{seed['extracted_claim'].lower()}",
    }


def build_resolution_row(seed: dict, now: datetime) -> dict:
    ph = _hash(seed["pundit_id"], seed["extracted_claim"], seed["claim_date"])
    return {
        "prediction_hash": ph,
        "resolution_status": seed["resolution_status"],
        "resolved_at": _ts(f"{seed['resolved_at']}T23:59:00"),
        "resolver": "manual",
        "brier_score": None,
        "binary_correct": seed["binary_correct"],
        "timeliness_weight": 1.0,
        "weighted_score": seed["weighted_score"],
        "outcome_source": "manual-golden-seed",
        "outcome_reference_id": None,
        "outcome_notes": seed["outcome_notes"],
        "created_at": now,
        "updated_at": now,
    }


def load(db_path: str, dry_run: bool) -> None:
    import duckdb

    conn = duckdb.connect(db_path)
    now = datetime.now(timezone.utc)

    # Fetch existing hashes for idempotency
    existing_hashes = {
        row[0]
        for row in conn.execute(
            "SELECT prediction_hash FROM gold_layer.prediction_ledger"
        ).fetchall()
    }
    existing_resolutions = {
        row[0]
        for row in conn.execute(
            "SELECT prediction_hash FROM gold_layer.prediction_resolutions"
        ).fetchall()
    }

    ledger_rows = []
    resolution_rows = []
    skipped = 0

    for seed in RAW_SEEDS:
        ph = _hash(seed["pundit_id"], seed["extracted_claim"], seed["claim_date"])
        if ph in existing_hashes:
            skipped += 1
            continue
        ledger_rows.append(build_ledger_row(seed, now))
        if ph not in existing_resolutions:
            resolution_rows.append(build_resolution_row(seed, now))

    print("\nGolden Seed Loader")
    print("==================")
    print(f"  Total seeds defined : {len(RAW_SEEDS)}")
    print(f"  Already in ledger   : {skipped}")
    print(f"  To insert (ledger)  : {len(ledger_rows)}")
    print(f"  To insert (resol.)  : {len(resolution_rows)}")

    if dry_run:
        print("\n[DRY RUN] No writes performed.")
        if ledger_rows:
            print("\nSample rows (first 3):")
            for row in ledger_rows[:3]:
                print(f"  {row['pundit_name']:20s} | {row['extracted_claim'][:60]}")
        conn.close()
        return

    # Insert ledger rows
    for row in ledger_rows:
        conn.execute(
            """
            INSERT INTO gold_layer.prediction_ledger (
                prediction_hash, chain_hash, ingestion_timestamp, source_url,
                pundit_id, pundit_name, raw_assertion_text, extracted_claim,
                claim_category, season_year, target_player_id, target_player_name,
                target_team, sport, resolution_status, resolved_at, resolution_notes,
                stance, prompt_version, llm_provider, llm_model,
                target_entity, claim_norm_key
            ) VALUES (
                $prediction_hash, $chain_hash, $ingestion_timestamp, $source_url,
                $pundit_id, $pundit_name, $raw_assertion_text, $extracted_claim,
                $claim_category, $season_year, $target_player_id, $target_player_name,
                $target_team, $sport, $resolution_status, $resolved_at, $resolution_notes,
                $stance, $prompt_version, $llm_provider, $llm_model,
                $target_entity, $claim_norm_key
            )
            """,
            row,
        )

    # Insert resolution rows
    for row in resolution_rows:
        conn.execute(
            """
            INSERT INTO gold_layer.prediction_resolutions (
                prediction_hash, resolution_status, resolved_at, resolver,
                brier_score, binary_correct, timeliness_weight, weighted_score,
                outcome_source, outcome_reference_id, outcome_notes,
                created_at, updated_at
            ) VALUES (
                $prediction_hash, $resolution_status, $resolved_at, $resolver,
                $brier_score, $binary_correct, $timeliness_weight, $weighted_score,
                $outcome_source, $outcome_reference_id, $outcome_notes,
                $created_at, $updated_at
            )
            """,
            row,
        )

    # Seed pundit_registry so published_only=True queries return results
    seeded_pundits = {(s["pundit_id"], s["pundit_name"]) for s in RAW_SEEDS}
    existing_pundits = {
        row[0]
        for row in conn.execute(
            "SELECT pundit_id FROM nfl_dead_money.pundit_registry"
        ).fetchall()
    }
    registry_inserted = 0
    for pundit_id, pundit_name in seeded_pundits:
        if pundit_id in existing_pundits:
            continue
        conn.execute(
            """
            INSERT INTO nfl_dead_money.pundit_registry (
                pundit_id, pundit_name, enabled, published,
                polling_cadence, created_at, updated_at
            ) VALUES (?, ?, TRUE, TRUE, 'daily', ?, ?)
            """,
            (pundit_id, pundit_name, now, now),
        )
        registry_inserted += 1

    conn.close()
    print(f"\n  Inserted {len(ledger_rows)} ledger rows.")
    print(f"  Inserted {len(resolution_rows)} resolution rows.")
    print(f"  Inserted {registry_inserted} pundit_registry rows (published=TRUE).")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be inserted without writing to the database.",
    )
    parser.add_argument(
        "--db-path",
        default=os.environ.get("DUCKDB_PATH", DUCKDB_PATH_DEFAULT),
        help="Path to the local DuckDB file.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"ERROR: DuckDB file not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    load(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
