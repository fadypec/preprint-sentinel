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
        assert call_kwargs["messages"] == [{"role": "user", "content": "User message here"}]

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
            mock_client.messages.create = AsyncMock(side_effect=[overloaded_error, mock_response])
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
        # Response with text block instead of tool_use
        from anthropic.types import TextBlock

        from pipeline.triage.llm import LLMClient

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
