# Phase 3: DURC Triage Dashboard — Design Spec

## 1. Overview

A Next.js web dashboard for biosecurity analysts to review papers flagged by the DURC triage pipeline. The dashboard reads pipeline data from PostgreSQL via Prisma and controls the Python pipeline through a FastAPI sidecar. It provides daily feed review, paper detail drill-down, analytics, pipeline control, and settings management.

**Users**: Biosecurity analysts, policy researchers, institutional biosafety committees.

**Goal**: Surface flagged papers with enough context for analysts to make review decisions without leaving the dashboard.

---

## 2. Architecture

### System topology

```
┌─────────────────────────────────┐
│         Browser (Analyst)       │
└────────────┬────────────────────┘
             │ HTTPS
┌────────────▼────────────────────┐
│   Next.js 15 (App Router, RSC) │
│   - Prisma → PostgreSQL (reads)│
│   - Auth.js v5 (OAuth/SSO)     │
│   - API routes (proxy to sidecar│
│     for pipeline control)       │
└────────────┬────────────────────┘
             │ HTTP (internal, API secret)
┌────────────▼────────────────────┐
│   FastAPI Sidecar (Python)      │
│   - Wraps PipelineScheduler     │
│   - ~5 endpoints                │
│   - Runs in same process as     │
│     scheduler + pipeline        │
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│   PostgreSQL                    │
│   - papers, paper_groups,       │
│     assessment_logs,            │
│     pipeline_runs               │
└─────────────────────────────────┘
```

### Data flow

- **Read operations** (papers, runs, logs, analytics): Next.js → Prisma → PostgreSQL. Server Components fetch data at render time. No client-side fetching for initial page loads.
- **Write operations** (review status, analyst notes): Next.js Server Actions → Prisma → PostgreSQL.
- **Pipeline control** (run, pause, resume, reschedule, config): Next.js API route → FastAPI sidecar (authenticated via `PIPELINE_API_SECRET` header) → PipelineScheduler methods.

### Why this split

Prisma gives type-safe, fast reads with React Server Components (no API round-trip for data). The FastAPI sidecar is necessary because PipelineScheduler is a Python in-memory object (APScheduler) that can't be accessed from Node.js. The sidecar is intentionally thin — it just exposes the existing `PipelineScheduler` methods as HTTP endpoints.

---

## 3. Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | Next.js 15 (App Router, React Server Components) | Server-side rendering, streaming, file-based routing |
| Styling | Tailwind CSS 4 | Utility-first, native dark mode via `dark:` prefix, design token support |
| Component Library | shadcn/ui (Radix primitives) | Accessible by default (ARIA, keyboard nav, focus management). Not a dependency — components copied into project and customizable. |
| ORM | Prisma | Type-safe queries, introspects existing PostgreSQL schema. No migration conflicts with SQLAlchemy — read-only Prisma schema. |
| Auth | Auth.js v5 (NextAuth) | GitHub + Google OAuth providers. Encrypted HTTP-only session cookies. Middleware-based route protection. |
| Charts | Recharts | Composable React chart library. Specified in project CLAUDE.md. |
| Data Tables | TanStack Table + shadcn/ui DataTable | Client-side sorting, filtering, pagination with accessible markup |
| Full-Text Search | PostgreSQL `tsvector` | Built into existing DB. `tsvector` index on `title` (weight A) and `abstract` (weight B). No external search service. |
| URL State | `nuqs` | Type-safe URL search params for filters, search, pagination. Shareable/bookmarkable URLs. |
| Python API | FastAPI | Thin sidecar wrapping PipelineScheduler. Async, fast, minimal boilerplate. |

---

## 4. Visual Design

### Theme

**Adaptive light/dark mode.** Follows OS `prefers-color-scheme` by default with a manual toggle in the sidebar. Implemented via Tailwind's `class` dark mode strategy with `next-themes` for persistence.

- **Dark mode**: Slate palette (`slate-900` background, `slate-800` cards, `slate-700` borders). Optimised for extended monitoring sessions.
- **Light mode**: White background, `slate-50` cards, `slate-200` borders. Clean, clinical feel for daytime review.
- Risk tier colours use warm accents (red/orange/yellow/green) that maintain WCAG AA contrast in both modes.

