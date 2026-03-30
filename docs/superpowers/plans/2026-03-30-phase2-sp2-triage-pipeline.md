# Triage Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the AI classification chain (coarse filter → full-text retrieval → methods analysis) with both sync and batch execution modes.

**Architecture:** Papers flow through Haiku screening (Stage 2), full-text retrieval cascade (Stage 3), and Sonnet risk rubric assessment (Stage 4). The LLM layer uses Anthropic tool-use for structured output and supports both individual calls and the 50%-cheaper Message Batches API via a config toggle. Every LLM call is audited in AssessmentLog.

**Tech Stack:** Anthropic Python SDK (0.86.0), httpx, lxml, SQLAlchemy async, structlog, respx

**Design Spec:** `docs/superpowers/specs/2026-03-30-phase2-sp2-triage-pipeline-design.md`

---

### Task 1: Configuration updates and package init files

**Files:**
- Modify: `pipeline/config.py`
- Create: `pipeline/triage/__init__.py`
- Create: `pipeline/fulltext/__init__.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_settings_sp2_defaults(monkeypatch):
    """SP2 config fields have correct defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    from pipeline.config import Settings

    s = Settings()
    assert s.use_batch_api is False
    assert s.unpaywall_request_delay == 0.1
    assert s.fulltext_request_delay == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_settings_sp2_defaults -v`
Expected: FAIL — `use_batch_api` not found

- [ ] **Step 3: Add new config fields and create init files**

Add to `pipeline/config.py` after the `pubmed_mesh_query` field:

```python
    # Batch API toggle
    use_batch_api: bool = False

    # Unpaywall rate limiting
    unpaywall_request_delay: float = 0.1

    # Full-text retrieval rate limiting
    fulltext_request_delay: float = 1.0
```

Create empty init files:

`pipeline/triage/__init__.py`:
```python
```

`pipeline/fulltext/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: All config tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/config.py pipeline/triage/__init__.py pipeline/fulltext/__init__.py tests/test_config.py
git commit -m "feat: add SP2 config fields and triage/fulltext packages"
```

---

### Task 2: Prompt templates and tool schemas

**Files:**
- Create: `pipeline/triage/prompts.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prompts.py`:

```python
"""Tests for pipeline.triage.prompts — prompt templates and tool schemas."""


class TestPromptConstants:
    """Verify prompt constants exist and are well-formed."""

    def test_coarse_filter_prompt_exists(self):
        from pipeline.triage.prompts import COARSE_FILTER_SYSTEM_PROMPT

        assert isinstance(COARSE_FILTER_SYSTEM_PROMPT, str)
        assert len(COARSE_FILTER_SYSTEM_PROMPT) > 100
        assert "dual-use" in COARSE_FILTER_SYSTEM_PROMPT.lower()

    def test_coarse_filter_version_exists(self):
        from pipeline.triage.prompts import COARSE_FILTER_VERSION

        assert isinstance(COARSE_FILTER_VERSION, str)
        assert COARSE_FILTER_VERSION.startswith("v")

    def test_methods_analysis_prompt_exists(self):
        from pipeline.triage.prompts import METHODS_ANALYSIS_SYSTEM_PROMPT

        assert isinstance(METHODS_ANALYSIS_SYSTEM_PROMPT, str)
        assert len(METHODS_ANALYSIS_SYSTEM_PROMPT) > 100
        assert "risk" in METHODS_ANALYSIS_SYSTEM_PROMPT.lower()

    def test_methods_analysis_version_exists(self):
        from pipeline.triage.prompts import METHODS_ANALYSIS_VERSION

        assert isinstance(METHODS_ANALYSIS_VERSION, str)
        assert METHODS_ANALYSIS_VERSION.startswith("v")


class TestToolSchemas:
    """Verify tool schemas are valid Anthropic tool definitions."""

    def test_classify_paper_tool_structure(self):
        from pipeline.triage.prompts import CLASSIFY_PAPER_TOOL

        assert CLASSIFY_PAPER_TOOL["name"] == "classify_paper"
        schema = CLASSIFY_PAPER_TOOL["input_schema"]
        assert "relevant" in schema["properties"]
        assert "confidence" in schema["properties"]
        assert "reason" in schema["properties"]
        assert set(schema["required"]) == {"relevant", "confidence", "reason"}

    def test_assess_durc_risk_tool_structure(self):
        from pipeline.triage.prompts import ASSESS_DURC_RISK_TOOL

        assert ASSESS_DURC_RISK_TOOL["name"] == "assess_durc_risk"
        schema = ASSESS_DURC_RISK_TOOL["input_schema"]
        dims = schema["properties"]["dimensions"]["properties"]
        expected_dims = {
            "pathogen_enhancement",
            "synthesis_barrier_lowering",
            "select_agent_relevance",
            "novel_technique",
            "information_hazard",
            "defensive_framing",
        }
        assert set(dims.keys()) == expected_dims
        assert "risk_tier" in schema["properties"]
        assert schema["properties"]["risk_tier"]["enum"] == ["low", "medium", "high", "critical"]

    def test_classify_paper_tool_relevant_is_boolean(self):
        from pipeline.triage.prompts import CLASSIFY_PAPER_TOOL

        assert CLASSIFY_PAPER_TOOL["input_schema"]["properties"]["relevant"]["type"] == "boolean"

    def test_dimension_scores_have_correct_range(self):
        from pipeline.triage.prompts import ASSESS_DURC_RISK_TOOL

        dims = ASSESS_DURC_RISK_TOOL["input_schema"]["properties"]["dimensions"]["properties"]
        for dim_name, dim_schema in dims.items():
            score = dim_schema["properties"]["score"]
            assert score["minimum"] == 0, f"{dim_name} min should be 0"
            assert score["maximum"] == 3, f"{dim_name} max should be 3"


class TestUserMessageTemplates:
    """Verify user message formatting functions."""

    def test_format_coarse_filter_message(self):
        from pipeline.triage.prompts import format_coarse_filter_message

        msg = format_coarse_filter_message("My Title", "My abstract text.")
        assert "My Title" in msg
        assert "My abstract text." in msg

    def test_format_methods_analysis_with_methods(self):
        from pipeline.triage.prompts import format_methods_analysis_message

        msg = format_methods_analysis_message("Title", "Abstract", methods="We used CRISPR...")
        assert "Title" in msg
        assert "Abstract" in msg
        assert "We used CRISPR..." in msg
        assert "NOTE:" not in msg

    def test_format_methods_analysis_without_methods(self):
        from pipeline.triage.prompts import format_methods_analysis_message

        msg = format_methods_analysis_message("Title", "Abstract", methods=None)
        assert "Title" in msg
        assert "Abstract" in msg
        assert "NOTE:" in msg
        assert "not available" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the prompts module**

Create `pipeline/triage/prompts.py`:

```python
"""Centralised prompt templates and tool schemas for the triage pipeline.

Every prompt has a version string stored alongside each AssessmentLog entry,
enabling prompt regression tracking.
"""

# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

COARSE_FILTER_VERSION = "v1.0"
METHODS_ANALYSIS_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

COARSE_FILTER_SYSTEM_PROMPT = """\
You are a biosecurity screening assistant. Your task is to determine whether \
a scientific paper's abstract suggests it MAY be relevant to dual-use research \
of concern (DURC) in the biological sciences.

A paper is RELEVANT if its abstract suggests ANY of the following:
- Enhancement of pathogen transmissibility, virulence, host range, or immune evasion
- Reconstruction or synthesis of dangerous pathogens (select agents, PPPs, or novel threats)
- Novel methods for producing biological toxins or bioactive compounds with harm potential
- Techniques that could lower barriers to creating biological weapons (simplified reverse \
genetics, benchtop synthesis protocols, democratised access to dangerous capabilities)
- Gain-of-function research on potential pandemic pathogens
- Novel delivery mechanisms for biological agents (aerosol, vector-based, environmental release)
- Identification of novel vulnerabilities in human, animal, or plant biology that could be exploited
- Work on agents listed under the Australia Group, BWC, or national select agent regulations
- De novo protein design or directed evolution of proteins with potential toxin-like or \
pathogen-enhancing functions
- Dual-use research on prions, mirror-life organisms, or xenobiology
- AI/ML methods specifically applied to pathogen enhancement, toxin design, or \
bioweapon-relevant optimisation

A paper is NOT RELEVANT if it is:
- Standard clinical research, epidemiology, public health surveillance (unless involving \
enhanced pathogens)
- Drug discovery, vaccine development, or diagnostics (unless the methods themselves are dual-use)
- Basic molecular biology, structural biology, or biochemistry with no obvious dual-use application
- Ecology, environmental science, agriculture (unless involving biological control agents \
with crossover potential)
- Pure computational biology, bioinformatics methods papers (unless specifically applied \
to the above)

You MUST err on the side of flagging. If there is ANY ambiguity, flag it as RELEVANT.

Use the classify_paper tool to report your assessment."""

