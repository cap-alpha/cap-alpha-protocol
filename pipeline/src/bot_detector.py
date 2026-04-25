"""
Bot & Astroturfing Detection (SP23-1, GH-#83)

Filters synthetic articles and highly repetitive NLP phrasing that signals a
coordinated attack before content reaches the assertion extractor.

Detection signals:
  1. N-gram Jaccard similarity  — content overlap with recent articles in the
     same window identifies copy-paste coordination.
  2. Template phrase fingerprint — known astroturfing boilerplate (repetitive
     openers, synthetic urgency markers).
  3. Duplicate sentence ratio   — fraction of sentences that are exact repeats
     across recent items.
  4. Micro-burst detection      — unusually high publish rate from one source
     within a short rolling window.

Verdicts:
  CLEAN      — no signals triggered; safe to ingest
  SUSPICIOUS — one or more weak signals; ingest but flag for review
  BOT        — high-confidence synthetic content; quarantine / skip
"""

import hashlib
import logging
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (all tunable)
# ---------------------------------------------------------------------------

# Jaccard similarity of 2-grams above this → coordinated (BOT if >HARD, else SUSPICIOUS)
NGRAM_SOFT_THRESHOLD = 0.55
NGRAM_HARD_THRESHOLD = 0.80

# Fraction of sentences duplicated across the window → suspicious
DUPLICATE_SENTENCE_SOFT = 0.35
DUPLICATE_SENTENCE_HARD = 0.70

# Rolling window used for all recency checks
WINDOW_MINUTES = 60

# How many recent articles to keep in the similarity window per source type
MAX_WINDOW_ARTICLES = 200

# If a single source_id publishes this many articles within WINDOW_MINUTES → suspicious
SOURCE_BURST_SOFT = 15
SOURCE_BURST_HARD = 30

# Minimum text length (chars) to bother running detection — skip stubs
MIN_TEXT_LENGTH = 80

# ---------------------------------------------------------------------------
# Known astroturfing template phrases (case-insensitive regex anchors)
# ---------------------------------------------------------------------------

_TEMPLATE_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^breaking\s*:",
        r"exclusive\s*:",
        r"sources\s+tell\s+us",
        r"according\s+to\s+multiple\s+sources",
        r"i\s+can\s+confirm\s+that",
        r"just\s+in\s*:",
        r"developing\s+story\s*:",
        r"learn\s+more\s+at\s+\S+",
        r"click\s+here\s+to\s+read",
        r"as\s+per\s+our\s+sources",
        # Highly formulaic openers common in machine-generated sports "articles"
        r"^the\s+\w+\s+have\s+reportedly\s+(signed|traded|released)",
        r"^reports?\s+suggest\s+that",
        r"^it\s+has\s+been\s+confirmed\s+that",
    ]
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DetectionSignal:
    name: str
    value: float
    threshold: float
    severity: str  # soft | hard


