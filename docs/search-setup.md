# Search Setup

The dashboard uses PostgreSQL full-text search with a generated `tsvector` column for optimal performance.

## Initial Setup

After running `prisma db push`, execute the post-push script to add the search column:

```bash
cd dashboard
psql $DATABASE_URL -f prisma/post-push.sql
```

Or manually run these SQL commands:

```sql
-- Add full-text search vector (generated column)
ALTER TABLE papers ADD COLUMN IF NOT EXISTS search_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
) STORED;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_papers_search ON papers USING GIN(search_vector);
```

## Fallback Behavior

The search implementation includes automatic fallback:

1. **Primary**: Uses `search_vector @@ to_tsquery()` for fast full-text search
2. **Fallback**: Uses `ILIKE` pattern matching if `search_vector` column doesn't exist

This ensures the dashboard works even if the search column hasn't been added yet.

## Search Features

- **Weighted results**: Title matches score higher than abstract matches
- **Prefix matching**: Terms are expanded with `:*` for partial matches
- **AND logic**: Multiple terms are joined with `&` (all must match)
- **Automatic sanitization**: Special characters are stripped to prevent query errors

## Performance

- Full-text search: ~1ms for typical queries
- ILIKE fallback: ~50-100ms depending on dataset size
- Index size: ~2-5MB for 100K papers