METHODS_ANALYSIS_SYSTEM_PROMPT = """\
You are a dual-use research of concern (DURC) risk assessor with deep expertise in \
microbiology, virology, synthetic biology, and biosecurity policy. You are reviewing a \
scientific paper that has been flagged as potentially relevant to DURC.

Assess this paper against each of the following risk dimensions. For each dimension, \
provide a score (0-3) and a brief justification.

## Risk dimensions

1. **Pathogen enhancement** (0-3): Does the paper describe experimental enhancement of \
pathogen transmissibility, virulence, host range, immune evasion, or drug resistance? \
Score 0 if no enhancement work. Score 1 if indirect (e.g., characterisation that could \
inform enhancement). Score 2 if methods could be adapted for enhancement. Score 3 if \
direct enhancement is described.

2. **Synthesis/reconstruction barrier lowering** (0-3): Do the methods lower technical \
barriers to synthesising or reconstructing dangerous pathogens? Consider: are protocols \
unusually detailed? Are simplified or novel techniques described that make previously \
difficult work accessible? Score 0-3 based on degree of barrier lowering.

3. **Select agent / PPP relevance** (0-3): Does the work involve pathogens on the WHO, \
Australia Group, CDC Select Agent, or ACDP Hazard Group 3/4 lists? Or potential pandemic \
pathogens? Score 0 if no relevant agents. Score 1 for Hazard Group 2 / non-select agents. \
Score 2 for HG3 / select agents. Score 3 for HG4 / PPPs / Tier 1 select agents.

4. **Novelty of dual-use technique** (0-3): Does the paper describe a genuinely novel \
technique, tool, or approach that has dual-use potential? Score 0 for well-established \
methods. Score 1 for incremental improvements. Score 2 for significant methodological \
advances. Score 3 for transformative new capabilities.

5. **Information hazard** (0-3): Does the paper provide specific, actionable information \
that could be directly misused (exact sequences, detailed protocols, step-by-step synthesis \
routes)? Score 0 if information is generic or already widely known. Score 3 if the paper \
is essentially a recipe.

6. **Defensive framing adequacy** (0-3, inverse): Does the paper adequately discuss \
dual-use implications, describe risk mitigation measures, or frame the work in a \
defensive context? Score 0 if the paper has robust dual-use discussion and risk mitigation. \
Score 3 if there is NO mention of dual-use risks despite clearly dual-use methods.

Use the assess_durc_risk tool to report your assessment."""

# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool-use format)
# ---------------------------------------------------------------------------

_DIMENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 3},
        "justification": {"type": "string"},
    },
    "required": ["score", "justification"],
}

CLASSIFY_PAPER_TOOL: dict = {
    "name": "classify_paper",
    "description": (
        "Classify whether a paper is potentially relevant to "
        "dual-use research of concern."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "reason": {
                "type": "string",
                "description": "One sentence explanation",
            },
        },
        "required": ["relevant", "confidence", "reason"],
    },
}

ASSESS_DURC_RISK_TOOL: dict = {
    "name": "assess_durc_risk",
    "description": "Assess a paper against the 6-dimension DURC risk rubric.",
    "input_schema": {
        "type": "object",
        "properties": {
            "dimensions": {
                "type": "object",
                "properties": {
                    "pathogen_enhancement": _DIMENSION_SCHEMA,
                    "synthesis_barrier_lowering": _DIMENSION_SCHEMA,
                    "select_agent_relevance": _DIMENSION_SCHEMA,
                    "novel_technique": _DIMENSION_SCHEMA,
                    "information_hazard": _DIMENSION_SCHEMA,
                    "defensive_framing": _DIMENSION_SCHEMA,
                },
                "required": [
                    "pathogen_enhancement",
                    "synthesis_barrier_lowering",
                    "select_agent_relevance",
                    "novel_technique",
                    "information_hazard",
                    "defensive_framing",
                ],
            },
            "aggregate_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 18,
            },
            "risk_tier": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence overall assessment",
            },
            "key_methods_of_concern": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recommended_action": {
                "type": "string",
                "enum": ["archive", "monitor", "review", "escalate"],
            },
        },
        "required": [
            "dimensions",
            "aggregate_score",
            "risk_tier",
            "summary",
            "key_methods_of_concern",
            "recommended_action",
        ],
    },
}

# ---------------------------------------------------------------------------
# User message formatting
# ---------------------------------------------------------------------------


def format_coarse_filter_message(title: str, abstract: str) -> str:
    """Format the user message for Stage 2 coarse filter."""
    return f"Paper title: {title}\nAbstract: {abstract}"


def format_methods_analysis_message(
    title: str, abstract: str, methods: str | None
) -> str:
    """Format the user message for Stage 4 methods analysis."""
    if methods:
        return (
            f"Paper title: {title}\nAbstract: {abstract}\n"
            f"Methods section: {methods}"
        )
    return (
        f"Paper title: {title}\nAbstract: {abstract}\n\n"
        "NOTE: Full text was not available for this paper. "
        "Assess based on the abstract only. Note this limitation in your summary."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/triage/prompts.py tests/test_prompts.py
uv run ruff format pipeline/triage/prompts.py tests/test_prompts.py
git add pipeline/triage/prompts.py tests/test_prompts.py
git commit -m "feat: add triage prompt templates and tool schemas"
```

---

### Task 3: LLM infrastructure — LLMResult and sync call_tool

**Files:**
- Create: `pipeline/triage/llm.py`
- Create: `tests/test_llm.py`

**Reference:** The Anthropic Python SDK (v0.86.0) is already installed. Key types:
- `anthropic.AsyncAnthropic` — async client
- `anthropic.types.Message` — response type with `content`, `usage` fields
- `anthropic.types.ToolUseBlock` — content block with `name`, `input` fields
- `anthropic.types.Usage` — with `input_tokens`, `output_tokens` fields

- [ ] **Step 1: Write the failing tests**

Create `tests/test_llm.py`:

```python
"""Tests for pipeline.triage.llm — LLM calling infrastructure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import Message, ToolUseBlock, Usage


def _make_tool_use_message(
    tool_input: dict,
    tool_name: str = "classify_paper",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> Message:
    """Build a mock Anthropic Message with a tool_use content block."""
    return Message(
        id="msg_test123",
        content=[
            ToolUseBlock(
                id="tu_1",
                name=tool_name,
                input=tool_input,
                type="tool_use",
            )
        ],
        model="claude-haiku-4-5-20251001",
        role="assistant",
        stop_reason="tool_use",
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


SAMPLE_TOOL = {
    "name": "classify_paper",
    "description": "Test tool",
    "input_schema": {
        "type": "object",
        "properties": {"relevant": {"type": "boolean"}},
        "required": ["relevant"],
    },
}


class TestLLMResult:
    """Tests for LLMResult dataclass."""

    def test_fields_accessible(self):
        from pipeline.triage.llm import LLMResult

        result = LLMResult(
            tool_input={"relevant": True},
            raw_response="raw text",
            input_tokens=100,
            output_tokens=50,
            cost_estimate_usd=0.001,
        )
        assert result.tool_input == {"relevant": True}
        assert result.input_tokens == 100
        assert result.error is None

    def test_error_field(self):
        from pipeline.triage.llm import LLMResult

        result = LLMResult(
            tool_input={},
            raw_response="",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
            error="Something went wrong",
        )
        assert result.error == "Something went wrong"


class TestCostCalculation:
    """Tests for estimate_cost helper."""

    def test_haiku_cost(self):
        from pipeline.triage.llm import estimate_cost

        cost = estimate_cost("claude-haiku-4-5-20251001", 1000, 500, batch=False)
        # Haiku: $0.80/MTok in, $4.00/MTok out
        expected = (1000 * 0.80 / 1_000_000) + (500 * 4.00 / 1_000_000)
        assert abs(cost - expected) < 1e-9

    def test_sonnet_cost(self):
        from pipeline.triage.llm import estimate_cost

        cost = estimate_cost("claude-sonnet-4-6", 1000, 500, batch=False)
        expected = (1000 * 3.00 / 1_000_000) + (500 * 15.00 / 1_000_000)
        assert abs(cost - expected) < 1e-9

    def test_batch_mode_halves_cost(self):
        from pipeline.triage.llm import estimate_cost

        sync_cost = estimate_cost("claude-haiku-4-5-20251001", 1000, 500, batch=False)
        batch_cost = estimate_cost("claude-haiku-4-5-20251001", 1000, 500, batch=True)
        assert abs(batch_cost - sync_cost / 2) < 1e-9

    def test_unknown_model_uses_sonnet_pricing(self):
        from pipeline.triage.llm import estimate_cost

        cost = estimate_cost("some-unknown-model", 1000, 500, batch=False)
        expected = (1000 * 3.00 / 1_000_000) + (500 * 15.00 / 1_000_000)
        assert abs(cost - expected) < 1e-9


class TestCallTool:
    """Tests for LLMClient.call_tool — sync tool-use calls."""

    async def test_call_tool_returns_parsed_result(self):
        from pipeline.triage.llm import LLMClient

        tool_input = {"relevant": True, "confidence": 0.95, "reason": "GoF"}
        mock_response = _make_tool_use_message(tool_input)

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            result = await llm.call_tool(
                model="claude-haiku-4-5-20251001",
                system_prompt="Test prompt",
                user_message="Test message",
                tool=SAMPLE_TOOL,
            )

        assert result.tool_input == tool_input
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.error is None

    async def test_call_tool_passes_correct_params(self):
        from pipeline.triage.llm import LLMClient

        mock_response = _make_tool_use_message({"relevant": True})

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            await llm.call_tool(
                model="claude-haiku-4-5-20251001",
                system_prompt="System prompt here",
                user_message="User message here",
                tool=SAMPLE_TOOL,
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["system"] == "System prompt here"
        assert call_kwargs["tools"] == [SAMPLE_TOOL]
        assert call_kwargs["tool_choice"] == {"type": "any"}
        assert call_kwargs["messages"] == [
            {"role": "user", "content": "User message here"}
        ]

    async def test_call_tool_retries_on_overloaded(self):
        from anthropic import APIStatusError

        from pipeline.triage.llm import LLMClient

        tool_input = {"relevant": False}
        mock_response = _make_tool_use_message(tool_input)

        error_response = MagicMock()
        error_response.status_code = 529
        error_response.headers = {}
        overloaded_error = APIStatusError(
            message="overloaded",
            response=error_response,
            body={"error": {"type": "overloaded_error", "message": "overloaded"}},
        )

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=[overloaded_error, mock_response]
            )
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            result = await llm.call_tool(
                model="claude-haiku-4-5-20251001",
                system_prompt="test",
                user_message="test",
                tool=SAMPLE_TOOL,
            )

        assert result.tool_input == tool_input
        assert mock_client.messages.create.call_count == 2

    async def test_call_tool_raises_after_max_retries(self):
        from anthropic import APIStatusError

        from pipeline.triage.llm import LLMClient

        error_response = MagicMock()
        error_response.status_code = 529
        error_response.headers = {}
        overloaded_error = APIStatusError(
            message="overloaded",
            response=error_response,
            body={"error": {"type": "overloaded_error", "message": "overloaded"}},
        )

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=overloaded_error)
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            with pytest.raises(APIStatusError):
                await llm.call_tool(
                    model="claude-haiku-4-5-20251001",
                    system_prompt="test",
                    user_message="test",
                    tool=SAMPLE_TOOL,
                    max_retries=2,
                )

        assert mock_client.messages.create.call_count == 2

    async def test_call_tool_no_tool_use_block_returns_error(self):
        from pipeline.triage.llm import LLMClient

        # Response with text block instead of tool_use
        from anthropic.types import TextBlock

        msg = Message(
            id="msg_test",
            content=[TextBlock(text="I cannot use the tool.", type="text")],
            model="claude-haiku-4-5-20251001",
            role="assistant",
            stop_reason="end_turn",
            stop_sequence=None,
            type="message",
            usage=Usage(input_tokens=50, output_tokens=20),
        )

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=msg)
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            result = await llm.call_tool(
                model="claude-haiku-4-5-20251001",
                system_prompt="test",
                user_message="test",
                tool=SAMPLE_TOOL,
            )

        assert result.error is not None
        assert "no tool_use block" in result.error.lower()
        assert result.tool_input == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement LLMResult, estimate_cost, and LLMClient.call_tool**

Create `pipeline/triage/llm.py`:

```python
"""LLM calling infrastructure for the triage pipeline.

Wraps the Anthropic SDK with retry logic and cost tracking.
Returns LLMResult dataclasses — callers create AssessmentLog entries.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog
from anthropic import APIStatusError, APITimeoutError, AsyncAnthropic
from anthropic.types import ToolUseBlock

log = structlog.get_logger()

# Per-model pricing (USD per million tokens)
_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_mtok, output_per_mtok)
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (15.00, 75.00),
}
_DEFAULT_PRICING = (3.00, 15.00)  # Fall back to Sonnet pricing