@dataclass
class BotDetectionResult:
    verdict: str  # CLEAN | SUSPICIOUS | BOT
    confidence: float  # 0.0 – 1.0
    signals: List[DetectionSignal] = field(default_factory=list)
    reason: str = ""

    @property
    def is_clean(self) -> bool:
        return self.verdict == "CLEAN"

    @property
    def should_quarantine(self) -> bool:
        return self.verdict == "BOT"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokenize_ngrams(text: str, n: int = 2) -> Set[str]:
    """Returns the set of lowercased n-grams from text tokens."""
    tokens = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _sentence_hashes(text: str) -> List[str]:
    """Return MD5 hashes for each sentence (normalised to lower-stripped)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [
        hashlib.md5(s.lower().strip().encode()).hexdigest()
        for s in sentences
        if len(s.strip()) > 20
    ]


def _count_template_matches(text: str) -> int:
    count = 0
    for pattern in _TEMPLATE_PATTERNS:
        if pattern.search(text):
            count += 1
    return count


# ---------------------------------------------------------------------------
# BotDetector
# ---------------------------------------------------------------------------


class BotDetector:
    """
    Stateful detector that maintains a rolling window of recent article
    n-gram fingerprints and sentence hashes to identify copy-paste campaigns.

    Intended to be instantiated once and reused across all articles in a run.
    Thread-safety: not thread-safe; run in a single process context.
    """

    def __init__(
        self,
        window_minutes: int = WINDOW_MINUTES,
        max_window_articles: int = MAX_WINDOW_ARTICLES,
    ):
        self._window_minutes = window_minutes
        self._max_window = max_window_articles

        # Deque of (published_at, ngram_set, sentence_hash_set)
        self._article_window: Deque[Tuple[datetime, Set[str], Set[str]]] = deque(
            maxlen=max_window_articles
        )

        # source_id → deque of published_at timestamps
        self._source_timestamps: Dict[str, Deque[datetime]] = {}

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def _prune_window(self, now: datetime) -> None:
        """Drop entries older than the rolling window."""
        cutoff = now - timedelta(minutes=self._window_minutes)
        while self._article_window and self._article_window[0][0] < cutoff:
            self._article_window.popleft()

    def _prune_source(self, source_id: str, now: datetime) -> None:
        q = self._source_timestamps.setdefault(source_id, deque())
        cutoff = now - timedelta(minutes=self._window_minutes)
        while q and q[0] < cutoff:
            q.popleft()

    # ------------------------------------------------------------------
    # Main assess API
    # ------------------------------------------------------------------

    def assess(
        self,
        text: str,
        source_id: str = "unknown",
        published_at: Optional[datetime] = None,
    ) -> BotDetectionResult:
        """
        Assess a single article for bot/astroturfing signals.

        Parameters
        ----------
        text        : Raw article text.
        source_id   : Source identifier (e.g. 'espn_nfl') for burst detection.
        published_at: Publication timestamp; defaults to utcnow() if omitted.

        Returns
        -------
        BotDetectionResult with verdict, confidence, and per-signal breakdown.
        """
        if not text or len(text) < MIN_TEXT_LENGTH:
            return BotDetectionResult(
                verdict="CLEAN",
                confidence=0.0,
                reason="Text too short for analysis",
            )

        now = published_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        self._prune_window(now)
        self._prune_source(source_id, now)

        signals: List[DetectionSignal] = []

        # ── 1. N-gram similarity ──────────────────────────────────────
        article_ngrams = _tokenize_ngrams(text, n=2)
        max_sim = 0.0
        for _, window_ngrams, _ in self._article_window:
            sim = _jaccard(article_ngrams, window_ngrams)
            if sim > max_sim:
                max_sim = sim

        if max_sim >= NGRAM_SOFT_THRESHOLD:
            signals.append(
                DetectionSignal(
                    name="ngram_similarity",
                    value=round(max_sim, 3),
                    threshold=NGRAM_SOFT_THRESHOLD,
                    severity="hard" if max_sim >= NGRAM_HARD_THRESHOLD else "soft",
                )
            )

        # ── 2. Template phrase fingerprint ───────────────────────────
        template_hits = _count_template_matches(text)
        if template_hits >= 2:
            signals.append(
                DetectionSignal(
                    name="template_phrases",
                    value=float(template_hits),
                    threshold=2.0,
                    severity="hard" if template_hits >= 4 else "soft",
                )
            )

        # ── 3. Duplicate sentence ratio ──────────────────────────────
        my_hashes = set(_sentence_hashes(text))
        all_prior_hashes: Set[str] = set()
        for _, _, sentence_hashes in self._article_window:
            all_prior_hashes |= sentence_hashes

        if my_hashes:
            dup_ratio = len(my_hashes & all_prior_hashes) / len(my_hashes)
            if dup_ratio >= DUPLICATE_SENTENCE_SOFT:
                signals.append(
                    DetectionSignal(
                        name="duplicate_sentences",
                        value=round(dup_ratio, 3),
                        threshold=DUPLICATE_SENTENCE_SOFT,
                        severity=(
                            "hard" if dup_ratio >= DUPLICATE_SENTENCE_HARD else "soft"
                        ),
                    )
                )
        else:
            dup_ratio = 0.0

        # ── 4. Source micro-burst ─────────────────────────────────────
        self._source_timestamps[source_id].append(now)
        burst_count = len(self._source_timestamps[source_id])
        if burst_count >= SOURCE_BURST_SOFT:
            signals.append(
                DetectionSignal(
                    name="source_burst",
                    value=float(burst_count),
                    threshold=float(SOURCE_BURST_SOFT),
                    severity="hard" if burst_count >= SOURCE_BURST_HARD else "soft",
                )
            )

        # ── Verdict logic ─────────────────────────────────────────────
        hard_signals = [s for s in signals if s.severity == "hard"]
        soft_signals = [s for s in signals if s.severity == "soft"]

        if hard_signals:
            verdict = "BOT"
            confidence = min(0.95, 0.7 + 0.1 * len(hard_signals))
        elif len(soft_signals) >= 2:
            verdict = "SUSPICIOUS"
            confidence = min(0.65, 0.4 + 0.1 * len(soft_signals))
        elif soft_signals:
            verdict = "SUSPICIOUS"
            confidence = 0.35
        else:
            verdict = "CLEAN"
            confidence = 0.0

        reason_parts = [f"{s.name}={s.value:.3g}" for s in signals]
        reason = "; ".join(reason_parts) if reason_parts else "no signals"

        # Register article into the rolling window AFTER assessment
        self._article_window.append((now, article_ngrams, my_hashes))

        logger.debug(
            f"[bot_detector] source={source_id} verdict={verdict} "
            f"confidence={confidence:.2f} signals={reason}"
        )

        return BotDetectionResult(
            verdict=verdict,
            confidence=confidence,
            signals=signals,
            reason=reason,
        )
