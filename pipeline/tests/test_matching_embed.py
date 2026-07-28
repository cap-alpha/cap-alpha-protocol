"""
Tests for pipeline/src/matching/embed.py (Issue #1133 — Stage-1 retrieval
funnel, local CPU embeddings).

`fastembed` is never imported here: `_get_model()` is monkeypatched with a
deterministic fake embedder so these tests exercise `embed_texts()`'s
contract (empty-input short-circuit, determinism, native-float output,
model caching) without downloading or running the real ONNX model. This
mirrors the task's "structure so unit tests can inject fake embeddings"
requirement.
"""

from __future__ import annotations

import pytest

from src.matching import embed as embed_module
from src.matching.embed import DEFAULT_MODEL_ID, embed_texts


class _FakeEmbedder:
    """Deterministic fake: each text maps to a fixed-length vector derived
    from a simple hash of its characters. Not semantically meaningful --
    only needs to be a pure function of the input text for these tests."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        for text in texts:
            seed = sum(ord(c) for c in text) or 1
            yield [((seed * (i + 1)) % 97) / 97.0 for i in range(4)]


@pytest.fixture
def fake_embedder(monkeypatch):
    embedder = _FakeEmbedder()
    monkeypatch.setattr(embed_module, "_get_model", lambda model_id: embedder)
    return embedder


class TestEmbedTextsEmptyInput:
    def test_empty_list_returns_empty_list_without_loading_model(self, monkeypatch):
        def _boom(model_id):
            raise AssertionError("_get_model must not be called for empty input")

        monkeypatch.setattr(embed_module, "_get_model", _boom)
        assert embed_texts([]) == []


class TestEmbedTextsDeterminism:
    def test_same_text_yields_same_vector(self, fake_embedder):
        v1 = embed_texts(["Mahomes will win MVP"])
        v2 = embed_texts(["Mahomes will win MVP"])
        assert v1 == v2

    def test_different_text_yields_different_vector(self, fake_embedder):
        v1 = embed_texts(["Mahomes will win MVP"])
        v2 = embed_texts(["Chiefs will miss the playoffs"])
        assert v1 != v2

    def test_batch_order_preserved(self, fake_embedder):
        texts = ["claim A", "claim B", "claim C"]
        batch = embed_texts(texts)
        singles = [embed_texts([t])[0] for t in texts]
        assert batch == singles


class TestEmbedTextsOutputShape:
    def test_returns_list_of_lists(self, fake_embedder):
        result = embed_texts(["one", "two"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(v, list) for v in result)

    def test_elements_are_native_python_floats(self, fake_embedder):
        result = embed_texts(["some claim text"])
        assert all(isinstance(x, float) for x in result[0])

    def test_default_model_id_used_when_not_specified(self, fake_embedder, monkeypatch):
        captured = {}

        def _get_model(model_id):
            captured["model_id"] = model_id
            return fake_embedder

        monkeypatch.setattr(embed_module, "_get_model", _get_model)
        embed_texts(["x"])
        assert captured["model_id"] == DEFAULT_MODEL_ID

    def test_explicit_model_id_passed_through(self, fake_embedder, monkeypatch):
        captured = {}

        def _get_model(model_id):
            captured["model_id"] = model_id
            return fake_embedder

        monkeypatch.setattr(embed_module, "_get_model", _get_model)
        embed_texts(["x"], model_id="some-other-model")
        assert captured["model_id"] == "some-other-model"


class TestEmbedTextsAcceptsPlainListVectors:
    """embed_texts() must not assume numpy arrays -- a fake embedder
    yielding plain Python float lists (as this module's own test double
    does) must work identically to a real fastembed model yielding numpy
    arrays with a .tolist() method."""

    def test_works_with_plain_list_vectors(self, monkeypatch):
        class _PlainListEmbedder:
            def embed(self, texts):
                return [[1.0, 2.0, 3.0] for _ in texts]

        monkeypatch.setattr(
            embed_module, "_get_model", lambda model_id: _PlainListEmbedder()
        )
        result = embed_texts(["a", "b"])
        assert result == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]


class TestGetModelCaching:
    def test_get_model_is_lru_cached(self):
        """_get_model itself (not embed_texts) is decorated with
        functools.lru_cache -- verify the cache_info API is present, i.e.
        repeated calls with the same model_id reuse one loaded instance
        rather than reloading fastembed each time."""
        assert hasattr(embed_module._get_model, "cache_info")
        assert hasattr(embed_module._get_model, "cache_clear")