### Risk tier colour system

| Tier | Dark mode | Light mode | Contrast |
|------|-----------|------------|----------|
| Critical | `bg-red-900` text `text-red-300` | `bg-red-50` text `text-red-700` | AA compliant both modes |
| High | `bg-orange-900` text `text-orange-200` | `bg-orange-50` text `text-orange-700` | AA compliant both modes |
| Medium | `bg-yellow-900` text `text-yellow-200` | `bg-yellow-50` text `text-yellow-700` | AA compliant both modes |
| Low | `bg-green-900` text `text-green-200` | `bg-green-50` text `text-green-700` | AA compliant both modes |

### Navigation

**Fixed left sidebar** (220px). Contains:
- App logo + name
- Navigation links: Daily Feed, Analytics, Pipeline, Settings
- Active link highlighted with left border accent + background
- Pipeline status indicator (green dot = running, yellow = paused, red = error) with next run time
- Theme toggle (sun/moon icon) at bottom
- User avatar + sign-out at bottom

---

## 5. Pages

### 5.1 Daily Feed (`/`)

The primary view. Reverse-chronological list of papers that passed the coarse filter.

**Layout**: Sidebar + main content area.

**Header**: Page title, paper count, date.

**Filter bar**: Horizontal row of filter controls:
- Risk tier dropdown (All / Critical / High / Medium / Low)
- Source server dropdown (All / bioRxiv / medRxiv / PubMed / Europe PMC)
- Review status dropdown (All / Unreviewed / Under Review / Confirmed Concern / False Positive / Archived)
- Date range picker (last 24h / 7d / 30d / custom)
- Search input (full-text search via `tsvector` on title + abstract)
- Filter by risk dimension (e.g., "information_hazard >= 2")

All filters stored in URL search params via `nuqs` so filtered views are shareable/bookmarkable.

**Paper cards** (expanded style): Each paper rendered as a card showing:
- Left colour bar indicating risk tier
- Paper title (clickable → detail view)
- Authors, institution, source server badge, posted date
- 2–3 sentence AI assessment summary (from `stage2_result.summary` or `stage3_result.summary`)
- Top risk dimension scores as small labelled badges (show dimensions scoring >= 2)
- Aggregate score
- Risk tier badge (coloured pill)
- Review status indicator

**Pagination**: Page-based, 20 papers per page. Page number stored in URL params via `nuqs` for bookmarkability. Previous/Next buttons at bottom.

**Sorting**: Default by risk tier (critical first), then by posted date (newest first). Sortable by aggregate score, posted date, or review status.

### 5.2 Paper Detail (`/paper/[id]`)

Full assessment view when analyst clicks a paper.

**Layout**: Two-column within the main content area (sidebar still visible).

**Header bar**: Back button, paper title, risk tier badge, aggregate score.

**Left column** (scrollable, ~70% width): Stacked sections:
1. **Paper Metadata** — Authors, institution, source server, DOI (linked), posted date, version.
2. **AI Assessment Summary** — Combined summary from Stage 4 (methods analysis) and Stage 5 (adjudication) if available. Styled as a highlighted card.
3. **Key Methods of Concern** — Tags/pills listing specific flagged methods from `stage2_result.key_methods_of_concern`.
4. **Adjudication Context** (if Stage 5 ran) — Institutional context assessment, DURC oversight indicators, adjustment reasoning from `stage3_result`.
5. **Author & Institution Context** — Enrichment data from OpenAlex/Semantic Scholar/ORCID: h-index, citation count, topics, employment history, ORCID. Warning banner if enrichment was partial (some sources failed).
6. **Methods Section** — Extracted methods text (plain text, not HTML) from `paper.methods_section`. If not available, show "Full text not retrieved" with explanation.
7. **Analyst Notes** — Editable text area. Saved via Server Action on blur or explicit save button. Persisted to `paper.analyst_notes`.
8. **Audit Trail** — Expandable section showing `assessment_logs` for this paper: stage, model used, prompt version, timestamp, token counts, cost. Click to expand full prompt/response (for auditability).

