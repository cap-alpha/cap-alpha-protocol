"""
Weekly NFL Dead Money Pipeline with Year Parameterization

Orchestrates complete data pipeline:
1. Layer 1: Scrapers (Spotrac team caps, rankings + PFR rosters)
2. Layer 2: Staging (Raw → Staging)
3. Layer 3: Normalization (Staging → Processed)
4. Layer 4: dbt Transforms (Processed → Marts)
5. Layer 5: Data Quality Checks
6. Layer 6: Notebook & Reporting

Configuration:
- Schedule: Weekly (Monday 2 AM UTC)
- Year Parameter: Via Airflow Variable 'pipeline_year' (defaults to current year)
- Retries: 2 with 5-min delay
- Rate Limiting: External API pool with 1 slot
- Max Active: 1 run at a time

Usage:
    # Default (current year)
    airflow dags trigger pipeline
    
    # Specific year
    airflow dags trigger pipeline --conf '{"pipeline_year": 2025}'
"""

from datetime import datetime, timedelta
from pathlib import Path
from airflow import DAG
from airflow.models import Variable
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
VENV_PYTHON = str(PROJECT_ROOT / '.venv' / 'bin' / 'python')

def get_pipeline_year(context=None):
    """Get pipeline year from Airflow Variable or execution date"""
    try:
        # Try to get from Variable (set via --conf)
        year_var = Variable.get('pipeline_year', default_var=None)
        if year_var:
            return int(year_var)
    except Exception:
        pass
    
    # Default: current year
    return datetime.now().year

# ============================================================================
# DEFAULT ARGS
# ============================================================================
default_args = {
    'owner': 'data-eng',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'email_on_failure': True,
    'email': ['data-alerts@example.com'],
}

