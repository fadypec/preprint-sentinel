# DURC Preprint Triage — Deployment Plan

Step-by-step guide for deploying the system to Railway + Supabase. Written for an agentic Claude Code instance with browser access.

**Repository:** `https://github.com/fadypec/preprint-sentinel`
**Current state:** Everything runs locally. Database is local PostgreSQL. Dashboard is `npm run dev` on localhost:3000. Pipeline is `python -m pipeline` run manually.
**Target state:** Dashboard at a public URL behind GitHub OAuth. Pipeline runs daily via cron. Database on Supabase.

---

## Architecture

```
[Supabase] PostgreSQL database (free tier)
     ↕
[Railway Service 1] Next.js dashboard (web, always-on)
     ↕
[Railway Service 2] Python pipeline (cron, runs daily at 06:00 UTC)
```

Both Railway services connect to the same Supabase database. The dashboard reads/writes paper data and serves the UI. The pipeline ingests papers, runs LLM triage, and writes results.

---

## Step 1: Create Supabase Database

1. Go to https://supabase.com/dashboard
2. Click **"New Project"**
3. Fill in:
   - **Organization:** Use existing org (same as CBM Lens)
   - **Name:** `durc-triage`
   - **Database Password:** Generate a strong password (save it — you'll need it)
   - **Region:** `eu-west-2` (London) — closest to the user
   - **Plan:** Free tier is sufficient
4. Click **"Create new project"** — wait ~2 minutes for provisioning
5. Once ready, go to **Settings → Database** (left sidebar)
6. Under **"Connection string"** section, select the **"URI"** tab
7. Copy the connection string. It looks like:
   ```
   postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-eu-west-2.pooler.supabase.com:6543/postgres
   ```
8. Replace `[YOUR-PASSWORD]` with the actual password you set
9. **Save two versions of this string:**
   - **For the dashboard (Node.js/Prisma):** Use the string as-is
   - **For the pipeline (Python/SQLAlchemy):** Replace `postgresql://` with `postgresql+asyncpg://` and change port `6543` to `5432` (direct connection, not pooler). The pipeline uses asyncpg which needs the direct connection.

   Example:
   - Dashboard: `postgresql://postgres.xxxx:PASS@aws-0-eu-west-2.pooler.supabase.com:6543/postgres`
   - Pipeline: `postgresql+asyncpg://postgres.xxxx:PASS@aws-0-eu-west-2.pooler.supabase.com:5432/postgres`

### Run database migrations

From the local machine (with the repo cloned), run:

```bash
cd /Users/pecaf/projects/DURC-preprints
DATABASE_URL="postgresql+asyncpg://postgres.xxxx:PASS@aws-0-eu-west-2.pooler.supabase.com:5432/postgres" .venv/bin/python -m alembic upgrade head
```

This creates all tables (papers, paper_groups, assessment_logs, pipeline_runs, users, pipeline_settings) with indexes and constraints.

**Verify:** Go to Supabase dashboard → Table Editor. You should see 6 tables.

---

## Step 2: Set Up GitHub OAuth App

This gates dashboard access. Only users you authorise can log in.

1. Go to https://github.com/settings/developers
2. Click **"OAuth Apps"** → **"New OAuth App"**
3. Fill in:
   - **Application name:** `DURC Preprint Triage`
   - **Homepage URL:** `https://durc-triage.up.railway.app` (placeholder — update after Railway gives you the real URL)
   - **Authorization callback URL:** `https://durc-triage.up.railway.app/api/auth/callback/github` (same — update later)
4. Click **"Register application"**
5. On the app page:
   - Copy the **Client ID** (visible immediately)
   - Click **"Generate a new client secret"** → copy the **Client Secret** (shown once)
6. **Save both values** — you'll enter them as Railway environment variables

**Important:** After Railway gives you the actual URL (Step 3), come back and update the Homepage URL and Callback URL to match.

---

## Step 3: Deploy the Dashboard to Railway

### Create the project

1. Go to https://railway.app/dashboard
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select the `fadypec/preprint-sentinel` repository
4. Railway will detect it's a monorepo. You need to configure the service to use the `dashboard/` subdirectory.

### Configure the dashboard service

1. Click on the service that was created
2. Go to **Settings**:
   - **Root Directory:** Set to `dashboard`
   - **Build Command:** `npm ci --legacy-peer-deps && npx prisma generate && npm run build`
   - **Start Command:** `npm start`
   - **Watch Paths:** `dashboard/**` (so it only redeploys when dashboard code changes)
3. Go to **Variables** and add these environment variables:

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | The Supabase connection string (Node.js version, port 6543) |
   | `AUTH_SECRET` | Generate with `openssl rand -base64 32` — a random 32-byte secret for NextAuth session encryption |
   | `AUTH_GITHUB_ID` | The GitHub OAuth Client ID from Step 2 |
   | `AUTH_GITHUB_SECRET` | The GitHub OAuth Client Secret from Step 2 |
   | `NEXTAUTH_URL` | The Railway public URL (set after first deploy — see below) |
   | `NODE_ENV` | `production` |
   | `OPENALEX_EMAIL` | `paul-enguerrand@longtermresilience.org` (for polite pool API access) |

4. Go to **Networking** → **"Generate Domain"** to get a public URL (e.g., `durc-triage-production.up.railway.app`)
5. Copy this URL and:
   - Set `NEXTAUTH_URL` to `https://durc-triage-production.up.railway.app`
   - Go back to GitHub OAuth App settings (Step 2) and update:
     - **Homepage URL** → `https://durc-triage-production.up.railway.app`
     - **Authorization callback URL** → `https://durc-triage-production.up.railway.app/api/auth/callback/github`
6. Click **"Deploy"** (or it may auto-deploy from the GitHub push)

### Verify

- Visit the Railway URL — you should see the GitHub login page
- Log in with your GitHub account
- After login, you'll see the dashboard (likely empty since the pipeline hasn't run yet)

