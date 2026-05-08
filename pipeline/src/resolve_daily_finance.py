"""
Finance/business prediction resolution — Phase A stub (Issue #683).

Fetches PENDING predictions with sport='finance' and logs the count.
Phase B will add FRED API (rate_decision, macro_indicator), yfinance
(price_target), and SEC EDGAR (earnings_prediction, merger_acquisition)
adapters.
"""

import logging
from typing import Optional

from src.db_manager import DBManager
from src.resolution_engine import get_pending_predictions

logger = logging.getLogger(__name__)


def resolve_pending_finance(
    dry_run: bool = False,
    db: Optional[DBManager] = None,
) -> list:
    """
    Fetch and log all PENDING finance/business predictions.
    Returns an empty list until Phase B adapters are implemented.
    """
    predictions = get_pending_predictions(sport="finance", db=db)
    count = (
        len(predictions) if hasattr(predictions, "__len__") else predictions.shape[0]
    )
    logger.info(
        f"[finance resolver] {count} PENDING claims found — "
        "resolution adapters not yet implemented (Phase B: FRED + yfinance + SEC EDGAR)"
    )
    return []
