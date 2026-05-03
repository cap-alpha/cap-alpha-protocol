"""
Tests for cross-provider model validation (Issue #592).

These tests would have caught the production bug where
LLM_EXTRACTION_PROVIDER=gemini was deployed while llm_config.yaml
still contained model: llama3.1:8b — causing zero extraction for days
with CI showing green.
"""

import pytest

from src.llm_provider import (
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    _validate_provider_model,
    get_provider,
)

# ---------------------------------------------------------------------------
# _validate_provider_model unit tests
# ---------------------------------------------------------------------------

GEMINI_VALID_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
]

OLLAMA_MODELS = [
    "llama3.1:8b",
    "llama3.1:70b",
    "qwen2.5:32b",
    "mistral:7b",
]

CLAUDE_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-7",
]

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o1-preview",
    "o3-mini",
]


class TestValidateProviderModel:
    """Direct unit tests for _validate_provider_model."""

    @pytest.mark.parametrize("model", GEMINI_VALID_MODELS)
    def test_gemini_accepts_gemini_models(self, model):
        # Should not raise
        _validate_provider_model("gemini", model)

    @pytest.mark.parametrize("model", GEMINI_VALID_MODELS)
    def test_gemini_flash_alias_accepts_gemini_models(self, model):
        _validate_provider_model("gemini-flash", model)

    @pytest.mark.parametrize("ollama_model", OLLAMA_MODELS)
    def test_gemini_rejects_ollama_models(self, ollama_model):
        with pytest.raises(ValueError, match="gemini-\\*"):
            _validate_provider_model("gemini", ollama_model)

    @pytest.mark.parametrize("claude_model", CLAUDE_MODELS)
    def test_gemini_rejects_claude_models(self, claude_model):
        with pytest.raises(ValueError, match="gemini-\\*"):
            _validate_provider_model("gemini", claude_model)

    @pytest.mark.parametrize("model", CLAUDE_MODELS)
    def test_claude_accepts_claude_models(self, model):
        _validate_provider_model("claude", model)

    @pytest.mark.parametrize("bad_model", OLLAMA_MODELS + GEMINI_VALID_MODELS)
    def test_claude_rejects_non_claude_models(self, bad_model):
        with pytest.raises(ValueError, match="claude-\\*"):
            _validate_provider_model("claude", bad_model)

    @pytest.mark.parametrize("model", OPENAI_MODELS)
    def test_openai_accepts_openai_models(self, model):
        _validate_provider_model("openai", model)

    @pytest.mark.parametrize("bad_model", OLLAMA_MODELS + GEMINI_VALID_MODELS)
    def test_openai_rejects_non_openai_models(self, bad_model):
        with pytest.raises(ValueError, match="gpt-\\*"):
            _validate_provider_model("openai", bad_model)

    @pytest.mark.parametrize(
        "model", OLLAMA_MODELS + GEMINI_VALID_MODELS + CLAUDE_MODELS
    )
    def test_ollama_accepts_any_model(self, model):
        # Ollama is unrestricted
        _validate_provider_model("ollama", model)


# ---------------------------------------------------------------------------
# get_provider integration tests via env var overrides
# ---------------------------------------------------------------------------


class TestGeminiProviderConfig:
    """test_gemini_provider_uses_gemini_model — env override path."""

    def test_gemini_provider_uses_gemini_model(self, monkeypatch):
        """When LLM_EXTRACTION_PROVIDER=gemini, the resolved model must be gemini-*."""
        monkeypatch.setenv("LLM_EXTRACTION_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_EXTRACTION_MODEL", "gemini-2.5-flash")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")

        config = {"extraction": {"provider": "gemini", "model": "gemini-2.5-flash"}}

        # Mock the google.genai import so we don't need the real SDK
        import sys
        from unittest.mock import MagicMock

        fake_genai = MagicMock()
        fake_types = MagicMock()
        sys.modules.setdefault("google", MagicMock())
        sys.modules["google.genai"] = fake_genai
        sys.modules["google.genai.types"] = fake_types

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.llm_provider.GeminiProvider.__init__",
                lambda self, model, **kw: setattr(self, "model", model) or None,
            )
            provider = get_provider("extraction", config=config)

        assert isinstance(provider, GeminiProvider)
        assert provider.model in {
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
        }, f"Expected a gemini-* model, got {provider.model!r}"


