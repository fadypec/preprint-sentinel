# Phase 2, Sub-project 2: Triage Pipeline (Stages 2–4)

## Goal

Build the core AI classification chain from coarse filter through methods analysis. Papers flow through three stages: Haiku binary screening, full-text retrieval, and Sonnet risk rubric assessment. Every LLM call is auditable via AssessmentLog. Both synchronous and batch (50% cheaper) execution modes are supported via a config toggle.

## Architecture

```
INGESTED papers
    → Stage 2: Coarse Filter (Haiku)
        → ~95% discarded, ~5% pass
    → Stage 3: Full-Text Retrieval
        → Cascade: bioRxiv XML → Europe PMC → PMC OA → Unpaywall
        → Falls back to abstract-only if all sources fail
    → Stage 4: Methods Analysis (Sonnet)
        → 6-dimension risk rubric scoring
        → Sets risk_tier, aggregate_score, recommended_action
```

Every LLM call (stages 2 and 4) creates an `AssessmentLog` entry. Both stages support two execution modes via a `use_batch_api` config toggle:

- **Sync mode** (default): Individual `client.messages.create()` calls with tool use. Simpler, good for development and testing.
- **Batch mode**: Submit all papers as an Anthropic Message Batch via `client.batches.create()`. 50% cost reduction. Results collected by polling `client.batches.retrieve()`. Each request uses `custom_id` = paper UUID for result mapping.

Both modes use identical prompt templates and tool-use schemas from `pipeline/triage/prompts.py`.

## Components

### 1. Prompt Templates (`pipeline/triage/prompts.py`)

Centralised prompt templates with version tracking. Each prompt is a named constant with a version string.

**Constants:**

- `COARSE_FILTER_SYSTEM_PROMPT` — system message for Stage 2 Haiku screening
- `COARSE_FILTER_VERSION = "v1.0"` — stored in AssessmentLog for every call
- `METHODS_ANALYSIS_SYSTEM_PROMPT` — system message for Stage 4 Sonnet assessment
- `METHODS_ANALYSIS_VERSION = "v1.0"`

**Tool-use schemas** defined as Python dicts matching Anthropic's tool format:

**Coarse filter tool (`classify_paper`):**
```json
{
    "name": "classify_paper",
    "description": "Classify whether a paper is potentially relevant to dual-use research of concern.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reason": {"type": "string", "description": "One sentence explanation"}
        },
        "required": ["relevant", "confidence", "reason"]
    }
}
```

**Methods analysis tool (`assess_durc_risk`):**
```json
{
    "name": "assess_durc_risk",
    "description": "Assess a paper against the 6-dimension DURC risk rubric.",
    "input_schema": {
        "type": "object",
        "properties": {
            "dimensions": {
                "type": "object",
                "properties": {
                    "pathogen_enhancement": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "integer", "minimum": 0, "maximum": 3},
                            "justification": {"type": "string"}
                        },
                        "required": ["score", "justification"]
                    },
                    "synthesis_barrier_lowering": {"type": "object", "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 3}, "justification": {"type": "string"}}, "required": ["score", "justification"]},
                    "select_agent_relevance": {"type": "object", "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 3}, "justification": {"type": "string"}}, "required": ["score", "justification"]},
                    "novel_technique": {"type": "object", "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 3}, "justification": {"type": "string"}}, "required": ["score", "justification"]},
                    "information_hazard": {"type": "object", "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 3}, "justification": {"type": "string"}}, "required": ["score", "justification"]},
                    "defensive_framing": {"type": "object", "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 3}, "justification": {"type": "string"}}, "required": ["score", "justification"]}
                },
                "required": ["pathogen_enhancement", "synthesis_barrier_lowering", "select_agent_relevance", "novel_technique", "information_hazard", "defensive_framing"]
            },
            "aggregate_score": {"type": "integer", "minimum": 0, "maximum": 18},
            "risk_tier": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "summary": {"type": "string", "description": "2-3 sentence overall assessment"},
            "key_methods_of_concern": {"type": "array", "items": {"type": "string"}},
            "recommended_action": {"type": "string", "enum": ["archive", "monitor", "review", "escalate"]}
        },
        "required": ["dimensions", "aggregate_score", "risk_tier", "summary", "key_methods_of_concern", "recommended_action"]
    }
}
```

**Coarse filter system prompt** (from CLAUDE.md, adapted for tool use):