**Right column** (sticky, ~30% width): Risk assessment panel:
1. **Risk Dimensions** — All 6 dimension scores as labelled horizontal progress bars (0–3 scale). Each bar colour-coded by severity. Below each bar, the one-sentence justification text from `stage2_result.dimensions[name].justification`.
2. **Review Status** — Dropdown to change status: Unreviewed → Under Review → Confirmed Concern / False Positive / Archived. Saved via Server Action.
3. **Action Buttons** — "Escalate" button (sets status + triggers notification if alerts configured). "Open Original" link (to DOI URL or source server).

### 5.3 Analytics (`/analytics`)

Pipeline performance and risk distribution over time.

**Top row**: 4 summary KPI cards:
- Papers processed today (with trend arrow vs. 7-day average)
- Critical/High papers today
- Average aggregate score (7-day rolling)
- Pipeline health (last run status, success/error)

**Charts** (Recharts, responsive grid):
1. **Papers over time** — Area chart. X: date, Y: count. Stacked by risk tier. Filterable by date range.
2. **Risk tier distribution** — Stacked bar chart. Weekly buckets. Shows proportion of each tier.
3. **Top flagged institutions** — Horizontal bar chart. Top 10 institutions by number of high/critical papers.
4. **Top flagged categories** — Horizontal bar chart. Top 10 subject categories.
5. **Risk dimension trends** — Line chart. Each of the 6 dimensions as a separate line showing average score over time.
6. **Pipeline throughput** — Line chart showing papers at each stage (ingested → filtered → retrieved → analysed → adjudicated) per run.

All charts filterable by date range. Dark mode compatible (Recharts supports custom themes).

### 5.4 Pipeline (`/pipeline`)

Pipeline run history and scheduler control.

**Left panel: Run History**
- Table of `pipeline_runs` records: started_at, duration (computed), papers_ingested, papers_coarse_passed, papers_adjudicated, errors (count), total_cost_usd, trigger (scheduled/manual).
- Click row to expand: full per-stage counts, error details, individual paper links.
- Sortable by date, filterable by trigger type.

**Right panel: Controls**
- **Status display**: Current state (Running / Paused / Idle), animated indicator.
- **Next scheduled run**: Date/time display.
- **"Run Now" button**: Triggers `POST /api/pipeline` → FastAPI `trigger_run()`. Shows progress indicator while running.
- **Pause / Resume toggle**: Calls FastAPI `pause()` / `resume()`.
- **Schedule picker**: Time input for daily run hour/minute. Calls FastAPI `update_schedule()`.

### 5.5 Settings (`/settings`)

Pipeline configuration form. Admin role required.

**Sections**:

1. **Model Selection**
   - Stage 1 (Coarse Filter) model — dropdown
   - Stage 2 (Methods Analysis) model — dropdown
   - Stage 3 (Adjudication) model — dropdown

2. **Pipeline Tuning**
   - Coarse filter threshold — slider (0.0–1.0) with numeric display
   - Adjudication min tier — dropdown (low / medium / high / critical)
   - Batch API toggle — switch
   - PubMed query mode — dropdown (all / mesh_filtered)

3. **Rate Limits** (seconds between requests)
   - bioRxiv, PubMed, Europe PMC, Unpaywall, OpenAlex, Semantic Scholar, ORCID, full-text retrieval — numeric inputs

4. **Alerts**
   - Email recipients — comma-separated input
   - Slack webhook URL — text input (masked)
   - Digest frequency — dropdown (daily / weekly)
   - Alert tier threshold — dropdown (medium / high / critical)

5. **User Management** (admin only)
   - List of users with role assignment (admin / analyst)
   - Invite user flow (sends OAuth link)

All settings saved via Server Action to a `pipeline_settings` table in the database (single-row, key-value JSON column with typed defaults from environment variables). Dashboard reads from DB; pipeline reads from DB with env var fallback. Changes take effect on next pipeline run. Schedule changes take effect immediately via FastAPI sidecar.

### 5.6 Login (`/login`)

Simple OAuth login page. Shows app name, brief description, and OAuth buttons (GitHub, Google). Unauthenticated users are redirected here by middleware.

---

## 6. Accessibility (WCAG 2.1 AA)

### Colour contrast
- All text meets 4.5:1 contrast ratio against its background in both light and dark modes.
- UI components (badges, buttons, borders) meet 3:1 contrast ratio.
- Risk tier colours tested in both themes. Never rely on colour alone — tier badges always include text labels ("CRITICAL", "HIGH", etc.).

