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


class TestAdjudicationPromptConstants:
    """Verify adjudication prompt constants exist and are well-formed."""

    def test_adjudication_version_exists(self):
        from pipeline.triage.prompts import ADJUDICATION_VERSION

        assert isinstance(ADJUDICATION_VERSION, str)
        assert ADJUDICATION_VERSION.startswith("v")

    def test_adjudication_system_prompt_exists(self):
        from pipeline.triage.prompts import ADJUDICATION_SYSTEM_PROMPT

        assert isinstance(ADJUDICATION_SYSTEM_PROMPT, str)
        assert len(ADJUDICATION_SYSTEM_PROMPT) > 100
        assert "dual-use" in ADJUDICATION_SYSTEM_PROMPT.lower()
        assert "institutional" in ADJUDICATION_SYSTEM_PROMPT.lower()
        assert "enrichment" in ADJUDICATION_SYSTEM_PROMPT.lower()


class TestAdjudicateToolSchema:
    """Verify adjudication tool schema is valid."""

    def test_adjudicate_paper_tool_structure(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        assert ADJUDICATE_PAPER_TOOL["name"] == "adjudicate_paper"
        schema = ADJUDICATE_PAPER_TOOL["input_schema"]
        assert "adjusted_risk_tier" in schema["properties"]
        assert "adjusted_action" in schema["properties"]
        assert "confidence" in schema["properties"]
        assert "partial_enrichment" in schema["properties"]
        assert "missing_sources" in schema["properties"]
        assert "institutional_context" in schema["properties"]
        assert "durc_oversight_indicators" in schema["properties"]
        assert "adjustment_reasoning" in schema["properties"]
        assert "summary" in schema["properties"]

    def test_adjudicate_paper_tool_required_fields(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        schema = ADJUDICATE_PAPER_TOOL["input_schema"]
        required = set(schema["required"])
        expected = {
            "adjusted_risk_tier",
            "adjusted_action",
            "confidence",
            "partial_enrichment",
            "missing_sources",
            "institutional_context",
            "durc_oversight_indicators",
            "adjustment_reasoning",
            "summary",
        }
        assert required == expected

    def test_adjusted_risk_tier_enum(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        tier = ADJUDICATE_PAPER_TOOL["input_schema"]["properties"]["adjusted_risk_tier"]
        assert tier["enum"] == ["low", "medium", "high", "critical"]

    def test_adjusted_action_enum(self):
        from pipeline.triage.prompts import ADJUDICATE_PAPER_TOOL

        action = ADJUDICATE_PAPER_TOOL["input_schema"]["properties"]["adjusted_action"]
        assert action["enum"] == ["archive", "monitor", "review", "escalate"]


class TestAdjudicationMessageFormatting:
    """Verify adjudication message formatting."""

    def test_format_with_all_data(self):
        from pipeline.triage.prompts import format_adjudication_message

        msg = format_adjudication_message(
            title="H5N1 GoF Paper",
            abstract="We enhanced transmissibility.",
            methods="Serial passage in ferrets.",
            stage2_result={"risk_tier": "high", "aggregate_score": 10},
            enrichment_data={"openalex": {"primary_institution": "MIT"}},
            sources_failed=[],
        )
        assert "H5N1 GoF Paper" in msg
        assert "We enhanced transmissibility." in msg
        assert "Serial passage in ferrets." in msg
        assert "high" in msg
        assert "MIT" in msg

    def test_format_without_methods(self):
        from pipeline.triage.prompts import format_adjudication_message

        msg = format_adjudication_message(
            title="Title",
            abstract="Abstract",
            methods=None,
            stage2_result={"risk_tier": "high"},
            enrichment_data={},
            sources_failed=["semantic_scholar"],
        )
        assert "Title" in msg
        assert "Abstract" in msg
        assert "methods" in msg.lower() or "not available" in msg.lower()
        assert "semantic_scholar" in msg

    def test_format_with_enrichment_failures(self):
        from pipeline.triage.prompts import format_adjudication_message

        msg = format_adjudication_message(
            title="Title",
            abstract="Abstract",
            methods=None,
            stage2_result={},
            enrichment_data={},
            sources_failed=["openalex", "orcid"],
        )
        assert "openalex" in msg
        assert "orcid" in msg
