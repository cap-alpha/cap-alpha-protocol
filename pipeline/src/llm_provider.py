"""
LLM Provider Abstraction (Issue #178)

Provides a unified interface for structured prediction extraction across
multiple LLM backends: Gemini, Claude, OpenAI, and Ollama (local).

The assertion extractor uses this interface instead of calling Gemini directly,
allowing zero-cost local inference and easy provider swapping via config.

Usage:
    from src.llm_provider import get_provider

    provider = get_provider()  # reads from llm_config.yaml
    predictions = provider.extract_predictions(prompt)
    has_predictions = provider.classify(prompt)  # "yes" / "no"

Async batch usage (Gemini Flash burst mode):
    from src.llm_provider import AsyncGeminiProvider, TokenBudgetTracker
    import asyncio

    budget = TokenBudgetTracker(max_tokens=2_000_000)
    provider = AsyncGeminiProvider(budget=budget, concurrency=20)
    results = asyncio.run(provider.extract_predictions_batch(prompts))
"""

import asyncio
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_config.yaml"

# The JSON schema description included in prompts for providers that don't
# support native schema enforcement (Ollama, OpenAI function_calling workaround).
PREDICTION_SCHEMA_DESCRIPTION = """
Return a JSON array of objects. Each object must have:
- "extracted_claim": string — concise, testable statement (REQUIRED)
- "claim_category": string — one of: player_performance, game_outcome, trade, draft_pick, injury, contract (REQUIRED)
- "stance": string — directional sentiment: "bullish" (positive outcome predicted), "bearish" (negative outcome predicted), or "neutral" (no clear directional bias) (REQUIRED)
- "season_year": integer or null — season year the prediction applies to (CRITICAL for draft_pick: must be the draft year, e.g. 2025, 2026)
- "draft_year": integer or null — for draft pick predictions, set to the year of the draft (e.g. 2026). Otherwise null.
- "target_player": string or null — player name if about a specific player
- "target_team": string or null — team abbreviation (e.g. "KC", "CHI")
- "confidence_note": string — how explicit/confident the prediction is (REQUIRED)
- "prediction_horizon_days": integer — estimated days from publication date to when the event resolves; use -1 for retroactive/past statements (REQUIRED)

For draft_pick category: season_year MUST be populated with the draft year (infer if not explicitly stated).

If no testable predictions exist, return an empty array: []
"""