### Keyboard navigation
- All interactive elements reachable via Tab key in logical order.
- Sidebar navigation: arrow keys to move between items, Enter to activate.
- Filter dropdowns: shadcn/ui Select (Radix) provides full keyboard support (arrow keys, type-ahead, Escape to close).
- Paper cards: focusable, Enter to open detail view.
- Focus indicators: visible focus ring (2px `ring-blue-500`) on all interactive elements. Never removed via `outline-none` without replacement.

### Screen readers
- Semantic HTML: `<nav>`, `<main>`, `<aside>`, `<header>`, `<section>` with appropriate `aria-label` attributes.
- Risk dimension bars: `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label`.
- Status badges: `aria-label` includes full text (e.g., "Risk tier: Critical, score 16 out of 18").
- Dynamic content updates: `aria-live="polite"` regions for filter results count, pipeline status changes, toast notifications.
- Charts: Recharts renders SVG. Each chart wrapped with `aria-label` describing what it shows. Data tables provided as accessible alternatives (expandable below chart).

### Reduced motion
- Respect `prefers-reduced-motion`: disable chart animations, transitions, and loading spinners. Use instant state changes instead.

### Touch targets
- All clickable elements minimum 44x44px touch target (per WCAG 2.5.5).
- Filter pills, badges, and small controls have adequate padding.

---

## 7. Security

### Authentication & Authorization

- **Auth.js v5** with GitHub and Google OAuth providers.
- Session stored as encrypted HTTP-only, Secure, SameSite=Lax cookie.
- `AUTH_SECRET` environment variable (32+ random bytes) for session encryption.
- Next.js middleware (`middleware.ts`) protects all routes except `/login` and `/api/auth/*`.
- Two roles stored in database: `admin` and `analyst`.
  - `analyst`: View papers, search, filter, update review status, add notes.
  - `admin`: All analyst permissions + settings changes, pipeline control, user management.
- Role checked in Server Components and Server Actions before rendering/executing.

### Cross-Site Request Forgery (CSRF)

- Auth.js includes CSRF protection for its own routes.
- Next.js Server Actions include CSRF tokens automatically.
- FastAPI sidecar does not accept browser requests — only accepts requests from Next.js API routes, authenticated via `Authorization: Bearer <PIPELINE_API_SECRET>` header. This secret is server-side only, never exposed to the browser.

### Content Security Policy

```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
font-src 'self';
connect-src 'self';
frame-ancestors 'none';
```

`unsafe-inline` for styles is required by Tailwind's runtime. No `unsafe-eval`. No inline scripts.

### Additional Headers

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Strict-Transport-Security: max-age=31536000; includeSubDomains (when HTTPS)
```

### Input Handling

- All database queries via Prisma parameterized queries — SQL injection not possible.
- User inputs (analyst notes, search queries) passed through Prisma, never interpolated into SQL.
- React JSX auto-escapes all rendered text — XSS not possible through normal rendering.
- Methods section text rendered as `<pre>` or with `white-space: pre-wrap` — never as raw HTML via `dangerouslySetInnerHTML`.
- Search queries sanitised before passing to PostgreSQL `tsvector` (strip special characters that could break `to_tsquery`).

### Rate Limiting

- Next.js API routes: rate-limited per IP (100 requests/minute for reads, 10/minute for writes).
- FastAPI sidecar: `slowapi` rate limiting (5 requests/minute for pipeline control endpoints).
- Auth endpoints: Auth.js handles brute-force protection.

### Secrets Management

All secrets in environment variables, never committed:
- `AUTH_SECRET` — Auth.js session encryption
- `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` — GitHub OAuth
- `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET` — Google OAuth
- `DATABASE_URL` — PostgreSQL connection string
- `PIPELINE_API_SECRET` — FastAPI sidecar authentication
- `PIPELINE_API_URL` — FastAPI sidecar URL (e.g., `http://localhost:8000`)

---

## 8. FastAPI Sidecar

Thin Python HTTP wrapper around the existing `PipelineScheduler`. Runs in the same process as the scheduler and pipeline.

### Endpoints

