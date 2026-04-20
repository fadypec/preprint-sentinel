#!/usr/bin/env python3
"""
Add search_vector column to production Supabase database.
This is needed for full-text search to work properly in the dashboard.
"""

import os
import sys
import psycopg2
from urllib.parse import urlparse

def setup_search_column():
    # Get production DATABASE_URL (should be the Supabase connection string)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("   Set it to your Supabase connection string and try again")
        sys.exit(1)

    # Parse URL to check if it's Supabase
    parsed = urlparse(database_url)
    if "supabase" not in parsed.hostname:
        print("❌ DATABASE_URL doesn't appear to be a Supabase connection")
        print(f"   Host: {parsed.hostname}")
        print("   This script is intended for Supabase production setup only")
        sys.exit(1)

    try:
        print("🔗 Connecting to Supabase database...")
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        # Check if search_vector column already exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'papers' AND column_name = 'search_vector'
        """)

        if cur.fetchone():
            print("✅ search_vector column already exists")
            cur.close()
            conn.close()
            return

        print("📄 Adding search_vector generated column...")
        cur.execute("""
            ALTER TABLE papers ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
            ) STORED
        """)

        print("🔍 Creating GIN index for fast search...")
        cur.execute("""
            CREATE INDEX idx_papers_search ON papers USING GIN(search_vector)
        """)

        # Commit changes
        conn.commit()
        cur.close()
        conn.close()

        print("✅ Search setup complete!")
        print("   - Added search_vector column with title/abstract content")
        print("   - Created GIN index for fast full-text search")
        print("   - Dashboard search should now work at full speed")

    except Exception as e:
        print(f"❌ Error setting up search: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_search_column()