@dataclass(frozen=True)
class LLMResult:
    """Result of a single LLM tool-use call."""

    tool_input: dict
    raw_response: str
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float
    error: str | None = field(default=None)


def estimate_cost(
    model: str, input_tokens: int, output_tokens: int, *, batch: bool = False
) -> float:
    """Calculate estimated cost in USD."""
    in_rate, out_rate = _PRICING.get(model, _DEFAULT_PRICING)
    cost = (input_tokens * in_rate / 1_000_000) + (output_tokens * out_rate / 1_000_000)
    if batch:
        cost *= 0.5
    return cost


# Retryable status codes from the Anthropic API
_RETRYABLE_STATUS_CODES = {429, 529}


class LLMClient:
    """Async wrapper around the Anthropic SDK for tool-use calls."""

    def __init__(self, api_key: str) -> None:
        self._anthropic = AsyncAnthropic(api_key=api_key)

    async def call_tool(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        tool: dict,
        max_retries: int = 3,
    ) -> LLMResult:
        """Make a single tool-use call with retry on transient errors."""
        for attempt in range(1, max_retries + 1):
            try:
                response = await self._anthropic.messages.create(
                    model=model,
                    max_tokens=1024,
                    system=system_prompt,
                    tools=[tool],
                    tool_choice={"type": "any"},
                    messages=[{"role": "user", "content": user_message}],
                )

                raw = response.model_dump_json()
                in_tok = response.usage.input_tokens
                out_tok = response.usage.output_tokens
                cost = estimate_cost(model, in_tok, out_tok)

                # Extract tool_use block
                tool_block = next(
                    (b for b in response.content if isinstance(b, ToolUseBlock)),
                    None,
                )
                if tool_block is None:
                    return LLMResult(
                        tool_input={},
                        raw_response=raw,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        cost_estimate_usd=cost,
                        error="No tool_use block in response",
                    )

                return LLMResult(
                    tool_input=tool_block.input,
                    raw_response=raw,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_estimate_usd=cost,
                )

            except (APIStatusError, APITimeoutError) as exc:
                retryable = isinstance(exc, APITimeoutError) or (
                    isinstance(exc, APIStatusError)
                    and exc.status_code in _RETRYABLE_STATUS_CODES
                )
                if retryable and attempt < max_retries:
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "llm_retry",
                        attempt=attempt,
                        backoff=backoff,
                        error=str(exc),
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/triage/llm.py tests/test_llm.py
uv run ruff format pipeline/triage/llm.py tests/test_llm.py
git add pipeline/triage/llm.py tests/test_llm.py
git commit -m "feat: add LLM infrastructure with sync call_tool and cost tracking"
```

---

### Task 4: LLM batch mode — submit_batch and collect_batch

**Files:**
- Modify: `pipeline/triage/llm.py`
- Modify: `tests/test_llm.py`

**Reference:** The Anthropic SDK batch API lives at `client.messages.batches`. Key types:
- `anthropic.types.messages.MessageBatch` — has `id`, `processing_status`
- `anthropic.types.messages.MessageBatchIndividualResponse` — has `custom_id`, `result`
- `anthropic.types.messages.MessageBatchSucceededResult` — has `message` (a Message)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_llm.py`:

