# Phase 2, Sub-project 1: Additional Ingest Clients (Europe PMC + PubMed)

## Goal

Add two Tier 1 data sources — Europe PMC and PubMed — to the ingestion pipeline, following the established async client pattern from `BiorxivClient`. Europe PMC provides broad preprint coverage across 35+ servers. PubMed provides published journal article coverage. Together with bioRxiv/medRxiv, these three clients cover the primary literature sources defined in the project spec.

## Architecture

Both clients follow the same pattern as `pipeline/ingest/biorxiv.py`:
- Async context manager (`__aenter__`/`__aexit__`) wrapping an `httpx.AsyncClient`
- `fetch_papers(from_date, to_date)` returning `AsyncGenerator[dict, None]`
- Internal pagination handling (caller sees a flat stream of normalised dicts)
- Configurable rate limiting with exponential backoff on 429/503/timeout
- Field normalisation to the common metadata schema used by the rest of the pipeline

All ingested papers pass through the existing three-tier `DedupEngine` before insertion. No changes to the dedup logic are needed.

## Components

### 1. Europe PMC Client (`pipeline/ingest/europepmc.py`)

**API:** `https://www.ebi.ac.uk/europepmc/webservices/rest/search`

**Query construction:**
- Date range filter: `FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD]`
- Preprint filter: `SRC:PPR`
- Combined: `(FIRST_PDATE:[2026-03-01 TO 2026-03-01]) AND SRC:PPR`
- Format: `resultType=core&format=json` (core includes abstracts)
- Page size: `pageSize=1000` (Europe PMC supports up to 1000)

**Pagination:** Cursor-based using `cursorMark` parameter.
- First request: `cursorMark=*`
- Each response includes `nextCursorMark`
- Stop when `nextCursorMark` equals the previous cursor (no more results) or when the result list is empty

**Rate limiting:**
- No official rate limit documented; enforce 1 request/second to be polite
- Configurable via `europepmc_request_delay` in Settings
- Retry with exponential backoff on 429, 503, and timeouts (same pattern as bioRxiv)
- Max 3 retries per request

**Response structure:**
```json
{
  "hitCount": 1234,
  "nextCursorMark": "AoE...",
  "resultList": {
    "result": [
      {
        "id": "PPR123456",
        "doi": "10.1101/2026.03.01.123456",
        "title": "...",
        "authorString": "Smith J, Jones A, ...",
        "firstPublicationDate": "2026-03-01",
        "abstractText": "...",
        "source": "PPR",
        "commentCorrection": null,
        "journalInfo": { "journal": { "title": "bioRxiv" } }
      }
    ]
  }
}
```

**Field normalisation:**

| Europe PMC field | Common schema field | Notes |
|-----------------|-------------------|-------|
| `doi` | `doi` | Direct mapping |
| `title` | `title` | Strip whitespace |
| `authorString` | `authors` | Split on `", "` then reassemble as `[{"name": "..."}]`. Europe PMC uses `"Smith J, Jones A"` format (no semicolons). |
| `firstPublicationDate` | `posted_date` | Parse as `date.fromisoformat()` |
| `abstractText` | `abstract` | HTML-unescape |
| `source` / `journalInfo.journal.title` | `source_server` | Always `SourceServer.EUROPEPMC` |
| — | `subject_category` | Not reliably available; set to `None` |
| `doi` prefix or `id` | `full_text_url` | Not available from search; set to `None` |
| — | `version` | Default `1` |
| — | `corresponding_author` | Not available from search; set to `None` |
| — | `corresponding_institution` | Not available from search; set to `None` |

**Author parsing detail:** Europe PMC's `authorString` field uses comma-space between authors: `"Smith J, Jones A, Williams BC"`. Each author name is `"Surname Initials"` (no comma between surname and initials, unlike bioRxiv's `"Surname, I."` format). Split on `", "` to get individual author strings, then store each as `{"name": "Smith J"}`.

**Overlap handling:** Many Europe PMC preprint records will duplicate bioRxiv/medRxiv records (same DOI). The existing Tier 1 dedup (DOI exact match) handles this. When a duplicate is found, the earlier-ingested record (typically bioRxiv, which has richer metadata including subject categories) is kept as canonical.

### 2. PubMed Client (`pipeline/ingest/pubmed.py`)

**Two-step fetch:** PubMed E-utilities require searching for IDs first, then fetching full records.