| Method | Path | Auth | Description | Maps to |
|--------|------|------|-------------|---------|
| `GET` | `/status` | API secret | Pipeline scheduler status | `scheduler.get_status()` |
| `POST` | `/run` | API secret | Trigger immediate pipeline run | `scheduler.trigger_run()` |
| `POST` | `/pause` | API secret | Pause scheduled runs | `scheduler.pause()` |
| `POST` | `/resume` | API secret | Resume scheduled runs | `scheduler.resume()` |
| `PUT` | `/schedule` | API secret | Update daily run time | `scheduler.update_schedule(hour, minute)` |
| `GET` | `/config` | API secret | Current pipeline settings | Read from settings/env |
| `PUT` | `/config` | API secret | Update pipeline settings | Write to settings store |

All endpoints require `Authorization: Bearer <PIPELINE_API_SECRET>` header. Returns JSON. Errors return appropriate HTTP status codes with JSON error body.

### File

Single file: `pipeline/api.py`. Imports `PipelineScheduler` and `Settings`. Runs via `uvicorn` alongside the scheduler.

---

## 9. Database Additions

### New table: `users`

For storing OAuth user info and roles.

```
users
├── id: UUID (PK)
├── email: String (unique, indexed)
├── name: String
├── image: String (avatar URL, nullable)
├── role: Enum('admin', 'analyst') (default: 'analyst')
├── created_at: DateTime
└── updated_at: DateTime
```

Auth.js adapter creates/manages user records on OAuth login. Role field added for authorization.

### New table: `accounts` + `sessions`

Standard Auth.js adapter tables for OAuth account linking and session management. Created automatically by the Auth.js Prisma adapter.

### New table: `pipeline_settings`

Single-row table for dashboard-editable pipeline configuration.

```
pipeline_settings
├── id: Integer (PK, always 1)
├── settings: JSONB (all configurable values)
└── updated_at: DateTime
```

The `settings` JSON column stores all values from Settings page Section 5.5 (model selection, thresholds, rate limits, alert config). Pipeline reads this table on each run, falling back to environment variables for any missing keys. Dashboard writes to this table via Server Action.

### Search index

Add `tsvector` generated column and GIN index on `papers` table:

```sql
ALTER TABLE papers ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
  ) STORED;

CREATE INDEX idx_papers_search ON papers USING GIN(search_vector);
```

Title weighted higher (A) than abstract (B) for ranking relevance.

### Prisma schema

Generated via `prisma db pull` (introspection) from the existing PostgreSQL database. Read-only — migrations still managed by Alembic on the Python side. Prisma schema includes all existing tables (papers, paper_groups, assessment_logs, pipeline_runs) plus the new Auth.js tables.

---

## 10. File Structure

