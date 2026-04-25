"""
Unit tests for LLM Provider abstraction (Issue #178/#179).
All tests mock HTTP/API calls — no real LLM required.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from src.llm_provider import (PREDICTION_SCHEMA_DESCRIPTION, GeminiProvider,
                              OllamaProvider, _FallbackProvider, get_provider,
                              load_llm_config)

# ---------------------------------------------------------------------------
# _parse_json_response (shared helper)
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def setup_method(self):
        self.provider = OllamaProvider.__new__(OllamaProvider)
        self.provider.model = "qwen2.5:32b"

    def test_parses_array(self):
        data = [
            {
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "player_performance",
                "confidence_note": "explicit",
            }
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1
        assert result[0]["extracted_claim"] == "Mahomes wins MVP"

    def test_strips_markdown_fences(self):
        text = '```json\n[{"extracted_claim": "Bears win Super Bowl", "claim_category": "game_outcome", "confidence_note": "strong"}]\n```'
        result = self.provider._parse_json_response(text)
        assert len(result) == 1

    def test_handles_predictions_wrapper(self):
        data = {
            "predictions": [
                {
                    "extracted_claim": "Stafford retires",
                    "claim_category": "player_performance",
                    "confidence_note": "rumor",
                }
            ]
        }
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1

    def test_handles_single_prediction_dict(self):
        data = {
            "extracted_claim": "Hill traded to Jets",
            "claim_category": "trade",
            "confidence_note": "report",
        }
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1

    def test_filters_empty_claims(self):
        data = [
            {"extracted_claim": "", "claim_category": "trade", "confidence_note": "x"},
            {
                "extracted_claim": "  ",
                "claim_category": "trade",
                "confidence_note": "x",
            },
            {
                "extracted_claim": "Valid claim",
                "claim_category": "trade",
                "confidence_note": "x",
            },
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1

    def test_returns_empty_on_malformed_json(self):
        result = self.provider._parse_json_response("not json at all")
        assert result == []

    def test_returns_empty_on_unexpected_structure(self):
        result = self.provider._parse_json_response('"just a string"')
        assert result == []


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    def test_default_model_is_qwen(self):
        provider = OllamaProvider()
        assert provider.model == "qwen2.5:32b"

    def test_custom_model(self):
        provider = OllamaProvider(model="llama3.1:8b")
        assert provider.model == "llama3.1:8b"

    def test_base_url_from_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        provider = OllamaProvider()
        assert provider.base_url == "http://host.docker.internal:11434"

    def test_base_url_default(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        provider = OllamaProvider()
        assert provider.base_url == "http://localhost:11434"

    def test_extract_predictions_success(self):
        predictions = [
            {
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "player_performance",
                "confidence_note": "explicit",
            }
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": json.dumps(predictions)}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            provider = OllamaProvider()
            result = provider.extract_predictions("Some article text")

        assert len(result) == 1
        assert result[0]["extracted_claim"] == "Mahomes wins MVP"

    def test_extract_predictions_empty(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "[]"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            provider = OllamaProvider()
            result = provider.extract_predictions("No predictions here.")

        assert result == []

    def test_extract_predictions_malformed_json_returns_empty(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "sorry, i can't do that"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            provider = OllamaProvider()
            result = provider.extract_predictions("Some text")

        assert result == []

    def test_classify_returns_stripped_lower(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "  YES  "}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            provider = OllamaProvider()
            result = provider.classify("Does this article contain predictions?")

        assert result == "yes"

    def test_generate_raises_on_request_failure(self):
        with patch("requests.post", side_effect=Exception("connection refused")):
            provider = OllamaProvider()
            with pytest.raises(Exception, match="connection refused"):
                provider.extract_predictions("some text")

    def test_schema_description_in_prompt(self):
        captured = {}

        def mock_post(url, json=None, timeout=None):
            captured["payload"] = json
            resp = MagicMock()
            resp.json.return_value = {"response": "[]"}
            resp.raise_for_status = MagicMock()
            return resp

        with patch("requests.post", side_effect=mock_post):
            provider = OllamaProvider()
            provider.extract_predictions("test article")

        assert PREDICTION_SCHEMA_DESCRIPTION in captured["payload"]["prompt"]

    def test_format_json_set_for_extraction(self):
        captured = {}

        def mock_post(url, json=None, timeout=None):
            captured["payload"] = json
            resp = MagicMock()
            resp.json.return_value = {"response": "[]"}
            resp.raise_for_status = MagicMock()
            return resp

        with patch("requests.post", side_effect=mock_post):
            provider = OllamaProvider()
            provider.extract_predictions("test article")

        assert captured["payload"].get("format") == "json"

    def test_format_json_not_set_for_classify(self):
        captured = {}

        def mock_post(url, json=None, timeout=None):
            captured["payload"] = json
            resp = MagicMock()
            resp.json.return_value = {"response": "yes"}
            resp.raise_for_status = MagicMock()
            return resp

        with patch("requests.post", side_effect=mock_post):
            provider = OllamaProvider()
            provider.classify("Does this have predictions?")

        assert "format" not in captured["payload"]


# ---------------------------------------------------------------------------
# get_provider / load_llm_config
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_returns_ollama_provider(self):
        config = {"extraction": {"provider": "ollama", "model": "qwen2.5:32b"}}
        provider = get_provider("extraction", config=config)
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "qwen2.5:32b"

    def test_unknown_provider_raises(self):
        config = {"extraction": {"provider": "unknown_llm", "model": "foo"}}
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider("extraction", config=config)

    def test_falls_back_to_extraction_config_for_missing_role(self):
        config = {"extraction": {"provider": "ollama", "model": "llama3.1:8b"}}
        provider = get_provider("filter", config=config)
        assert isinstance(provider, OllamaProvider)

    def test_load_llm_config_missing_file_returns_defaults(self, tmp_path):
        from pathlib import Path

        missing = tmp_path / "no_config.yaml"
        config = load_llm_config(missing)
        assert config["extraction"]["provider"] == "gemini"


# ---------------------------------------------------------------------------
# _FallbackProvider
# ---------------------------------------------------------------------------


class TestFallbackProvider:
    def _make_provider(self, extract_result=None, classify_result="yes", raises=False):
        p = MagicMock()
        if raises:
            p.extract_predictions.side_effect = Exception("fail")
            p.classify.side_effect = Exception("fail")
        else:
            p.extract_predictions.return_value = extract_result or []
            p.classify.return_value = classify_result
        p.model = "mock-model"
        return p

    def test_uses_primary_when_ok(self):
        primary = self._make_provider(
            extract_result=[
                {
                    "extracted_claim": "x",
                    "claim_category": "trade",
                    "confidence_note": "y",
                }
            ]
        )
        fallback = self._make_provider()
        fp = _FallbackProvider(primary, fallback)
        result = fp.extract_predictions("prompt")
        assert len(result) == 1
        fallback.extract_predictions.assert_not_called()

    def test_falls_back_on_primary_failure(self):
        primary = self._make_provider(raises=True)
        fallback = self._make_provider(
            extract_result=[
                {
                    "extracted_claim": "fallback claim",
                    "claim_category": "trade",
                    "confidence_note": "y",
                }
            ]
        )
        fp = _FallbackProvider(primary, fallback)
        result = fp.extract_predictions("prompt")
        assert result[0]["extracted_claim"] == "fallback claim"

    def test_classify_falls_back_on_failure(self):
        primary = self._make_provider(raises=True)
        fallback = self._make_provider(classify_result="no")
        fp = _FallbackProvider(primary, fallback)
        result = fp.classify("prompt")
        assert result == "no"


# ---------------------------------------------------------------------------
# Stance field in schema and parsing
# ---------------------------------------------------------------------------


class TestStanceField:
    def test_schema_description_includes_stance(self):
        assert "stance" in PREDICTION_SCHEMA_DESCRIPTION
        assert "bullish" in PREDICTION_SCHEMA_DESCRIPTION
        assert "bearish" in PREDICTION_SCHEMA_DESCRIPTION
        assert "neutral" in PREDICTION_SCHEMA_DESCRIPTION

    def setup_method(self):
        self.provider = OllamaProvider.__new__(OllamaProvider)
        self.provider.model = "qwen2.5:32b"

    def test_parse_preserves_bullish_stance(self):
        data = [
            {
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "player_performance",
                "stance": "bullish",
                "confidence_note": "explicit",
            }
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1
        assert result[0]["stance"] == "bullish"

    def test_parse_preserves_bearish_stance(self):
        data = [
            {
                "extracted_claim": "Browns miss playoffs",
                "claim_category": "game_outcome",
                "stance": "bearish",
                "confidence_note": "explicit",
            }
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert result[0]["stance"] == "bearish"

    def test_parse_preserves_neutral_stance(self):
        data = [
            {
                "extracted_claim": "Kelce retires after 2026",
                "claim_category": "player_performance",
                "stance": "neutral",
                "confidence_note": "rumor",
            }
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert result[0]["stance"] == "neutral"

    def test_parse_passes_through_missing_stance(self):
        """Missing stance key is preserved as-is; assertion_extractor handles normalization."""
        data = [
            {
                "extracted_claim": "Allen to Pro Bowl",
                "claim_category": "player_performance",
                "confidence_note": "strong",
            }
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert "stance" not in result[0]
