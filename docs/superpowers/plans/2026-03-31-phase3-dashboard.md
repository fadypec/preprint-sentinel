# Phase 3: DURC Triage Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js dashboard for biosecurity analysts to review flagged papers, view analytics, and control the pipeline.

**Architecture:** Next.js 15 (App Router, RSC) reads PostgreSQL via Prisma for all data. A thin FastAPI sidecar wraps the existing Python `PipelineScheduler` for pipeline control. Auth.js v5 provides OAuth/SSO. Adaptive dark/light theme via Tailwind + next-themes.

**Tech Stack:** Next.js 15, Tailwind CSS 4, shadcn/ui, Prisma, Auth.js v5, Recharts, TanStack Table, nuqs, FastAPI, uvicorn

---

### Task 1: FastAPI Sidecar

**Files:**
- Create: `pipeline/api.py`
- Create: `tests/test_api.py`
- Modify: `pyproject.toml` (add fastapi + uvicorn deps)

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add `fastapi` and `uvicorn` to the project dependencies:

```toml
# In [project] dependencies list, add:
    "fastapi>=0.115.0",
    "uvicorn>=0.32.0",
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_api.py
"""Tests for the FastAPI pipeline sidecar."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from pipeline.api import create_app


@pytest.fixture
def mock_scheduler():
    scheduler = MagicMock()
    scheduler.get_status.return_value = {
        "running": True,
        "paused": False,
        "next_run_time": "2026-04-01T06:00:00+00:00",
        "last_run_time": None,
        "last_run_stats": None,
    }
    scheduler.trigger_run = AsyncMock(return_value=MagicMock(
        papers_ingested=10,
        papers_adjudicated=2,
        errors=[],
    ))
    scheduler.pause = AsyncMock()
    scheduler.resume = AsyncMock()
    scheduler.update_schedule = AsyncMock()
    return scheduler


@pytest.fixture
def app(mock_scheduler):
    return create_app(scheduler=mock_scheduler, api_secret="test-secret")


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


HEADERS = {"Authorization": "Bearer test-secret"}


async def test_status_returns_scheduler_state(client, mock_scheduler):
    resp = await client.get("/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is True
    assert data["paused"] is False
    mock_scheduler.get_status.assert_called_once()


async def test_status_rejects_missing_auth(client):
    resp = await client.get("/status")
    assert resp.status_code == 401


async def test_status_rejects_wrong_secret(client):
    resp = await client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


async def test_run_triggers_pipeline(client, mock_scheduler):
    resp = await client.post("/run", headers=HEADERS)
    assert resp.status_code == 200
    mock_scheduler.trigger_run.assert_awaited_once()


async def test_pause_calls_scheduler(client, mock_scheduler):
    resp = await client.post("/pause", headers=HEADERS)
    assert resp.status_code == 200
    mock_scheduler.pause.assert_awaited_once()


async def test_resume_calls_scheduler(client, mock_scheduler):
    resp = await client.post("/resume", headers=HEADERS)
    assert resp.status_code == 200
    mock_scheduler.resume.assert_awaited_once()


async def test_update_schedule(client, mock_scheduler):
    resp = await client.put("/schedule", headers=HEADERS, json={"hour": 8, "minute": 30})
    assert resp.status_code == 200
    mock_scheduler.update_schedule.assert_awaited_once_with(8, 30)


async def test_update_schedule_validates_hour(client):
    resp = await client.put("/schedule", headers=HEADERS, json={"hour": 25})
    assert resp.status_code == 422
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_app' from 'pipeline.api'`

- [ ] **Step 4: Implement the FastAPI sidecar**