### First user setup

After your first login, you need to promote yourself to admin. In Supabase:

1. Go to Table Editor → `users` table
2. Find your row (created on first OAuth login)
3. Change `role` from `analyst` to `admin`

This lets you trigger pipeline runs and modify settings from the dashboard.

---

## Step 4: Deploy the Pipeline to Railway

### Add a second service

1. In the same Railway project, click **"New"** → **"Service"** → **"Deploy from GitHub repo"**
2. Select the same `fadypec/preprint-sentinel` repository again
3. This creates a second service in the project

### Configure the pipeline service

1. Click on the new service → **Settings**:
   - **Root Directory:** Leave empty (repo root — the pipeline is at `/pipeline/`)
   - **Build Command:** `pip install -e ".[dev]"`
   - **Start Command:** Leave empty (this will be a cron job, not an always-on service)
   - **Watch Paths:** `pipeline/**,scripts/**,pyproject.toml`

2. Go to **Variables** and add:

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | The Supabase connection string (**Python version** — `postgresql+asyncpg://`, port 5432) |
   | `ANTHROPIC_API_KEY` | Your Anthropic API key (the new one you generated) |
   | `NCBI_API_KEY` | Your NCBI E-utilities API key (optional but recommended) |
   | `UNPAYWALL_EMAIL` | `paul-enguerrand@longtermresilience.org` |
   | `OPENALEX_EMAIL` | `paul-enguerrand@longtermresilience.org` |
   | `STAGE1_MODEL` | `claude-haiku-4-5-20251001` |
   | `STAGE2_MODEL` | `claude-sonnet-4-6` |
   | `STAGE3_MODEL` | `claude-opus-4-6` |

3. **Set up the cron schedule:**
   - Railway supports cron jobs. In the service settings, find **"Cron Schedule"**
   - Set to: `0 6 * * *` (runs daily at 06:00 UTC)
   - The command to run: `python -m pipeline`

   **Alternative if Railway cron is not available for your plan:** Set the start command to `python -m pipeline --scheduled` which uses APScheduler to run daily at the configured hour. In this case, the service stays running (always-on) but only does work once per day.

### Verify

- Check Railway logs for the pipeline service after it runs
- Papers should start appearing in the dashboard after the first run
- The pipeline page in the dashboard will show run history

---

## Step 5: Custom Domain (Optional)

If you want the dashboard at `durc.fady.phd` instead of the Railway URL:

1. In Railway, go to the **dashboard service** → **Settings** → **Networking**
2. Click **"Custom Domain"** → enter `durc.fady.phd` (or whatever subdomain you want)
3. Railway will show you a **CNAME record** to add
4. Go to your DNS provider (wherever `fady.phd` is managed — likely the same place as `cbm.fady.phd`)
5. Add a **CNAME record:**
   - **Name:** `durc` (or whatever subdomain)
   - **Value:** The Railway-provided target (e.g., `durc-triage-production.up.railway.app`)
   - **TTL:** 300 (or auto)
