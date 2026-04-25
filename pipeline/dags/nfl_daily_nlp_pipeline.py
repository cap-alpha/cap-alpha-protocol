"""
Daily NFL NLP Pipeline

Orchestrates the daily text-based intelligence gathering:
1. Ingest NFLVerse Injuries (Differential updates)
2. Ingest breaking news/rumors via Google News RSS
3. Generate Gemini Sentiment Embeddings for all high-value targets

Configuration:
- Schedule: Daily (12:00 PM UTC)
- Retries: 2 with 5-min delay
- Max Active: 1 run at a time
"""

from datetime import datetime, timedelta
from pathlib import Path
from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ["data-alerts@example.com"],
}

# ============================================================================
# DAG DEFINITION
# ============================================================================
with DAG(
    "nfl_daily_nlp_pipeline",
    default_args=default_args,
    description="Daily intelligence scraping and embedding generation",
    schedule="0 12 * * *",  # Every Day at 12 PM UTC
    start_date=datetime(2025, 1, 13),
    catchup=False,
    max_active_runs=1,
    tags=["nfl", "nlp", "daily", "sentiment"],
) as dag:

    # 1. Update latest injuries
    ingest_injuries = BashOperator(
        task_id="ingest_injuries",
        bash_command=f"cd {PROJECT_ROOT} && {VENV_PYTHON} scripts/ingest_nflverse_injuries.py 2>&1 | tail -20",
        dag=dag,
    )

    # 2. Scrape live news, extract AI intelligence, and inject to MotherDuck raw_media_sentiment
    ingest_news = BashOperator(
        task_id="ingest_news",
        bash_command=f'cd {PROJECT_ROOT} && export GEMINI_API_KEY=$(cat ../web/.env.local | grep GEMINI_API_KEY | cut -d "=" -f 2) && export MOTHERDUCK_TOKEN=$(cat ../web/.env.local | grep MOTHERDUCK_TOKEN | cut -d "=" -f 2) && {VENV_PYTHON} scripts/hydrate_live_news.py 2>&1 | tail -20',
        dag=dag,
    )

    # 3. Generate embeddings
    generate_features = BashOperator(
        task_id="generate_sentiment_features",
        bash_command=f'cd {PROJECT_ROOT} && export GEMINI_API_KEY=$(cat ../web/.env.local | grep GEMINI_API_KEY | cut -d "=" -f 2) && {VENV_PYTHON} src/generate_sentiment_features.py 2>&1 | tail -20',
        dag=dag,
    )

    # 4. Generate Media Lag Consensus (The missing step)
    analyze_media_lag = BashOperator(
        task_id="analyze_media_lag",
        bash_command=f'cd {PROJECT_ROOT} && export GEMINI_API_KEY=$(cat ../web/.env.local | grep GEMINI_API_KEY | cut -d "=" -f 2) && export MOTHERDUCK_TOKEN=$(cat ../web/.env.local | grep MOTHERDUCK_TOKEN | cut -d "=" -f 2) && {VENV_PYTHON} scripts/media_lag_analyzer.py 2>&1 | tail -20',
        dag=dag,
    )

    # DAG Dependencies
    [ingest_injuries, ingest_news] >> generate_features >> analyze_media_lag
