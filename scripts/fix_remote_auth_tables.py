"""One-time script to fix corrupted auth tables on Supabase.

The pg_restore merged the local users table with Supabase's built-in
auth.users, creating duplicate columns. This drops and recreates
the users, accounts, and sessions tables with the correct schema.

Usage:
    python scripts/fix_remote_auth_tables.py
"""

import asyncio
import asyncpg


async def fix():
    conn = await asyncpg.connect(
        host="aws-1-eu-west-2.pooler.supabase.com",
        port=5432,
        user="postgres.xrxomftihbmyxfugumov",
        password="Wl2xtEQdZb01fpAS",
        database="postgres",
    )

    print("Dropping corrupted auth tables...")
    await conn.execute("DROP TABLE IF EXISTS sessions CASCADE")
    await conn.execute("DROP TABLE IF EXISTS accounts CASCADE")
    await conn.execute("DROP TABLE IF EXISTS users CASCADE")

    print("Creating users table...")
    await conn.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(320) UNIQUE NOT NULL,
            name VARCHAR(255),
            image TEXT,
            email_verified TIMESTAMPTZ,
            role user_role NOT NULL DEFAULT 'analyst',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    print("Creating accounts table...")
    await conn.execute("""
        CREATE TABLE accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_account_id TEXT NOT NULL,
            refresh_token TEXT,
            access_token TEXT,
            expires_at INTEGER,
            token_type TEXT,
            scope TEXT,
            id_token TEXT,
            UNIQUE(provider, provider_account_id)
        )
    """)

    print("Creating sessions table...")
    await conn.execute("""
        CREATE TABLE sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_token TEXT UNIQUE NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires TIMESTAMPTZ NOT NULL
        )
    """)

    print("Done! Auth tables recreated successfully.")
    await conn.close()


asyncio.run(fix())
