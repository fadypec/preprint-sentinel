"""Centralised prompt templates and tool schemas for the triage pipeline.

Every prompt has a version string stored alongside each AssessmentLog entry,
enabling prompt regression tracking.
"""

# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

COARSE_FILTER_VERSION = "v1.0"
METHODS_ANALYSIS_VERSION = "v1.0"
ADJUDICATION_VERSION = "v1.0"

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

ADJUDICATION_SYSTEM_PROMPT = """\
You are a senior biosecurity expert conducting contextual adjudication of a paper \
that has been flagged as potentially dual-use research of concern (DURC). You have \
access to the paper's abstract, methods section, the Stage 4 risk assessment, and \
enrichment data about the authors and institution.

Your task is to provide a contextual assessment considering:

1. **Author credibility**: Is the research group well-established in this field? \
Consider their h-index, citation counts, publication volume, and institutional affiliation.

2. **Institutional context**: Is the institution known for responsible dual-use research? \
Is it a major research university, government lab, or biodefense facility with oversight?

3. **Funding oversight**: Is the work funded by an agency with DURC review processes \
(e.g., NIH, BARDA, DTRA, BBSRC, Wellcome Trust)? Funded research at these agencies \
undergoes institutional biosafety committee (IBC) review.

4. **Research context**: Does the work duplicate or extend previously published dual-use \
research? Is this incremental in a well-governed research programme, or a concerning \
new direction from an unexpected source?

5. **Enrichment completeness**: If enrichment data is partial (some sources failed), \
note which sources were unavailable and how that limits your confidence. Reduce your \
confidence score accordingly.

You may adjust the risk tier UP or DOWN based on contextual factors. For example:
- A paper from a well-known virology lab with NIH funding and IBC approval described \
in the methods may warrant DOWNgrading from "high" to "medium".
- A paper with no institutional affiliation, no ORCID, and unusually detailed synthesis \
protocols may warrant UPgrading.

Always explain your reasoning clearly. The analyst reviewing your assessment needs to \
understand exactly why the tier was adjusted (or confirmed).

Use the adjudicate_paper tool to report your assessment."""

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
        "Classify whether a paper is potentially relevant to dual-use research of concern."
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

ADJUDICATE_PAPER_TOOL: dict = {
    "name": "adjudicate_paper",
    "description": "Provide contextual adjudication of a DURC-flagged paper.",
    "input_schema": {
        "type": "object",
        "properties": {
            "adjusted_risk_tier": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "adjusted_action": {
                "type": "string",
                "enum": ["archive", "monitor", "review", "escalate"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "Confidence in this adjudication, "
                    "reduced when enrichment is partial"
                ),
            },
            "partial_enrichment": {
                "type": "boolean",
                "description": "True if enrichment data was incomplete",
            },
            "missing_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Enrichment sources that failed",
            },
            "institutional_context": {
                "type": "string",
                "description": (
                    "Assessment of institutional/author credibility "
                    "and oversight context"
                ),
            },
            "durc_oversight_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Evidence of DURC oversight "
                    "(IBC approval, DURC review, biosafety protocols)"
                ),
            },
            "adjustment_reasoning": {
                "type": "string",
                "description": "Why the risk tier was adjusted (or confirmed)",
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence contextual assessment",
            },
        },
        "required": [
            "adjusted_risk_tier",
            "adjusted_action",
            "confidence",
            "partial_enrichment",
            "missing_sources",
            "institutional_context",
            "durc_oversight_indicators",
            "adjustment_reasoning",
            "summary",
        ],
    },
}

# ---------------------------------------------------------------------------
# User message formatting
# ---------------------------------------------------------------------------


def format_coarse_filter_message(title: str, abstract: str) -> str:
    """Format the user message for Stage 2 coarse filter."""
    return f"Paper title: {title}\nAbstract: {abstract}"


def format_methods_analysis_message(title: str, abstract: str, methods: str | None) -> str:
    """Format the user message for Stage 4 methods analysis."""
    if methods:
        return f"Paper title: {title}\nAbstract: {abstract}\nMethods section: {methods}"
    return (
        f"Paper title: {title}\nAbstract: {abstract}\n\n"
        "NOTE: Full text was not available for this paper. "
        "Assess based on the abstract only. Note this limitation in your summary."
    )


def format_adjudication_message(
    title: str,
    abstract: str,
    methods: str | None,
    stage2_result: dict,
    enrichment_data: dict,
    sources_failed: list[str],
) -> str:
    """Format the user message for Stage 5 adjudication."""
    import json

    parts = [
        f"Paper title: {title}",
        f"Abstract: {abstract}",
    ]

    if methods:
        parts.append(f"Methods section: {methods}")
    else:
        parts.append("Methods section: Not available.")

    parts.append(f"Stage 4 risk assessment: {json.dumps(stage2_result, indent=2)}")
    parts.append(f"Enrichment data: {json.dumps(enrichment_data, indent=2)}")

    if sources_failed:
        parts.append(
            f"WARNING: The following enrichment sources failed and their data is unavailable: "
            f"{', '.join(sources_failed)}. Reduce confidence accordingly."
        )

    return "\n\n".join(parts)
