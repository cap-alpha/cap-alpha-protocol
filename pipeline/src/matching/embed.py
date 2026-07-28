"""
Local CPU text embedding for the news->claim retrieval funnel Stage 1 --
Issue #1133 (#1129 spec §1: "Stage 1 - retrieval (candidate generation) ...
Local, CPU-only (bge-small/nomic-embed-text), zero per-call cost").

Model choice: BAAI/bge-small-en-v1.5, served via `fastembed`
(https://github.com/qdrant/fastembed).

Why this model + library, specifically:
  - `fastembed` runs on ONNX Runtime -- no torch/GPU dependency, small
    install footprint, fast CPU inference. Matches the spec's explicit
    "Local, CPU-only ... zero per-call cost" and "Runs even on ephemeral
    ubuntu-latest (no GPU)" requirements verbatim.
  - `BAAI/bge-small-en-v1.5` is fastembed's default general-purpose English
    model: 384-dim, ~130MB on disk, strong MTEB retrieval scores for its
    size class. Good accuracy/latency tradeoff for a Stage-1 recall funnel
    where Stage 2 (LLM adjudication) is the precision backstop -- Stage 1
    only needs to keep the true match inside the top-K, not rank it #1.
  - #1129 Decision 8 explicitly lists `bge-small`/`nomic-embed-text` as the
    two candidates under consideration; bge-small was picked here for the
    smaller footprint and because fastembed bundles ONNX weights for it
    directly -- no separate Ollama dependency for the retrieval stage.
    Ollama is reserved for Stage-2 adjudication per the spec's tiered
    inference decision, kept on its own swappable seam.

Every function here is pure w.r.t. I/O beyond loading the (cached) local
model -- no DB, no network calls beyond the one-time model download that
`fastembed` itself manages and caches on disk after first run.
`_get_model()` is the sole seam that touches `fastembed`; unit tests
monkeypatch it to inject a deterministic fake embedder so the real ONNX
model never has to load in CI (fastembed is not installed in this
environment's venv at authoring time -- the import is deliberately lazy,
see `_get_model()`'s docstring).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol, Sequence

logger = logging.getLogger(__name__)

# fastembed's identifier for BAAI/bge-small-en-v1.5. Also the `model_id`
# value written to silver_v2_claims.claim_embedding.model_id -- re-pointing
# this at a different model automatically causes
# claim_index.build_claim_embeddings() to treat every active claim as
# unembedded for the new model_id (old rows are left alone, not
# overwritten -- see claim_index.py's module docstring).
DEFAULT_MODEL_ID = "BAAI/bge-small-en-v1.5"

# Output dimensionality of DEFAULT_MODEL_ID. Documented for callers/tests
# that want a sanity-check shape without loading the model; not enforced
# at runtime here -- fastembed itself is the source of truth for shape.
EMBEDDING_DIM = 384


class _Embedder(Protocol):
    """Minimal shape `_get_model()` must return. fastembed's `TextEmbedding`
    satisfies this today; a fake test double only needs to satisfy this --
    `embed()` takes an iterable of strings and returns an iterable of
    per-text vectors (numpy arrays or plain float sequences both work,
    `embed_texts()` normalises either)."""

    def embed(self, texts: Sequence[str]): ...


@lru_cache(maxsize=4)
def _get_model(model_id: str) -> _Embedder:
    """
    Load (and cache) the fastembed model for `model_id`.

    Cached via lru_cache so repeated `embed_texts()` calls within one
    process (e.g. once per claim-index build, once per retrieval call)
    reuse the same loaded model instead of re-reading ONNX weights from
    disk each time. `maxsize=4` is generous headroom for "old model_id
    still cached mid-migration to a new one" without unbounded growth --
    this process is not expected to churn through more than a handful of
    embedding models in one run.

    Imports fastembed lazily, inside the function body: keeps
    `import src.matching.embed` cheap and dependency-free for callers that
    only need the module's constants (e.g. DEFAULT_MODEL_ID), and lets
    tests run without fastembed installed at all by monkeypatching this
    function directly -- the exact seam `embed_texts()`'s docstring
    describes.
    """
    from fastembed import TextEmbedding  # local import -- see docstring

    logger.info("matching.embed: loading fastembed model %s", model_id)
    return TextEmbedding(model_name=model_id)


def embed_texts(
    texts: Sequence[str], model_id: str = DEFAULT_MODEL_ID
) -> list[list[float]]:
    """
    Embed a batch of texts into dense vectors.

    Deterministic: the same text always yields the same vector for a given
    model_id (fastembed's ONNX inference has no sampling/randomness, and
    `_get_model()` returns the same cached model instance across calls).

    Returns `[]` for `[]` input without loading the model at all -- lets
    callers pass through empty batches (e.g. "no new claims to embed")
    without paying model-load cost.

    Returns a plain `list[list[float]]`, not numpy arrays: callers that
    don't otherwise need numpy (e.g. a caller just writing rows to
    BigQuery) don't have to import it, and the return value is directly
    JSON/BigQuery ARRAY<FLOAT64>-serializable. Each element is coerced via
    `float(x)` rather than relying on `.tolist()`, so this also accepts a
    test double whose `embed()` yields plain Python float lists instead of
    numpy arrays.
    """
    if not texts:
        return []
    model = _get_model(model_id)
    return [[float(x) for x in vector] for vector in model.embed(list(texts))]
