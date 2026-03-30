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
                    isinstance(exc, APIStatusError) and exc.status_code in _RETRYABLE_STATUS_CODES
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