```
You are a biosecurity screening assistant. Your task is to determine whether a scientific paper's abstract suggests it MAY be relevant to dual-use research of concern (DURC) in the biological sciences.

A paper is RELEVANT if its abstract suggests ANY of the following:
- Enhancement of pathogen transmissibility, virulence, host range, or immune evasion
- Reconstruction or synthesis of dangerous pathogens (select agents, PPPs, or novel threats)
- Novel methods for producing biological toxins or bioactive compounds with harm potential
- Techniques that could lower barriers to creating biological weapons (simplified reverse genetics, benchtop synthesis protocols, democratised access to dangerous capabilities)
- Gain-of-function research on potential pandemic pathogens
- Novel delivery mechanisms for biological agents (aerosol, vector-based, environmental release)
- Identification of novel vulnerabilities in human, animal, or plant biology that could be exploited
- Work on agents listed under the Australia Group, BWC, or national select agent regulations
- De novo protein design or directed evolution of proteins with potential toxin-like or pathogen-enhancing functions
- Dual-use research on prions, mirror-life organisms, or xenobiology
- AI/ML methods specifically applied to pathogen enhancement, toxin design, or bioweapon-relevant optimisation

A paper is NOT RELEVANT if it is:
- Standard clinical research, epidemiology, public health surveillance (unless involving enhanced pathogens)
- Drug discovery, vaccine development, or diagnostics (unless the methods themselves are dual-use)
- Basic molecular biology, structural biology, or biochemistry with no obvious dual-use application
- Ecology, environmental science, agriculture (unless involving biological control agents with crossover potential)
- Pure computational biology, bioinformatics methods papers (unless specifically applied to the above)

You MUST err on the side of flagging. If there is ANY ambiguity, flag it as RELEVANT.

Use the classify_paper tool to report your assessment.
```

**Methods analysis system prompt** (from CLAUDE.md, adapted for tool use):

```
You are a dual-use research of concern (DURC) risk assessor with deep expertise in microbiology, virology, synthetic biology, and biosecurity policy. You are reviewing a scientific paper that has been flagged as potentially relevant to DURC.

Assess this paper against each of the following risk dimensions. For each dimension, provide a score (0-3) and a brief justification.

## Risk dimensions

1. **Pathogen enhancement** (0-3): Does the paper describe experimental enhancement of pathogen transmissibility, virulence, host range, immune evasion, or drug resistance? Score 0 if no enhancement work. Score 1 if indirect (e.g., characterisation that could inform enhancement). Score 2 if methods could be adapted for enhancement. Score 3 if direct enhancement is described.

2. **Synthesis/reconstruction barrier lowering** (0-3): Do the methods lower technical barriers to synthesising or reconstructing dangerous pathogens? Consider: are protocols unusually detailed? Are simplified or novel techniques described that make previously difficult work accessible? Score 0-3 based on degree of barrier lowering.

3. **Select agent / PPP relevance** (0-3): Does the work involve pathogens on the WHO, Australia Group, CDC Select Agent, or ACDP Hazard Group 3/4 lists? Or potential pandemic pathogens? Score 0 if no relevant agents. Score 1 for Hazard Group 2 / non-select agents. Score 2 for HG3 / select agents. Score 3 for HG4 / PPPs / Tier 1 select agents.

4. **Novelty of dual-use technique** (0-3): Does the paper describe a genuinely novel technique, tool, or approach that has dual-use potential? Score 0 for well-established methods. Score 1 for incremental improvements. Score 2 for significant methodological advances. Score 3 for transformative new capabilities.

5. **Information hazard** (0-3): Does the paper provide specific, actionable information that could be directly misused (exact sequences, detailed protocols, step-by-step synthesis routes)? Score 0 if information is generic or already widely known. Score 3 if the paper is essentially a recipe.

6. **Defensive framing adequacy** (0-3, inverse): Does the paper adequately discuss dual-use implications, describe risk mitigation measures, or frame the work in a defensive context? Score 0 if the paper has robust dual-use discussion and risk mitigation. Score 3 if there is NO mention of dual-use risks despite clearly dual-use methods.

Use the assess_durc_risk tool to report your assessment.
```

**User message templates:**

Coarse filter:
```
Paper title: {title}
Abstract: {abstract}
```

Methods analysis (with full text):
```
Paper title: {title}
Abstract: {abstract}
Methods section: {methods}
```

Methods analysis (abstract only, when full text unavailable):
```
Paper title: {title}
Abstract: {abstract}

NOTE: Full text was not available for this paper. Assess based on the abstract only. Note this limitation in your summary.
```

### 2. LLM Infrastructure (`pipeline/triage/llm.py`)

