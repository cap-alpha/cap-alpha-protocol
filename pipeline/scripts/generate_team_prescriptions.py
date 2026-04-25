import logging
from pathlib import Path
from src.strategic_engine import StrategicEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "data/nfl_data.db"
REPORT_PATH = "reports/nfl_team_strategic_audit_2025.md"


def main():
    engine = StrategicEngine(DB_PATH)
    engine.generate_audit_report(REPORT_PATH, year=2025)


if __name__ == "__main__":
    main()
