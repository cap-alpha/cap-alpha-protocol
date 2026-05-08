"""
Political prediction resolution — Phase A stub (Issue #683).

Fetches PENDING predictions with sport='politics' and logs the count.
Phase B will add Congress.gov (legislation/appointment) and Ballotpedia
(election_outcome) adapters.
"""

import logging
from typing import Optional

from src.db_manager import DBManager
from src.resolution_engine import get_pending_predictions

logger = logging.getLogger(__name__)


def resolve_pending_politics(
    dry_run: bool = False,
    db: Optional[DBManager] = None,
) -> list:
    """
    Fetch and log all PENDING political predictions.
    Returns an empty list until Phase B adapters are implemented.
    """
    predictions = get_pending_predictions(sport="politics", db=db)
    count = (
        len(predictions) if hasattr(predictions, "__len__") else predictions.shape[0]
    )
    logger.info(
        f"[politics resolver] {count} PENDING claims found — "
        "resolution adapters not yet implemented (Phase B: Congress.gov + Ballotpedia)"
    )
    return []