Shared LLM calling layer wrapping the Anthropic SDK.

**Class: `LLMClient`**

**Result dataclass:**
```python
@dataclass
class LLMResult:
    tool_input: dict          # The parsed tool input dict (the structured output)
    raw_response: str         # Full API response text for audit
    input_tokens: int         # From response.usage
    output_tokens: int        # From response.usage
    cost_estimate_usd: float  # Calculated from tokens + model pricing
    error: str | None = None  # Error message if the call failed
```

**Class: `LLMClient`**

```python
class LLMClient:
    def __init__(self, api_key: str) -> None: ...

    async def call_tool(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        tool: dict,
        max_retries: int = 3,
    ) -> LLMResult:
        """Make a single tool-use call. Returns an LLMResult with parsed output and metadata."""

    async def submit_batch(
        self,
        model: str,
        system_prompt: str,
        messages: list[tuple[str, str]],  # [(custom_id, user_message), ...]
        tool: dict,
    ) -> str:
        """Submit a message batch. Returns batch_id."""

    async def collect_batch(self, batch_id: str) -> dict[str, LLMResult]:
        """Poll until batch completes. Returns {custom_id: LLMResult}."""
```

The LLM layer is database-free. Callers (coarse_filter, methods_analysis) receive `LLMResult` objects and are responsible for creating `AssessmentLog` entries using the metadata plus their own context (`paper_id`, `stage`, `prompt_version`).

**Retry logic for `call_tool`:**
- Retry on Anthropic `overloaded_error`, `rate_limit_error`, and `APITimeoutError`
- Exponential backoff: `min(2**attempt, 30)` seconds
- Max 3 retries (configurable)
- On final failure: raise

**Cost calculation** (inside `LLMResult` construction):
- Haiku: $0.80/MTok input, $4.00/MTok output
- Sonnet: $3.00/MTok input, $15.00/MTok output
- Batch mode: multiply by 0.5

**Batch mode mechanics:**
- `submit_batch` builds a list of request dicts with `custom_id` = paper UUID string
- Each request contains the same `model`, `system`, `tools`, and per-paper `messages`
- Submits via `client.batches.create(requests=...)`
- `collect_batch` polls with exponential backoff (start at 30s, cap at 5 minutes) until `processing_status == "ended"`
- Iterates `client.batches.results(batch_id)`, extracts tool input from each result, maps back by `custom_id`
- Failed individual requests within the batch return `LLMResult` with `error` set and `tool_input` empty

### 3. Coarse Filter (`pipeline/triage/coarse_filter.py`)

**Function: `async def run_coarse_filter(session, llm_client, papers, use_batch)`**

Processes a list of `INGESTED` papers through Haiku screening.

**Sync mode (`use_batch=False`):**
```
for each paper:
    llm_result = llm_client.call_tool(stage1_model, COARSE_FILTER_SYSTEM_PROMPT, user_msg, classify_paper_tool)
    paper.stage1_result = llm_result.tool_input
    paper.pipeline_stage = COARSE_FILTERED
    create AssessmentLog from llm_result + paper_id + stage + prompt_version
    if llm_result.tool_input["relevant"] or llm_result.tool_input["confidence"] <= coarse_filter_threshold:
        yield paper  # passes to stage 3
    session.flush()
```

**Batch mode (`use_batch=True`):**
```
batch_id = llm_client.submit_batch(stage1_model, prompt, [(str(paper.id), msg) for paper in papers], tool)
results = llm_client.collect_batch(batch_id)
for paper in papers:
    llm_result = results.get(str(paper.id))
    # same logic as sync mode — store result, create AssessmentLog, apply filter
```

**Filter logic:** A paper passes the coarse filter if:
- `relevant == True` (regardless of confidence), OR
- `relevant == False` but `confidence <= coarse_filter_threshold` (borderline — we err on inclusion)

This means only papers where the model is confident they are NOT relevant get filtered out.

### 4. Full-Text Retriever (`pipeline/fulltext/retriever.py`)

**Function: `async def retrieve_full_text(session, paper, settings)`**

Tries four sources in priority order. First success wins.

**Source cascade:**

1. **bioRxiv/medRxiv TDM XML** — only for papers where `source_server in (BIORXIV, MEDRXIV)` and `doi` is set.
   - URL: `https://www.biorxiv.org/content/{doi}.full.xml`
   - Returns JATS XML → pass to `jats_parser.extract_methods()`