6. Wait for DNS propagation (usually 5-30 minutes)
7. **Update these values to match the custom domain:**
   - Railway env var `NEXTAUTH_URL` → `https://durc.fady.phd`
   - GitHub OAuth App → Homepage URL → `https://durc.fady.phd`
   - GitHub OAuth App → Callback URL → `https://durc.fady.phd/api/auth/callback/github`

Railway automatically provisions an SSL certificate once the CNAME is verified.

---

## Post-Deployment Checklist

After everything is deployed, verify:

- [ ] Dashboard loads at the public URL
- [ ] GitHub OAuth login works (redirects to GitHub, then back)
- [ ] You can see the daily feed (may be empty until first pipeline run)
- [ ] Pipeline page shows controls (trigger, schedule)
- [ ] Triggering a manual pipeline run from the dashboard works
- [ ] Pipeline completes and papers appear in the feed
- [ ] Analytics page loads with data
- [ ] Health endpoint returns "ok": `https://your-url/api/health`
- [ ] Settings page is accessible (admin only)

---

## Data Migration (Optional)

If you want to migrate your existing local database to Supabase:

1. Create a backup of your local database:
   ```bash
   pg_dump -Fc durc_triage > local_backup.dump
   ```

2. Restore to Supabase (use the direct connection, not the pooler):
   ```bash
   pg_restore -h aws-0-eu-west-2.pooler.supabase.com -p 5432 -U postgres.xxxx -d postgres --clean --if-exists --no-owner local_backup.dump
   ```

   You'll be prompted for the Supabase database password.

This preserves all your existing papers, assessments, and pipeline history.

---

## Environment Variables Summary

### Dashboard (Railway Service 1)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Supabase connection (pooler, port 6543) | `postgresql://postgres.xxx:PASS@...supabase.com:6543/postgres` |
| `AUTH_SECRET` | NextAuth session secret (random 32 bytes) | `openssl rand -base64 32` |
| `AUTH_GITHUB_ID` | GitHub OAuth Client ID | `Iv1.abc123...` |
| `AUTH_GITHUB_SECRET` | GitHub OAuth Client Secret | `ghs_abc123...` |
| `NEXTAUTH_URL` | Public dashboard URL | `https://durc.fady.phd` |
| `NODE_ENV` | Must be `production` | `production` |
| `OPENALEX_EMAIL` | For polite pool API access | `your@email.com` |

### Pipeline (Railway Service 2)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Supabase connection (direct, port 5432, asyncpg) | `postgresql+asyncpg://postgres.xxx:PASS@...supabase.com:5432/postgres` |
| `ANTHROPIC_API_KEY` | For LLM triage | `sk-ant-...` |
| `NCBI_API_KEY` | PubMed rate limit (optional) | From NCBI account |
| `UNPAYWALL_EMAIL` | For OA full-text lookups | `your@email.com` |
| `OPENALEX_EMAIL` | For enrichment polite pool | `your@email.com` |
| `STAGE1_MODEL` | Coarse filter model | `claude-haiku-4-5-20251001` |
| `STAGE2_MODEL` | Methods analysis model | `claude-sonnet-4-6` |
| `STAGE3_MODEL` | Adjudication model | `claude-opus-4-6` |

---

## Troubleshooting

### Dashboard won't start
- Check Railway build logs for errors
- Most common: missing environment variable (DATABASE_URL, AUTH_SECRET)
- Verify `npm ci --legacy-peer-deps` in build command (peer dep conflict with next-auth beta)

### OAuth callback fails
- Verify the callback URL in GitHub OAuth settings matches EXACTLY: `https://your-url/api/auth/callback/github`
- Verify `NEXTAUTH_URL` matches the public URL (no trailing slash)
- Verify `AUTH_SECRET` is set

### Pipeline fails to connect to database
- Verify the Python connection string uses `postgresql+asyncpg://` (not plain `postgresql://`)
- Verify port is `5432` (direct connection), not `6543` (pooler)
- Supabase may require SSL: try appending `?sslmode=require` to the connection string

### Pipeline runs but no papers appear
- Check Railway logs for the pipeline service
- Common: Anthropic API key invalid → 401 errors in methods analysis stage
- Common: rate limiting from external APIs → check for 429 errors in logs

### "Authentication required" error on dashboard
- This is correct behaviour in production without OAuth configured
- Verify `AUTH_GITHUB_ID` and `AUTH_GITHUB_SECRET` are set
- Verify you've logged in via GitHub and promoted yourself to admin in the users table