# ============================================================================
# DAG DEFINITION
# ============================================================================
with DAG(
    'pipeline',
    default_args=default_args,
    description='Daily NFL dead money pipeline (scrapers → dbt → validation → notebooks → LLM Predictions)',
    schedule='0 2 * * *',  # Every Day at 2 AM UTC (Trade Deadline coverage)
    start_date=datetime(2025, 1, 13),
    catchup=False,
    max_active_runs=1,
    tags=['nfl', 'dead-money', 'weekly', 'production'],
) as dag:
    
    # ========================================================================
    # DYNAMIC YEAR PARAMETER
    # ========================================================================
    def set_pipeline_year(**context):
        """Extract and log pipeline year"""
        year = get_pipeline_year(context)
        logger.info(f"Pipeline Year: {year}")
        context['task_instance'].xcom_push(key='pipeline_year', value=year)
        return year
    
    set_year = PythonOperator(
        task_id='set_pipeline_year',
        python_callable=set_pipeline_year,
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 1: SCRAPERS (Raw Data Collection)
    # ========================================================================
    
    # Generate curated contract dataset (idempotent - creates if missing)
    generate_curated_contracts = BashOperator(
        task_id='generate_curated_contracts',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/generate_2024_curated_full.py 2>&1 | tail -20',
        pool='external_api',
        pool_slots=1,
        dag=dag,
    )
    
    scrape_spotrac_team_caps = BashOperator(
        task_id='scrape_spotrac_team_caps',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} -c "import sys; sys.path.insert(0, \\"{PROJECT_ROOT}\\"); year = int(\\\"${{PIPELINE_YEAR}}\\\"); from src.spotrac_scraper_v2 import scrape_and_save_team_cap; scrape_and_save_team_cap(year)"',
        pool='external_api',
        pool_slots=1,
        env={'PIPELINE_YEAR': "{{ ti.xcom_pull(task_ids='set_pipeline_year') }}"},
        dag=dag,
    )
    
    scrape_pfr_rosters = BashOperator(
        task_id='scrape_pfr_rosters',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/historical_scraper.py --year "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        pool='external_api',
        pool_slots=1,
        dag=dag,
    )
    
    scrape_spotrac_player_rankings = BashOperator(
        task_id='scrape_spotrac_player_rankings',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} -c "import sys; sys.path.insert(0, \\"{PROJECT_ROOT}\\"); year = int(\\\"${{PIPELINE_YEAR}}\\\"); from src.spotrac_scraper_v2 import scrape_and_save_player_rankings; scrape_and_save_player_rankings(year)"',
        pool='external_api',
        pool_slots=1,
        env={'PIPELINE_YEAR': "{{ ti.xcom_pull(task_ids='set_pipeline_year') }}"},
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 2: DATA STAGING (Load Raw → Staging)
    # ========================================================================
    
    stage_spotrac_team_caps = BashOperator(
        task_id='stage_spotrac_team_caps',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/ingestion.py --source spotrac-team-cap --year "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        dag=dag,
    )
    
    stage_pfr_rosters = BashOperator(
        task_id='stage_pfr_rosters',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/ingestion.py --source pfr-rosters --year "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        dag=dag,
    )
    
    stage_spotrac_rankings = BashOperator(
        task_id='stage_spotrac_rankings',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/ingestion.py --source spotrac-rankings --year "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        dag=dag,
    )
    
    stage_spotrac_contracts = BashOperator(
        task_id='stage_spotrac_contracts',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/ingestion.py --source spotrac-contracts --year "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 3: NORMALIZATION (Staging → Processed)
    # ========================================================================
    
    normalize_data = BashOperator(
        task_id='normalize_data',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/normalization.py --year "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 3.5: LOAD TO DUCKDB (Processed → DuckDB for Marts)
    # ========================================================================
    
    load_to_warehouse = BashOperator(
        task_id='load_to_warehouse',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/load_to_duckdb.py "{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}"',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 4: DBT TRANSFORMS (Processed → Marts)
    # ========================================================================
    
    dbt_seed = BashOperator(
        task_id='dbt_seed',
        bash_command=f'cd {PROJECT_ROOT} && ./.venv/bin/dbt seed --project-dir ./dbt --profiles-dir ./dbt 2>&1 | tail -20',
        dag=dag,
    )
    
    dbt_run_staging = BashOperator(
        task_id='dbt_run_staging',
        bash_command=f'cd {PROJECT_ROOT} && ./.venv/bin/dbt run --project-dir ./dbt --profiles-dir ./dbt --select tag:staging 2>&1 | tail -20',
        dag=dag,
    )
    
    dbt_run_marts = BashOperator(
        task_id='dbt_run_marts',
        bash_command=f'cd {PROJECT_ROOT} && ./.venv/bin/dbt run --project-dir ./dbt --profiles-dir ./dbt --select tag:mart 2>&1 | tail -20',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 5: DATA QUALITY & VALIDATION
    # ========================================================================
    
    data_quality_checks = BashOperator(
        task_id='data_quality_checks',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} -m pytest tests/test_data_freshness.py tests/test_pipeline_idempotency.py -v --tb=short 2>&1 | tail -30',
        dag=dag,
    )
    
    validate_dead_money = BashOperator(
        task_id='validate_dead_money',
        bash_command=f'cd {PROJECT_ROOT} && make validate 2>&1 | tail -20',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 6: HYPERSCALE INTELLIGENCE (NEW)
    # ========================================================================
    
    run_feature_factory = BashOperator(
        task_id='run_feature_factory',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/feature_factory.py 2>&1 | tail -20',
        dag=dag,
    )
    
    train_risk_model = BashOperator(
        task_id='train_risk_model',
        bash_command=f'cd {PROJECT_ROOT} && {VENV_PYTHON} src/train_model.py 2>&1 | tail -20',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 7: NOTEBOOKS & REPORTING
    # ========================================================================
    
    run_salary_analysis_notebook = BashOperator(
        task_id='run_salary_analysis_notebook',
        bash_command=f'cd {PROJECT_ROOT} && ./.venv/bin/papermill notebooks/09_salary_distribution_analysis.ipynb notebooks/outputs/09_salary_distribution_analysis_{{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}}_{{{{ ds }}}}.ipynb -p data_year {{{{ ti.xcom_pull(task_ids=\'set_pipeline_year\') }}}} 2>&1 | tail -20',
        dag=dag,
    )
    
    # ========================================================================
    # LAYER 8: AUTOMATED PUBLICATION (PROOF OF ALPHA)
    # ========================================================================
    
    generate_alpha_payload = BashOperator(
        task_id='generate_alpha_payload',
        bash_command=f'cd {PROJECT_ROOT} && export GEMINI_API_KEY=$(grep GEMINI_API_KEY web/.env.local | cut -d "=" -f 2) && {VENV_PYTHON} scripts/generate_proof_of_alpha.py 2>&1 | tail -20',
        dag=dag,
    )
    
    sync_alpha_to_postgres = BashOperator(
        task_id='sync_alpha_to_postgres',
        bash_command=f'cd {PROJECT_ROOT}/web && npm run db:alpha-sync 2>&1 | tail -20',
        dag=dag,
    )
    
    # ========================================================================
    # TASK DEPENDENCIES (DAG GRAPH)
    # ========================================================================
    
    # Layer 1 (Scrapers) - parallel after year is set
    # generate_curated_contracts runs first (idempotent, creates CSV if missing)
    # Then run optional live scrapers in parallel (use generated contracts as fallback)
    set_year >> generate_curated_contracts
    set_year >> [scrape_spotrac_team_caps, scrape_pfr_rosters, scrape_spotrac_player_rankings]
    
    # Layer 2 (Staging) - depends on respective scrapers + curated contracts
    scrape_spotrac_team_caps >> stage_spotrac_team_caps
    scrape_pfr_rosters >> stage_pfr_rosters
    scrape_spotrac_player_rankings >> stage_spotrac_rankings
    generate_curated_contracts >> stage_spotrac_contracts  # Use generated contracts as primary source
    
    # Layer 3 (Normalization) - depends on all staging
    [stage_spotrac_team_caps, stage_pfr_rosters, stage_spotrac_rankings, stage_spotrac_contracts] >> normalize_data
    
    # Layer 3.5 (DuckDB Loading) - depends on normalization
    normalize_data >> load_to_warehouse
    
    # Layer 4 (dbt Transforms) - depends on DuckDB loading (can skip dbt_seed if using direct load)
    load_to_warehouse >> dbt_seed >> dbt_run_staging >> dbt_run_marts
    
    # Layer 5 (Validation) - depends on dbt marts
    dbt_run_marts >> [data_quality_checks, validate_dead_money]
    
    # Layer 6 (Hyperscale Intelligence) - depends on validation
    [data_quality_checks, validate_dead_money] >> run_feature_factory >> train_risk_model
    
    # Layer 7 (Notebooks)
    train_risk_model >> run_salary_analysis_notebook
    
    # Layer 8 (Automated Publication via Gemini & Vercel Postgres)
    run_salary_analysis_notebook >> generate_alpha_payload >> sync_alpha_to_postgres