2. **Europe PMC full text** — for any paper with a DOI.
   - URL: `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&resultType=core&format=json` to get the source/id, then `https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/fullTextXML`
   - Returns JATS XML → pass to `jats_parser.extract_methods()`

3. **PubMed Central OA** — for papers where `full_text_url` contains a PMC ID.
   - URL: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmcid}&rettype=xml`
   - Returns JATS XML → pass to `jats_parser.extract_methods()`

4. **Unpaywall** — for any paper with a DOI.
   - Calls `unpaywall.py` to get best OA URL.
   - If URL points to XML: fetch and parse with `jats_parser.extract_methods()`
   - If URL points to HTML: fetch and parse with `html_parser.extract_methods()`
   - If URL points to PDF: skip (PDF extraction out of scope)

**After cascade:**
- Success: `paper.full_text_content = full_text`, `paper.methods_section = methods_text`, `paper.full_text_retrieved = True`
- Failure: `paper.full_text_retrieved = False`, `paper.methods_section = None`
- Either way: `paper.pipeline_stage = FULLTEXT_RETRIEVED`

Each HTTP request in the cascade uses the same retry pattern (exponential backoff on 429/503/timeout) and respects `fulltext_request_delay`.

### 5. JATS Parser (`pipeline/fulltext/jats_parser.py`)

**Function: `def extract_methods(xml_bytes: bytes) -> tuple[str, str]`**

Returns `(full_text, methods_section)`.

**Methods section detection** (in priority order):
1. `<sec sec-type="methods">` — explicit JATS tagging
2. `<sec sec-type="materials|methods">` or `<sec sec-type="materials">` — alternative tagging
3. Any `<sec>` where the `<title>` text matches (case-insensitive): "Methods", "Materials and Methods", "Materials & Methods", "Experimental Procedures", "Experimental Methods", "Study Methods"
4. If no methods section found: return the full body text as both values

**Full text extraction:** Concatenate all text content from `<body>` elements, stripping XML tags.

**Parser safety:** Uses `etree.XMLParser(resolve_entities=False, no_network=True)` — same hardened configuration as the PubMed client.

### 6. HTML Parser (`pipeline/fulltext/html_parser.py`)

**Function: `def extract_methods(html_bytes: bytes) -> tuple[str, str]`**

Returns `(full_text, methods_section)`.

**Methods section detection:**
1. Find heading elements (`h1`-`h4`) whose text matches the same patterns as the JATS parser
2. Extract all content between that heading and the next heading at the same level
3. If no methods heading found: return full body text as both values

**Cleanup:** Strip `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>` elements before extraction. Use `lxml.html` for parsing.

### 7. Unpaywall Client (`pipeline/fulltext/unpaywall.py`)

**Class: `UnpaywallClient`**

Follows the established async context manager pattern.

```python
class UnpaywallClient:
    def __init__(self, email: str, request_delay: float = 0.1, max_retries: int = 3): ...
    async def __aenter__(self) -> UnpaywallClient: ...
    async def __aexit__(self, *exc) -> None: ...
    async def lookup(self, doi: str) -> UnpaywallResult | None: ...
```

**`UnpaywallResult`** dataclass:
```python
@dataclass
class UnpaywallResult:
    url: str
    content_type: str  # "xml", "html", "pdf", "unknown"
    host_type: str     # "publisher", "repository"
```

**URL selection logic:**
- From the Unpaywall response `best_oa_location`, extract `url_for_pdf` and `url_for_landing_page`
- Prefer URLs ending in `.xml` → content_type "xml"
- Then URLs from known JATS hosts (europepmc, ncbi) → content_type "xml"
- Then other URLs → fetch HEAD request, check Content-Type header
- PDF URLs → content_type "pdf" (caller skips these)
- Everything else → content_type "html"

**Retry:** Same pattern as other API clients — exponential backoff on 429/503/timeout.

## Configuration Changes

Three new fields in `Settings`:

```python
# Batch API toggle
use_batch_api: bool = False

# Unpaywall rate limiting
unpaywall_request_delay: float = 0.1