```python
class TestBatchMode:
    """Tests for LLMClient.submit_batch and collect_batch."""

    async def test_submit_batch_returns_batch_id(self):
        from pipeline.triage.llm import LLMClient

        mock_batch = MagicMock()
        mock_batch.id = "batch_abc123"

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.batches.create = AsyncMock(return_value=mock_batch)
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            batch_id = await llm.submit_batch(
                model="claude-haiku-4-5-20251001",
                system_prompt="System",
                messages=[("paper-1", "Message 1"), ("paper-2", "Message 2")],
                tool=SAMPLE_TOOL,
            )

        assert batch_id == "batch_abc123"
        call_kwargs = mock_client.messages.batches.create.call_args.kwargs
        assert len(call_kwargs["requests"]) == 2
        assert call_kwargs["requests"][0]["custom_id"] == "paper-1"

    async def test_submit_batch_request_structure(self):
        from pipeline.triage.llm import LLMClient

        mock_batch = MagicMock()
        mock_batch.id = "batch_xyz"

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.batches.create = AsyncMock(return_value=mock_batch)
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            await llm.submit_batch(
                model="claude-haiku-4-5-20251001",
                system_prompt="System prompt",
                messages=[("id1", "Hello")],
                tool=SAMPLE_TOOL,
            )

        req = mock_client.messages.batches.create.call_args.kwargs["requests"][0]
        assert req["custom_id"] == "id1"
        params = req["params"]
        assert params["model"] == "claude-haiku-4-5-20251001"
        assert params["system"] == "System prompt"
        assert params["tools"] == [SAMPLE_TOOL]
        assert params["tool_choice"] == {"type": "any"}
        assert params["messages"] == [{"role": "user", "content": "Hello"}]

    async def test_collect_batch_polls_until_ended(self):
        from anthropic.types.messages import MessageBatch

        from pipeline.triage.llm import LLMClient

        processing_batch = MagicMock(spec=MessageBatch)
        processing_batch.processing_status = "in_progress"

        ended_batch = MagicMock(spec=MessageBatch)
        ended_batch.processing_status = "ended"

        tool_input = {"relevant": True, "confidence": 0.9, "reason": "GoF"}
        mock_response = _make_tool_use_message(tool_input)

        mock_result = MagicMock()
        mock_result.custom_id = "paper-1"
        mock_result.result.type = "succeeded"
        mock_result.result.message = mock_response

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.batches.retrieve = AsyncMock(
                side_effect=[processing_batch, ended_batch]
            )
            mock_client.messages.batches.results = MagicMock(
                return_value=[mock_result]
            )
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            results = await llm.collect_batch(
                "batch_123",
                model="claude-haiku-4-5-20251001",
                poll_interval=0,
            )

        assert "paper-1" in results
        assert results["paper-1"].tool_input == tool_input
        assert mock_client.messages.batches.retrieve.call_count == 2

    async def test_collect_batch_handles_errored_result(self):
        from anthropic.types.messages import MessageBatch

        from pipeline.triage.llm import LLMClient

        ended_batch = MagicMock(spec=MessageBatch)
        ended_batch.processing_status = "ended"

        mock_errored = MagicMock()
        mock_errored.custom_id = "paper-err"
        mock_errored.result.type = "errored"
        mock_errored.result.error = MagicMock()
        mock_errored.result.error.message = "Internal error"

        with patch("pipeline.triage.llm.AsyncAnthropic") as MockAnthropic:
            mock_client = AsyncMock()
            mock_client.messages.batches.retrieve = AsyncMock(
                return_value=ended_batch
            )
            mock_client.messages.batches.results = MagicMock(
                return_value=[mock_errored]
            )
            MockAnthropic.return_value = mock_client

            llm = LLMClient(api_key="test-key")
            results = await llm.collect_batch(
                "batch_456",
                model="claude-haiku-4-5-20251001",
                poll_interval=0,
            )

        assert "paper-err" in results
        assert results["paper-err"].error is not None
        assert results["paper-err"].tool_input == {}
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `uv run pytest tests/test_llm.py::TestBatchMode -v`
Expected: FAIL — `submit_batch` not defined

- [ ] **Step 3: Implement submit_batch and collect_batch**

Add these methods to the `LLMClient` class in `pipeline/triage/llm.py`:

```python
    async def submit_batch(
        self,
        model: str,
        system_prompt: str,
        messages: list[tuple[str, str]],
        tool: dict,
    ) -> str:
        """Submit a message batch. Returns batch_id."""
        requests = [
            {
                "custom_id": custom_id,
                "params": {
                    "model": model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "tools": [tool],
                    "tool_choice": {"type": "any"},
                    "messages": [{"role": "user", "content": user_message}],
                },
            }
            for custom_id, user_message in messages
        ]
        batch = await self._anthropic.messages.batches.create(requests=requests)
        log.info("batch_submitted", batch_id=batch.id, count=len(requests))
        return batch.id

    async def collect_batch(
        self,
        batch_id: str,
        model: str,
        *,
        poll_interval: float = 30.0,
        batch: bool = True,
    ) -> dict[str, LLMResult]:
        """Poll until batch completes, then return {custom_id: LLMResult}."""
        while True:
            batch_obj = await self._anthropic.messages.batches.retrieve(batch_id)
            if batch_obj.processing_status == "ended":
                break
            log.info(
                "batch_polling",
                batch_id=batch_id,
                status=batch_obj.processing_status,
            )
            await asyncio.sleep(poll_interval)

        results: dict[str, LLMResult] = {}
        for item in self._anthropic.messages.batches.results(batch_id):
            custom_id = item.custom_id
            if item.result.type != "succeeded":
                error_msg = getattr(
                    getattr(item.result, "error", None), "message", "Unknown batch error"
                )
                results[custom_id] = LLMResult(
                    tool_input={},
                    raw_response="",
                    input_tokens=0,
                    output_tokens=0,
                    cost_estimate_usd=0.0,
                    error=error_msg,
                )
                log.warning("batch_item_error", custom_id=custom_id, error=error_msg)
                continue

            response = item.result.message
            raw = response.model_dump_json()
            in_tok = response.usage.input_tokens
            out_tok = response.usage.output_tokens
            cost = estimate_cost(model, in_tok, out_tok, batch=batch)

            tool_block = next(
                (b for b in response.content if isinstance(b, ToolUseBlock)),
                None,
            )
            if tool_block is None:
                results[custom_id] = LLMResult(
                    tool_input={},
                    raw_response=raw,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_estimate_usd=cost,
                    error="No tool_use block in batch response",
                )
                continue

            results[custom_id] = LLMResult(
                tool_input=tool_block.input,
                raw_response=raw,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_estimate_usd=cost,
            )

        log.info("batch_collected", batch_id=batch_id, count=len(results))
        return results
```

- [ ] **Step 4: Run all LLM tests**

Run: `uv run pytest tests/test_llm.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/triage/llm.py tests/test_llm.py
uv run ruff format pipeline/triage/llm.py tests/test_llm.py
git add pipeline/triage/llm.py tests/test_llm.py
git commit -m "feat: add LLM batch mode with submit_batch and collect_batch"
```

---

### Task 5: Coarse filter

**Files:**
- Create: `pipeline/triage/coarse_filter.py`
- Create: `tests/test_coarse_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coarse_filter.py`:

```python
"""Tests for pipeline.triage.coarse_filter — Stage 2 Haiku screening."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _make_llm_result(relevant: bool, confidence: float, reason: str = "test"):
    from pipeline.triage.llm import LLMResult

    return LLMResult(
        tool_input={"relevant": relevant, "confidence": confidence, "reason": reason},
        raw_response='{"test": true}',
        input_tokens=100,
        output_tokens=50,
        cost_estimate_usd=0.001,
    )


class TestCoarseFilterSync:
    """Tests for run_coarse_filter in sync mode."""

    async def test_relevant_paper_passes(self, db_session: AsyncSession):
        from pipeline.models import AssessmentLog, PipelineStage
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="GoF H5N1")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_llm_result(relevant=True, confidence=0.95)
        )

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 1
        assert passed[0].id == paper.id
        assert paper.pipeline_stage == PipelineStage.COARSE_FILTERED
        assert paper.stage1_result["relevant"] is True

        # AssessmentLog created
        logs = (await db_session.execute(select(AssessmentLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].stage == "coarse_filter"

    async def test_irrelevant_high_confidence_filtered(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="Basic epidemiology")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_llm_result(relevant=False, confidence=0.95)
        )

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 0
        assert paper.pipeline_stage == PipelineStage.COARSE_FILTERED
        assert paper.stage1_result["relevant"] is False

    async def test_irrelevant_low_confidence_passes(self, db_session: AsyncSession):
        """Low confidence non-relevant still passes — err on inclusion."""
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="Borderline paper")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_llm_result(relevant=False, confidence=0.6)
        )

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 1

    async def test_llm_error_skips_paper(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.llm import LLMResult
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="Error paper")
        error_result = LLMResult(
            tool_input={},
            raw_response="",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
            error="No tool_use block in response",
        )
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=error_result)

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 0
        # Paper stays at INGESTED when there's an error
        assert paper.pipeline_stage == PipelineStage.INGESTED


class TestCoarseFilterBatch:
    """Tests for run_coarse_filter in batch mode."""

    async def test_batch_mode_processes_papers(self, db_session: AsyncSession):
        from pipeline.triage.coarse_filter import run_coarse_filter
        from pipeline.triage.llm import LLMResult

        p1 = await insert_paper(db_session, title="Paper A")
        p2 = await insert_paper(db_session, title="Paper B")

        results = {
            str(p1.id): _make_llm_result(relevant=True, confidence=0.9),
            str(p2.id): _make_llm_result(relevant=False, confidence=0.95),
        }

        mock_llm = AsyncMock()
        mock_llm.submit_batch = AsyncMock(return_value="batch_123")
        mock_llm.collect_batch = AsyncMock(return_value=results)

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[p1, p2],
            use_batch=True,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 1
        assert passed[0].id == p1.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coarse_filter.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement coarse_filter.py**

Create `pipeline/triage/coarse_filter.py`:

```python
"""Stage 2: Coarse filter — Haiku binary screening.

Processes INGESTED papers and classifies them as relevant or not relevant
to dual-use research of concern. Papers where the model is confident they
are NOT relevant get filtered out. Everything else passes to Stage 3.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import AssessmentLog, Paper, PipelineStage
from pipeline.triage.llm import LLMClient, LLMResult
from pipeline.triage.prompts import (
    CLASSIFY_PAPER_TOOL,
    COARSE_FILTER_SYSTEM_PROMPT,
    COARSE_FILTER_VERSION,
    format_coarse_filter_message,
)

log = structlog.get_logger()


def _paper_passes(result: dict, threshold: float) -> bool:
    """Determine if a paper should advance past the coarse filter.

    Passes if relevant=True OR if model confidence is at or below threshold.
    Only filters papers the model is confident are NOT relevant.
    """
    if result.get("relevant", True):
        return True
    return result.get("confidence", 0.0) <= threshold


def _create_assessment_log(
    session: AsyncSession,
    paper: Paper,
    llm_result: LLMResult,
    model: str,
    user_message: str,
) -> None:
    """Create an AssessmentLog entry from an LLM result."""
    session.add(
        AssessmentLog(
            paper_id=paper.id,
            stage="coarse_filter",
            model_used=model,
            prompt_version=COARSE_FILTER_VERSION,
            prompt_text=user_message,
            raw_response=llm_result.raw_response,
            parsed_result=llm_result.tool_input if not llm_result.error else None,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            cost_estimate_usd=llm_result.cost_estimate_usd,
            error=llm_result.error,
        )
    )


async def run_coarse_filter(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    use_batch: bool,
    model: str,
    threshold: float,
) -> list[Paper]:
    """Run Stage 2 coarse filter on a list of papers.

    Returns the subset of papers that pass the filter (advance to Stage 3).
    """
    if not papers:
        return []

    if use_batch:
        return await _run_batch(session, llm_client, papers, model, threshold)
    return await _run_sync(session, llm_client, papers, model, threshold)


async def _run_sync(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    threshold: float,
) -> list[Paper]:
    """Process papers one at a time."""
    passed: list[Paper] = []

    for paper in papers:
        user_msg = format_coarse_filter_message(paper.title, paper.abstract or "")

        llm_result = await llm_client.call_tool(
            model=model,
            system_prompt=COARSE_FILTER_SYSTEM_PROMPT,
            user_message=user_msg,
            tool=CLASSIFY_PAPER_TOOL,
        )

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning("coarse_filter_error", paper_id=str(paper.id), error=llm_result.error)
            continue

        paper.stage1_result = llm_result.tool_input
        paper.pipeline_stage = PipelineStage.COARSE_FILTERED

        if _paper_passes(llm_result.tool_input, threshold):
            passed.append(paper)
            log.info(
                "coarse_filter_pass",
                paper_id=str(paper.id),
                relevant=llm_result.tool_input.get("relevant"),
                confidence=llm_result.tool_input.get("confidence"),
            )

        await session.flush()

    log.info("coarse_filter_complete", total=len(papers), passed=len(passed))
    return passed