**Step 1 — Search (esearch):**
- Endpoint: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi`
- Parameters: `db=pubmed`, `retmode=json`, `retmax=10000`, `usehistory=y`
- Date filter: `datetype=pdat&mindate=YYYY/MM/DD&maxdate=YYYY/MM/DD`
- Auth: `api_key={ncbi_api_key}` (if configured)

**Two query modes** (configurable via `pubmed_query_mode` setting):

1. **`"all"` (default):** Date-range only. No subject filtering. Fetches all articles published on the target date(s). Estimated ~4,500 articles/day. This is the comprehensive mode — every paper goes through the Haiku coarse filter.

2. **`"mesh_filtered"`:** Date-range + a subject filter query. Reduces volume to ~1,000-1,500 articles/day. The filter query is stored in `pubmed_mesh_query` setting and defaults to:

```
(virology[MeSH] OR microbiology[MeSH] OR "synthetic biology"[MeSH] OR
"genetic engineering"[MeSH] OR "gain of function"[tiab] OR
"gain-of-function"[tiab] OR "directed evolution"[tiab] OR
"reverse genetics"[tiab] OR "gene drive"[tiab] OR "gene drives"[tiab] OR
"select agent"[tiab] OR "select agents"[tiab] OR
"dual use"[tiab] OR "dual-use"[tiab] OR
"pathogen enhancement"[tiab] OR "immune evasion"[tiab] OR
"host range"[tiab] OR "transmissibility"[tiab] OR
"virulence factor"[tiab] OR "virulence factors"[tiab] OR
toxins[MeSH] OR "biological warfare"[MeSH] OR "biodefense"[MeSH] OR
CRISPR[tiab] OR "base editing"[tiab] OR
"pandemic preparedness"[tiab] OR "pandemic pathogen"[tiab] OR
"biosafety level"[tiab] OR "BSL-3"[tiab] OR "BSL-4"[tiab] OR
prions[MeSH] OR "mirror life"[tiab] OR "xenobiology"[tiab] OR
"de novo protein design"[tiab] OR "protein design"[tiab] OR
"aerosol transmission"[tiab] OR "airborne transmission"[tiab])
```

This query combines MeSH headings (for indexed articles) with title/abstract text searches (`[tiab]`) to catch recently added articles that lack MeSH indexing. The `[tiab]` terms cover the key DURC signals from the project rubric.

**Step 1 response (esearch):** Returns `webenv` and `query_key` for history server, plus `count` of matching PMIDs.

**Step 2 — Fetch (efetch):**
- Endpoint: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`
- Parameters: `db=pubmed`, `rettype=xml`, `retmode=xml`, `retmax=200`
- Uses `webenv` and `query_key` from esearch (avoids passing large PMID lists in URL)
- Paginates via `retstart` in increments of 200

**Rate limiting:**
- 10 req/s with API key, 3 req/s without
- Configurable via `pubmed_request_delay` (already exists in Settings at 0.1s)
- Retry with exponential backoff on 429, 503, and timeouts
- Max 3 retries per request

**XML parsing (efetch response):**

The efetch response is `PubmedArticleSet` XML. For each `<PubmedArticle>`:

```xml
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <ArticleTitle>...</ArticleTitle>
      <Abstract><AbstractText>...</AbstractText></Abstract>
      <AuthorList>
        <Author>
          <LastName>Smith</LastName>
          <ForeName>John</ForeName>
          <AffiliationInfo><Affiliation>MIT</Affiliation></AffiliationInfo>
        </Author>
      </AuthorList>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1234/...</ArticleId>
        <ArticleId IdType="pmc">PMC1234567</ArticleId>
      </ArticleIdList>
    </Article>
    <MeshHeadingList>
      <MeshHeading><DescriptorName>Virology</DescriptorName></MeshHeading>
    </MeshHeadingList>
  </MedlineCitation>
  <PubmedData>
    <History>
      <PubMedPubDate PubStatus="pubmed">
        <Year>2026</Year><Month>3</Month><Day>1</Day>
      </PubMedPubDate>
    </History>
  </PubmedData>
</PubmedArticle>
```

Parse with `lxml.etree`. Extract into common schema.

**Field normalisation:**

| PubMed XML path | Common schema field | Notes |
|----------------|-------------------|-------|
| `ArticleId[@IdType="doi"]` | `doi` | May be absent for some articles |
| `ArticleTitle` | `title` | Strip whitespace, handle inline markup (`<i>`, `<sub>`, etc. — extract text only) |
| `Author/LastName` + `Author/ForeName` | `authors` | Format as `[{"name": "Smith, J."}]` to match bioRxiv convention |
| `Author[1]/AffiliationInfo/Affiliation` | `corresponding_institution` | First author's affiliation as proxy |
| `AbstractText` | `abstract` | May have multiple `<AbstractText>` with `Label` attrs (Background, Methods, Results, Conclusions) — concatenate with labels |
| `PubMedPubDate[@PubStatus="pubmed"]` | `posted_date` | Construct `date(Year, Month, Day)` |
| `MeshHeading/DescriptorName` | `subject_category` | Join all MeSH terms with `"; "` |
| — | `source_server` | Always `SourceServer.PUBMED` |
| — | `full_text_url` | Set to PMC URL if `ArticleId[@IdType="pmc"]` exists, else `None` |
| — | `version` | Default `1` |

