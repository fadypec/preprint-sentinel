-- Post-push script to add search_vector column for full-text search
-- This should be run after `prisma db push` to ensure the dashboard search works

-- Add full-text search vector (generated column)
ALTER TABLE papers ADD COLUMN IF NOT EXISTS search_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
) STORED;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_papers_search ON papers USING GIN(search_vector);