```python
# pipeline/api.py
"""FastAPI sidecar for dashboard ↔ pipeline control.

Thin HTTP wrapper around PipelineScheduler. All endpoints require
Bearer token auth via PIPELINE_API_SECRET.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel, Field


def _make_auth_checker(api_secret: str):
    """Return a dependency that validates the Bearer token."""

    async def check_auth(authorization: Annotated[str | None, Header()] = None):
        if not authorization or authorization != f"Bearer {api_secret}":
            raise HTTPException(status_code=401, detail="Invalid or missing API secret")

    return check_auth


class ScheduleUpdate(BaseModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


def create_app(scheduler, api_secret: str) -> FastAPI:
    """Create the FastAPI app wrapping a PipelineScheduler instance."""
    app = FastAPI(title="DURC Pipeline Control", docs_url=None, redoc_url=None)
    auth = _make_auth_checker(api_secret)

    @app.get("/status", dependencies=[Depends(auth)])
    async def status():
        return scheduler.get_status()

    @app.post("/run", dependencies=[Depends(auth)])
    async def run():
        stats = await scheduler.trigger_run()
        return {
            "papers_ingested": stats.papers_ingested,
            "papers_adjudicated": stats.papers_adjudicated,
            "errors": stats.errors,
        }

    @app.post("/pause", dependencies=[Depends(auth)])
    async def pause():
        await scheduler.pause()
        return {"status": "paused"}

    @app.post("/resume", dependencies=[Depends(auth)])
    async def resume():
        await scheduler.resume()
        return {"status": "resumed"}

    @app.put("/schedule", dependencies=[Depends(auth)])
    async def update_schedule(body: ScheduleUpdate):
        await scheduler.update_schedule(body.hour, body.minute)
        return {"hour": body.hour, "minute": body.minute}

    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: 8 passed

- [ ] **Step 6: Run full test suite and lint**

Run: `python -m pytest && ruff check pipeline/api.py tests/test_api.py`
Expected: All tests pass, no lint errors

- [ ] **Step 7: Commit**

```bash
git add pipeline/api.py tests/test_api.py pyproject.toml
git commit -m "feat: add FastAPI sidecar for pipeline control"
```

---

### Task 2: Database Migration for Dashboard Tables

**Files:**
- Create: `alembic/versions/xxxx_add_dashboard_tables.py` (via alembic revision)
- Modify: `pipeline/models.py` (add User, PipelineSettings, UserRole enum)

- [ ] **Step 1: Add new models to pipeline/models.py**

Add after the existing `DedupRelationship` enum:

```python
class UserRole(enum.StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
```

Add after the `PipelineRun` class:

```python
class User(Base):
    """Dashboard user (created on OAuth login)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    image: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role", create_constraint=True),
        default=UserRole.ANALYST,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PipelineSettings(Base):
    """Single-row table for dashboard-editable pipeline config."""

    __tablename__ = "pipeline_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    settings: Mapped[dict] = mapped_column(PlatformJSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
```

Also update the module docstring from "Four tables" to "Six tables" (papers, paper_groups, assessment_logs, pipeline_runs, users, pipeline_settings).

- [ ] **Step 2: Generate alembic migration**

Run: `cd /Users/pecaf/projects/DURC-preprints && alembic revision --autogenerate -m "add dashboard tables"`

This generates a migration that creates `users` and `pipeline_settings` tables. Review the generated file to confirm it creates both tables with correct columns.

- [ ] **Step 3: Manually add the search vector index to the migration**

The `tsvector` generated column cannot be autogenerated by Alembic. Edit the generated migration file and add to the `upgrade()` function, after the table creation:

```python
    # Full-text search index on papers
    op.execute("""
        ALTER TABLE papers ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_papers_search ON papers USING GIN(search_vector)
    """)
```

And add to the `downgrade()` function:

```python
    op.execute("DROP INDEX IF EXISTS idx_papers_search")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS search_vector")
```

- [ ] **Step 4: Run existing tests to ensure models still work**

Run: `python -m pytest tests/ -v`
Expected: All existing tests pass (SQLite tests won't use the tsvector — that's PostgreSQL-only and tested via migration).

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py alembic/versions/
git commit -m "feat: add User, PipelineSettings models and search vector migration"
```

---

### Task 3: Next.js Project Scaffold

**Files:**
- Create: `dashboard/` (entire directory via create-next-app)
- Modify: `dashboard/package.json` (add dependencies)
- Create: `dashboard/.env.example`
- Modify: `dashboard/next.config.ts` (security headers)
- Modify: `dashboard/tailwind.config.ts` (dark mode)

- [ ] **Step 1: Create Next.js project**

```bash
cd /Users/pecaf/projects/DURC-preprints
npx create-next-app@latest dashboard \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src=no \
  --import-alias="@/*" \
  --use-npm
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm install prisma @prisma/client next-auth@beta @auth/prisma-adapter \
  next-themes nuqs recharts @tanstack/react-table \
  clsx tailwind-merge class-variance-authority \
  lucide-react
npm install -D @types/node
```

- [ ] **Step 3: Initialize shadcn/ui**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npx shadcn@latest init -d
```

When prompted, select: New York style, Slate base colour, CSS variables.

- [ ] **Step 4: Install shadcn/ui components**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npx shadcn@latest add badge button card dialog dropdown-menu input \
  select separator slider switch table textarea tooltip
```

- [ ] **Step 5: Create .env.example**

```bash
# dashboard/.env.example
AUTH_SECRET=generate-a-32-byte-random-string
AUTH_GITHUB_ID=your-github-oauth-app-id
AUTH_GITHUB_SECRET=your-github-oauth-app-secret
AUTH_GOOGLE_ID=your-google-oauth-client-id
AUTH_GOOGLE_SECRET=your-google-oauth-client-secret

DATABASE_URL=postgresql://user:pass@localhost:5432/durc_triage

PIPELINE_API_URL=http://localhost:8000
PIPELINE_API_SECRET=your-shared-api-secret
```

- [ ] **Step 6: Configure next.config.ts with security headers**

Replace `dashboard/next.config.ts`:

```typescript
// dashboard/next.config.ts
import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self'",
      "connect-src 'self'",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
```

- [ ] **Step 7: Configure Tailwind for dark mode**

Edit `dashboard/tailwind.config.ts` — ensure dark mode uses class strategy (shadcn/ui init should set this, but verify):

```typescript
// dashboard/tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
```

Note: shadcn/ui init may generate a different format. The key requirement is `darkMode: ["class"]`. Preserve whatever shadcn/ui generated and ensure this setting is present.

- [ ] **Step 8: Verify the app builds**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 9: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/ .gitignore
git commit -m "feat: scaffold Next.js dashboard with shadcn/ui and security headers"
```

---

### Task 4: Prisma Schema + Client

**Files:**
- Create: `dashboard/prisma/schema.prisma`
- Create: `dashboard/lib/prisma.ts`

- [ ] **Step 1: Write the Prisma schema**

This mirrors the existing SQLAlchemy models. Prisma is read-only — migrations stay in Alembic.

```prisma
// dashboard/prisma/schema.prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

enum SourceServer {
  biorxiv
  medrxiv
  europepmc
  pubmed
  arxiv
  research_square
  chemrxiv
  zenodo
  ssrn

  @@map("source_server")
}

enum PipelineStage {
  ingested
  coarse_filtered
  fulltext_retrieved
  methods_analysed
  adjudicated

  @@map("pipeline_stage")
}

enum RiskTier {
  low
  medium
  high
  critical

  @@map("risk_tier")
}

enum RecommendedAction {
  archive
  monitor
  review
  escalate

  @@map("recommended_action")
}

enum ReviewStatus {
  unreviewed
  under_review
  confirmed_concern
  false_positive
  archived

  @@map("review_status")
}

enum UserRole {
  admin
  analyst

  @@map("user_role")
}

model Paper {
  id                       String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  doi                      String?          @db.VarChar(255)
  title                    String
  authors                  Json?
  correspondingAuthor      String?          @map("corresponding_author") @db.VarChar(512)
  correspondingInstitution String?          @map("corresponding_institution") @db.VarChar(512)
  abstract                 String?
  sourceServer             SourceServer     @map("source_server")
  postedDate               DateTime         @map("posted_date") @db.Date
  subjectCategory          String?          @map("subject_category") @db.VarChar(255)
  version                  Int              @default(1)
  fullTextUrl              String?          @map("full_text_url")
  fullTextRetrieved        Boolean          @default(false) @map("full_text_retrieved")
  fullTextContent          String?          @map("full_text_content")
  methodsSection           String?          @map("methods_section")
  enrichmentData           Json?            @map("enrichment_data")
  pipelineStage            PipelineStage    @default(ingested) @map("pipeline_stage")
  stage1Result             Json?            @map("stage1_result")
  stage2Result             Json?            @map("stage2_result")
  stage3Result             Json?            @map("stage3_result")
  riskTier                 RiskTier?        @map("risk_tier")
  recommendedAction        RecommendedAction? @map("recommended_action")
  aggregateScore           Int?             @map("aggregate_score")
  reviewStatus             ReviewStatus     @default(unreviewed) @map("review_status")
  analystNotes             String?          @map("analyst_notes")
  isDuplicateOf            String?          @map("is_duplicate_of") @db.Uuid
  createdAt                DateTime         @default(now()) @map("created_at") @db.Timestamptz
  updatedAt                DateTime         @default(now()) @updatedAt @map("updated_at") @db.Timestamptz

  assessmentLogs AssessmentLog[]

  @@index([doi])
  @@index([postedDate])
  @@index([pipelineStage])
  @@index([riskTier])
  @@index([reviewStatus])
  @@index([isDuplicateOf])
  @@map("papers")
}

model AssessmentLog {
  id            String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  paperId       String   @map("paper_id") @db.Uuid
  stage         String   @db.VarChar(50)
  modelUsed     String   @map("model_used") @db.VarChar(100)
  promptVersion String   @map("prompt_version") @db.VarChar(50)
  promptText    String   @map("prompt_text")
  rawResponse   String   @map("raw_response")
  parsedResult  Json?    @map("parsed_result")
  inputTokens   Int      @map("input_tokens")
  outputTokens  Int      @map("output_tokens")
  costEstimateUsd Float  @map("cost_estimate_usd")
  error         String?
  createdAt     DateTime @default(now()) @map("created_at") @db.Timestamptz

  paper Paper @relation(fields: [paperId], references: [id])

  @@index([paperId])
  @@index([stage])
  @@index([createdAt])
  @@map("assessment_logs")
}

model PipelineRun {
  id                     String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  startedAt              DateTime  @map("started_at") @db.Timestamptz
  finishedAt             DateTime? @map("finished_at") @db.Timestamptz
  papersIngested         Int       @default(0) @map("papers_ingested")
  papersAfterDedup       Int       @default(0) @map("papers_after_dedup")
  papersCoarsePassed     Int       @default(0) @map("papers_coarse_passed")
  papersFulltextRetrieved Int      @default(0) @map("papers_fulltext_retrieved")
  papersMethodsAnalysed  Int       @default(0) @map("papers_methods_analysed")
  papersEnriched         Int       @default(0) @map("papers_enriched")
  papersAdjudicated      Int       @default(0) @map("papers_adjudicated")
  errors                 Json?
  totalCostUsd           Float     @default(0) @map("total_cost_usd")
  trigger                String    @db.VarChar(50)

  @@map("pipeline_runs")
}

model User {
  id        String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  email     String   @unique @db.VarChar(320)
  name      String?  @db.VarChar(255)
  image     String?
  role      UserRole @default(analyst)
  createdAt DateTime @default(now()) @map("created_at") @db.Timestamptz
  updatedAt DateTime @default(now()) @updatedAt @map("updated_at") @db.Timestamptz

  accounts Account[]
  sessions Session[]

  @@map("users")
}

model Account {
  id                String @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  userId            String @map("user_id") @db.Uuid
  type              String
  provider          String
  providerAccountId String @map("provider_account_id")
  refreshToken      String? @map("refresh_token")
  accessToken       String? @map("access_token")
  expiresAt         Int?    @map("expires_at")
  tokenType         String? @map("token_type")
  scope             String?
  idToken           String? @map("id_token")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([provider, providerAccountId])
  @@map("accounts")
}

model Session {
  id           String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  sessionToken String   @unique @map("session_token")
  userId       String   @map("user_id") @db.Uuid
  expires      DateTime

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@map("sessions")
}

model PipelineSettings {
  id        Int      @id @default(1)
  settings  Json     @default("{}")
  updatedAt DateTime @default(now()) @updatedAt @map("updated_at") @db.Timestamptz

  @@map("pipeline_settings")
}
```

- [ ] **Step 2: Create Prisma client singleton**

```typescript
// dashboard/lib/prisma.ts
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

- [ ] **Step 3: Generate Prisma client**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npx prisma generate
```

Expected: `Prisma Client generated successfully`.

- [ ] **Step 4: Verify build still works**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/prisma/ dashboard/lib/prisma.ts
git commit -m "feat: add Prisma schema mirroring SQLAlchemy models"
```

---

### Task 5: Auth Setup

**Files:**
- Create: `dashboard/lib/auth.ts`
- Create: `dashboard/lib/auth-guard.ts`
- Create: `dashboard/middleware.ts`
- Create: `dashboard/app/api/auth/[...nextauth]/route.ts`
- Create: `dashboard/app/login/page.tsx`

- [ ] **Step 1: Create Auth.js configuration**

```typescript
// dashboard/lib/auth.ts
import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";

export const { handlers, signIn, signOut, auth } = NextAuth({
  adapter: PrismaAdapter(prisma),
  providers: [GitHub, Google],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async session({ session, user }) {
      // Fetch role from our users table
      const dbUser = await prisma.user.findUnique({
        where: { email: user.email! },
        select: { role: true, id: true },
      });
      if (dbUser) {
        session.user.role = dbUser.role;
        session.user.id = dbUser.id;
      }
      return session;
    },
  },
});
```

- [ ] **Step 2: Create auth type augmentation**

Add a type augmentation file so TypeScript knows about the `role` property on the session:

```typescript
// dashboard/types/next-auth.d.ts
import { UserRole } from "@prisma/client";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
      role: UserRole;
    };
  }
}
```

- [ ] **Step 3: Create auth guard helpers**

```typescript
// dashboard/lib/auth-guard.ts
import { auth } from "@/lib/auth";
import { UserRole } from "@prisma/client";
import { redirect } from "next/navigation";

export async function requireAuth() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }
  return session;
}

export async function requireAdmin() {
  const session = await requireAuth();
  if (session.user.role !== UserRole.admin) {
    redirect("/");
  }
  return session;
}
```

- [ ] **Step 4: Create middleware for route protection**

```typescript
// dashboard/middleware.ts
export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - /login
     * - /api/auth (Auth.js routes)
     * - /_next/static, /_next/image (Next.js internals)
     * - /favicon.ico
     */
    "/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
};
```

- [ ] **Step 5: Create Auth.js API route**

```typescript
// dashboard/app/api/auth/[...nextauth]/route.ts
import { handlers } from "@/lib/auth";

export const { GET, POST } = handlers;
```

- [ ] **Step 6: Create login page**

```tsx
// dashboard/app/login/page.tsx
import { signIn } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-900">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-600 text-white font-bold">
            DT
          </div>
          <CardTitle className="text-2xl">DURC Triage</CardTitle>
          <CardDescription>
            Sign in to access the biosecurity paper review dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <form
            action={async () => {
              "use server";
              await signIn("github", { redirectTo: "/" });
            }}
          >
            <Button variant="outline" className="w-full" type="submit">
              Sign in with GitHub
            </Button>
          </form>
          <form
            action={async () => {
              "use server";
              await signIn("google", { redirectTo: "/" });
            }}
          >
            <Button variant="outline" className="w-full" type="submit">
              Sign in with Google
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 7: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

Expected: Build succeeds. (OAuth won't work without real credentials, but the code compiles.)

- [ ] **Step 8: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/lib/auth.ts dashboard/lib/auth-guard.ts dashboard/middleware.ts \
  dashboard/app/api/auth/ dashboard/app/login/ dashboard/types/
git commit -m "feat: add Auth.js v5 with GitHub + Google OAuth and role-based guards"
```

---

### Task 6: Shared Libraries

**Files:**
- Create: `dashboard/lib/risk-colors.ts`
- Create: `dashboard/lib/utils.ts`
- Create: `dashboard/lib/pipeline-api.ts`
- Create: `dashboard/lib/search.ts`

- [ ] **Step 1: Create risk colour mapping**

```typescript
// dashboard/lib/risk-colors.ts
import { RiskTier } from "@prisma/client";

type RiskStyle = {
  badge: string;
  border: string;
  dot: string;
  label: string;
};

const styles: Record<RiskTier, RiskStyle> = {
  [RiskTier.critical]: {
    badge: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
    border: "border-l-red-500",
    dot: "bg-red-500",
    label: "CRITICAL",
  },
  [RiskTier.high]: {
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-200",
    border: "border-l-orange-500",
    dot: "bg-orange-500",
    label: "HIGH",
  },
  [RiskTier.medium]: {
    badge: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-200",
    border: "border-l-yellow-500",
    dot: "bg-yellow-500",
    label: "MEDIUM",
  },
  [RiskTier.low]: {
    badge: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200",
    border: "border-l-green-500",
    dot: "bg-green-500",
    label: "LOW",
  },
};

export function riskStyle(tier: RiskTier | null): RiskStyle {
  if (!tier) return styles[RiskTier.low];
  return styles[tier];
}

export function dimensionColor(score: number): string {
  if (score >= 3) return "bg-red-500";
  if (score >= 2) return "bg-orange-500";
  if (score >= 1) return "bg-yellow-500";
  return "bg-slate-300 dark:bg-slate-600";
}
```

- [ ] **Step 2: Create utility functions**

```typescript
// dashboard/lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDuration(start: Date | string, end: Date | string | null): string {
  if (!end) return "Running...";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining}s`;
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

export function sourceServerLabel(server: string): string {
  const labels: Record<string, string> = {
    biorxiv: "bioRxiv",
    medrxiv: "medRxiv",
    europepmc: "Europe PMC",
    pubmed: "PubMed",
    arxiv: "arXiv",
    research_square: "Research Square",
    chemrxiv: "ChemRxiv",
    zenodo: "Zenodo",
    ssrn: "SSRN",
  };
  return labels[server] ?? server;
}
```

Note: shadcn/ui may have already created a `lib/utils.ts` with just the `cn` function. If so, add the other functions to it rather than overwriting.

- [ ] **Step 3: Create pipeline API client**

```typescript
// dashboard/lib/pipeline-api.ts
const PIPELINE_URL = process.env.PIPELINE_API_URL ?? "http://localhost:8000";
const PIPELINE_SECRET = process.env.PIPELINE_API_SECRET ?? "";

async function pipelineFetch(path: string, options: RequestInit = {}) {
  const res = await fetch(`${PIPELINE_URL}${path}`, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${PIPELINE_SECRET}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Pipeline API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getPipelineStatus() {
  return pipelineFetch("/status");
}

export async function triggerPipelineRun() {
  return pipelineFetch("/run", { method: "POST" });
}

export async function pausePipeline() {
  return pipelineFetch("/pause", { method: "POST" });
}

export async function resumePipeline() {
  return pipelineFetch("/resume", { method: "POST" });
}

export async function updatePipelineSchedule(hour: number, minute: number) {
  return pipelineFetch("/schedule", {
    method: "PUT",
    body: JSON.stringify({ hour, minute }),
  });
}
```

- [ ] **Step 4: Create search query builder**

```typescript
// dashboard/lib/search.ts
/**
 * Sanitize user input for PostgreSQL to_tsquery.
 * Strips characters that would break query parsing, joins terms with &.
 */
export function buildSearchQuery(raw: string): string {
  const cleaned = raw
    .replace(/[^\w\s-]/g, "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (cleaned.length === 0) return "";
  return cleaned.map((term) => `${term}:*`).join(" & ");
}
```

- [ ] **Step 5: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/lib/risk-colors.ts dashboard/lib/utils.ts \
  dashboard/lib/pipeline-api.ts dashboard/lib/search.ts
git commit -m "feat: add shared dashboard utilities (risk colors, search, pipeline client)"
```

---

### Task 7: Root Layout + Sidebar + Theme

**Files:**
- Modify: `dashboard/app/layout.tsx`
- Create: `dashboard/components/sidebar.tsx`
- Create: `dashboard/components/theme-toggle.tsx`
- Modify: `dashboard/app/globals.css` (if needed)

- [ ] **Step 1: Create theme toggle component**

```tsx
// dashboard/components/theme-toggle.tsx
"use client";

import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}
```

- [ ] **Step 2: Create sidebar component**

```tsx
// dashboard/components/sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, FileText, Settings, Workflow } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

const navItems = [
  { href: "/", label: "Daily Feed", icon: FileText },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/pipeline", label: "Pipeline", icon: Workflow },
  { href: "/settings", label: "Settings", icon: Settings },
];

type SidebarProps = {
  pipelineStatus?: {
    running: boolean;
    paused: boolean;
    next_run_time: string | null;
  } | null;
  userName?: string | null;
};

export function Sidebar({ pipelineStatus, userName }: SidebarProps) {
  const pathname = usePathname();

  const statusDot = pipelineStatus
    ? pipelineStatus.paused
      ? "bg-yellow-500"
      : pipelineStatus.running
        ? "bg-green-500"
        : "bg-slate-400"
    : "bg-slate-400";

  const statusLabel = pipelineStatus
    ? pipelineStatus.paused
      ? "Paused"
      : pipelineStatus.running
        ? "Running"
        : "Idle"
    : "Unknown";

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
          DT
        </div>
        <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
          DURC Triage
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2" aria-label="Main navigation">
        <ul className="flex flex-col gap-1">
          {navItems.map((item) => {
            const isActive = item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "border-l-2 border-blue-500 bg-slate-100 text-blue-600 dark:bg-slate-700 dark:text-blue-400"
                      : "text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-700"
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Pipeline status */}
      <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <div className={cn("h-2 w-2 rounded-full", statusDot)} aria-hidden="true" />
          <span>Pipeline {statusLabel}</span>
        </div>
        {pipelineStatus?.next_run_time && (
          <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
            Next: {new Date(pipelineStatus.next_run_time).toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-700">
        <span className="truncate text-xs text-slate-500 dark:text-slate-400">
          {userName ?? "User"}
        </span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
```

- [ ] **Step 3: Update root layout**

```tsx
// dashboard/app/layout.tsx
import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { auth } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "DURC Triage Dashboard",
  description: "Biosecurity paper review and triage system",
};

async function getPipelineStatusSafe() {
  try {
    const url = process.env.PIPELINE_API_URL ?? "http://localhost:8000";
    const secret = process.env.PIPELINE_API_SECRET ?? "";
    const res = await fetch(`${url}/status`, {
      headers: { Authorization: `Bearer ${secret}` },
      cache: "no-store",
    });
    if (res.ok) return res.json();
  } catch {
    // Pipeline sidecar may not be running
  }
  return null;
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  const pipelineStatus = session ? await getPipelineStatusSafe() : null;

  // Login page renders without sidebar
  if (!session) {
    return (
      <html lang="en" suppressHydrationWarning>
        <body>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
            <NuqsAdapter>
              {children}
            </NuqsAdapter>
          </ThemeProvider>
        </body>
      </html>
    );
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <NuqsAdapter>
            <div className="flex h-screen bg-slate-50 dark:bg-slate-900">
              <Sidebar
                pipelineStatus={pipelineStatus}
                userName={session.user?.name}
              />
              <main className="flex-1 overflow-y-auto p-6">
                {children}
              </main>
            </div>
          </NuqsAdapter>
        </ThemeProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/app/layout.tsx dashboard/components/sidebar.tsx \
  dashboard/components/theme-toggle.tsx
git commit -m "feat: add root layout with sidebar navigation and dark mode toggle"
```

---

### Task 8: Paper Card + Filters Components

**Files:**
- Create: `dashboard/components/paper-card.tsx`
- Create: `dashboard/components/paper-filters.tsx`

- [ ] **Step 1: Create paper card component**

```tsx
// dashboard/components/paper-card.tsx
import Link from "next/link";
import type { Paper } from "@prisma/client";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { riskStyle } from "@/lib/risk-colors";
import { formatDate, sourceServerLabel } from "@/lib/utils";

type Stage2Result = {
  summary?: string;
  dimensions?: Record<string, { score: number; justification: string }>;
  aggregate_score?: number;
};

type PaperCardProps = {
  paper: Paper;
};

export function PaperCard({ paper }: PaperCardProps) {
  const style = riskStyle(paper.riskTier);
  const stage2 = paper.stage2Result as Stage2Result | null;
  const stage3 = paper.stage3Result as { summary?: string } | null;
  const summary = stage3?.summary ?? stage2?.summary ?? null;

  // Show risk dimensions scoring >= 2
  const highDimensions = stage2?.dimensions
    ? Object.entries(stage2.dimensions)
        .filter(([, d]) => d.score >= 2)
        .sort(([, a], [, b]) => b.score - a.score)
    : [];

  // Format author list
  const authors = Array.isArray(paper.authors)
    ? paper.authors
        .slice(0, 3)
        .map((a: { name?: string }) => a.name ?? "Unknown")
        .join(", ") + (paper.authors.length > 3 ? " et al." : "")
    : paper.correspondingAuthor ?? "Unknown authors";

  return (
    <Link href={`/paper/${paper.id}`} className="block">
      <Card
        className={cn(
          "border-l-4 p-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800",
          style.border
        )}
        role="article"
        aria-label={`${paper.title}. Risk tier: ${style.label}, score ${paper.aggregateScore ?? 0} out of 18`}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {paper.title}
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {authors} &middot; {paper.correspondingInstitution ?? ""} &middot;{" "}
              {sourceServerLabel(paper.sourceServer)} &middot; {formatDate(paper.postedDate)}
            </p>
          </div>
          <Badge className={cn("shrink-0", style.badge)} aria-label={`Risk tier: ${style.label}`}>
            {style.label}
          </Badge>
        </div>

        {summary && (
          <p className="mt-2 line-clamp-2 text-xs text-slate-600 dark:text-slate-300">
            {summary}
          </p>
        )}

        {highDimensions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {highDimensions.map(([name, dim]) => (
              <span
                key={name}
                className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 dark:bg-slate-700 dark:text-slate-300"
              >
                {name.replace(/_/g, " ")}: {dim.score}
              </span>
            ))}
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
              Score: {paper.aggregateScore ?? 0}/18
            </span>
          </div>
        )}
      </Card>
    </Link>
  );
}
```

- [ ] **Step 2: Create filter bar component**

```tsx
// dashboard/components/paper-filters.tsx
"use client";

import { useQueryState, parseAsString, parseAsInteger } from "nuqs";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Search, X } from "lucide-react";

export function PaperFilters() {
  const [riskTier, setRiskTier] = useQueryState("tier", parseAsString.withDefault("all"));
  const [source, setSource] = useQueryState("source", parseAsString.withDefault("all"));
  const [status, setStatus] = useQueryState("status", parseAsString.withDefault("all"));
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));
  const [, setPage] = useQueryState("page", parseAsInteger.withDefault(1));

  const resetPage = () => setPage(1);

  const hasFilters = riskTier !== "all" || source !== "all" || status !== "all" || search !== "";

  function clearAll() {
    setRiskTier("all");
    setSource("all");
    setStatus("all");
    setSearch("");
    setPage(1);
  }

  return (
    <div className="flex flex-wrap items-center gap-2" role="search" aria-label="Filter papers">
      <Select
        value={riskTier}
        onValueChange={(v) => { setRiskTier(v); resetPage(); }}
      >
        <SelectTrigger className="w-32" aria-label="Filter by risk tier">
          <SelectValue placeholder="Risk Tier" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Tiers</SelectItem>
          <SelectItem value="critical">Critical</SelectItem>
          <SelectItem value="high">High</SelectItem>
          <SelectItem value="medium">Medium</SelectItem>
          <SelectItem value="low">Low</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={source}
        onValueChange={(v) => { setSource(v); resetPage(); }}
      >
        <SelectTrigger className="w-36" aria-label="Filter by source">
          <SelectValue placeholder="Source" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Sources</SelectItem>
          <SelectItem value="biorxiv">bioRxiv</SelectItem>
          <SelectItem value="medrxiv">medRxiv</SelectItem>
          <SelectItem value="pubmed">PubMed</SelectItem>
          <SelectItem value="europepmc">Europe PMC</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={status}
        onValueChange={(v) => { setStatus(v); resetPage(); }}
      >
        <SelectTrigger className="w-40" aria-label="Filter by review status">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Statuses</SelectItem>
          <SelectItem value="unreviewed">Unreviewed</SelectItem>
          <SelectItem value="under_review">Under Review</SelectItem>
          <SelectItem value="confirmed_concern">Confirmed Concern</SelectItem>
          <SelectItem value="false_positive">False Positive</SelectItem>
          <SelectItem value="archived">Archived</SelectItem>
        </SelectContent>
      </Select>

      <div className="relative flex-1">
        <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
        <Input
          type="search"
          placeholder="Search papers..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); resetPage(); }}
          className="pl-8"
          aria-label="Search papers by title or abstract"
        />
      </div>

      {hasFilters && (
        <Button variant="ghost" size="sm" onClick={clearAll} aria-label="Clear all filters">
          <X className="mr-1 h-3 w-3" />
          Clear
        </Button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/components/paper-card.tsx dashboard/components/paper-filters.tsx
git commit -m "feat: add paper card and filter bar components"
```

---

### Task 9: Daily Feed Page + API Route

**Files:**
- Modify: `dashboard/app/page.tsx`
- Create: `dashboard/app/api/papers/route.ts`

- [ ] **Step 1: Create papers API route**

```typescript
// dashboard/app/api/papers/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma, PipelineStage } from "@prisma/client";
import { buildSearchQuery } from "@/lib/search";

const PAGE_SIZE = 20;

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const page = Math.max(1, parseInt(params.get("page") ?? "1", 10));
  const tier = params.get("tier");
  const source = params.get("source");
  const status = params.get("status");
  const search = params.get("q")?.trim();

  const where: Prisma.PaperWhereInput = {
    // Only show papers that passed the coarse filter
    pipelineStage: { not: PipelineStage.ingested },
    isDuplicateOf: null,
  };

  if (tier && tier !== "all") {
    where.riskTier = tier as Prisma.EnumRiskTierFilter["equals"];
  }
  if (source && source !== "all") {
    where.sourceServer = source as Prisma.EnumSourceServerFilter["equals"];
  }
  if (status && status !== "all") {
    where.reviewStatus = status as Prisma.EnumReviewStatusFilter["equals"];
  }

  // Full-text search via raw SQL for tsvector
  let papers;
  let total;

  if (search) {
    const tsquery = buildSearchQuery(search);
    if (tsquery) {
      const countResult = await prisma.$queryRaw<[{ count: bigint }]>`
        SELECT COUNT(*) as count FROM papers
        WHERE search_vector @@ to_tsquery('english', ${tsquery})
          AND pipeline_stage != 'ingested'
          AND is_duplicate_of IS NULL
          ${tier && tier !== "all" ? Prisma.sql`AND risk_tier = ${tier}::risk_tier` : Prisma.empty}
          ${source && source !== "all" ? Prisma.sql`AND source_server = ${source}::source_server` : Prisma.empty}
          ${status && status !== "all" ? Prisma.sql`AND review_status = ${status}::review_status` : Prisma.empty}
      `;
      total = Number(countResult[0].count);

      papers = await prisma.$queryRaw`
        SELECT * FROM papers
        WHERE search_vector @@ to_tsquery('english', ${tsquery})
          AND pipeline_stage != 'ingested'
          AND is_duplicate_of IS NULL
          ${tier && tier !== "all" ? Prisma.sql`AND risk_tier = ${tier}::risk_tier` : Prisma.empty}
          ${source && source !== "all" ? Prisma.sql`AND source_server = ${source}::source_server` : Prisma.empty}
          ${status && status !== "all" ? Prisma.sql`AND review_status = ${status}::review_status` : Prisma.empty}
        ORDER BY ts_rank(search_vector, to_tsquery('english', ${tsquery})) DESC
        LIMIT ${PAGE_SIZE} OFFSET ${(page - 1) * PAGE_SIZE}
      `;
    } else {
      papers = [];
      total = 0;
    }
  } else {
    total = await prisma.paper.count({ where });
    papers = await prisma.paper.findMany({
      where,
      orderBy: [
        { riskTier: "desc" },
        { postedDate: "desc" },
      ],
      take: PAGE_SIZE,
      skip: (page - 1) * PAGE_SIZE,
    });
  }

  return NextResponse.json({
    papers,
    total,
    page,
    pageSize: PAGE_SIZE,
    totalPages: Math.ceil(total / PAGE_SIZE),
  });
}
```

- [ ] **Step 2: Create daily feed page**

```tsx
// dashboard/app/page.tsx
import { prisma } from "@/lib/prisma";
import { PipelineStage, Prisma } from "@prisma/client";
import { PaperCard } from "@/components/paper-card";
import { PaperFilters } from "@/components/paper-filters";
import { Button } from "@/components/ui/button";
import { buildSearchQuery } from "@/lib/search";
import Link from "next/link";

const PAGE_SIZE = 20;

type Props = {
  searchParams: Promise<{
    page?: string;
    tier?: string;
    source?: string;
    status?: string;
    q?: string;
  }>;
};

export default async function DailyFeedPage({ searchParams }: Props) {
  const params = await searchParams;
  const page = Math.max(1, parseInt(params.page ?? "1", 10));
  const tier = params.tier;
  const source = params.source;
  const status = params.status;
  const search = params.q?.trim();

  const where: Prisma.PaperWhereInput = {
    pipelineStage: { not: PipelineStage.ingested },
    isDuplicateOf: null,
  };

  if (tier && tier !== "all") {
    where.riskTier = tier as Prisma.EnumRiskTierFilter["equals"];
  }
  if (source && source !== "all") {
    where.sourceServer = source as Prisma.EnumSourceServerFilter["equals"];
  }
  if (status && status !== "all") {
    where.reviewStatus = status as Prisma.EnumReviewStatusFilter["equals"];
  }

  let papers;
  let total: number;

  if (search) {
    const tsquery = buildSearchQuery(search);
    if (tsquery) {
      const countResult = await prisma.$queryRaw<[{ count: bigint }]>`
        SELECT COUNT(*) as count FROM papers
        WHERE search_vector @@ to_tsquery('english', ${tsquery})
          AND pipeline_stage != 'ingested'
          AND is_duplicate_of IS NULL
      `;
      total = Number(countResult[0].count);
      papers = await prisma.$queryRaw`
        SELECT * FROM papers
        WHERE search_vector @@ to_tsquery('english', ${tsquery})
          AND pipeline_stage != 'ingested'
          AND is_duplicate_of IS NULL
        ORDER BY ts_rank(search_vector, to_tsquery('english', ${tsquery})) DESC
        LIMIT ${PAGE_SIZE} OFFSET ${(page - 1) * PAGE_SIZE}
      `;
    } else {
      papers = [];
      total = 0;
    }
  } else {
    total = await prisma.paper.count({ where });
    papers = await prisma.paper.findMany({
      where,
      orderBy: [{ riskTier: "desc" }, { postedDate: "desc" }],
      take: PAGE_SIZE,
      skip: (page - 1) * PAGE_SIZE,
    });
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Daily Feed
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {total} papers flagged &middot; {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </p>
        </div>
      </div>

      <div className="mb-4">
        <PaperFilters />
      </div>

      <div className="flex flex-col gap-3" role="feed" aria-label="Flagged papers">
        {(papers as typeof papers & { id: string }[]).map((paper) => (
          <PaperCard key={paper.id} paper={paper} />
        ))}
        {(papers as unknown[]).length === 0 && (
          <p className="py-12 text-center text-sm text-slate-500 dark:text-slate-400">
            No papers match your filters.
          </p>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-2" role="navigation" aria-label="Pagination">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            asChild={page > 1}
          >
            {page > 1 ? (
              <Link href={`/?page=${page - 1}&tier=${tier ?? "all"}&source=${source ?? "all"}&status=${status ?? "all"}&q=${search ?? ""}`}>
                Previous
              </Link>
            ) : (
              <span>Previous</span>
            )}
          </Button>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            asChild={page < totalPages}
          >
            {page < totalPages ? (
              <Link href={`/?page=${page + 1}&tier=${tier ?? "all"}&source=${source ?? "all"}&status=${status ?? "all"}&q=${search ?? ""}`}>
                Next
              </Link>
            ) : (
              <span>Next</span>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/app/page.tsx dashboard/app/api/papers/route.ts
git commit -m "feat: add daily feed page with filtering, search, and pagination"
```

---

### Task 10: Paper Detail — Risk Panel + Shared Detail Components

**Files:**
- Create: `dashboard/components/dimension-bar.tsx`
- Create: `dashboard/components/risk-panel.tsx`
- Create: `dashboard/components/review-status-select.tsx`
- Create: `dashboard/components/analyst-notes.tsx`
- Create: `dashboard/components/methods-viewer.tsx`
- Create: `dashboard/components/enrichment-card.tsx`
- Create: `dashboard/components/audit-trail.tsx`

- [ ] **Step 1: Create dimension bar component**

```tsx
// dashboard/components/dimension-bar.tsx
import { cn } from "@/lib/utils";
import { dimensionColor } from "@/lib/risk-colors";

type DimensionBarProps = {
  label: string;
  score: number;
  maxScore?: number;
  justification?: string;
};

export function DimensionBar({ label, score, maxScore = 3, justification }: DimensionBarProps) {
  const pct = (score / maxScore) * 100;
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-600 dark:text-slate-400">{label}</span>
        <span className="font-semibold text-slate-700 dark:text-slate-300">
          {score}/{maxScore}
        </span>
      </div>
      <div
        className="mt-1 h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-600"
        role="progressbar"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={maxScore}
        aria-label={`${label}: ${score} out of ${maxScore}`}
      >
        <div
          className={cn("h-full rounded-full transition-all", dimensionColor(score))}
          style={{ width: `${pct}%` }}
        />
      </div>
      {justification && (
        <p className="mt-1 text-[10px] leading-tight text-slate-500 dark:text-slate-400">
          {justification}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create risk panel component**

```tsx
// dashboard/components/risk-panel.tsx
import { DimensionBar } from "@/components/dimension-bar";
import { ReviewStatusSelect } from "@/components/review-status-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { riskStyle } from "@/lib/risk-colors";
import { cn } from "@/lib/utils";
import { ExternalLink } from "lucide-react";
import type { Paper } from "@prisma/client";

type Dimensions = Record<string, { score: number; justification: string }>;

const dimensionLabels: Record<string, string> = {
  pathogen_enhancement: "Pathogen Enhancement",
  synthesis_barrier_lowering: "Synthesis Barrier",
  select_agent_relevance: "Select Agent",
  novel_technique: "Novel Technique",
  information_hazard: "Info Hazard",
  defensive_framing: "Defensive Framing",
};

type RiskPanelProps = {
  paper: Paper;
};

export function RiskPanel({ paper }: RiskPanelProps) {
  const style = riskStyle(paper.riskTier);
  const stage2 = paper.stage2Result as { dimensions?: Dimensions } | null;
  const dimensions = stage2?.dimensions ?? {};

  const doiUrl = paper.doi ? `https://doi.org/${paper.doi}` : null;

  return (
    <div className="sticky top-6 space-y-4">
      {/* Aggregate badge */}
      <div className="text-center">
        <Badge className={cn("text-lg px-3 py-1", style.badge)}>
          {style.label} &middot; {paper.aggregateScore ?? 0}/18
        </Badge>
      </div>

      {/* Risk dimensions */}
      <div>
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Risk Dimensions
        </h3>
        {Object.entries(dimensionLabels).map(([key, label]) => {
          const dim = dimensions[key];
          return (
            <DimensionBar
              key={key}
              label={label}
              score={dim?.score ?? 0}
              justification={dim?.justification}
            />
          );
        })}
      </div>

      {/* Review status */}
      <div className="border-t border-slate-200 pt-4 dark:border-slate-700">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Review Status
        </h3>
        <ReviewStatusSelect paperId={paper.id} currentStatus={paper.reviewStatus} />
      </div>

      {/* Actions */}
      <div className="space-y-2">
        {doiUrl && (
          <Button variant="outline" size="sm" className="w-full" asChild>
            <a href={doiUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="mr-2 h-3 w-3" />
              Open Original
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create review status select component**

```tsx
// dashboard/components/review-status-select.tsx
"use client";

import { useState, useTransition } from "react";
import { ReviewStatus } from "@prisma/client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const statusLabels: Record<ReviewStatus, string> = {
  [ReviewStatus.unreviewed]: "Unreviewed",
  [ReviewStatus.under_review]: "Under Review",
  [ReviewStatus.confirmed_concern]: "Confirmed Concern",
  [ReviewStatus.false_positive]: "False Positive",
  [ReviewStatus.archived]: "Archived",
};

type Props = {
  paperId: string;
  currentStatus: ReviewStatus;
};

export function ReviewStatusSelect({ paperId, currentStatus }: Props) {
  const [status, setStatus] = useState(currentStatus);
  const [isPending, startTransition] = useTransition();

  function handleChange(value: string) {
    const newStatus = value as ReviewStatus;
    setStatus(newStatus);
    startTransition(async () => {
      await fetch(`/api/papers/${paperId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewStatus: newStatus }),
      });
    });
  }

  return (
    <Select value={status} onValueChange={handleChange} disabled={isPending}>
      <SelectTrigger aria-label="Change review status">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(statusLabels).map(([value, label]) => (
          <SelectItem key={value} value={value}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

- [ ] **Step 4: Create analyst notes component**

```tsx
// dashboard/components/analyst-notes.tsx
"use client";

import { useState, useTransition } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Save } from "lucide-react";

type Props = {
  paperId: string;
  initialNotes: string | null;
};

export function AnalystNotes({ paperId, initialNotes }: Props) {
  const [notes, setNotes] = useState(initialNotes ?? "");
  const [isPending, startTransition] = useTransition();
  const [saved, setSaved] = useState(false);

  function save() {
    startTransition(async () => {
      await fetch(`/api/papers/${paperId}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div>
      <Textarea
        value={notes}
        onChange={(e) => { setNotes(e.target.value); setSaved(false); }}
        placeholder="Add analyst notes..."
        rows={4}
        aria-label="Analyst notes"
      />
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" onClick={save} disabled={isPending}>
          <Save className="mr-1 h-3 w-3" />
          {isPending ? "Saving..." : "Save"}
        </Button>
        {saved && (
          <span className="text-xs text-green-600 dark:text-green-400" aria-live="polite">
            Saved
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create methods viewer component**

```tsx
// dashboard/components/methods-viewer.tsx
type Props = {
  methods: string | null;
};

export function MethodsViewer({ methods }: Props) {
  if (!methods) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
        Full text not retrieved. The paper may not have an open-access version, or the methods section could not be extracted.
      </div>
    );
  }

  return (
    <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
      {methods}
    </pre>
  );
}
```

- [ ] **Step 6: Create enrichment card component**

```tsx
// dashboard/components/enrichment-card.tsx
import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";

type EnrichmentData = {
  openalex?: {
    cited_by_count?: number;
    topics?: { display_name: string }[];
    primary_institution?: string;
    funder_names?: string[];
  };
  s2?: {
    tldr?: string;
    citation_count?: number;
    first_author_h_index?: number;
  };
  orcid?: {
    orcid_id?: string;
    current_institution?: string;
    employment_history?: string[];
  };
  _meta?: {
    sources_succeeded: string[];
    sources_failed: string[];
  };
};

type Props = {
  data: EnrichmentData | null;
};

export function EnrichmentCard({ data }: Props) {
  if (!data) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No enrichment data available.
      </p>
    );
  }

  const meta = data._meta;
  const failed = meta?.sources_failed ?? [];

  return (
    <div className="space-y-3">
      {failed.length > 0 && (
        <div className="flex items-start gap-2 rounded-md bg-orange-50 p-3 text-xs text-orange-700 dark:bg-orange-900/20 dark:text-orange-300" role="alert">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          <span>Partial enrichment — failed sources: {failed.join(", ")}</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {data.s2?.first_author_h_index != null && (
          <>
            <span className="text-slate-500 dark:text-slate-400">h-index</span>
            <span className="text-slate-700 dark:text-slate-300">{data.s2.first_author_h_index}</span>
          </>
        )}
        {data.openalex?.cited_by_count != null && (
          <>
            <span className="text-slate-500 dark:text-slate-400">Citations</span>
            <span className="text-slate-700 dark:text-slate-300">{data.openalex.cited_by_count.toLocaleString()}</span>
          </>
        )}
        {data.orcid?.orcid_id && (
          <>
            <span className="text-slate-500 dark:text-slate-400">ORCID</span>
            <span className="text-slate-700 dark:text-slate-300">{data.orcid.orcid_id}</span>
          </>
        )}
        {data.openalex?.primary_institution && (
          <>
            <span className="text-slate-500 dark:text-slate-400">Institution</span>
            <span className="text-slate-700 dark:text-slate-300">{data.openalex.primary_institution}</span>
          </>
        )}
      </div>

      {data.openalex?.topics && data.openalex.topics.length > 0 && (
        <div>
          <span className="text-xs text-slate-500 dark:text-slate-400">Topics: </span>
          <span className="text-xs text-slate-700 dark:text-slate-300">
            {data.openalex.topics.map((t) => t.display_name).join(", ")}
          </span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Create audit trail component**

```tsx
// dashboard/components/audit-trail.tsx
"use client";

import { useState } from "react";
import type { AssessmentLog } from "@prisma/client";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight } from "lucide-react";
import { formatCost } from "@/lib/utils";

type Props = {
  logs: AssessmentLog[];
};

export function AuditTrail({ logs }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (logs.length === 0) {
    return <p className="text-sm text-slate-500">No assessment logs.</p>;
  }

  return (
    <div className="space-y-2">
      {logs.map((log) => {
        const isExpanded = expandedId === log.id;
        return (
          <div
            key={log.id}
            className="rounded-md border border-slate-200 dark:border-slate-700"
          >
            <button
              className="flex w-full items-center gap-2 p-3 text-left text-xs"
              onClick={() => setExpandedId(isExpanded ? null : log.id)}
              aria-expanded={isExpanded}
            >
              {isExpanded ? (
                <ChevronDown className="h-3 w-3 shrink-0" />
              ) : (
                <ChevronRight className="h-3 w-3 shrink-0" />
              )}
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {log.stage}
              </span>
              <span className="text-slate-500 dark:text-slate-400">
                {log.modelUsed} &middot; {log.promptVersion} &middot;{" "}
                {log.inputTokens + log.outputTokens} tokens &middot;{" "}
                {formatCost(log.costEstimateUsd)}
              </span>
              <span className="ml-auto text-slate-400">
                {new Date(log.createdAt).toLocaleString()}
              </span>
            </button>
            {isExpanded && (
              <div className="border-t border-slate-200 p-3 dark:border-slate-700">
                <details className="mb-2">
                  <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-400">
                    Prompt
                  </summary>
                  <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500 dark:text-slate-400">
                    {log.promptText}
                  </pre>
                </details>
                <details>
                  <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-400">
                    Response
                  </summary>
                  <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500 dark:text-slate-400">
                    {log.rawResponse}
                  </pre>
                </details>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 8: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/components/dimension-bar.tsx dashboard/components/risk-panel.tsx \
  dashboard/components/review-status-select.tsx dashboard/components/analyst-notes.tsx \
  dashboard/components/methods-viewer.tsx dashboard/components/enrichment-card.tsx \
  dashboard/components/audit-trail.tsx
git commit -m "feat: add paper detail components (risk panel, notes, enrichment, audit trail)"
```

---

### Task 11: Paper Detail Page + API Routes

**Files:**
- Create: `dashboard/app/paper/[id]/page.tsx`
- Create: `dashboard/app/api/papers/[id]/route.ts`
- Create: `dashboard/app/api/papers/[id]/notes/route.ts`

- [ ] **Step 1: Create paper detail API route**

```typescript
// dashboard/app/api/papers/[id]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

type RouteParams = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const paper = await prisma.paper.findUnique({
    where: { id },
    include: {
      assessmentLogs: { orderBy: { createdAt: "desc" } },
    },
  });
  if (!paper) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(paper);
}

export async function PATCH(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const body = await request.json();

  const data: Record<string, unknown> = {};
  if (body.reviewStatus) data.reviewStatus = body.reviewStatus;

  const paper = await prisma.paper.update({
    where: { id },
    data,
  });
  return NextResponse.json(paper);
}
```

- [ ] **Step 2: Create notes API route**

```typescript
// dashboard/app/api/papers/[id]/notes/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

type RouteParams = { params: Promise<{ id: string }> };

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const { notes } = await request.json();
  const paper = await prisma.paper.update({
    where: { id },
    data: { analystNotes: notes },
  });
  return NextResponse.json({ success: true, analystNotes: paper.analystNotes });
}
```

- [ ] **Step 3: Create paper detail page**

```tsx
// dashboard/app/paper/[id]/page.tsx
import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RiskPanel } from "@/components/risk-panel";
import { EnrichmentCard } from "@/components/enrichment-card";
import { MethodsViewer } from "@/components/methods-viewer";
import { AnalystNotes } from "@/components/analyst-notes";
import { AuditTrail } from "@/components/audit-trail";
import { riskStyle } from "@/lib/risk-colors";
import { cn, formatDate, sourceServerLabel } from "@/lib/utils";
import { ArrowLeft } from "lucide-react";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function PaperDetailPage({ params }: Props) {
  const { id } = await params;
  const paper = await prisma.paper.findUnique({
    where: { id },
    include: {
      assessmentLogs: { orderBy: { createdAt: "desc" } },
    },
  });

  if (!paper) notFound();

  const style = riskStyle(paper.riskTier);
  const stage2 = paper.stage2Result as { summary?: string; key_methods_of_concern?: string[] } | null;
  const stage3 = paper.stage3Result as {
    summary?: string;
    institutional_context?: string;
    durc_oversight_indicators?: string[];
    adjustment_reasoning?: string;
  } | null;

  const authors = Array.isArray(paper.authors)
    ? paper.authors.map((a: { name?: string }) => a.name ?? "Unknown").join(", ")
    : paper.correspondingAuthor ?? "Unknown";

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start gap-3">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/" aria-label="Back to feed">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {paper.title}
          </h1>
          <div className="mt-1 flex items-center gap-2">
            <Badge className={cn(style.badge)}>{style.label}</Badge>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Score: {paper.aggregateScore ?? 0}/18
            </span>
          </div>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex gap-6">
        {/* Left column — scrollable content */}
        <div className="flex-1 space-y-6 min-w-0" style={{ flex: "7" }}>
          {/* Metadata */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Paper Metadata
            </h2>
            <div className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
              <div><span className="text-slate-500 dark:text-slate-400">Authors: </span>{authors}</div>
              {paper.correspondingInstitution && (
                <div><span className="text-slate-500 dark:text-slate-400">Institution: </span>{paper.correspondingInstitution}</div>
              )}
              <div>
                <span className="text-slate-500 dark:text-slate-400">Source: </span>
                {sourceServerLabel(paper.sourceServer)}
                {paper.doi && (
                  <> &middot; <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline dark:text-blue-400">{paper.doi}</a></>
                )}
              </div>
              <div><span className="text-slate-500 dark:text-slate-400">Posted: </span>{formatDate(paper.postedDate)}</div>
            </div>
          </section>

          {/* AI Summary */}
          {(stage3?.summary || stage2?.summary) && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                AI Assessment Summary
              </h2>
              <div className="rounded-md bg-slate-100 p-4 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {stage3?.summary ?? stage2?.summary}
              </div>
            </section>
          )}

          {/* Key Methods of Concern */}
          {stage2?.key_methods_of_concern && stage2.key_methods_of_concern.length > 0 && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Key Methods of Concern
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {stage2.key_methods_of_concern.map((method) => (
                  <Badge key={method} variant="outline" className="border-red-300 text-red-700 dark:border-red-700 dark:text-red-300">
                    {method}
                  </Badge>
                ))}
              </div>
            </section>
          )}

          {/* Adjudication Context */}
          {stage3?.institutional_context && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Adjudication Context
              </h2>
              <div className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
                <p>{stage3.institutional_context}</p>
                {stage3.durc_oversight_indicators && stage3.durc_oversight_indicators.length > 0 && (
                  <div>
                    <span className="text-xs text-slate-500 dark:text-slate-400">DURC Oversight Indicators: </span>
                    {stage3.durc_oversight_indicators.join(", ")}
                  </div>
                )}
                {stage3.adjustment_reasoning && (
                  <div>
                    <span className="text-xs text-slate-500 dark:text-slate-400">Reasoning: </span>
                    {stage3.adjustment_reasoning}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Enrichment */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Author &amp; Institution Context
            </h2>
            <EnrichmentCard data={paper.enrichmentData as Record<string, unknown> | null} />
          </section>

          {/* Methods Section */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Methods Section
            </h2>
            <MethodsViewer methods={paper.methodsSection} />
          </section>

          {/* Analyst Notes */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Analyst Notes
            </h2>
            <AnalystNotes paperId={paper.id} initialNotes={paper.analystNotes} />
          </section>

          {/* Audit Trail */}
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Audit Trail
            </h2>
            <AuditTrail logs={paper.assessmentLogs} />
          </section>
        </div>

        {/* Right column — sticky risk panel */}
        <div className="w-72 shrink-0" style={{ flex: "3" }}>
          <RiskPanel paper={paper} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/app/paper/ dashboard/app/api/papers/
git commit -m "feat: add paper detail page with two-column layout and all assessment sections"
```

---

### Task 12: Analytics Page

**Files:**
- Create: `dashboard/components/kpi-card.tsx`
- Create: `dashboard/components/analytics-charts.tsx`
- Create: `dashboard/app/analytics/page.tsx`
- Create: `dashboard/app/api/stats/route.ts`

- [ ] **Step 1: Create KPI card component**

```tsx
// dashboard/components/kpi-card.tsx
import { Card } from "@/components/ui/card";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

type KpiCardProps = {
  title: string;
  value: string | number;
  trend?: number | null; // percentage change
  subtitle?: string;
};

export function KpiCard({ title, value, trend, subtitle }: KpiCardProps) {
  const TrendIcon = trend && trend > 0 ? TrendingUp : trend && trend < 0 ? TrendingDown : Minus;
  const trendColor = trend && trend > 0 ? "text-red-500" : trend && trend < 0 ? "text-green-500" : "text-slate-400";

  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{title}</p>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</span>
        {trend != null && (
          <span className={`flex items-center text-xs ${trendColor}`}>
            <TrendIcon className="mr-0.5 h-3 w-3" />
            {Math.abs(trend)}%
          </span>
        )}
      </div>
      {subtitle && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Create analytics charts component**

```tsx
// dashboard/components/analytics-charts.tsx
"use client";

import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Card } from "@/components/ui/card";
import { useTheme } from "next-themes";

const COLORS = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

type PapersOverTimeData = {
  date: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
}[];

type InstitutionData = { name: string; count: number }[];

type DimensionTrendData = {
  date: string;
  pathogen_enhancement: number;
  synthesis_barrier_lowering: number;
  select_agent_relevance: number;
  novel_technique: number;
  information_hazard: number;
  defensive_framing: number;
}[];

type Props = {
  papersOverTime: PapersOverTimeData;
  topInstitutions: InstitutionData;
  topCategories: InstitutionData;
  dimensionTrends: DimensionTrendData;
};

export function AnalyticsCharts({
  papersOverTime,
  topInstitutions,
  topCategories,
  dimensionTrends,
}: Props) {
  const { resolvedTheme } = useTheme();
  const textColor = resolvedTheme === "dark" ? "#94a3b8" : "#64748b";
  const gridColor = resolvedTheme === "dark" ? "#334155" : "#e2e8f0";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Papers over time */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Papers Over Time
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={papersOverTime}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="date" tick={{ fill: textColor, fontSize: 10 }} />
            <YAxis tick={{ fill: textColor, fontSize: 10 }} />
            <Tooltip />
            <Area type="monotone" dataKey="critical" stackId="1" fill={COLORS.critical} stroke={COLORS.critical} />
            <Area type="monotone" dataKey="high" stackId="1" fill={COLORS.high} stroke={COLORS.high} />
            <Area type="monotone" dataKey="medium" stackId="1" fill={COLORS.medium} stroke={COLORS.medium} />
            <Area type="monotone" dataKey="low" stackId="1" fill={COLORS.low} stroke={COLORS.low} />
            <Legend />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Top flagged institutions */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Flagged Institutions
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={topInstitutions} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis type="number" tick={{ fill: textColor, fontSize: 10 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: textColor, fontSize: 10 }} width={120} />
            <Tooltip />
            <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Top flagged categories */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Top Flagged Categories
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={topCategories} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis type="number" tick={{ fill: textColor, fontSize: 10 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: textColor, fontSize: 10 }} width={120} />
            <Tooltip />
            <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Risk dimension trends */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Risk Dimension Trends (Avg Score)
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={dimensionTrends}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="date" tick={{ fill: textColor, fontSize: 10 }} />
            <YAxis domain={[0, 3]} tick={{ fill: textColor, fontSize: 10 }} />
            <Tooltip />
            <Line type="monotone" dataKey="pathogen_enhancement" stroke={COLORS.critical} dot={false} />
            <Line type="monotone" dataKey="information_hazard" stroke={COLORS.high} dot={false} />
            <Line type="monotone" dataKey="synthesis_barrier_lowering" stroke={COLORS.medium} dot={false} />
            <Line type="monotone" dataKey="novel_technique" stroke="#3b82f6" dot={false} />
            <Line type="monotone" dataKey="select_agent_relevance" stroke="#8b5cf6" dot={false} />
            <Line type="monotone" dataKey="defensive_framing" stroke="#64748b" dot={false} />
            <Legend />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Create stats API route**

```typescript
// dashboard/app/api/stats/route.ts
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { PipelineStage, RiskTier } from "@prisma/client";

export async function GET() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const thirtyDaysAgo = new Date(today);
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  // KPI: papers today
  const papersToday = await prisma.paper.count({
    where: {
      createdAt: { gte: today },
      pipelineStage: { not: PipelineStage.ingested },
    },
  });

  // KPI: critical/high today
  const criticalHighToday = await prisma.paper.count({
    where: {
      createdAt: { gte: today },
      riskTier: { in: [RiskTier.critical, RiskTier.high] },
    },
  });

  // KPI: 7-day average
  const papersLastWeek = await prisma.paper.count({
    where: {
      createdAt: { gte: sevenDaysAgo },
      pipelineStage: { not: PipelineStage.ingested },
    },
  });
  const dailyAvg = Math.round(papersLastWeek / 7);

  // KPI: last pipeline run
  const lastRun = await prisma.pipelineRun.findFirst({
    orderBy: { startedAt: "desc" },
  });

  // Top institutions (last 30 days, high/critical only)
  const institutionRows = await prisma.paper.groupBy({
    by: ["correspondingInstitution"],
    where: {
      createdAt: { gte: thirtyDaysAgo },
      riskTier: { in: [RiskTier.critical, RiskTier.high] },
      correspondingInstitution: { not: null },
    },
    _count: { id: true },
    orderBy: { _count: { id: "desc" } },
    take: 10,
  });

  const topInstitutions = institutionRows.map((r) => ({
    name: r.correspondingInstitution ?? "Unknown",
    count: r._count.id,
  }));

  // Top categories (last 30 days)
  const categoryRows = await prisma.paper.groupBy({
    by: ["subjectCategory"],
    where: {
      createdAt: { gte: thirtyDaysAgo },
      pipelineStage: { not: PipelineStage.ingested },
      subjectCategory: { not: null },
    },
    _count: { id: true },
    orderBy: { _count: { id: "desc" } },
    take: 10,
  });

  const topCategories = categoryRows.map((r) => ({
    name: r.subjectCategory ?? "Unknown",
    count: r._count.id,
  }));

  return NextResponse.json({
    kpi: {
      papersToday,
      criticalHighToday,
      dailyAvg,
      trendPct: dailyAvg > 0 ? Math.round(((papersToday - dailyAvg) / dailyAvg) * 100) : 0,
      lastRunStatus: lastRun ? (lastRun.errors ? "error" : "success") : "unknown",
    },
    topInstitutions,
    topCategories,
    // papersOverTime and dimensionTrends require date-bucketed aggregation
    // which is simpler via raw SQL — see analytics page for direct queries
  });
}
```

- [ ] **Step 4: Create analytics page**

```tsx
// dashboard/app/analytics/page.tsx
import { prisma } from "@/lib/prisma";
import { KpiCard } from "@/components/kpi-card";
import { AnalyticsCharts } from "@/components/analytics-charts";
import { PipelineStage } from "@prisma/client";

type DimensionTrendRow = {
  date: string;
  pathogen_enhancement: number;
  synthesis_barrier_lowering: number;
  select_agent_relevance: number;
  novel_technique: number;
  information_hazard: number;
  defensive_framing: number;
};

async function getDimensionTrends(since: Date): Promise<DimensionTrendRow[]> {
  // Extract average dimension scores per week from stage2_result JSON
  return prisma.$queryRaw<DimensionTrendRow[]>`
    SELECT
      to_char(date_trunc('week', created_at), 'MM/DD') as date,
      ROUND(AVG((stage2_result->'dimensions'->'pathogen_enhancement'->>'score')::numeric), 1)::float as pathogen_enhancement,
      ROUND(AVG((stage2_result->'dimensions'->'synthesis_barrier_lowering'->>'score')::numeric), 1)::float as synthesis_barrier_lowering,
      ROUND(AVG((stage2_result->'dimensions'->'select_agent_relevance'->>'score')::numeric), 1)::float as select_agent_relevance,
      ROUND(AVG((stage2_result->'dimensions'->'novel_technique'->>'score')::numeric), 1)::float as novel_technique,
      ROUND(AVG((stage2_result->'dimensions'->'information_hazard'->>'score')::numeric), 1)::float as information_hazard,
      ROUND(AVG((stage2_result->'dimensions'->'defensive_framing'->>'score')::numeric), 1)::float as defensive_framing
    FROM papers
    WHERE created_at >= ${since}
      AND stage2_result IS NOT NULL
      AND stage2_result->'dimensions' IS NOT NULL
    GROUP BY date_trunc('week', created_at)
    ORDER BY date_trunc('week', created_at)
  `;
}

async function getStats() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const thirtyDaysAgo = new Date(today);
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const papersToday = await prisma.paper.count({
    where: { createdAt: { gte: today }, pipelineStage: { not: PipelineStage.ingested } },
  });

  const criticalHighToday = await prisma.paper.count({
    where: {
      createdAt: { gte: today },
      riskTier: { in: ["critical", "high"] },
    },
  });

  const papersLastWeek = await prisma.paper.count({
    where: { createdAt: { gte: sevenDaysAgo }, pipelineStage: { not: PipelineStage.ingested } },
  });
  const dailyAvg = Math.round(papersLastWeek / 7);

  const lastRun = await prisma.pipelineRun.findFirst({ orderBy: { startedAt: "desc" } });

  // Papers over time (daily, last 30 days) — raw SQL for date bucketing
  const papersOverTime = await prisma.$queryRaw<
    { date: string; critical: number; high: number; medium: number; low: number }[]
  >`
    SELECT
      to_char(created_at::date, 'MM/DD') as date,
      COUNT(*) FILTER (WHERE risk_tier = 'critical')::int as critical,
      COUNT(*) FILTER (WHERE risk_tier = 'high')::int as high,
      COUNT(*) FILTER (WHERE risk_tier = 'medium')::int as medium,
      COUNT(*) FILTER (WHERE risk_tier = 'low')::int as low
    FROM papers
    WHERE created_at >= ${thirtyDaysAgo}
      AND pipeline_stage != 'ingested'
    GROUP BY created_at::date
    ORDER BY created_at::date
  `;

  // Top institutions
  const topInstitutions = await prisma.$queryRaw<{ name: string; count: number }[]>`
    SELECT corresponding_institution as name, COUNT(*)::int as count
    FROM papers
    WHERE created_at >= ${thirtyDaysAgo}
      AND risk_tier IN ('critical', 'high')
      AND corresponding_institution IS NOT NULL
    GROUP BY corresponding_institution
    ORDER BY count DESC
    LIMIT 10
  `;

  // Top categories
  const topCategories = await prisma.$queryRaw<{ name: string; count: number }[]>`
    SELECT subject_category as name, COUNT(*)::int as count
    FROM papers
    WHERE created_at >= ${thirtyDaysAgo}
      AND pipeline_stage != 'ingested'
      AND subject_category IS NOT NULL
    GROUP BY subject_category
    ORDER BY count DESC
    LIMIT 10
  `;

  return {
    papersToday,
    criticalHighToday,
    dailyAvg,
    trendPct: dailyAvg > 0 ? Math.round(((papersToday - dailyAvg) / dailyAvg) * 100) : 0,
    lastRunOk: lastRun ? !(lastRun.errors as unknown[])?.length : null,
    papersOverTime,
    topInstitutions,
    topCategories,
    dimensionTrends: await getDimensionTrends(thirtyDaysAgo)
  };
}

export default async function AnalyticsPage() {
  const stats = await getStats();

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Analytics
      </h1>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Papers Today"
          value={stats.papersToday}
          trend={stats.trendPct}
          subtitle={`7-day avg: ${stats.dailyAvg}`}
        />
        <KpiCard
          title="Critical/High Today"
          value={stats.criticalHighToday}
        />
        <KpiCard
          title="Daily Average (7d)"
          value={stats.dailyAvg}
        />
        <KpiCard
          title="Pipeline Health"
          value={stats.lastRunOk === null ? "No runs" : stats.lastRunOk ? "Healthy" : "Error"}
        />
      </div>

      <AnalyticsCharts
        papersOverTime={stats.papersOverTime}
        topInstitutions={stats.topInstitutions}
        topCategories={stats.topCategories}
        dimensionTrends={stats.dimensionTrends}
      />
    </div>
  );
}
```

- [ ] **Step 5: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

- [ ] **Step 6: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/components/kpi-card.tsx dashboard/components/analytics-charts.tsx \
  dashboard/app/analytics/ dashboard/app/api/stats/
git commit -m "feat: add analytics page with KPI cards and Recharts visualizations"
```

---

### Task 13: Pipeline Page

**Files:**
- Create: `dashboard/components/run-history-table.tsx`
- Create: `dashboard/components/pipeline-controls.tsx`
- Create: `dashboard/app/pipeline/page.tsx`
- Create: `dashboard/app/api/pipeline/route.ts`
- Create: `dashboard/app/api/pipeline/pause/route.ts`
- Create: `dashboard/app/api/pipeline/resume/route.ts`
- Create: `dashboard/app/api/pipeline/schedule/route.ts`

- [ ] **Step 1: Create pipeline API proxy routes**

```typescript
// dashboard/app/api/pipeline/route.ts
import { NextResponse } from "next/server";
import { getPipelineStatus, triggerPipelineRun } from "@/lib/pipeline-api";

export async function GET() {
  try {
    const status = await getPipelineStatus();
    return NextResponse.json(status);
  } catch {
    return NextResponse.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}

export async function POST() {
  try {
    const result = await triggerPipelineRun();
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
```

```typescript
// dashboard/app/api/pipeline/pause/route.ts
import { NextResponse } from "next/server";
import { pausePipeline } from "@/lib/pipeline-api";

export async function POST() {
  try {
    const result = await pausePipeline();
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
```

```typescript
// dashboard/app/api/pipeline/resume/route.ts
import { NextResponse } from "next/server";
import { resumePipeline } from "@/lib/pipeline-api";

export async function POST() {
  try {
    const result = await resumePipeline();
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
```

```typescript
// dashboard/app/api/pipeline/schedule/route.ts
import { NextRequest, NextResponse } from "next/server";
import { updatePipelineSchedule } from "@/lib/pipeline-api";

export async function PUT(request: NextRequest) {
  try {
    const { hour, minute } = await request.json();
    const result = await updatePipelineSchedule(hour, minute ?? 0);
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: "Pipeline unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 2: Create run history table component**

```tsx
// dashboard/components/run-history-table.tsx
import type { PipelineRun } from "@prisma/client";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDuration, formatCost } from "@/lib/utils";

type Props = {
  runs: PipelineRun[];
};

export function RunHistoryTable({ runs }: Props) {
  if (runs.length === 0) {
    return <p className="text-sm text-slate-500">No pipeline runs recorded.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Ingested</TableHead>
          <TableHead>Passed</TableHead>
          <TableHead>Adjudicated</TableHead>
          <TableHead>Errors</TableHead>
          <TableHead>Cost</TableHead>
          <TableHead>Trigger</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => {
          const errors = (run.errors as string[] | null) ?? [];
          return (
            <TableRow key={run.id}>
              <TableCell className="text-xs">
                {new Date(run.startedAt).toLocaleString()}
              </TableCell>
              <TableCell className="text-xs">
                {formatDuration(run.startedAt, run.finishedAt)}
              </TableCell>
              <TableCell className="text-xs">{run.papersIngested}</TableCell>
              <TableCell className="text-xs">{run.papersCoarsePassed}</TableCell>
              <TableCell className="text-xs">{run.papersAdjudicated}</TableCell>
              <TableCell className="text-xs">
                {errors.length > 0 ? (
                  <Badge variant="destructive" className="text-[10px]">{errors.length}</Badge>
                ) : (
                  <span className="text-green-600 dark:text-green-400">0</span>
                )}
              </TableCell>
              <TableCell className="text-xs">{formatCost(run.totalCostUsd)}</TableCell>
              <TableCell className="text-xs">
                <Badge variant="outline" className="text-[10px]">{run.trigger}</Badge>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 3: Create pipeline controls component**

```tsx
// dashboard/components/pipeline-controls.tsx
"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Play, Pause, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

type PipelineStatus = {
  running: boolean;
  paused: boolean;
  next_run_time: string | null;
};

type Props = {
  initialStatus: PipelineStatus | null;
};

export function PipelineControls({ initialStatus }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [isPending, startTransition] = useTransition();
  const [hour, setHour] = useState(6);
  const [minute, setMinute] = useState(0);

  function runNow() {
    startTransition(async () => {
      await fetch("/api/pipeline", { method: "POST" });
      const res = await fetch("/api/pipeline");
      if (res.ok) setStatus(await res.json());
    });
  }

  function togglePause() {
    startTransition(async () => {
      const endpoint = status?.paused ? "/api/pipeline/resume" : "/api/pipeline/pause";
      await fetch(endpoint, { method: "POST" });
      const res = await fetch("/api/pipeline");
      if (res.ok) setStatus(await res.json());
    });
  }

  function updateSchedule() {
    startTransition(async () => {
      await fetch("/api/pipeline/schedule", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hour, minute }),
      });
      const res = await fetch("/api/pipeline");
      if (res.ok) setStatus(await res.json());
    });
  }

  const statusDot = status
    ? status.paused ? "bg-yellow-500" : status.running ? "bg-green-500" : "bg-slate-400"
    : "bg-slate-400";
  const statusLabel = status
    ? status.paused ? "Paused" : status.running ? "Running" : "Idle"
    : "Unreachable";

  return (
    <div className="space-y-4">
      {/* Status */}
      <div className="flex items-center gap-2">
        <div className={cn("h-3 w-3 rounded-full", statusDot)} />
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {statusLabel}
        </span>
      </div>

      {/* Next run */}
      {status?.next_run_time && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Next scheduled: {new Date(status.next_run_time).toLocaleString()}
        </p>
      )}

      {/* Buttons */}
      <div className="flex gap-2">
        <Button size="sm" onClick={runNow} disabled={isPending}>
          <Play className="mr-1 h-3 w-3" />
          Run Now
        </Button>
        <Button size="sm" variant="outline" onClick={togglePause} disabled={isPending}>
          {status?.paused ? (
            <><RefreshCw className="mr-1 h-3 w-3" /> Resume</>
          ) : (
            <><Pause className="mr-1 h-3 w-3" /> Pause</>
          )}
        </Button>
      </div>

      {/* Schedule */}
      <div>
        <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          Daily Run Time (UTC)
        </p>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={0} max={23}
            value={hour}
            onChange={(e) => setHour(parseInt(e.target.value, 10))}
            className="w-16"
            aria-label="Hour"
          />
          <span className="text-slate-500">:</span>
          <Input
            type="number"
            min={0} max={59}
            value={minute}
            onChange={(e) => setMinute(parseInt(e.target.value, 10))}
            className="w-16"
            aria-label="Minute"
          />
          <Button size="sm" variant="outline" onClick={updateSchedule} disabled={isPending}>
            Update
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create pipeline page**

```tsx
// dashboard/app/pipeline/page.tsx
import { prisma } from "@/lib/prisma";
import { getPipelineStatus } from "@/lib/pipeline-api";
import { RunHistoryTable } from "@/components/run-history-table";
import { PipelineControls } from "@/components/pipeline-controls";
import { Card } from "@/components/ui/card";

export default async function PipelinePage() {
  const runs = await prisma.pipelineRun.findMany({
    orderBy: { startedAt: "desc" },
    take: 50,
  });

  let pipelineStatus = null;
  try {
    pipelineStatus = await getPipelineStatus();
  } catch {
    // Sidecar may not be running
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Pipeline
      </h1>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Run history — 2/3 width */}
        <div className="lg:col-span-2">
          <Card className="p-4">
            <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Run History
            </h2>
            <RunHistoryTable runs={runs} />
          </Card>
        </div>

        {/* Controls — 1/3 width */}
        <div>
          <Card className="p-4">
            <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
              Controls
            </h2>
            <PipelineControls initialStatus={pipelineStatus} />
          </Card>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

- [ ] **Step 6: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/app/pipeline/ dashboard/app/api/pipeline/ \
  dashboard/components/run-history-table.tsx dashboard/components/pipeline-controls.tsx
git commit -m "feat: add pipeline page with run history table and scheduler controls"
```

---

### Task 14: Settings Page

**Files:**
- Create: `dashboard/components/settings-form.tsx`
- Create: `dashboard/app/settings/page.tsx`

- [ ] **Step 1: Create settings form component**

```tsx
// dashboard/components/settings-form.tsx
"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Card } from "@/components/ui/card";
import { Save } from "lucide-react";

type SettingsData = {
  stage1_model: string;
  stage2_model: string;
  stage3_model: string;
  coarse_filter_threshold: number;
  adjudication_min_tier: string;
  use_batch_api: boolean;
  pubmed_query_mode: string;
  biorxiv_request_delay: number;
  pubmed_request_delay: number;
  europepmc_request_delay: number;
  unpaywall_request_delay: number;
  openalex_request_delay: number;
  semantic_scholar_request_delay: number;
  orcid_request_delay: number;
  fulltext_request_delay: number;
  alert_email_recipients: string;
  alert_slack_webhook: string;
  alert_digest_frequency: string;
  alert_tier_threshold: string;
};

const DEFAULTS: SettingsData = {
  stage1_model: "claude-haiku-4-5-20251001",
  stage2_model: "claude-sonnet-4-6",
  stage3_model: "claude-opus-4-6",
  coarse_filter_threshold: 0.8,
  adjudication_min_tier: "high",
  use_batch_api: false,
  pubmed_query_mode: "all",
  biorxiv_request_delay: 1.0,
  pubmed_request_delay: 0.1,
  europepmc_request_delay: 1.0,
  unpaywall_request_delay: 0.1,
  openalex_request_delay: 0.1,
  semantic_scholar_request_delay: 1.0,
  orcid_request_delay: 1.0,
  fulltext_request_delay: 1.0,
  alert_email_recipients: "",
  alert_slack_webhook: "",
  alert_digest_frequency: "daily",
  alert_tier_threshold: "high",
};

type Props = {
  initialSettings: Partial<SettingsData>;
};

export function SettingsForm({ initialSettings }: Props) {
  const [settings, setSettings] = useState<SettingsData>({ ...DEFAULTS, ...initialSettings });
  const [isPending, startTransition] = useTransition();
  const [saved, setSaved] = useState(false);

  function update<K extends keyof SettingsData>(key: K, value: SettingsData[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function save() {
    startTransition(async () => {
      await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    });
  }

  return (
    <div className="space-y-6">
      {/* Model Selection */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">Model Selection</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {(["stage1_model", "stage2_model", "stage3_model"] as const).map((key) => (
            <div key={key}>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                {key === "stage1_model" ? "Stage 1 (Coarse)" : key === "stage2_model" ? "Stage 2 (Methods)" : "Stage 3 (Adjudication)"}
              </label>
              <Input
                value={settings[key]}
                onChange={(e) => update(key, e.target.value)}
              />
            </div>
          ))}
        </div>
      </Card>

      {/* Pipeline Tuning */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">Pipeline Tuning</h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Coarse Filter Threshold: {settings.coarse_filter_threshold.toFixed(2)}
            </label>
            <Slider
              value={[settings.coarse_filter_threshold]}
              onValueChange={([v]) => update("coarse_filter_threshold", v)}
              min={0} max={1} step={0.05}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Adjudication Min Tier</label>
            <Select value={settings.adjudication_min_tier} onValueChange={(v) => update("adjudication_min_tier", v)}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              checked={settings.use_batch_api}
              onCheckedChange={(v) => update("use_batch_api", v)}
              id="batch-api"
            />
            <label htmlFor="batch-api" className="text-xs text-slate-700 dark:text-slate-300">Use Batch API</label>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">PubMed Query Mode</label>
            <Select value={settings.pubmed_query_mode} onValueChange={(v) => update("pubmed_query_mode", v)}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="mesh_filtered">MeSH Filtered</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {/* Rate Limits */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">Rate Limits (seconds)</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {([
            ["biorxiv_request_delay", "bioRxiv"],
            ["pubmed_request_delay", "PubMed"],
            ["europepmc_request_delay", "Europe PMC"],
            ["unpaywall_request_delay", "Unpaywall"],
            ["openalex_request_delay", "OpenAlex"],
            ["semantic_scholar_request_delay", "Semantic Scholar"],
            ["orcid_request_delay", "ORCID"],
            ["fulltext_request_delay", "Full-text"],
          ] as const).map(([key, label]) => (
            <div key={key}>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">{label}</label>
              <Input
                type="number"
                step={0.1}
                min={0}
                value={settings[key]}
                onChange={(e) => update(key, parseFloat(e.target.value))}
              />
            </div>
          ))}
        </div>
      </Card>

      {/* Alerts */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">Alerts</h2>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Email Recipients (comma-separated)</label>
            <Input value={settings.alert_email_recipients} onChange={(e) => update("alert_email_recipients", e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Slack Webhook URL</label>
            <Input type="password" value={settings.alert_slack_webhook} onChange={(e) => update("alert_slack_webhook", e.target.value)} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Digest Frequency</label>
              <Select value={settings.alert_digest_frequency} onValueChange={(v) => update("alert_digest_frequency", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Alert Tier Threshold</label>
              <Select value={settings.alert_tier_threshold} onValueChange={(v) => update("alert_tier_threshold", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="medium">Medium+</SelectItem>
                  <SelectItem value="high">High+</SelectItem>
                  <SelectItem value="critical">Critical only</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </Card>

      {/* Save */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={isPending}>
          <Save className="mr-2 h-4 w-4" />
          {isPending ? "Saving..." : "Save Settings"}
        </Button>
        {saved && (
          <span className="text-sm text-green-600 dark:text-green-400" aria-live="polite">
            Settings saved
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create settings API route**

```typescript
// dashboard/app/api/settings/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const row = await prisma.pipelineSettings.findFirst({ where: { id: 1 } });
  return NextResponse.json(row?.settings ?? {});
}

export async function PUT(request: NextRequest) {
  const settings = await request.json();
  const row = await prisma.pipelineSettings.upsert({
    where: { id: 1 },
    create: { id: 1, settings },
    update: { settings },
  });
  return NextResponse.json(row.settings);
}
```

- [ ] **Step 3: Create settings page**

```tsx
// dashboard/app/settings/page.tsx
import { requireAdmin } from "@/lib/auth-guard";
import { prisma } from "@/lib/prisma";
import { SettingsForm } from "@/components/settings-form";

export default async function SettingsPage() {
  await requireAdmin();

  const row = await prisma.pipelineSettings.findFirst({ where: { id: 1 } });
  const settings = (row?.settings as Record<string, unknown>) ?? {};

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Settings
      </h1>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Configure pipeline parameters. Changes take effect on the next pipeline run.
      </p>
      <SettingsForm initialSettings={settings} />
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npm run build
```

- [ ] **Step 5: Commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add dashboard/app/settings/ dashboard/app/api/settings/ dashboard/components/settings-form.tsx
git commit -m "feat: add settings page with full pipeline configuration form"
```

---

### Task 15: Verify Full Build + Accessibility Spot Check

**Files:** None new — verification only.

- [ ] **Step 1: Clean build**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
rm -rf .next
npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Lint check**

```bash
cd /Users/pecaf/projects/DURC-preprints/dashboard
npx next lint
```

Fix any linting issues found.

- [ ] **Step 3: Accessibility spot check**

Manually verify these patterns exist in the codebase:
- `aria-label` on all interactive elements without visible text (icon buttons, select triggers)
- `role="progressbar"` on dimension bars with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`
- `aria-live="polite"` on dynamic status messages (save confirmations, filter counts)
- `aria-current="page"` on active sidebar link
- Semantic HTML: `<nav>`, `<main>`, `<aside>`, `<section>`, `<h1>`-`<h3>` hierarchy
- No `outline-none` without `ring-*` replacement
- All images have `alt` text (or `aria-hidden` if decorative)

- [ ] **Step 4: Run Python test suite**

Ensure the FastAPI sidecar and model changes haven't broken anything:

```bash
cd /Users/pecaf/projects/DURC-preprints
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Final commit**

```bash
cd /Users/pecaf/projects/DURC-preprints
git add -A
git commit -m "chore: fix lint and accessibility issues from build verification"
```

Only commit if there were actual fixes. If everything was clean, skip this step.

---

## Appendix: NuQs Provider Setup

The `NuqsAdapter` is already included in Task 7's root layout. No additional setup is needed.
