"""
News -> claim retrieval funnel — Stage 1 (candidate generation).

Issue #1133 (#1129 spec §1 "Architecture — two-stage retrieval funnel",
Decision 8). This package builds ONLY Stage 1: local CPU embeddings of
claims + incoming news events, brute-force cosine top-K candidate
generation. Stage 2 (LLM adjudication of the top-K candidates) is out of
scope here and lives in `src.resolvers.llm_judge_silver` (being enhanced in
parallel — not touched by this package).

Modules:
    embed.py        — local CPU text embedding (fastembed / bge-small-en-v1.5).
    claim_index.py  — build + query the claim embedding index
                       (silver_v2_claims.claim_embedding, migration 031).
"""
