"""
Unit tests for LLM Provider abstraction (Issue #178/#179).
All tests mock HTTP/API calls — no real LLM required.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.llm_provider import (
    PREDICTION_SCHEMA_DESCRIPTION,
    GeminiProvider,
    OllamaProvider,
    _FallbackProvider,
    _call_ollama_raw,
    _extract_json_from_response,
    get_provider,
    load_llm_config,
    verify_utterance,
)

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

    def test_phase_c_text_field_accepted(self):
        # Phase C responses use "text" as the primary field
        data = [
            {
                "text": "Mahomes wins MVP",
                "speech_act_type": "assertion",
                "testability_score": 0.9,
            },
            {"text": "", "speech_act_type": "commentary", "testability_score": 0.1},
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1
        assert result[0]["text"] == "Mahomes wins MVP"

    def test_phase_c_text_takes_priority_over_extracted_claim(self):
        # When both fields present, item is accepted
        data = [
            {
                "text": "Eagles win NFC",
                "extracted_claim": "Eagles win NFC East",
                "speech_act_type": "assertion",
            }
        ]
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1

    def test_phase_c_single_dict_with_text_field(self):
        data = {
            "text": "Brady returns",
            "speech_act_type": "assertion",
            "testability_score": 0.8,
        }
        result = self.provider._parse_json_response(json.dumps(data))
        assert len(result) == 1


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
        # Default provider is ollama (Ollama-first, zero cloud cost strategy)
        assert config["extraction"]["provider"] == "ollama"


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


# ---------------------------------------------------------------------------
# PREDICTION_SCHEMA_DESCRIPTION — new fields (#675)
# ---------------------------------------------------------------------------


class TestSchemaDescriptionNewFields:
    """resolution_condition and hedge_level must appear in the schema description
    so Ollama/Claude providers include them in prompts."""

    def test_resolution_condition_in_schema(self):
        assert "resolution_condition" in PREDICTION_SCHEMA_DESCRIPTION

    def test_hedge_level_in_schema(self):
        assert "hedge_level" in PREDICTION_SCHEMA_DESCRIPTION

    def test_hedge_level_values_in_schema(self):
        assert "strong" in PREDICTION_SCHEMA_DESCRIPTION
        assert "moderate" in PREDICTION_SCHEMA_DESCRIPTION
        assert "weak" in PREDICTION_SCHEMA_DESCRIPTION


# ---------------------------------------------------------------------------
# verify_utterance — 7B post-extraction verification pass (#675)
# ---------------------------------------------------------------------------


class TestVerifyUtterance:
    """Unit tests for the 7B model verification helper in llm_provider."""

    _UTTERANCE = {
        "extracted_claim": "Patrick Mahomes will win MVP",
        "target_player": "Patrick Mahomes",
        "target_team": "KC",
        "testability_score": 0.85,
    }

    _SOURCE_TEXT = (
        "Patrick Mahomes of the Kansas City Chiefs is the favorite for MVP this year."
    )

    def _mock_response(self, payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = {"response": json.dumps(payload)}
        resp.raise_for_status = MagicMock()
        return resp

    def test_returns_all_verification_fields(self):
        """Happy path: 7B returns valid JSON → all fields present in result."""
        payload = {
            "claim_text_alignment": 0.95,
            "player_mentioned_in_source": True,
            "team_mentioned_in_source": True,
            "hallucination_risk": "low",
            "verification_flags": [],
        }
        with patch("requests.post", return_value=self._mock_response(payload)):
            result = verify_utterance(self._UTTERANCE, self._SOURCE_TEXT)

        assert "claim_text_alignment" in result
        assert "hallucination_risk" in result
        assert "verification_flags" in result
        assert "quality_score" in result
        assert "needs_review" in result

    def test_quality_score_formula(self):
        """quality_score = 0.6 * testability + 0.4 * alignment."""
        payload = {
            "claim_text_alignment": 1.0,
            "player_mentioned_in_source": True,
            "team_mentioned_in_source": True,
            "hallucination_risk": "low",
            "verification_flags": [],
        }
        with patch("requests.post", return_value=self._mock_response(payload)):
            result = verify_utterance(self._UTTERANCE, self._SOURCE_TEXT)

        expected = round(0.6 * 0.85 + 0.4 * 1.0, 3)
        assert result["quality_score"] == pytest.approx(expected, abs=1e-3)

    def test_needs_review_when_quality_low(self):
        """needs_review=True when quality_score < 0.5."""
        low_testability_utterance = dict(self._UTTERANCE, testability_score=0.1)
        payload = {
            "claim_text_alignment": 0.1,
            "player_mentioned_in_source": False,
            "team_mentioned_in_source": False,
            "hallucination_risk": "low",
            "verification_flags": ["player_name_uncertain"],
        }
        with patch("requests.post", return_value=self._mock_response(payload)):
            result = verify_utterance(low_testability_utterance, self._SOURCE_TEXT)

        assert result["needs_review"] is True

    def test_needs_review_when_high_hallucination_risk(self):
        """needs_review=True when hallucination_risk == 'high', even if quality is OK."""
        payload = {
            "claim_text_alignment": 0.9,
            "player_mentioned_in_source": True,
            "team_mentioned_in_source": True,
            "hallucination_risk": "high",
            "verification_flags": ["claim_overstated"],
        }
        with patch("requests.post", return_value=self._mock_response(payload)):
            result = verify_utterance(self._UTTERANCE, self._SOURCE_TEXT)

        assert result["needs_review"] is True

    def test_returns_empty_dict_on_request_failure(self):
        """Non-blocking: connection errors return empty dict, not an exception."""
        with patch("requests.post", side_effect=Exception("connection refused")):
            result = verify_utterance(self._UTTERANCE, self._SOURCE_TEXT)

        assert result == {}

    def test_returns_empty_dict_on_bad_json(self):
        """Non-blocking: malformed JSON response returns empty dict."""
        bad_resp = MagicMock()
        bad_resp.json.return_value = {"response": "not json at all"}
        bad_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=bad_resp):
            result = verify_utterance(self._UTTERANCE, self._SOURCE_TEXT)

        assert result == {}

    def test_verification_flags_preserved(self):
        """Flags returned by the 7B model are passed through unchanged."""
        payload = {
            "claim_text_alignment": 0.6,
            "player_mentioned_in_source": True,
            "team_mentioned_in_source": False,
            "hallucination_risk": "medium",
            "verification_flags": ["team_inferred", "date_not_in_source"],
        }
        with patch("requests.post", return_value=self._mock_response(payload)):
            result = verify_utterance(self._UTTERANCE, self._SOURCE_TEXT)

        assert result["verification_flags"] == ["team_inferred", "date_not_in_source"]

    def test_uses_first_800_chars_of_source(self):
        """Only the first 800 chars of source_text are included in the prompt."""
        long_source = "A" * 1600
        payload_holder = {}

        def capturing_post(url, json=None, timeout=None):
            payload_holder["prompt"] = json.get("prompt", "")
            resp = MagicMock()
            resp.json.return_value = {
                "response": '{"claim_text_alignment": 0.8, "player_mentioned_in_source": true, "team_mentioned_in_source": true, "hallucination_risk": "low", "verification_flags": []}'
            }
            resp.raise_for_status = MagicMock()
            return resp

        with patch("requests.post", side_effect=capturing_post):
            verify_utterance(self._UTTERANCE, long_source)

        prompt = payload_holder["prompt"]
        # 800 "A"s must be present but the next chunk of As must NOT be
        assert "A" * 800 in prompt
        assert "A" * 801 not in prompt

    def test_missing_testability_score_defaults_to_0_5(self):
        """utterances without testability_score use 0.5 for quality formula."""
        utterance_no_score = {
            "extracted_claim": "Eagles win NFC",
            "target_player": None,
            "target_team": "PHI",
        }
        payload = {
            "claim_text_alignment": 1.0,
            "player_mentioned_in_source": False,
            "team_mentioned_in_source": True,
            "hallucination_risk": "low",
            "verification_flags": [],
        }
        with patch("requests.post", return_value=self._mock_response(payload)):
            result = verify_utterance(utterance_no_score, "Eagles beat Cowboys")

        # quality = 0.6 * 0.5 + 0.4 * 1.0 = 0.7
        assert result["quality_score"] == pytest.approx(0.7, abs=1e-3)


# ---------------------------------------------------------------------------
# _extract_json_from_response — JSON extraction helper (#675)
# ---------------------------------------------------------------------------


class TestExtractJsonFromResponse:
    def test_passes_through_plain_json_object(self):
        text = '{"key": "value"}'
        assert _extract_json_from_response(text) == '{"key": "value"}'

    def test_strips_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json_from_response(text)
        assert "{" in result
        assert "key" in result

    def test_extracts_json_from_surrounding_text(self):
        text = 'Here is the result: {"hallucination_risk": "low"} end'
        result = _extract_json_from_response(text)
        assert result == '{"hallucination_risk": "low"}'

    def test_extracts_array(self):
        text = "Result: [1, 2, 3] done"
        result = _extract_json_from_response(text)
        assert result == "[1, 2, 3]"