class LLMProvider(ABC):
    """Abstract base for LLM extraction backends."""

    provider_name: str = None  # Override in subclasses

    def __init__(self, model: str, **kwargs):
        self.model = model

    @abstractmethod
    def extract_predictions(self, prompt: str) -> list[dict]:
        """Send prompt with extraction instructions, get structured predictions."""
        ...

    @abstractmethod
    def classify(self, prompt: str) -> str:
        """Simple text classification. Returns the model's short text response."""
        ...

    def _parse_json_response(self, text: str) -> list[dict]:
        """Parse JSON from model response, handling common formatting issues."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [p for p in result if p.get("extracted_claim", "").strip()]
            if isinstance(result, dict):
                # Handle {"predictions": [...]} wrapper
                if "predictions" in result:
                    preds = result["predictions"]
                    if isinstance(preds, list):
                        return [
                            p for p in preds if p.get("extracted_claim", "").strip()
                        ]
                # Handle single prediction dict (common with smaller models)
                if "extracted_claim" in result:
                    return [result] if result["extracted_claim"].strip() else []
            logger.warning(f"Unexpected JSON structure: {type(result)}")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}. Response: {text[:200]}")
            return []


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------


class GeminiProvider(LLMProvider):
    """Google Gemini API with native schema enforcement."""

    provider_name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash", **kwargs):
        super().__init__(model)
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.types = types
        self._schema = self._build_schema()

    def _build_schema(self):
        types = self.types
        return types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "extracted_claim": types.Schema(
                        type=types.Type.STRING,
                        description="Concise, testable statement",
                    ),
                    "claim_category": types.Schema(
                        type=types.Type.STRING,
                        enum=[
                            "player_performance",
                            "game_outcome",
                            "trade",
                            "draft_pick",
                            "injury",
                            "contract",
                        ],
                    ),
                    "stance": types.Schema(
                        type=types.Type.STRING,
                        enum=["bullish", "bearish", "neutral"],
                        description="Directional sentiment: bullish=positive outcome predicted, bearish=negative, neutral=no clear bias",
                    ),
                    "season_year": types.Schema(type=types.Type.INTEGER, nullable=True),
                    "draft_year": types.Schema(
                        type=types.Type.INTEGER,
                        nullable=True,
                        description="For draft pick predictions, the year of the draft (e.g. 2026). Otherwise null.",
                    ),
                    "target_player": types.Schema(
                        type=types.Type.STRING, nullable=True
                    ),
                    "target_team": types.Schema(type=types.Type.STRING, nullable=True),
                    "confidence_note": types.Schema(
                        type=types.Type.STRING,
                        description="How explicit/confident the prediction is",
                    ),
                    "prediction_horizon_days": types.Schema(
                        type=types.Type.INTEGER,
                        description="Days from publication date to event resolution; use -1 for retroactive/past statements",
                    ),
                },
                required=[
                    "extracted_claim",
                    "claim_category",
                    "stance",
                    "confidence_note",
                    "prediction_horizon_days",
                ],
            ),
        )

    def extract_predictions(self, prompt: str) -> list[dict]:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=self._schema,
            ),
        )
        return self._parse_json_response(response.text)

    def classify(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model, contents=prompt
        )
        return response.text.strip().lower()


# ---------------------------------------------------------------------------
# Token budget tracker (for cost-capped burst runs)
# ---------------------------------------------------------------------------


class TokenBudgetTracker:
    """Thread/async-safe token budget tracker.

    Gemini Flash pricing (as of 2026-04): $0.15/1M input + $0.60/1M output.
    Default 2M token budget ≈ ~$0.30 blended.
    """

    # Conservative blended rate: mostly input tokens, some output
    COST_PER_TOKEN = 0.15 / 1_000_000  # input-dominated estimate

    def __init__(self, max_tokens: int = 2_000_000):
        self.max_tokens = max_tokens
        self._used_input: int = 0
        self._used_output: int = 0
        self._lock = asyncio.Lock()

    @property
    def used_tokens(self) -> int:
        return self._used_input + self._used_output

    @property
    def estimated_cost_usd(self) -> float:
        return (self._used_input * 0.15 / 1_000_000) + (
            self._used_output * 0.60 / 1_000_000
        )

    async def record(self, input_tokens: int, output_tokens: int) -> bool:
        """Record token usage. Returns False if budget exceeded."""
        async with self._lock:
            self._used_input += input_tokens
            self._used_output += output_tokens
            total = self._used_input + self._used_output
            print(
                f"[tokens] +{input_tokens}in/{output_tokens}out "
                f"| total={total:,}/{self.max_tokens:,} "
                f"| ~${self.estimated_cost_usd:.4f}",
                file=sys.stderr,
            )
            return total <= self.max_tokens

    def is_exhausted(self) -> bool:
        return (self._used_input + self._used_output) >= self.max_tokens

    def summary(self) -> dict:
        return {
            "input_tokens": self._used_input,
            "output_tokens": self._used_output,
            "total_tokens": self._used_input + self._used_output,
            "budget_tokens": self.max_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "budget_exhausted": self.is_exhausted(),
        }


# ---------------------------------------------------------------------------
# Async Gemini Provider — high-concurrency burst mode
# ---------------------------------------------------------------------------


class AsyncGeminiProvider:
    """Async Gemini Flash provider with semaphore-based concurrency control.

    Designed for high-volume historical backfill. Runs ~20 calls in-flight
    concurrently vs Ollama's serial throughput. Stops early if token budget
    is exhausted.

    Usage:
        budget = TokenBudgetTracker(max_tokens=2_000_000)
        provider = AsyncGeminiProvider(budget=budget, concurrency=20)
        results = await provider.extract_predictions_batch(prompts_list)
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        concurrency: int = 20,
        budget: Optional[TokenBudgetTracker] = None,
    ):
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY not set — required for gemini-flash provider. "
                "Set it with: export GEMINI_API_KEY=<your-key>"
            )
        self.client = genai.Client(api_key=api_key)
        self.types = types
        self.model = model
        self.concurrency = concurrency
        self.budget = budget or TokenBudgetTracker()
        self._schema = self._build_schema()
        self._semaphore: Optional[asyncio.Semaphore] = None

    def _build_schema(self):
        types = self.types
        return types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "extracted_claim": types.Schema(
                        type=types.Type.STRING,
                        description="Concise, testable statement",
                    ),
                    "claim_category": types.Schema(
                        type=types.Type.STRING,
                        enum=[
                            "player_performance",
                            "game_outcome",
                            "trade",
                            "draft_pick",
                            "injury",
                            "contract",
                        ],
                    ),
                    "stance": types.Schema(
                        type=types.Type.STRING,
                        enum=["bullish", "bearish", "neutral"],
                        description="Directional sentiment",
                    ),
                    "season_year": types.Schema(type=types.Type.INTEGER, nullable=True),
                    "target_player": types.Schema(
                        type=types.Type.STRING, nullable=True
                    ),
                    "target_team": types.Schema(type=types.Type.STRING, nullable=True),
                    "confidence_note": types.Schema(
                        type=types.Type.STRING,
                        description="How explicit/confident the prediction is",
                    ),
                },
                required=[
                    "extracted_claim",
                    "claim_category",
                    "stance",
                    "confidence_note",
                ],
            ),
        )

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily create semaphore in the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.concurrency)
        return self._semaphore

    def _parse_json_response(self, text: str) -> list[dict]:
        """Parse JSON from model response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [p for p in result if p.get("extracted_claim", "").strip()]
            if isinstance(result, dict):
                if "predictions" in result:
                    preds = result["predictions"]
                    if isinstance(preds, list):
                        return [
                            p for p in preds if p.get("extracted_claim", "").strip()
                        ]
                if "extracted_claim" in result:
                    return [result] if result["extracted_claim"].strip() else []
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}. Response: {text[:200]}")
            return []

    async def _extract_one(
        self, idx: int, prompt: str
    ) -> tuple[int, list[dict], Optional[str]]:
        """Extract predictions for a single prompt. Returns (idx, predictions, error)."""
        if self.budget.is_exhausted():
            return idx, [], "budget_exhausted"

        sem = self._get_semaphore()
        async with sem:
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=self.types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=self._schema,
                        ),
                    ),
                )
                # Record token usage
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    in_tok = getattr(usage, "prompt_token_count", 0) or 0
                    out_tok = getattr(usage, "candidates_token_count", 0) or 0
                    within_budget = await self.budget.record(in_tok, out_tok)
                    if not within_budget:
                        logger.warning(
                            f"[budget] Token budget exhausted after item {idx}. "
                            f"Stopping. {self.budget.summary()}"
                        )

                predictions = self._parse_json_response(response.text)
                return idx, predictions, None

            except Exception as e:
                logger.error(f"Gemini async call failed for item {idx}: {e}")
                return idx, [], str(e)

    async def extract_predictions_batch(
        self, prompts: list[str]
    ) -> list[tuple[list[dict], Optional[str]]]:
        """
        Run extraction on a batch of prompts concurrently.

        Returns list of (predictions, error_or_None) in input order.
        Stops dispatching new tasks once budget is exhausted.
        """
        self._semaphore = asyncio.Semaphore(self.concurrency)
        tasks = []
        for idx, prompt in enumerate(prompts):
            if self.budget.is_exhausted():
                logger.warning(
                    f"[budget] Budget exhausted at item {idx}/{len(prompts)}. "
                    f"Remaining {len(prompts) - idx} items skipped."
                )
                # Fill remaining with budget_exhausted markers
                for remaining_idx in range(idx, len(prompts)):
                    tasks.append(asyncio.create_task(self._noop(remaining_idx)))
                break
            tasks.append(asyncio.create_task(self._extract_one(idx, prompt)))

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        # Re-sort by idx (gather preserves order, but be safe)
        ordered = {}
        for res in results_raw:
            if isinstance(res, Exception):
                logger.error(f"Task exception: {res}")
                continue
            idx, preds, err = res
            ordered[idx] = (preds, err)

        return [ordered.get(i, ([], "missing")) for i in range(len(prompts))]

    async def _noop(self, idx: int) -> tuple[int, list[dict], str]:
        return idx, [], "budget_exhausted"


# ---------------------------------------------------------------------------
# Claude Provider
# ---------------------------------------------------------------------------


class ClaudeProvider(LLMProvider):
    """Anthropic Claude API with structured output via system prompt."""

    provider_name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-20250514", **kwargs):
        super().__init__(model)
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip install anthropic")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=api_key)

    def extract_predictions(self, prompt: str) -> list[dict]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=f"You are a prediction extraction system. Always respond with valid JSON.\n{PREDICTION_SCHEMA_DESCRIPTION}",
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        return self._parse_json_response(text)

    def classify(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip().lower()


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    """OpenAI API with JSON mode."""

    provider_name = "openai"

    def __init__(self, model: str = "gpt-4o", **kwargs):
        super().__init__(model)
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=api_key)

    def extract_predictions(self, prompt: str) -> list[dict]:
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": f"You are a prediction extraction system. Respond with a JSON object containing a 'predictions' key.\n{PREDICTION_SCHEMA_DESCRIPTION}",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
        )
        text = response.choices[0].message.content
        return self._parse_json_response(text)

    def classify(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10,
        )
        return response.choices[0].message.content.strip().lower()


# ---------------------------------------------------------------------------
# Ollama Provider (local, zero cost)
# ---------------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    """Local Ollama models via HTTP API. Zero cost."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5:32b",
        base_url: str = "http://localhost:11434",
        **kwargs,
    ):
        super().__init__(model)
        self.base_url = os.environ.get("OLLAMA_BASE_URL", base_url)

    def _generate(self, prompt: str, format_json: bool = False) -> str:
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        if format_json:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["response"]
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise

    def extract_predictions(self, prompt: str) -> list[dict]:
        full_prompt = f"{prompt}\n\n{PREDICTION_SCHEMA_DESCRIPTION}\n\nRespond with ONLY a JSON array:"
        text = self._generate(full_prompt, format_json=True)
        return self._parse_json_response(text)

    def classify(self, prompt: str) -> str:
        text = self._generate(prompt)
        return text.strip().lower()


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

