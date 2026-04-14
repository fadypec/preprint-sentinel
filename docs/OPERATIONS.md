# DURC Preprint Triage — Operations Runbook

Emergency and routine procedures for operating the pipeline.

---

## Emergency: Pipeline stuck or failing

**Symptoms:** Pipeline has been running for >2 hours, or multiple consecutive runs fail.

1. **Check the dashboard** — go to Pipeline page, check run history for errors
2. **Check logs** — `tail -100 logs/pipeline-*.log` (latest log file)
3. **Kill the stuck process** — click "Stop Pipeline" in the dashboard, or:
   ```bash
   # Find the process
   ps aux | grep "python -m pipeline"
   # Kill it
   kill <PID>
   ```
4. **Re-run** — click "Run Pipeline" in the dashboard. If the same error recurs:
   - Check API key validity: `curl -s https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01"` — should return a 400 (bad request), not 401 (auth error)
   - Check database connectivity: `psql $DATABASE_URL -c "SELECT 1"`
   - Check external API status: bioRxiv, PubMed, Europe PMC may be down

5. **Skip a failing source** — if one ingest source (e.g., Crossref) keeps returning errors, the pipeline will log the error and continue with other sources. No action needed.

---

## Emergency: Database connection lost

**Symptoms:** Dashboard shows errors, pipeline fails at start.

1. **Check PostgreSQL is running:**
   ```bash
   pg_isready -h <host> -p <port>
   ```
2. **Check connection string** — verify `DATABASE_URL` in `.env` is correct
3. **Check connection pool** — if using managed PostgreSQL (e.g., Supabase), check their dashboard for connection limit warnings
4. **Restart the database** if self-hosted:
   ```bash
   sudo systemctl restart postgresql
   ```

---

## Emergency: API key rotation

When an API key needs to be rotated (compromised, expired, etc.):

### Anthropic API key

1. Go to https://console.anthropic.com/settings/keys
2. Create a new key
3. Edit `.env` and replace `ANTHROPIC_API_KEY=sk-ant-...`
4. **Do NOT change the key while a pipeline run is active** — wait for it to finish or stop it first
5. Verify: run the pipeline — if the coarse filter stage succeeds, the key works

### NCBI API key

1. Go to https://www.ncbi.nlm.nih.gov/account/settings/
2. Create/regenerate your API key
3. Edit `.env` and replace `NCBI_API_KEY=...`
4. Verify: PubMed ingest should succeed on next run

### Slack webhook

1. Go to your Slack app settings → Incoming Webhooks
2. Create a new webhook URL
3. In the dashboard, go to Settings → paste the new webhook URL
4. Click "Test" to verify

---

## Routine: Database backup

Backups run via the `scripts/backup_db.py` script.

### Manual backup

```bash
python scripts/backup_db.py --dir backups/
```

This creates a timestamped `durc_triage_YYYYMMDD_HHMMSS.dump` file in the `backups/` directory. Old backups are automatically pruned after 14 days (configurable with `--keep N`).

### Scheduled backup (cron)

Add to crontab (`crontab -e`):

```
0 4 * * * cd /path/to/DURC-preprints && .venv/bin/python scripts/backup_db.py --dir backups/ >> logs/backup.log 2>&1
```

This runs daily at 04:00.

### Restore from backup

```bash
python scripts/restore_db.py backups/durc_triage_20260414_040000.dump
```

**Warning:** This overwrites the current database. Make a fresh backup first.

---

## Routine: Reprocessing papers with errors

If papers have processing errors (visible as warning triangles in the dashboard):

1. Go to Pipeline page
2. Click **"Fix Errors"** — this resets error papers to their previous stage
3. Click **"Run Pipeline"** with "Include Backlog" enabled
4. The pipeline will reprocess the reset papers

Alternatively, from the command line:

```bash
python -m scripts.resume_pipeline
```

This auto-detects papers stuck at intermediate stages and reprocesses them.

---

## Routine: Adding a new analyst user

Users are created automatically on first OAuth login. To grant admin access:

```sql
UPDATE users SET role = 'admin' WHERE email = 'analyst@example.com';
```

Or via Prisma:

```bash
cd dashboard && npx prisma studio
```

Navigate to the Users table and change the role.

---

## Monitoring

### Health check

```
GET /api/health
```

Returns JSON with `status` ("ok", "degraded", "error"), database connectivity, and last pipeline run timestamp. No authentication required — suitable for uptime monitors.

### Key metrics to watch

- **Hours since last pipeline run** — should be < 24 (daily runs)
- **Coverage gaps** — check Analytics page → Intelligence Coverage
- **Error count per run** — check Pipeline page → Run History
- **Cost per run** — check Pipeline page → Run History (total_cost_usd column)

### Alerts

Pipeline failures automatically send alerts to Slack (webhook) and email (SMTP) if configured in Settings. Configure both for redundancy.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Yes | For LLM triage (Haiku, Sonnet, Opus) |
| `NCBI_API_KEY` | No | PubMed rate limit increase (10 req/s vs 3/s) |
| `UNPAYWALL_EMAIL` | No | Required for Unpaywall full-text lookups |
| `OPENALEX_EMAIL` | No | For OpenAlex polite pool access |
| `SEMANTIC_SCHOLAR_API_KEY` | No | Higher S2 rate limits |
| `PIPELINE_PYTHON` | No | Path to Python binary (defaults to `.venv/bin/python`) |
| `AUTH_GITHUB_ID` / `AUTH_GITHUB_SECRET` | No | GitHub OAuth for dashboard auth |
| `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` | No | Google OAuth for dashboard auth |