async def _run_batch(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    threshold: float,
) -> list[Paper]:
    """Process papers via the batch API."""
    messages = []
    paper_map: dict[str, tuple[Paper, str]] = {}

    for paper in papers:
        user_msg = format_coarse_filter_message(paper.title, paper.abstract or "")
        custom_id = str(paper.id)
        messages.append((custom_id, user_msg))
        paper_map[custom_id] = (paper, user_msg)

    batch_id = await llm_client.submit_batch(
        model=model,
        system_prompt=COARSE_FILTER_SYSTEM_PROMPT,
        messages=messages,
        tool=CLASSIFY_PAPER_TOOL,
    )

    results = await llm_client.collect_batch(batch_id, model=model)

    passed: list[Paper] = []
    for custom_id, (paper, user_msg) in paper_map.items():
        llm_result = results.get(custom_id)
        if llm_result is None:
            log.warning("coarse_filter_missing_result", paper_id=custom_id)
            continue

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning("coarse_filter_error", paper_id=custom_id, error=llm_result.error)
            continue

        paper.stage1_result = llm_result.tool_input
        paper.pipeline_stage = PipelineStage.COARSE_FILTERED

        if _paper_passes(llm_result.tool_input, threshold):
            passed.append(paper)

    await session.flush()
    log.info("coarse_filter_batch_complete", total=len(papers), passed=len(passed))
    return passed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_coarse_filter.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/triage/coarse_filter.py tests/test_coarse_filter.py
uv run ruff format pipeline/triage/coarse_filter.py tests/test_coarse_filter.py
git add pipeline/triage/coarse_filter.py tests/test_coarse_filter.py
git commit -m "feat: add coarse filter with sync and batch modes"
```

---

### Task 6: JATS parser and fixture

**Files:**
- Create: `pipeline/fulltext/jats_parser.py`
- Create: `tests/test_jats_parser.py`
- Create: `tests/fixtures/sample_jats.xml`

- [ ] **Step 1: Create the JATS fixture file**

Create `tests/fixtures/sample_jats.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving and Interchange DTD v1.2 20190208//EN" "JATS-archivearticle1.dtd">
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Gain-of-function analysis of H5N1 influenza virus</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec id="s1">
      <title>Introduction</title>
      <p>Influenza A viruses remain a major pandemic threat. In this study we investigate transmissibility determinants.</p>
    </sec>
    <sec id="s2" sec-type="methods">
      <title>Materials and Methods</title>
      <p>We performed serial passage of H5N1 in ferrets to identify mutations enhancing airborne transmissibility.</p>
      <p>Reverse genetics was used to introduce candidate mutations into a laboratory-adapted strain.</p>
    </sec>
    <sec id="s3">
      <title>Results</title>
      <p>Three mutations in the hemagglutinin gene were sufficient to confer airborne transmission between ferrets.</p>
    </sec>
    <sec id="s4">
      <title>Discussion</title>
      <p>These findings highlight the pandemic potential of currently circulating H5N1 strains.</p>
    </sec>
  </body>
</article>
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_jats_parser.py`:

```python
"""Tests for pipeline.fulltext.jats_parser — JATS XML methods extraction."""

from __future__ import annotations

