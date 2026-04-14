# DURC Preprint Triage System — Roadmap

Living document tracking audit remediation and feature work.
Based on comprehensive codebase audits conducted 2026-04-09 and 2026-04-10.

---

## Completed

### Batch 1 — Immediate (2026-04-09)

- [x] **#1** Parallelise enrichment pipeline with asyncio.gather + semaphore (~10x speedup)
- [x] **#2** Add CASCADE delete on AssessmentLog and PaperGroup FKs (SQLAlchemy, Prisma, Alembic migration)
- [x] **#3** Fix `authors[0]` IndexError in enricher when OpenAlex returns empty authors
- [x] **#4** Add session error logging with exc_info in db.py
- [x] **#5** Replace `assert` with `raise RuntimeError` in all 7 API clients
- [x] **#6** Accessibility: skip-to-content link, sr-only form labels, aria-hidden on decorative logo
- [x] **#8** Increase DB pool to 10, add 30s connection timeout
- [x] **#9** Add language column index (SQLAlchemy, Prisma, Alembic)
- [x] Error boundaries (error.tsx) on all 4 major dashboard routes
- [x] Fix duplicate SQL execution in monitor_data_corruption.py

### Pre-audit

- [x] Paper sorting by score within risk tiers (date/score, asc/desc)
- [x] JSON parsing bug fix — recovered 54/65 corrupted papers
- [x] Data corruption prevention system (validation, monitoring)

### Batch 2 — Short-term hardening

- [x] **#11** Auth-disabled warning logging — prevent silent auth bypass in production
- [x] **#18** Extract shared retry utility — deduplicate retry/backoff logic across 6+ API clients
- [x] **#13** Dimension-level filtering UI — let analysts filter by specific risk dimension scores

### Batch 3 — Security and alerting

- [x] **#7** CSP nonces for script-src (replace `unsafe-inline`) — per-request nonce via proxy.ts, `strict-dynamic`
- [x] **#12** Alert system: email digests (daily/weekly) + Slack webhook for critical-tier papers
- [x] **#17** Pre-commit hooks (ruff lint + format) and mypy type checking in CI

### Batch 4 — Coverage expansion and hardening (2026-04-10)

- [x] **#14** Tier 2 ingest clients: arXiv (q-bio), Crossref (Research Square, ChemRxiv, SSRN), Zenodo
- [x] **#15** Frontend test framework — Vitest + happy-dom with 18 unit tests for lib/utils
- [x] **#16** Database backup/restore scripts with retention policy (pg_dump/pg_restore wrappers)
- [x] React.memo on AnalyticsCharts — prevent unnecessary chart re-renders (audit medium-severity)
- [x] Parallelize raw SQL queries with Promise.all — eliminate extra totalIngested table scan (audit medium-severity)

### Batch 5 — Feeds, filters, and audit fixes (2026-04-10)

- [x] Tier 2 sources added to dashboard source filter dropdown
- [x] RSS/JSON feed endpoint (`/api/feed` with `?format=rss` option) for programmatic consumption
- [x] Author/institution dedicated text filters in dashboard (ILIKE queries)
- [x] Dedup thresholds moved from hardcoded class constants to config settings (audit medium-severity)
- [x] Accessibility: aria-controls on audit trail expandable buttons (audit low-severity)

### Batch 6 — Analyst workflow (2026-04-10)

- [x] Dimension-level trend analytics — already implemented (weekly avg per-dimension line chart)
- [x] Analyst feedback export endpoint (`/api/feedback`) for prompt refinement analysis
- [x] Related papers section on paper detail page (by institution and first author)
- [x] Country distribution chart in analytics (from OpenAlex enrichment JSONB)

### Batch 7 — Final audit remediation (2026-04-10)

- [x] NCBI API key moved from URL query params to httpx client defaults (audit high-severity security)
- [x] Methods section passage highlighting using key_methods_of_concern (audit high-priority UX gap)
- [x] Batch DOI lookup in dedup — single IN query replaces N sequential lookups (audit high-severity efficiency)
- [x] Version tracking — detect paper version upgrades and flag for re-screening (backlog)
- [x] Slack webhook placeholder replaced with generic text (audit medium-severity security)

### Batch 8 — CI, analytics redesign, and data quality (2026-04-10 to 2026-04-14)

- [x] CodeQL security scanning workflow added
- [x] pytest-cov coverage reporting in CI (78% coverage)
- [x] CI fixes: ruff formatting, ESLint setState-in-effect, npm peer deps, ReDoS regex
- [x] Per-source error handling in ingest — one failing source no longer kills entire pipeline
- [x] Analytics page redesign: actionable KPIs, intelligence coverage heatmap + source detail table
- [x] Institution name normalisation (regex extraction of university names from department strings)
- [x] Dashboard Vitest run added to CI
- [x] Markdown rendering for LLM assessment summaries and reasoning
- [x] Score fallback chain: paper.aggregateScore → stage2 score → computed from dimensions
- [x] Regex fallback in parseDimensions for malformed LLM JSON output
- [x] Processing error indicator (warning triangle) on paper cards
- [x] "Has Errors" filter toggle in feed
- [x] "Fix Errors" button on Pipeline page (resets error papers for reprocessing)
- [x] Sort by computed score when aggregate_score is NULL (COALESCE with JSONB dimension sum)
- [x] Coverage heatmap rewritten: pipeline runs (Pipeline page) + source-aware paper coverage (Analytics page)

---

## Deferred

- [ ] **#10** Known-case regression test suite — validate triage against ground-truth DURC papers (blocked by LLM safety guardrails rejecting synthetic DURC content in test fixtures)

---

## Documented Limitations

- **In-memory rate limiting** — working as designed for single-server deployment. Would need Redis for multi-instance.
- **DedupRelationship.PUBLISHED_VERSION** enum — forward declaration for planned preprint→publication linking. Not dead code.
- **Stage naming mismatch** (stage1/2/3 vs pipeline stage numbers) — cosmetic; changing would require a migration and break existing data.

---

### Critical & High Priority Hardening (2026-04-14)

- [x] Auth guards (`requireAdmin()`) on all 5 pipeline server actions
- [x] Pipeline failure alerting via Slack webhook and SMTP email
- [x] Unauthenticated `/api/health` endpoint for infrastructure monitoring
- [x] Operations runbook (`docs/OPERATIONS.md`)
- [x] CSRF protection via Origin header verification on all PUT/PATCH routes
- [x] Coverage threshold enforcement (`--cov-fail-under=70`) + dashboard tests in CI

---

### Backlog Completion (2026-04-14)

- [x] Dependabot configuration — weekly scans for Python, Node, and GitHub Actions
- [x] Crossref funder enrichment — 4th enrichment source extracting funder names and grant IDs
- [x] OpenAPI documentation — `docs/API.md` covering all 27 dashboard endpoints
- [x] Developer onboarding guide — `docs/DEVELOPMENT.md` with setup, debugging, contribution instructions

---

## Backlog (deferred)

- [ ] Analyst feedback loop — use exported FP/confirmed data to refine LLM prompts (deferred until analyst hired)