**Structured abstracts:** PubMed articles often have structured abstracts with labeled sections. When multiple `<AbstractText>` elements exist, concatenate them as `"BACKGROUND: ... METHODS: ... RESULTS: ... CONCLUSIONS: ..."` to preserve section context for downstream LLM processing.

### 3. Configuration Changes (`pipeline/config.py`)

Add three new fields to `Settings`:

```python
# Europe PMC
europepmc_request_delay: float = 1.0

# PubMed query mode
pubmed_query_mode: str = "all"       # "all" or "mesh_filtered"
pubmed_mesh_query: str = '(virology[MeSH] OR microbiology[MeSH] OR ...)'  # Full default defined in PubMed Client section above
```

`pubmed_request_delay` already exists (0.1s). `ncbi_api_key` already exists (empty string default).

### 4. No Schema or Migration Changes

The existing database schema fully supports both new sources:
- `SourceServer` enum already includes `EUROPEPMC` and `PUBMED`
- All metadata fields map to existing `Paper` columns
- Dedup engine works on the common schema without modification

## Testing Strategy

### Europe PMC Tests (`tests/test_europepmc.py`)

**Unit tests (mocked with `respx`):**
1. **Field normalisation** — single record with all fields populated; verify correct mapping
2. **Author parsing** — Europe PMC `"Smith J, Jones A, Williams BC"` format correctly split into `[{"name": "Smith J"}, ...]`
3. **Single-page fetch** — one page of results, verify all records yielded
4. **Cursor-based pagination** — mock two pages with different `cursorMark` values; verify both pages fetched and cursor terminates
5. **Empty results** — response with `hitCount: 0` yields nothing
6. **Rate limiting / retry** — mock 429 response then 200; verify backoff and successful retry
7. **Timeout handling** — mock timeout then success; verify retry

**Fixture file:** `tests/fixtures/sample_europepmc.json` — 5 realistic Europe PMC search results including a bioRxiv cross-post (same DOI as a sample_biorxiv record) for dedup testing.

### PubMed Tests (`tests/test_pubmed.py`)

**Unit tests (mocked with `respx`):**
1. **esearch response parsing** — verify webenv, query_key, count extraction from JSON
2. **efetch XML parsing** — single PubmedArticle with all fields; verify correct field mapping
3. **Author extraction** — multiple authors with LastName/ForeName; verify `"Smith, J."` format
4. **Structured abstract** — multiple `<AbstractText>` with labels; verify concatenation with labels
5. **DOI-less article** — article without DOI; verify `doi=None` and other fields still parsed
6. **Batch pagination** — mock esearch returning count=350, then two efetch pages (200 + 150); verify all records yielded
7. **Query mode "all"** — verify esearch URL has date range only, no MeSH terms
8. **Query mode "mesh_filtered"** — verify esearch URL includes the MeSH query string
9. **Rate limiting / retry** — same pattern as Europe PMC tests
10. **PMC full-text URL** — article with PMC ID; verify `full_text_url` is set

**Fixture file:** `tests/fixtures/sample_pubmed.xml` — 5 realistic PubmedArticle XML records including structured abstracts, MeSH headings, DOIs, and one DOI-less article.

### Integration Tests

**Dedup integration** (in `tests/test_dedup.py` or a new `tests/test_ingest_integration.py`):
1. Insert a paper with DOI `10.1101/xxx` via bioRxiv path. Run dedup check with same DOI from Europe PMC normalised record. Verify Tier 1 match.
2. Insert a paper. Run dedup check with same title/author from PubMed record (different DOI or no DOI). Verify Tier 2/3 match.

## Security Considerations

- **No new secrets introduced.** `ncbi_api_key` is already a config field (non-secret, free NCBI key). Europe PMC requires no auth.
- **XML parsing with `lxml`:** Use `lxml.etree.fromstring()` with default settings (external entity loading is disabled by default in recent lxml). Do NOT use `lxml.etree.XMLParser(resolve_entities=True)`. This prevents XXE attacks from malformed PubMed responses.
- **Input validation:** DOIs, titles, and author strings from external APIs are stored as-is but never interpolated into SQL (SQLAlchemy parameterises all queries). HTML in abstracts is unescaped via `html.unescape()` for readability but never rendered as HTML in the backend.

## Dependencies

No new Python packages required. `httpx`, `lxml`, `structlog`, and `respx` are already in `pyproject.toml`.
