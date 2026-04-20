#!/usr/bin/env python3
"""Backfill risk_tier and aggregate_score for adjudicated papers that have NULL values.

Three recovery paths:
1. stage3_result has adjusted_risk_tier → use that tier directly
2. stage2_result has dimensions with scores → compute aggregate_score, derive tier
3. LLM refused (no dimensions) → assign 'low' tier (safety guardrails trigger ≠ actual risk)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from pipeline.db import get_session
from pipeline.models import RiskTier

TIER_THRESHOLDS = {
    (0, 4): RiskTier.LOW,
    (5, 8): RiskTier.MEDIUM,
    (9, 13): RiskTier.HIGH,
    (14, 18): RiskTier.CRITICAL,
}

TIER_FROM_STR = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


def score_to_tier(score: int) -> str:
    for (lo, hi), tier in TIER_THRESHOLDS.items():
        if lo <= score <= hi:
            return tier.value
    return RiskTier.LOW.value


def compute_aggregate(dimensions: dict) -> int | None:
    total = 0
    for dim_value in dimensions.values():
        if isinstance(dim_value, dict) and "score" in dim_value:
            try:
                total += int(dim_value["score"])
            except (ValueError, TypeError):
                return None
    return total


async def backfill():
    async with get_session() as session:
        # Count before
        result = await session.execute(text("""
            SELECT COUNT(*) FROM papers
            WHERE is_duplicate_of IS NULL
              AND pipeline_stage = 'adjudicated'
              AND risk_tier IS NULL
        """))
        total = result.scalar()
        print(f"Papers with NULL risk_tier (adjudicated): {total}")

        if total == 0:
            print("Nothing to fix!")
            return

        # Path 1: stage3_result has adjusted_risk_tier
        result = await session.execute(text("""
            UPDATE papers
            SET risk_tier = (stage3_result->>'adjusted_risk_tier')::risk_tier
            WHERE is_duplicate_of IS NULL
              AND pipeline_stage = 'adjudicated'
              AND risk_tier IS NULL
              AND stage3_result->>'adjusted_risk_tier' IS NOT NULL
              AND stage3_result->>'adjusted_risk_tier' IN ('low', 'medium', 'high', 'critical')
            RETURNING id
        """))
        path1 = len(result.fetchall())
        print(f"Path 1 (stage3 adjusted_risk_tier): fixed {path1}")

        # Path 2: stage2_result has dimensions → compute score & tier
        result = await session.execute(text("""
            SELECT id, stage2_result->'dimensions' as dims
            FROM papers
            WHERE is_duplicate_of IS NULL
              AND pipeline_stage = 'adjudicated'
              AND risk_tier IS NULL
              AND stage2_result->'dimensions' IS NOT NULL
              AND jsonb_typeof(stage2_result->'dimensions') = 'object'
        """))
        rows = result.fetchall()
        path2 = 0
        for row in rows:
            dims = row.dims
            if not isinstance(dims, dict):
                continue
            agg = compute_aggregate(dims)
            if agg is None:
                continue
            tier = score_to_tier(agg)
            await session.execute(text("""
                UPDATE papers
                SET risk_tier = :tier::risk_tier,
                    aggregate_score = :score
                WHERE id = :id
            """), {"tier": tier, "score": agg, "id": row.id})
            path2 += 1
        print(f"Path 2 (computed from dimensions): fixed {path2}")

        # Path 3: LLM refused — default to low
        result = await session.execute(text("""
            UPDATE papers
            SET risk_tier = 'low'::risk_tier,
                aggregate_score = 0
            WHERE is_duplicate_of IS NULL
              AND pipeline_stage = 'adjudicated'
              AND risk_tier IS NULL
            RETURNING id
        """))
        path3 = len(result.fetchall())
        print(f"Path 3 (LLM refused → low): fixed {path3}")

        await session.commit()
        print(f"\nTotal fixed: {path1 + path2 + path3}")

        # Verify
        result = await session.execute(text("""
            SELECT COUNT(*) FROM papers
            WHERE is_duplicate_of IS NULL
              AND pipeline_stage = 'adjudicated'
              AND risk_tier IS NULL
        """))
        remaining = result.scalar()
        print(f"Remaining NULL risk_tier: {remaining}")


if __name__ == "__main__":
    asyncio.run(backfill())
