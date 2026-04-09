# DURC Preprint Triage System — Roadmap

Living document tracking audit remediation and feature work.
Based on comprehensive codebase audit conducted 2026-04-09 (see `2026-04-09_AUDIT.md`).

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

---

## In Progress

### Batch 2 — Short-term hardening

- [x] **#11** Auth-disabled warning logging — prevent silent auth bypass in production
- [x] **#18** Extract shared retry utility — deduplicate retry/backoff logic across 6+ API clients
- [ ] **#10** Known-case regression test suite — validate triage against ground-truth DURC papers (deferred)
- [x] **#13** Dimension-level filtering UI — let analysts filter by specific risk dimension scores

### Batch 3 — Security and alerting

- [x] **#7** CSP nonces for script-src (replace `unsafe-inline`) — per-request nonce via proxy.ts, `strict-dynamic`
- [x] **#12** Alert system: email digests (daily/weekly) + Slack webhook for critical-tier papers
- [x] **#17** Pre-commit hooks (ruff lint + format) and mypy type checking in CI

---

## Upcoming

### Batch 4 — Coverage expansion

- [ ] **#14** Tier 2 ingest clients: arXiv (q-bio, cs.AI+bio), then Crossref-based (Research Square, ChemRxiv, SSRN)
- [ ] **#15** Frontend test framework (Vitest unit + Playwright E2E)
- [ ] **#16** Database backup/restore scripts with scheduled execution

### Batch 5 — Analyst workflow

- [ ] Dimension-level trend analytics (per-dimension over time, not just aggregate)
- [ ] Methods section passage highlighting (flag specific sentences of concern)
- [ ] Related papers view (by author, topic, citation via Semantic Scholar)
- [ ] Analyst feedback loop (confirmed/false-positive labels feed back to prompt refinement)
- [ ] RSS/JSON feed for programmatic consumption

### Backlog

- [ ] Crossref enrichment client (funder info extraction)
- [ ] Author/institution dedicated filter in dashboard
- [ ] Country filter in analytics
- [ ] Version tracking and re-screening on paper updates