# Full-text retrieval rate limiting
fulltext_request_delay: float = 1.0
```

Existing fields used: `stage1_model`, `stage2_model`, `coarse_filter_threshold`, `anthropic_api_key`, `unpaywall_email`, `ncbi_api_key`.

## Testing Strategy

### Prompt Tests (`tests/test_prompts.py`)
1. Prompt constants exist and have non-empty version strings
2. Tool schemas are valid JSON Schema (validate with `jsonschema` or manual structure check)
3. Regression fixture — 10+ paper abstracts with expected coarse filter outcomes

### LLM Infrastructure Tests (`tests/test_llm.py`)
1. `call_tool` — mock Anthropic SDK, verify tool input extracted from response
2. `call_tool` retry on overloaded — mock 529 then success, verify retry
3. `call_tool` retry exhausted — verify raises after max retries
4. AssessmentLog creation — verify all fields populated (tokens, cost, prompt version, raw response)
5. Cost calculation — verify per-model pricing math for both sync and batch modes
6. `submit_batch` — mock batch creation, verify request structure
7. `collect_batch` — mock polling sequence (processing → ended), verify result mapping by custom_id

### Coarse Filter Tests (`tests/test_coarse_filter.py`)
1. Relevant paper advances — `relevant=True` → pipeline_stage becomes COARSE_FILTERED and paper is yielded
2. Irrelevant high-confidence paper filtered — `relevant=False, confidence=0.95` → paper stops
3. Irrelevant low-confidence paper passes — `relevant=False, confidence=0.6` → paper advances (errs on inclusion)
4. `stage1_result` stored correctly on the paper
5. Batch mode — mock batch submission/collection, verify same filter logic applied

### Full-Text Retriever Tests (`tests/test_retriever.py`)
1. Source 1 succeeds — bioRxiv XML fetched and parsed, sources 2-4 not called
2. Source 1 fails, source 2 succeeds — Europe PMC used
3. All sources fail — paper advances with `full_text_retrieved=False`
4. PMC source used when `full_text_url` has PMC ID
5. Unpaywall XML URL → JATS parser
6. Unpaywall HTML URL → HTML parser
7. Unpaywall PDF URL → skipped, next source tried (or failure)
8. Pipeline stage set to FULLTEXT_RETRIEVED regardless of success/failure

### JATS Parser Tests (`tests/test_jats_parser.py`)
1. `sec-type="methods"` found and extracted
2. `sec-type="materials|methods"` variant
3. Heading-text fallback — `<title>Materials and Methods</title>`
4. No methods section — returns full body text
5. Inline markup stripped from extracted text
6. Parser uses hardened XMLParser settings

Fixture file: `tests/fixtures/sample_jats.xml` — realistic JATS article with methods section.

### HTML Parser Tests (`tests/test_html_parser.py`)
1. Methods heading found — extracts section content
2. No methods heading — returns full body text
3. Script/style/nav elements stripped
4. Handles nested headings correctly

### Unpaywall Tests (`tests/test_unpaywall.py`)
1. Successful lookup — returns best OA URL with correct content_type
2. No OA copy found — returns None
3. Content-type detection — XML, HTML, PDF URLs classified correctly
4. Retry on 429/503 — same pattern as other API clients
5. DOI not found (404) — returns None

## Error Handling

- **LLM transient errors** (529 overloaded, rate limited, timeout): Retry up to 3 times with exponential backoff, same pattern as ingest clients.
- **LLM content errors** (tool use returns unexpected structure despite schema): Log full response in AssessmentLog with `error` field, skip paper, leave at current pipeline stage for manual review.
- **Full-text HTTP errors**: Each source in the cascade catches its own errors. Failure means trying the next source. Complete cascade failure is graceful — paper still advances.
- **Batch processing errors**: Individual failed requests within a batch are logged and skipped. Other results in the batch are processed normally.
- **Database errors**: Each paper is processed in its own flush. One failure does not block the batch.

## Security Considerations

- **No new secrets.** Uses existing `anthropic_api_key` and `unpaywall_email` from config.
- **XML parsing:** All `lxml.etree` usage uses `XMLParser(resolve_entities=False, no_network=True)` to prevent XXE attacks from fetched full-text XML.
- **HTML parsing:** `lxml.html` is used for Unpaywall HTML results. HTML content is parsed for text extraction only — never rendered or served to users.
- **LLM prompt injection:** Paper titles and abstracts are passed as user messages, not system prompts. The tool-use schema constrains the output format. Malicious content in papers cannot override the system prompt.

## Dependencies

No new Python packages required. `anthropic`, `httpx`, `lxml`, `structlog`, and `respx` are already in `pyproject.toml`.

## No Schema or Migration Changes

The existing database schema fully supports the triage pipeline:
- `PipelineStage` enum already includes all stage values
- `stage1_result`, `stage2_result` JSON columns exist
- `risk_tier`, `aggregate_score`, `recommended_action` columns exist
- `full_text_content`, `methods_section`, `full_text_retrieved` columns exist
- `AssessmentLog` table exists with all required fields
