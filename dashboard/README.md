# Preprint Sentinel -- Dashboard

The analyst-facing web dashboard for Preprint Sentinel. Displays papers flagged by the DURC screening pipeline, with risk scores, assessment details, filtering, search, analytics, and analyst workflow controls.

**Live instance:** [https://durc.fady.phd](https://durc.fady.phd)

## Running Locally

### Prerequisites

- Node.js 18+
- A PostgreSQL database with the Preprint Sentinel schema (see the pipeline's `seed_db.py`)

### Setup

```bash
cd dashboard
npm install
```

Create a `.env.local` file with the following variables:

```bash
# PostgreSQL connection string (same database the pipeline writes to)
DATABASE_URL=postgresql://user:pass@host:5432/durc_triage

# NextAuth (authentication)
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<random-secret>

# OAuth provider (configure at least one)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

### Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build for Production

```bash
npm run build
npm start
```

## Key Features

- **Daily feed** of flagged papers sorted by risk tier and score
- **6-dimension risk scoring** with expandable justifications per paper
- **Full-text search** across titles, abstracts, and assessment summaries
- **Filters** by risk tier, date range, source server, subject category, author, and individual risk dimensions
- **Paper detail view** with complete assessment chain (coarse filter, methods analysis, adjudication)
- **Analyst workflow** (Unreviewed, Under Review, Confirmed Concern, False Positive, Archived)
- **Analytics dashboard** with trends, distributions, and pipeline health metrics
- **Pipeline controls** to trigger runs and view run history from the dashboard
- **Settings UI** for configuring pipeline parameters, alert thresholds, and notification endpoints

## Documentation

- [Analyst Onboarding Guide](../docs/ANALYST-GUIDE.md) -- how to use the dashboard as a biosecurity analyst
- [Scoring Rubric](../docs/SCORING-RUBRIC.md) -- detailed explanation of risk dimensions and scoring
- [Development Guide](../docs/DEVELOPMENT.md) -- full setup instructions for the entire system
- [Operations Guide](../docs/OPERATIONS.md) -- deployment and operational procedures
