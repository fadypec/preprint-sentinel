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