class TestOllamaProviderConfig:
    def test_ollama_provider_uses_ollama_model(self, monkeypatch):
        """When LLM_EXTRACTION_PROVIDER=ollama, resolved model is a valid Ollama model."""
        monkeypatch.setenv("LLM_EXTRACTION_PROVIDER", "ollama")
        monkeypatch.delenv("LLM_EXTRACTION_MODEL", raising=False)

        config = {"extraction": {"provider": "ollama", "model": "qwen2.5:32b"}}
        provider = get_provider("extraction", config=config)

        assert isinstance(provider, OllamaProvider)
        # Ollama models should not contain '/' (Gemini uses 'models/gemini-...' paths)
        assert "/" not in provider.model
        # Should not be a Gemini model
        assert not provider.model.startswith("gemini-")
        # Should not be a Claude model
        assert not provider.model.startswith("claude-")


class TestClaudeProviderConfig:
    def test_claude_provider_uses_claude_model(self, monkeypatch):
        """When LLM_EXTRACTION_PROVIDER=claude, resolved model must start with claude-."""
        monkeypatch.setenv("LLM_EXTRACTION_PROVIDER", "claude")
        monkeypatch.setenv("LLM_EXTRACTION_MODEL", "claude-sonnet-4-20250514")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

        config = {
            "extraction": {
                "provider": "claude",
                "model": "claude-sonnet-4-20250514",
            }
        }

        from unittest.mock import MagicMock
        import sys

        sys.modules.setdefault("anthropic", MagicMock())

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.llm_provider.ClaudeProvider.__init__",
                lambda self, model, **kw: setattr(self, "model", model) or None,
            )
            provider = get_provider("extraction", config=config)

        assert isinstance(provider, ClaudeProvider)
        assert provider.model.startswith("claude-"), (
            f"Expected claude-* model, got {provider.model!r}"
        )


class TestModelEnvVarOverride:
    def test_model_env_var_overrides_config(self, monkeypatch):
        """LLM_EXTRACTION_MODEL env var takes precedence over llm_config.yaml."""
        monkeypatch.setenv("LLM_EXTRACTION_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_EXTRACTION_MODEL", "gemini-2.5-flash")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")

        # Config says a different gemini model
        config = {
            "extraction": {
                "provider": "gemini",
                "model": "gemini-1.5-pro",
            }
        }

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.llm_provider.GeminiProvider.__init__",
                lambda self, model, **kw: setattr(self, "model", model) or None,
            )
            provider = get_provider("extraction", config=config)

        # env var must win
        assert provider.model == "gemini-2.5-flash"


class TestOllamaModelRejectedByGeminiProvider:
    def test_ollama_model_rejected_by_gemini_provider(self, monkeypatch):
        """Providing an Ollama model name to the Gemini provider must raise ValueError.

        This is the exact scenario that caused #592: LLM_EXTRACTION_PROVIDER=gemini
        but config had model: llama3.1:8b.
        """
        monkeypatch.setenv("LLM_EXTRACTION_PROVIDER", "gemini")
        monkeypatch.setenv("LLM_EXTRACTION_MODEL", "llama3.1:8b")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")

        config = {
            "extraction": {
                "provider": "gemini",
                "model": "llama3.1:8b",
            }
        }

        with pytest.raises(ValueError, match="gemini-\\*"):
            get_provider("extraction", config=config)


class TestCrossProviderModelLeak:
    def test_cross_provider_model_leak_detected(self, monkeypatch):
        """The production bug: provider=gemini, config model=llama3.1:8b (no env override).

        Previously: silently called Gemini API with 'llama3.1:8b' model name → 404 on
        every item → zero claims for days, CI green.

        After this fix: ValueError is raised at provider construction time.
        """
        monkeypatch.setenv("LLM_EXTRACTION_PROVIDER", "gemini")
        monkeypatch.delenv("LLM_EXTRACTION_MODEL", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")

        # This mirrors the exact state at time of the #592 incident:
        # CI sets provider=gemini via env, but config file still has Ollama model.
        config = {
            "extraction": {
                "provider": "ollama",  # irrelevant — env var wins for provider
                "model": "llama3.1:8b",  # the stale Ollama model name
            }
        }

        with pytest.raises(ValueError) as exc_info:
            get_provider("extraction", config=config)

        error_msg = str(exc_info.value)
        assert "llama3.1:8b" in error_msg, "Error must name the bad model"
        assert "gemini-" in error_msg.lower() or "Gemini" in error_msg, (
            "Error must explain what a valid model looks like"
        )