```
dashboard/
├── package.json
├── next.config.ts                     # Security headers, env config
├── tailwind.config.ts                 # Dark mode (class strategy), theme
├── middleware.ts                       # Auth guard on all routes
├── prisma/
│   └── schema.prisma                  # Introspected from PostgreSQL
├── app/
│   ├── layout.tsx                     # Root: sidebar, ThemeProvider, SessionProvider
│   ├── page.tsx                       # Daily feed
│   ├── paper/
│   │   └── [id]/page.tsx             # Paper detail (two-column)
│   ├── analytics/page.tsx             # Charts + KPIs
│   ├── pipeline/page.tsx              # Run history + controls
│   ├── settings/page.tsx              # Config form (admin only)
│   ├── login/page.tsx                 # OAuth login
│   └── api/
│       ├── auth/[...nextauth]/route.ts
│       ├── papers/route.ts            # GET: list + search
│       ├── papers/[id]/
│       │   ├── route.ts              # GET: detail, PATCH: review status
│       │   └── notes/route.ts        # PUT: analyst notes
│       ├── pipeline/
│       │   ├── route.ts              # GET: status, POST: trigger run
│       │   ├── pause/route.ts        # POST: pause
│       │   ├── resume/route.ts       # POST: resume
│       │   └── schedule/route.ts     # PUT: update schedule
│       └── stats/route.ts            # GET: analytics aggregations
├── components/
│   ├── ui/                            # shadcn/ui primitives
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── dropdown-menu.tsx
│   │   ├── input.tsx
│   │   ├── select.tsx
│   │   ├── separator.tsx
│   │   ├── slider.tsx
│   │   ├── switch.tsx
│   │   ├── table.tsx
│   │   ├── textarea.tsx
│   │   └── tooltip.tsx
│   ├── sidebar.tsx                    # Fixed sidebar nav + pipeline status
│   ├── theme-toggle.tsx               # Light/dark switch
│   ├── paper-card.tsx                 # Expanded feed card
│   ├── paper-filters.tsx              # Filter bar + search
│   ├── risk-panel.tsx                 # Sticky right-column risk scores
│   ├── dimension-bar.tsx              # Single risk dimension progress bar
│   ├── review-status-select.tsx       # Status dropdown with Server Action
│   ├── analyst-notes.tsx              # Editable notes textarea
│   ├── audit-trail.tsx                # Expandable assessment log list
│   ├── enrichment-card.tsx            # Author/institution context display
│   ├── methods-viewer.tsx             # Plain-text methods section display
│   ├── kpi-card.tsx                   # Summary stat card
│   ├── analytics-charts.tsx           # Recharts chart wrappers
│   ├── run-history-table.tsx          # Pipeline run history
│   ├── pipeline-controls.tsx          # Status + pause/resume/run buttons
│   └── settings-form.tsx              # Full settings form
└── lib/
    ├── prisma.ts                      # Prisma client singleton
    ├── auth.ts                        # Auth.js config + adapter
    ├── auth-guard.ts                  # Role checking helpers
    ├── pipeline-api.ts                # FastAPI sidecar HTTP client
    ├── search.ts                      # tsvector query builder
    ├── risk-colors.ts                 # Risk tier → Tailwind class mappings (both themes)
    └── utils.ts                       # Date formatters, score calculators

pipeline/
└── api.py                             # FastAPI sidecar (new file)
```

---

## 11. Deployment

### Option A: Split (recommended for production)

- **Dashboard**: Deploy to Vercel. Zero-config Next.js hosting with edge functions, automatic HTTPS, preview deploys.
- **Pipeline + FastAPI**: Run on VPS (Hetzner/DigitalOcean). Managed via `systemd` or Docker. Long-running process for scheduler.
- **Database**: Managed PostgreSQL (Supabase, Neon, or self-hosted on VPS).

### Option B: Co-located (simpler for dev/small team)

- Both Next.js and Python run on the same VPS.
- Next.js via `pm2` or Docker.
- Python pipeline + FastAPI via `systemd` or Docker.
- Nginx reverse proxy: port 443 → Next.js (3000), `/api/pipeline/*` → FastAPI (8000).
- Database on same VPS or managed service.

### Environment variables (dashboard)

```bash
# Auth
AUTH_SECRET=<random-32-bytes>
AUTH_GITHUB_ID=<github-oauth-app-id>
AUTH_GITHUB_SECRET=<github-oauth-app-secret>
AUTH_GOOGLE_ID=<google-oauth-client-id>
AUTH_GOOGLE_SECRET=<google-oauth-client-secret>

# Database
DATABASE_URL=postgresql://user:pass@host:5432/durc_triage

# Pipeline sidecar
PIPELINE_API_URL=http://localhost:8000
PIPELINE_API_SECRET=<shared-secret>
```

---

## 12. Scope Boundaries

### In scope (this spec)

- All 6 pages described above (feed, detail, analytics, pipeline, settings, login)
- OAuth authentication with role-based authorization
- FastAPI sidecar for pipeline control
- Full-text search via PostgreSQL tsvector
- Adaptive light/dark theme
- WCAG 2.1 AA accessibility
- Security hardening (CSP, CSRF, rate limiting, input sanitization)

### Out of scope (future work)

- Email digest / Slack webhook alert delivery (alert configuration UI is in scope, but the actual sending infrastructure is Phase 4)
- RSS/JSON API for external consumption
- Real-time WebSocket updates (pipeline progress). Polling is sufficient for v1.
- Mobile-specific responsive design (desktop-first, but Tailwind responsive utilities used where practical)
- Analyst feedback loop (confirmed/false positive feeding back to prompt refinement)
- Paper version tracking and re-screening UI
- Multi-tenancy (single organisation assumed)