PROVIDERS = {
    "gemini": GeminiProvider,
    # gemini-flash is an alias for GeminiProvider that locks in gemini-2.5-flash
    # and is the recommended provider for high-volume historical backfill runs.
    "gemini-flash": GeminiProvider,
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def load_llm_config(config_path: Optional[Path] = None) -> dict:
    """Load LLM configuration from yaml file."""
    path = config_path or CONFIG_PATH
    if not path.exists():
        logger.info(f"No llm_config.yaml found at {path}, using defaults")
        return {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "enabled": False,
            },
        }
    with open(path) as f:
        return yaml.safe_load(f)


def get_provider(
    role: str = "extraction",
    config: Optional[dict] = None,
    provider_override: Optional[str] = None,
) -> LLMProvider:
    """
    Get an LLM provider for a specific role.

    Args:
        role: "extraction" or "filter" — selects config section
        config: Optional config dict. If None, loads from llm_config.yaml
        provider_override: Override provider name (e.g. "gemini-flash"). Also
            honored from EXTRACTION_LLM env var (lower priority than explicit arg).
    """
    if config is None:
        config = load_llm_config()

    role_config = config.get(role, config.get("extraction", {}))

    # Resolution order: explicit arg > EXTRACTION_LLM env var > yaml config
    env_provider = os.environ.get("EXTRACTION_LLM")
    provider_name = (
        provider_override or env_provider or role_config.get("provider", "ollama")
    )

    # gemini-flash alias always forces gemini-2.5-flash model
    if provider_name == "gemini-flash":
        model = "gemini-2.5-flash"
    else:
        model = role_config.get("model", "gemini-2.5-flash")

    provider_cls = PROVIDERS.get(provider_name)
    if not provider_cls:
        raise ValueError(
            f"Unknown LLM provider: {provider_name!r}. "
            f"Available: {list(PROVIDERS.keys())}"
        )

    if provider_name in ("gemini", "gemini-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is required when using the gemini/gemini-flash provider. "
                "Set it with: export GEMINI_API_KEY=<your-key>"
            )

    logger.info(f"Initializing {provider_name} provider (model={model}, role={role})")
    return provider_cls(model=model)


