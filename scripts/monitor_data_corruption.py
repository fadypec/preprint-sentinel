#!/usr/bin/env python3
"""Monitor pipeline for data corruption and structural issues.

This script can be run periodically (e.g., daily) to detect:
1. JSON parsing corruption in methods analysis results
2. Malformed tool_input structures
3. Missing risk dimension tags
4. Pipeline health metrics

Usage:
    python -m scripts.monitor_data_corruption           # check last 24 hours
    python -m scripts.monitor_data_corruption --days 7  # check last week
    python -m scripts.monitor_data_corruption --alert   # send alerts if issues found
"""

import asyncio
import json
import smtplib
import sys
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

import structlog
from sqlalchemy import func, select, text

from pipeline.config import get_settings
from pipeline.db import make_engine, make_session_factory
from pipeline.models import AssessmentLog, Paper

log = structlog.get_logger()


async def monitor_corruption(days: int = 1, send_alerts: bool = False) -> None:
    """Monitor for data corruption in the pipeline."""
    settings = get_settings()
    engine = make_engine(settings.database_url.get_secret_value())
    session_factory = make_session_factory(engine)

    cutoff_date = datetime.now(UTC) - timedelta(days=days)

    async with session_factory() as session:
        # Check 1: String dimensions corruption
        stmt = text('''
            SELECT count(*) as corrupted_count
            FROM papers
            WHERE stage2_result ? '_error'
            AND stage2_result->>'_error' LIKE 'Missing required keys%'
            AND jsonb_typeof(stage2_result->'dimensions') = 'string'
            AND updated_at >= :cutoff_date
        ''')
        result = await session.execute(stmt, {"cutoff_date": cutoff_date})
        string_dims_count = result.scalar() or 0

        # Check 2: New structural corruption detections
        stmt = text('''
            SELECT count(*) as structural_count
            FROM papers
            WHERE stage2_result ? '_corruption_detected'
            AND updated_at >= :cutoff_date
        ''')
        result = await session.execute(stmt, {"cutoff_date": cutoff_date})
        structural_count = result.scalar() or 0

        # Check 3: Papers missing risk dimensions (properly parsed but empty)
        stmt = text('''
            SELECT count(*) as missing_risk_count
            FROM papers
            WHERE updated_at >= :cutoff_date
            AND stage2_result IS NOT NULL
            AND risk_tier IS NULL
            AND NOT (stage2_result ? '_error')
        ''')
        result = await session.execute(stmt, {"cutoff_date": cutoff_date})
        result = await session.execute(stmt)
        missing_risk_tier_count = result.scalar() or 0

        # Check 4: High error rate in recent assessments
        stmt = select(
            func.count().label("total"),
            func.sum(
                func.case((AssessmentLog.error.isnot(None), 1), else_=0)
            ).label("errors")
        ).where(
            AssessmentLog.stage == "methods_analysis",
            AssessmentLog.created_at >= cutoff_date
        )
        result = await session.execute(stmt)
        assessment_stats = result.first()
        total_assessments = assessment_stats.total or 0
        error_assessments = assessment_stats.errors or 0

        error_rate = (error_assessments / total_assessments * 100) if total_assessments > 0 else 0

        # Check 5: Recent structural errors
        stmt = select(
            AssessmentLog.paper_id,
            AssessmentLog.error,
            AssessmentLog.created_at
        ).where(
            AssessmentLog.stage == "methods_analysis",
            AssessmentLog.error.like("%Malformed tool_input%"),
            AssessmentLog.created_at >= cutoff_date
        ).limit(10)
        result = await session.execute(stmt)
        recent_structural_errors = list(result.all())

        # Generate report
        report = _generate_report(
            days=days,
            string_dims_count=string_dims_count,
            structural_count=structural_count,
            missing_risk_tier_count=missing_risk_tier_count,
            total_assessments=total_assessments,
            error_assessments=error_assessments,
            error_rate=error_rate,
            recent_structural_errors=recent_structural_errors,
        )

        print(report)

        # Send alerts if requested and issues found
        if send_alerts and _should_alert(string_dims_count, structural_count, error_rate):
            await _send_alert(report, settings)

        log.info(
            "corruption_monitoring_complete",
            days=days,
            string_dims_count=string_dims_count,
            structural_count=structural_count,
            missing_risk_tier_count=missing_risk_tier_count,
            error_rate=error_rate,
        )

    await engine.dispose()


def _generate_report(
    days: int,
    string_dims_count: int,
    structural_count: int,
    missing_risk_tier_count: int,
    total_assessments: int,
    error_assessments: int,
    error_rate: float,
    recent_structural_errors: list,
) -> str:
    """Generate a monitoring report."""
    report_lines = [
        f"# DURC Pipeline Data Corruption Report",
        f"**Time Period**: Last {days} day(s)",
        f"**Generated**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"",
        f"## Summary",
        f"- **String Dimensions Corruption**: {string_dims_count} papers",
        f"- **New Structural Corruption**: {structural_count} papers",
        f"- **Missing Risk Tiers**: {missing_risk_tier_count} papers",
        f"- **Assessment Error Rate**: {error_rate:.1f}% ({error_assessments}/{total_assessments})",
        f"",
    ]

    if string_dims_count > 0:
        report_lines.extend([
            f"## ⚠️  String Dimensions Corruption Detected",
            f"Found {string_dims_count} papers with corrupted JSON where dimensions are stored as strings.",
            f"This indicates the JSON parsing bug has recurred. Run the fix script:",
            f"```",
            f"python -m scripts.fix_json_parsing_bug --apply",
            f"```",
            f"",
        ])

    if structural_count > 0:
        report_lines.extend([
            f"## 🔥 New Structural Corruption Detected",
            f"Found {structural_count} papers with new structural corruption detected by enhanced validation.",
            f"Check logs for details and investigate root cause.",
            f"",
        ])

    if error_rate > 10:
        report_lines.extend([
            f"## 📈 High Error Rate",
            f"Methods analysis error rate is {error_rate:.1f}%, which is above normal levels.",
            f"This may indicate API issues or prompt problems.",
            f"",
        ])

    if recent_structural_errors:
        report_lines.extend([
            f"## Recent Structural Errors",
        ])
        for paper_id, error, created_at in recent_structural_errors[:5]:
            report_lines.append(f"- {created_at}: Paper {paper_id} - {error}")
        report_lines.append("")

    if (string_dims_count == 0 and structural_count == 0 and
        missing_risk_tier_count == 0 and error_rate < 5):
        report_lines.extend([
            f"## ✅ All Systems Healthy",
            f"No corruption or high error rates detected.",
        ])

    return "\n".join(report_lines)


def _should_alert(string_dims_count: int, structural_count: int, error_rate: float) -> bool:
    """Determine if alerts should be sent."""
    return (
        string_dims_count > 0 or      # Any JSON corruption
        structural_count > 5 or       # More than 5 structural issues
        error_rate > 15               # Error rate above 15%
    )


async def _send_alert(report: str, settings) -> None:
    """Send alert email if configured."""
    # Placeholder for email alerting - would need SMTP configuration
    log.info("alert_would_be_sent", report_preview=report[:200])
    print("\n🚨 ALERT: Issues detected - email would be sent if SMTP configured")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor pipeline for data corruption")
    parser.add_argument("--days", type=int, default=1, help="Number of days to check (default: 1)")
    parser.add_argument("--alert", action="store_true", help="Send alerts if issues found")

    args = parser.parse_args()

    asyncio.run(monitor_corruption(days=args.days, send_alerts=args.alert))