from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_jats(body_xml: str) -> bytes:
    """Wrap body XML in a minimal JATS article structure."""
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<article><body>{body_xml}</body></article>""".encode()


class TestExtractMethods:
    """Tests for extract_methods function."""

    def test_sec_type_methods(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Introduction</title><p>Intro text.</p></sec>
            <sec sec-type="methods"><title>Methods</title><p>We did CRISPR.</p></sec>
            <sec><title>Results</title><p>It worked.</p></sec>
        """)
        full_text, methods = extract_methods(xml)
        assert "We did CRISPR." in methods
        assert "Intro text." not in methods
        assert "Intro text." in full_text

    def test_sec_type_materials_methods(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec sec-type="materials|methods"><title>Materials and Methods</title>
            <p>Cell culture and reagents.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "Cell culture" in methods

    def test_heading_text_fallback(self):
        """No sec-type attribute but heading text matches."""
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Introduction</title><p>Background.</p></sec>
            <sec><title>Materials and Methods</title><p>PCR amplification.</p></sec>
            <sec><title>Results</title><p>Bands observed.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "PCR amplification." in methods
        assert "Background." not in methods

    def test_experimental_procedures_heading(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Experimental Procedures</title><p>Western blot.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "Western blot." in methods

    def test_no_methods_section_returns_full_body(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec><title>Introduction</title><p>Some intro.</p></sec>
            <sec><title>Results</title><p>Some results.</p></sec>
        """)
        full_text, methods = extract_methods(xml)
        assert "Some intro." in methods
        assert "Some results." in methods
        assert full_text == methods

    def test_inline_markup_stripped(self):
        from pipeline.fulltext.jats_parser import extract_methods

        xml = _make_jats("""
            <sec sec-type="methods"><title>Methods</title>
            <p>We used <italic>E. coli</italic> strain K-12.</p></sec>
        """)
        _, methods = extract_methods(xml)
        assert "E. coli" in methods
        assert "<italic>" not in methods

    def test_fixture_file(self):
        """Parse the realistic JATS fixture and extract methods."""
        from pipeline.fulltext.jats_parser import extract_methods

        xml_bytes = (FIXTURES_DIR / "sample_jats.xml").read_bytes()
        full_text, methods = extract_methods(xml_bytes)
        assert "serial passage" in methods
        assert "Reverse genetics" in methods
        assert "Introduction" not in methods or "pandemic threat" in full_text
        assert "pandemic threat" in full_text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_jats_parser.py -v`
Expected: FAIL — module not found

- [ ] **Step 4: Implement jats_parser.py**

Create `pipeline/fulltext/jats_parser.py`:

```python
"""JATS XML methods section extraction.

Extracts the methods section from JATS-formatted full-text articles.
Falls back to the full body text if no methods section is found.
"""

from __future__ import annotations

import re

from lxml import etree

# Heading patterns that indicate a methods section (case-insensitive)
_METHODS_HEADINGS = re.compile(
    r"^(materials?\s*(and|&)\s*methods|methods|experimental\s*(procedures|methods)|study\s*methods)$",
    re.IGNORECASE,
)

# sec-type attribute values that indicate methods
_METHODS_SEC_TYPES = {"methods", "materials|methods", "materials"}


def _extract_text(elem) -> str:
    """Extract all text content from an element, stripping XML tags."""
    return "".join(elem.itertext()).strip()


def extract_methods(xml_bytes: bytes) -> tuple[str, str]:
    """Extract full text and methods section from JATS XML.

    Returns (full_text, methods_section). If no methods section is found,
    both values are the full body text.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(xml_bytes, parser=parser)

    # Extract full body text
    body = root.find(".//body")
    if body is None:
        return ("", "")

    full_text = _extract_text(body)

    # Strategy 1: sec-type attribute
    for sec in body.findall(".//sec"):
        sec_type = sec.get("sec-type", "")
        if sec_type in _METHODS_SEC_TYPES:
            return (full_text, _extract_text(sec))

    # Strategy 2: heading text match
    for sec in body.findall(".//sec"):
        title_elem = sec.find("title")
        if title_elem is not None:
            title_text = _extract_text(title_elem)
            if _METHODS_HEADINGS.match(title_text):
                return (full_text, _extract_text(sec))

    # No methods section found — return full body text for both
    return (full_text, full_text)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_jats_parser.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix pipeline/fulltext/jats_parser.py tests/test_jats_parser.py
uv run ruff format pipeline/fulltext/jats_parser.py tests/test_jats_parser.py
git add pipeline/fulltext/jats_parser.py tests/test_jats_parser.py tests/fixtures/sample_jats.xml
git commit -m "feat: add JATS XML methods section extraction"
```

---

### Task 7: HTML parser

**Files:**
- Create: `pipeline/fulltext/html_parser.py`
- Create: `tests/test_html_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_html_parser.py`:

```python
"""Tests for pipeline.fulltext.html_parser — HTML methods extraction."""

from __future__ import annotations


def _make_html(body_html: str) -> bytes:
    """Wrap body HTML in a minimal page structure."""
    return f"""\
<html><head><title>Test</title></head>
<body>{body_html}</body></html>""".encode()


class TestExtractMethods:
    """Tests for extract_methods function."""

    def test_methods_heading_found(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h2>Introduction</h2><p>Background info.</p>
            <h2>Methods</h2><p>We used CRISPR-Cas9.</p><p>Cells were cultured.</p>
            <h2>Results</h2><p>Editing was successful.</p>
        """)
        full_text, methods = extract_methods(html)
        assert "CRISPR-Cas9" in methods
        assert "Cells were cultured." in methods
        assert "Background info." not in methods
        assert "Editing was successful." not in methods

    def test_materials_and_methods_heading(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h2>Materials and Methods</h2><p>PCR was performed.</p>
            <h2>Results</h2><p>Bands observed.</p>
        """)
        _, methods = extract_methods(html)
        assert "PCR was performed." in methods

    def test_no_methods_heading_returns_full_text(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h2>Introduction</h2><p>Some intro.</p>
            <h2>Results</h2><p>Some results.</p>
        """)
        full_text, methods = extract_methods(html)
        assert "Some intro." in methods
        assert "Some results." in methods
        assert full_text == methods

    def test_script_and_style_stripped(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <script>var x = 1;</script>
            <style>body { color: red; }</style>
            <h2>Methods</h2><p>Real content here.</p>
            <h2>Results</h2><p>More content.</p>
        """)
        _, methods = extract_methods(html)
        assert "var x" not in methods
        assert "color: red" not in methods
        assert "Real content here." in methods

    def test_nav_header_footer_stripped(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <nav><a href="/">Home</a></nav>
            <header><p>Site header</p></header>
            <h2>Methods</h2><p>Experiment details.</p>
            <h2>Results</h2><p>Data.</p>
            <footer><p>Copyright 2026</p></footer>
        """)
        full_text, methods = extract_methods(html)
        assert "Home" not in full_text
        assert "Site header" not in full_text
        assert "Copyright" not in full_text
        assert "Experiment details." in methods

    def test_h3_heading_also_detected(self):
        from pipeline.fulltext.html_parser import extract_methods

        html = _make_html("""
            <h3>Introduction</h3><p>Intro.</p>
            <h3>Experimental Procedures</h3><p>Western blot.</p>
            <h3>Results</h3><p>Bands.</p>
        """)
        _, methods = extract_methods(html)
        assert "Western blot." in methods
        assert "Intro." not in methods
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_html_parser.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement html_parser.py**

Create `pipeline/fulltext/html_parser.py`:

```python
"""HTML fallback methods section extraction.

Used when full text is available only as HTML (e.g., from Unpaywall).
Identifies the methods section by heading text, similar to the JATS parser.
"""

from __future__ import annotations

import re

from lxml import html as lxml_html

# Same heading patterns as the JATS parser
_METHODS_HEADINGS = re.compile(
    r"^(materials?\s*(and|&)\s*methods|methods|experimental\s*(procedures|methods)|study\s*methods)$",
    re.IGNORECASE,
)

# Elements to strip before text extraction
_STRIP_TAGS = {"script", "style", "nav", "header", "footer"}

# Heading tags to look for
_HEADING_TAGS = {"h1", "h2", "h3", "h4"}


def _clean_tree(tree) -> None:
    """Remove script, style, nav, header, footer elements in-place."""
    for elem in tree.iter():
        if elem.tag in _STRIP_TAGS:
            elem.getparent().remove(elem)


def _extract_text(elem) -> str:
    """Extract all text content from an element."""
    return " ".join(elem.text_content().split())


def extract_methods(html_bytes: bytes) -> tuple[str, str]:
    """Extract full text and methods section from HTML.

    Returns (full_text, methods_section). If no methods section is found,
    both values are the full body text.
    """
    doc = lxml_html.fromstring(html_bytes)
    _clean_tree(doc)

    body = doc.find(".//body")
    if body is None:
        body = doc

    full_text = _extract_text(body)

    # Find methods heading
    for heading in body.iter(*_HEADING_TAGS):
        heading_text = heading.text_content().strip()
        if not _METHODS_HEADINGS.match(heading_text):
            continue

        heading_tag = heading.tag
        # Collect all content between this heading and the next heading at the same level
        parts = [heading_text]
        sibling = heading.getnext()
        while sibling is not None:
            if sibling.tag == heading_tag:
                break
            parts.append(_extract_text(sibling))
            sibling = sibling.getnext()

        methods_text = " ".join(parts)
        return (full_text, methods_text)

    return (full_text, full_text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_html_parser.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/fulltext/html_parser.py tests/test_html_parser.py
uv run ruff format pipeline/fulltext/html_parser.py tests/test_html_parser.py
git add pipeline/fulltext/html_parser.py tests/test_html_parser.py
git commit -m "feat: add HTML methods section extraction"
```

---

### Task 8: Unpaywall client

**Files:**
- Create: `pipeline/fulltext/unpaywall.py`
- Create: `tests/test_unpaywall.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_unpaywall.py`:

```python
"""Tests for pipeline.fulltext.unpaywall — Unpaywall API client."""

from __future__ import annotations

import httpx
import pytest
import respx


def _oa_response(
    url: str = "https://europepmc.org/articles/PMC123/full.xml",
    host_type: str = "repository",
) -> dict:
    """Build a mock Unpaywall API response."""
    return {
        "doi": "10.1234/test",
        "is_oa": True,
        "best_oa_location": {
            "url": url,
            "url_for_pdf": None,
            "url_for_landing_page": url,
            "host_type": host_type,
        },
    }


class TestLookup:
    """Tests for UnpaywallClient.lookup."""

    @respx.mock
    async def test_successful_xml_lookup(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
            return_value=httpx.Response(200, json=_oa_response(
                url="https://europepmc.org/articles/PMC123/fullTextXML"
            ))
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result.url == "https://europepmc.org/articles/PMC123/fullTextXML"
        assert result.content_type == "xml"

    @respx.mock
    async def test_html_url_detected(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
            return_value=httpx.Response(200, json=_oa_response(
                url="https://publisher.com/article/12345"
            ))
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result.content_type == "html"

    @respx.mock
    async def test_pdf_url_detected(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
            return_value=httpx.Response(200, json=_oa_response(
                url="https://publisher.com/article/12345.pdf"
            ))
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result.content_type == "pdf"

    @respx.mock
    async def test_not_found_returns_none(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/missing").mock(
            return_value=httpx.Response(404)
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/missing")

        assert result is None

    @respx.mock
    async def test_not_oa_returns_none(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/closed").mock(
            return_value=httpx.Response(200, json={
                "doi": "10.1234/closed",
                "is_oa": False,
                "best_oa_location": None,
            })
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/closed")

        assert result is None

    @respx.mock
    async def test_retry_on_429(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        route = respx.get("https://api.unpaywall.org/v2/10.1234/retry").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=_oa_response()),
            ]
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/retry")

        assert result is not None
        assert route.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_unpaywall.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement unpaywall.py**

Create `pipeline/fulltext/unpaywall.py`:

```python
"""Unpaywall API client — find open access full-text URLs by DOI.

Usage:
    async with UnpaywallClient(email="you@example.com") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result.url, result.content_type)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.unpaywall.org/v2"

# Known XML hosts (URLs from these domains are likely JATS XML)
_XML_HOSTS = {"europepmc.org", "ncbi.nlm.nih.gov", "ebi.ac.uk"}


@dataclass(frozen=True)
class UnpaywallResult:
    """Result of an Unpaywall DOI lookup."""

    url: str
    content_type: str  # "xml", "html", "pdf"
    host_type: str  # "publisher", "repository"


def _classify_url(url: str) -> str:
    """Classify a URL as xml, pdf, or html based on URL patterns."""
    lower = url.lower()
    if lower.endswith(".xml") or "fulltext" in lower and "xml" in lower:
        return "xml"
    if lower.endswith(".pdf") or "/pdf/" in lower:
        return "pdf"
    for host in _XML_HOSTS:
        if host in lower and ("xml" in lower or "fullTextXML" in url):
            return "xml"
    return "html"


class UnpaywallClient:
    """Async client for the Unpaywall API."""

    def __init__(
        self,
        email: str,
        request_delay: float = 0.1,
        max_retries: int = 3,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> UnpaywallClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> UnpaywallResult | None:
        """Look up a DOI and return the best OA location, or None."""
        assert self._client is not None, "Use UnpaywallClient as async context manager"

        url = f"{BASE_URL}/{doi}"
        params = {"email": self.email}

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return self._parse_response(resp.json())
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="unpaywall",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning("timeout", source="unpaywall", attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Unpaywall failed after {self.max_retries} retries: {doi}")

    def _parse_response(self, data: dict) -> UnpaywallResult | None:
        """Extract best OA location from Unpaywall response."""
        if not data.get("is_oa"):
            return None

        location = data.get("best_oa_location")
        if not location:
            return None

        url = location.get("url") or location.get("url_for_landing_page")
        if not url:
            return None

        return UnpaywallResult(
            url=url,
            content_type=_classify_url(url),
            host_type=location.get("host_type", "unknown"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_unpaywall.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/fulltext/unpaywall.py tests/test_unpaywall.py
uv run ruff format pipeline/fulltext/unpaywall.py tests/test_unpaywall.py
git add pipeline/fulltext/unpaywall.py tests/test_unpaywall.py
git commit -m "feat: add Unpaywall API client for OA full-text URLs"
```

---

### Task 9: Full-text retriever

**Files:**
- Create: `pipeline/fulltext/retriever.py`
- Create: `tests/test_retriever.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retriever.py`:

```python
"""Tests for pipeline.fulltext.retriever — full-text retrieval cascade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import PipelineStage, SourceServer
from tests.conftest import insert_paper


# Minimal JATS with a methods section
SAMPLE_JATS = b"""\
<?xml version="1.0"?>
<article><body>
<sec><title>Introduction</title><p>Intro.</p></sec>
<sec sec-type="methods"><title>Methods</title><p>We used PCR.</p></sec>
<sec><title>Results</title><p>It worked.</p></sec>
</body></article>"""

SAMPLE_HTML = b"""\
<html><body>
<h2>Introduction</h2><p>Background.</p>
<h2>Methods</h2><p>We used Western blot.</p>
<h2>Results</h2><p>Bands.</p>
</body></html>"""


class TestRetrieveCascade:
    """Tests for retrieve_full_text cascade logic."""

    @respx.mock
    async def test_biorxiv_source_succeeds(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1101/2026.03.01.999999",
            source_server=SourceServer.BIORXIV,
        )

        respx.get("https://www.biorxiv.org/content/10.1101/2026.03.01.999999.full.xml").mock(
            return_value=httpx.Response(200, content=SAMPLE_JATS)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is True
        assert "We used PCR." in paper.methods_section
        assert paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED

    @respx.mock
    async def test_biorxiv_fails_europepmc_succeeds(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1101/2026.03.01.888888",
            source_server=SourceServer.BIORXIV,
        )

        # bioRxiv returns 404
        respx.get("https://www.biorxiv.org/content/10.1101/2026.03.01.888888.full.xml").mock(
            return_value=httpx.Response(404)
        )
        # Europe PMC search returns source/id
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").mock(
            return_value=httpx.Response(200, json={
                "resultList": {"result": [{"source": "PPR", "id": "PPR999"}]}
            })
        )
        # Europe PMC full text
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/PPR/PPR999/fullTextXML").mock(
            return_value=httpx.Response(200, content=SAMPLE_JATS)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is True
        assert "We used PCR." in paper.methods_section

    @respx.mock
    async def test_all_sources_fail_gracefully(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1234/no-fulltext",
            source_server=SourceServer.PUBMED,
        )

        # Europe PMC returns empty
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").mock(
            return_value=httpx.Response(200, json={"resultList": {"result": []}})
        )
        # Unpaywall returns 404
        respx.get("https://api.unpaywall.org/v2/10.1234/no-fulltext").mock(
            return_value=httpx.Response(404)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = "test@test.com"
        settings.unpaywall_request_delay = 0

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is False
        assert paper.methods_section is None
        assert paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED

    @respx.mock
    async def test_pmc_source_used_when_available(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi="10.1234/pmc-test",
            source_server=SourceServer.PUBMED,
            full_text_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7654321/",
        )

        # Europe PMC returns empty
        respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").mock(
            return_value=httpx.Response(200, json={"resultList": {"result": []}})
        )
        # PMC OA succeeds
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
            return_value=httpx.Response(200, content=SAMPLE_JATS)
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is True

    @respx.mock
    async def test_paper_without_doi_goes_straight_to_failure(self, db_session: AsyncSession):
        from pipeline.fulltext.retriever import retrieve_full_text

        paper = await insert_paper(
            db_session,
            doi=None,
            source_server=SourceServer.EUROPEPMC,
        )

        settings = MagicMock()
        settings.fulltext_request_delay = 0
        settings.ncbi_api_key = ""
        settings.unpaywall_email = ""

        await retrieve_full_text(db_session, paper, settings)

        assert paper.full_text_retrieved is False
        assert paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_retriever.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement retriever.py**

Create `pipeline/fulltext/retriever.py`:

```python
"""Stage 3: Full-text retrieval cascade.

Tries multiple sources in priority order to fetch full-text content.
Extracts the methods section using the JATS or HTML parser.
Falls back gracefully if all sources fail — the paper still advances.
"""

from __future__ import annotations

import re

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.fulltext.html_parser import extract_methods as html_extract
from pipeline.fulltext.jats_parser import extract_methods as jats_extract
from pipeline.fulltext.unpaywall import UnpaywallClient
from pipeline.models import Paper, PipelineStage, SourceServer

log = structlog.get_logger()

_PMC_ID_PATTERN = re.compile(r"PMC\d+")


async def retrieve_full_text(
    session: AsyncSession,
    paper: Paper,
    settings,
) -> None:
    """Run the full-text retrieval cascade for a single paper.

    Updates paper.full_text_content, paper.methods_section,
    paper.full_text_retrieved, and paper.pipeline_stage in-place.
    """
    result = None

    async with httpx.AsyncClient() as http:
        # Source 1: bioRxiv/medRxiv TDM XML
        if (
            paper.doi
            and paper.source_server in (SourceServer.BIORXIV, SourceServer.MEDRXIV)
        ):
            result = await _try_biorxiv(http, paper.doi, settings.fulltext_request_delay)

        # Source 2: Europe PMC full text
        if result is None and paper.doi:
            result = await _try_europepmc(http, paper.doi, settings.fulltext_request_delay)

        # Source 3: PubMed Central OA
        if result is None and paper.full_text_url:
            pmc_id = _extract_pmc_id(paper.full_text_url)
            if pmc_id:
                result = await _try_pmc(
                    http, pmc_id, settings.fulltext_request_delay, settings.ncbi_api_key
                )

        # Source 4: Unpaywall
        if result is None and paper.doi and settings.unpaywall_email:
            result = await _try_unpaywall(http, paper.doi, settings)

    if result is not None:
        full_text, methods = result
        paper.full_text_content = full_text
        paper.methods_section = methods
        paper.full_text_retrieved = True
        log.info("fulltext_retrieved", paper_id=str(paper.id))
    else:
        paper.full_text_retrieved = False
        log.info("fulltext_not_found", paper_id=str(paper.id))

    paper.pipeline_stage = PipelineStage.FULLTEXT_RETRIEVED
    await session.flush()


def _extract_pmc_id(url: str) -> str | None:
    """Extract PMC ID from a URL like https://...pmc/articles/PMC7654321/."""
    match = _PMC_ID_PATTERN.search(url)
    return match.group(0) if match else None


async def _try_biorxiv(
    http: httpx.AsyncClient, doi: str, delay: float
) -> tuple[str, str] | None:
    """Source 1: bioRxiv/medRxiv TDM XML."""
    url = f"https://www.biorxiv.org/content/{doi}.full.xml"
    try:
        resp = await http.get(url, timeout=30.0)
        if resp.status_code == 200:
            return jats_extract(resp.content)
    except (httpx.HTTPError, Exception) as exc:
        log.debug("biorxiv_fulltext_error", doi=doi, error=str(exc))
    return None


async def _try_europepmc(
    http: httpx.AsyncClient, doi: str, delay: float
) -> tuple[str, str] | None:
    """Source 2: Europe PMC full text XML."""
    # First, find the Europe PMC source/id for this DOI
    search_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": f"DOI:{doi}", "format": "json", "resultType": "core", "pageSize": 1}
    try:
        resp = await http.get(search_url, params=params, timeout=30.0)
        if resp.status_code != 200:
            return None
        results = resp.json().get("resultList", {}).get("result", [])
        if not results:
            return None
        source = results[0].get("source", "")
        record_id = results[0].get("id", "")
        if not source or not record_id:
            return None

        # Fetch full text
        ft_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{record_id}/fullTextXML"
        resp = await http.get(ft_url, timeout=30.0)
        if resp.status_code == 200 and resp.content:
            return jats_extract(resp.content)
    except (httpx.HTTPError, Exception) as exc:
        log.debug("europepmc_fulltext_error", doi=doi, error=str(exc))
    return None


async def _try_pmc(
    http: httpx.AsyncClient, pmc_id: str, delay: float, api_key: str
) -> tuple[str, str] | None:
    """Source 3: PubMed Central OA via efetch."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params: dict = {"db": "pmc", "id": pmc_id, "rettype": "xml"}
    if api_key:
        params["api_key"] = api_key
    try:
        resp = await http.get(url, params=params, timeout=30.0)
        if resp.status_code == 200 and resp.content:
            return jats_extract(resp.content)
    except (httpx.HTTPError, Exception) as exc:
        log.debug("pmc_fulltext_error", pmc_id=pmc_id, error=str(exc))
    return None


async def _try_unpaywall(
    http: httpx.AsyncClient, doi: str, settings
) -> tuple[str, str] | None:
    """Source 4: Unpaywall → fetch OA URL → parse."""
    try:
        async with UnpaywallClient(
            email=settings.unpaywall_email,
            request_delay=settings.unpaywall_request_delay,
        ) as uw:
            result = await uw.lookup(doi)

        if result is None:
            return None

        if result.content_type == "pdf":
            log.debug("unpaywall_pdf_skipped", doi=doi)
            return None

        resp = await http.get(result.url, timeout=30.0)
        if resp.status_code != 200:
            return None

        if result.content_type == "xml":
            return jats_extract(resp.content)
        return html_extract(resp.content)

    except (httpx.HTTPError, Exception) as exc:
        log.debug("unpaywall_fulltext_error", doi=doi, error=str(exc))
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retriever.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/fulltext/retriever.py tests/test_retriever.py
uv run ruff format pipeline/fulltext/retriever.py tests/test_retriever.py
git add pipeline/fulltext/retriever.py tests/test_retriever.py
git commit -m "feat: add full-text retrieval cascade with 4 sources"
```

---

### Task 10: Methods analysis

**Files:**
- Create: `pipeline/triage/methods_analysis.py`
- Create: `tests/test_methods_analysis.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_methods_analysis.py`:

```python
"""Tests for pipeline.triage.methods_analysis — Stage 4 Sonnet risk assessment."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _make_risk_result(aggregate: int = 10, tier: str = "high"):
    from pipeline.triage.llm import LLMResult

    return LLMResult(
        tool_input={
            "dimensions": {
                "pathogen_enhancement": {"score": 2, "justification": "GoF work"},
                "synthesis_barrier_lowering": {"score": 1, "justification": "Standard"},
                "select_agent_relevance": {"score": 2, "justification": "H5N1"},
                "novel_technique": {"score": 2, "justification": "New approach"},
                "information_hazard": {"score": 2, "justification": "Detailed"},
                "defensive_framing": {"score": 1, "justification": "Some discussion"},
            },
            "aggregate_score": aggregate,
            "risk_tier": tier,
            "summary": "This paper describes GoF research on H5N1.",
            "key_methods_of_concern": ["serial passage", "reverse genetics"],
            "recommended_action": "review",
        },
        raw_response='{"test": true}',
        input_tokens=500,
        output_tokens=200,
        cost_estimate_usd=0.005,
    )


class TestMethodsAnalysisSync:
    """Tests for run_methods_analysis in sync mode."""

    async def test_paper_assessed_and_updated(self, db_session: AsyncSession):
        from pipeline.models import AssessmentLog, PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(
            db_session,
            title="H5N1 GoF",
            abstract="We enhanced transmissibility.",
            methods_section="Serial passage in ferrets.",
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_risk_result(10, "high"))

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        assert paper.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert paper.risk_tier == RiskTier.HIGH
        assert paper.aggregate_score == 10
        assert paper.recommended_action == RecommendedAction.REVIEW
        assert paper.stage2_result is not None

        logs = (await db_session.execute(select(AssessmentLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].stage == "methods_analysis"

    async def test_abstract_only_when_no_methods(self, db_session: AsyncSession):
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(
            db_session,
            title="No fulltext paper",
            abstract="Abstract only.",
            methods_section=None,
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_risk_result(3, "low"))

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        # Verify the "NOTE:" abstract-only message was sent
        call_kwargs = mock_llm.call_tool.call_args.kwargs
        assert "NOTE:" in call_kwargs["user_message"]
        assert paper.risk_tier is not None

    async def test_risk_tier_thresholds(self, db_session: AsyncSession):
        """Verify risk tier enum mapping."""
        from pipeline.models import RiskTier
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(db_session, title="Critical paper")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_risk_result(15, "critical")
        )

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        assert paper.risk_tier == RiskTier.CRITICAL
        assert paper.aggregate_score == 15

    async def test_llm_error_skips_paper(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.llm import LLMResult
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(db_session, title="Error paper")
        error_result = LLMResult(
            tool_input={},
            raw_response="",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
            error="Model refused",
        )
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=error_result)

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        assert paper.pipeline_stage == PipelineStage.INGESTED
        assert paper.risk_tier is None


class TestMethodsAnalysisBatch:
    """Tests for run_methods_analysis in batch mode."""

    async def test_batch_mode_processes_papers(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.methods_analysis import run_methods_analysis

        p1 = await insert_paper(db_session, title="Paper A")
        p2 = await insert_paper(db_session, title="Paper B")

        results = {
            str(p1.id): _make_risk_result(12, "high"),
            str(p2.id): _make_risk_result(2, "low"),
        }

        mock_llm = AsyncMock()
        mock_llm.submit_batch = AsyncMock(return_value="batch_999")
        mock_llm.collect_batch = AsyncMock(return_value=results)

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[p1, p2],
            use_batch=True,
            model="claude-sonnet-4-6",
        )

        assert p1.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert p2.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert p1.aggregate_score == 12
        assert p2.aggregate_score == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_methods_analysis.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement methods_analysis.py**

Create `pipeline/triage/methods_analysis.py`:

```python
"""Stage 4: Methods analysis — Sonnet 6-dimension risk rubric assessment.

Processes papers that passed the coarse filter, assessing their methods
section (or abstract if full text was unavailable) against a detailed
dual-use risk rubric.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import (
    AssessmentLog,
    Paper,
    PipelineStage,
    RecommendedAction,
    RiskTier,
)
from pipeline.triage.llm import LLMClient, LLMResult
from pipeline.triage.prompts import (
    ASSESS_DURC_RISK_TOOL,
    METHODS_ANALYSIS_SYSTEM_PROMPT,
    METHODS_ANALYSIS_VERSION,
    format_methods_analysis_message,
)

log = structlog.get_logger()

# Maps string values from LLM output to model enums
_RISK_TIER_MAP = {
    "low": RiskTier.LOW,
    "medium": RiskTier.MEDIUM,
    "high": RiskTier.HIGH,
    "critical": RiskTier.CRITICAL,
}

_ACTION_MAP = {
    "archive": RecommendedAction.ARCHIVE,
    "monitor": RecommendedAction.MONITOR,
    "review": RecommendedAction.REVIEW,
    "escalate": RecommendedAction.ESCALATE,
}


def _create_assessment_log(
    session: AsyncSession,
    paper: Paper,
    llm_result: LLMResult,
    model: str,
    user_message: str,
) -> None:
    """Create an AssessmentLog entry from an LLM result."""
    session.add(
        AssessmentLog(
            paper_id=paper.id,
            stage="methods_analysis",
            model_used=model,
            prompt_version=METHODS_ANALYSIS_VERSION,
            prompt_text=user_message,
            raw_response=llm_result.raw_response,
            parsed_result=llm_result.tool_input if not llm_result.error else None,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            cost_estimate_usd=llm_result.cost_estimate_usd,
            error=llm_result.error,
        )
    )


def _apply_result(paper: Paper, tool_input: dict) -> None:
    """Apply the LLM assessment result to the paper record."""
    paper.stage2_result = tool_input
    paper.aggregate_score = tool_input.get("aggregate_score")
    paper.risk_tier = _RISK_TIER_MAP.get(tool_input.get("risk_tier", ""))
    paper.recommended_action = _ACTION_MAP.get(tool_input.get("recommended_action", ""))
    paper.pipeline_stage = PipelineStage.METHODS_ANALYSED


async def run_methods_analysis(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    use_batch: bool,
    model: str,
) -> None:
    """Run Stage 4 methods analysis on a list of papers."""
    if not papers:
        return

    if use_batch:
        await _run_batch(session, llm_client, papers, model)
    else:
        await _run_sync(session, llm_client, papers, model)


async def _run_sync(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
) -> None:
    """Process papers one at a time."""
    for paper in papers:
        user_msg = format_methods_analysis_message(
            paper.title, paper.abstract or "", methods=paper.methods_section
        )

        llm_result = await llm_client.call_tool(
            model=model,
            system_prompt=METHODS_ANALYSIS_SYSTEM_PROMPT,
            user_message=user_msg,
            tool=ASSESS_DURC_RISK_TOOL,
        )

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning(
                "methods_analysis_error", paper_id=str(paper.id), error=llm_result.error
            )
            continue

        _apply_result(paper, llm_result.tool_input)
        log.info(
            "methods_analysis_complete",
            paper_id=str(paper.id),
            risk_tier=paper.risk_tier,
            aggregate_score=paper.aggregate_score,
        )
        await session.flush()

    log.info("methods_analysis_sync_complete", total=len(papers))


async def _run_batch(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
) -> None:
    """Process papers via the batch API."""
    messages = []
    paper_map: dict[str, tuple[Paper, str]] = {}

    for paper in papers:
        user_msg = format_methods_analysis_message(
            paper.title, paper.abstract or "", methods=paper.methods_section
        )
        custom_id = str(paper.id)
        messages.append((custom_id, user_msg))
        paper_map[custom_id] = (paper, user_msg)

    batch_id = await llm_client.submit_batch(
        model=model,
        system_prompt=METHODS_ANALYSIS_SYSTEM_PROMPT,
        messages=messages,
        tool=ASSESS_DURC_RISK_TOOL,
    )

    results = await llm_client.collect_batch(batch_id, model=model)

    for custom_id, (paper, user_msg) in paper_map.items():
        llm_result = results.get(custom_id)
        if llm_result is None:
            log.warning("methods_analysis_missing_result", paper_id=custom_id)
            continue

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning(
                "methods_analysis_error", paper_id=custom_id, error=llm_result.error
            )
            continue

        _apply_result(paper, llm_result.tool_input)

    await session.flush()
    log.info("methods_analysis_batch_complete", total=len(papers))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_methods_analysis.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix pipeline/triage/methods_analysis.py tests/test_methods_analysis.py
uv run ruff format pipeline/triage/methods_analysis.py tests/test_methods_analysis.py
git add pipeline/triage/methods_analysis.py tests/test_methods_analysis.py
git commit -m "feat: add methods analysis with 6-dimension risk rubric"
```

---

### Task 11: Final integration verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS. Expected test counts:
- `test_config.py`: 5 tests
- `test_models.py`: 4 tests
- `test_db.py`: 3 tests
- `test_ingest.py`: existing bioRxiv tests
- `test_dedup.py`: existing dedup tests
- `test_europepmc.py`: 14 tests
- `test_pubmed.py`: 25 tests
- `test_prompts.py`: 11 tests
- `test_llm.py`: ~13 tests
- `test_coarse_filter.py`: 5 tests
- `test_jats_parser.py`: 7 tests
- `test_html_parser.py`: 6 tests
- `test_unpaywall.py`: 6 tests
- `test_retriever.py`: 5 tests
- `test_methods_analysis.py`: 5 tests

- [ ] **Step 2: Run lint and format checks**

Run: `uv run ruff check pipeline/ tests/ && uv run ruff format --check pipeline/ tests/`
Expected: All checks passed

- [ ] **Step 3: Verify imports are clean**

Run: `uv run python -c "from pipeline.triage.coarse_filter import run_coarse_filter; from pipeline.triage.methods_analysis import run_methods_analysis; from pipeline.fulltext.retriever import retrieve_full_text; print('All imports OK')"`
Expected: `All imports OK`