def get_provider_with_fallback(
    role: str = "extraction",
    config: Optional[dict] = None,
    provider_override: Optional[str] = None,
) -> LLMProvider:
    """
    Get provider with fallback chain. Tries primary, falls back to secondary.
    Returns a FallbackProvider wrapper if fallback is configured.
    """
    if config is None:
        config = load_llm_config()

    primary = get_provider(role, config, provider_override=provider_override)

    fallback_config = config.get("fallback", {})
    if not fallback_config.get("enabled", False):
        return primary

    fallback_name = fallback_config.get("provider", "gemini")
    fallback_model = fallback_config.get("model", "gemini-2.5-flash")

    logger.info(f"Fallback configured: {fallback_name} (model={fallback_model})")
    fallback = PROVIDERS[fallback_name](model=fallback_model)

    return _FallbackProvider(primary, fallback)


class _FallbackProvider(LLMProvider):
    """Wraps two providers — tries primary, falls back on error."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        super().__init__(model=primary.model)
        self.primary = primary
        self.fallback = fallback
        self.provider_name = primary.provider_name

    def extract_predictions(self, prompt: str) -> list[dict]:
        try:
            return self.primary.extract_predictions(prompt)
        except Exception as e:
            logger.warning(
                f"Primary provider failed ({e}), falling back to {self.fallback.model}"
            )
            return self.fallback.extract_predictions(prompt)

    def classify(self, prompt: str) -> str:
        try:
            return self.primary.classify(prompt)
        except Exception as e:
            logger.warning(
                f"Primary classify failed ({e}), falling back to {self.fallback.model}"
            )
            return self.fallback.classify(prompt)
