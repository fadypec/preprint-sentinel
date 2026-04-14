# DURC Preprint Triage — Dashboard API Reference

All endpoints are served by the Next.js dashboard application.
Authentication is via NextAuth session cookies unless noted otherwise.

---

## Health & Monitoring

### GET /api/health

**Auth:** None (public endpoint for infrastructure monitoring)

Returns system health status.

**Response:**
```json
{
  "status": "ok | degraded | error",
  "database": true,
  "last_pipeline_run": "2026-04-14T06:00:00.000Z",
  "hours_since_run": 4,
  "last_run_had_errors": false,
  "checked_at": "2026-04-14T10:00:00.000Z"
}
```

**Status codes:**
- `200` — ok or degraded
- `503` — database unreachable

---

## Papers

### GET /api/papers

**Auth:** Required

Paginated list of flagged papers with filtering and sorting.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default: 1) |
| `tier` | string | Comma-separated risk tiers: `critical,high,medium,low` |
| `source` | string | Source server: `biorxiv`, `medrxiv`, `pubmed`, `europepmc`, `arxiv`, `research_square`, `chemrxiv`, `zenodo`, `ssrn` |
| `status` | string | Review status: `unreviewed`, `under_review`, `confirmed_concern`, `false_positive`, `archived` |
| `q` | string | Full-text search (title, abstract, summaries) |
| `sort` | string | `date_desc` (default), `date_asc`, `score_desc`, `score_asc` |
| `dim` | string | Risk dimension name (e.g., `information_hazard`) |
| `dim_min` | int | Minimum dimension score (1, 2, or 3) |
| `author` | string | Author name substring filter (ILIKE) |
| `institution` | string | Institution name substring filter (ILIKE) |
| `needs_review` | string | `true` to filter papers flagged for manual review |
| `has_errors` | string | `true` to filter papers with processing errors |

**Response:**
```json
{
  "papers": [...],
  "total": 42,
  "totalIngested": 5000,
  "page": 1,
  "pageSize": 20,
  "totalPages": 3
}
```

### GET /api/papers/:id

**Auth:** Required

Single paper with full details and assessment logs.

### PATCH /api/papers/:id

**Auth:** Required | **CSRF:** Checked

Update paper review status.

**Body:**
```json
{ "reviewStatus": "confirmed_concern" }
```

Valid values: `unreviewed`, `under_review`, `confirmed_concern`, `false_positive`, `archived`

### PUT /api/papers/:id/notes

**Auth:** Required | **CSRF:** Checked

Update analyst notes for a paper.

**Body:**
```json
{ "notes": "This paper requires further review of the synthesis protocol." }
```

---

## Pipeline Management

### GET /api/pipeline

**Auth:** Required

Current pipeline status (running/paused, last run info).

### POST /api/pipeline

**Auth:** Required

Start a new pipeline run.

**Body:**
```json
{
  "fromDate": "2026-04-12",
  "toDate": "2026-04-14"
}
```

### POST /api/pipeline/pause

**Auth:** Required

Pause the scheduled pipeline.

### POST /api/pipeline/resume

**Auth:** Required

Resume the scheduled pipeline.

### PUT /api/pipeline/schedule

**Auth:** Required

Update pipeline schedule.

**Body:**
```json
{ "hour": 6, "minute": 0 }
```

### GET /api/pipeline/progress

**Auth:** Required

Current running pipeline progress (stage, paper counts, cost).

### GET /api/pipeline/coverage

**Auth:** Required

Per-date pipeline run status for the coverage heatmap (last 200 days).

**Response:**
```json
{
  "2026-04-14": "success",
  "2026-04-13": "error",
  "2026-04-12": "success"
}
```

---

## Analytics

### GET /api/stats

**Auth:** Required

Dashboard KPIs and aggregated statistics.

### GET /api/analytics/paper-coverage

**Auth:** Required

Per-date, per-source paper counts for the intelligence coverage view.

**Response:**
```json
{
  "2026-04-14": { "biorxiv": 120, "pubmed": 45, "europepmc": 300 }
}
```

---

## Data Export

### GET /api/feed

**Auth:** Required

Feed of flagged papers for programmatic consumption.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `format` | string | `json` (default) or `rss` |
| `tier` | string | Comma-separated risk tiers to include |
| `limit` | int | Number of items (default: 50, max: 200) |

**RSS response:** `Content-Type: application/rss+xml`

### GET /api/feedback

**Auth:** Required

Export analyst-labelled papers (confirmed_concern / false_positive) for prompt refinement analysis.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | `confirmed_concern` or `false_positive` (default: both) |
| `since` | string | ISO date — only papers labelled after this date |

---

## Settings

### GET /api/settings

**Auth:** Required

All pipeline settings with secrets redacted.

### PUT /api/settings

**Auth:** Admin | **CSRF:** Checked

Update pipeline settings. Merges with existing; redacted secret placeholders are preserved.

---

## Alerts

### POST /api/alerts/test

**Auth:** Admin

Test alert channels. Send `{ "channel": "slack" }` or `{ "channel": "email" }`.

### POST /api/alerts/digest

**Auth:** Admin

Trigger an immediate digest of flagged papers to configured Slack/email recipients.
