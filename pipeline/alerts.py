"""Pipeline failure alerting — sends Slack/email when a run has errors.

Called at the end of each pipeline run if errors were recorded.
Reads alert config from the PipelineSettings database table (same
config the dashboard uses for digest alerts).
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import httpx
import structlog

log = structlog.get_logger()


async def send_pipeline_failure_alert(
    errors: list[str],
    settings_json: dict,
    run_duration_s: float,
    papers_ingested: int,
) -> None:
    """Send alert via Slack and/or email if configured.

    Args:
        errors: List of error messages from the pipeline run.
        settings_json: The PipelineSettings.settings JSONB dict.
        run_duration_s: Duration of the pipeline run in seconds.
        papers_ingested: Number of papers ingested before errors.
    """
    error_summary = "\n".join(f"• {e}" for e in errors[:10])
    if len(errors) > 10:
        error_summary += f"\n... and {len(errors) - 10} more"

    message = (
        f"Pipeline run failed with {len(errors)} error(s) "
        f"after {run_duration_s:.0f}s ({papers_ingested} papers ingested).\n\n"
        f"{error_summary}"
    )

    # Try Slack webhook
    webhook_url = settings_json.get("alert_slack_webhook", "")
    if webhook_url and isinstance(webhook_url, str) and webhook_url.startswith("http"):
        await _send_slack(webhook_url, message)

    # Try email
    smtp_host = settings_json.get("alert_smtp_host", "")
    recipients = settings_json.get("alert_recipients", "")
    if smtp_host and recipients:
        _send_email(settings_json, message)


async def _send_slack(webhook_url: str, message: str) -> None:
    """Post a failure alert to Slack via webhook."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                webhook_url,
                json={"text": f":rotating_light: *Pipeline Failure*\n{message}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                log.info("pipeline_alert_slack_sent")
            else:
                log.warning("pipeline_alert_slack_failed", status=resp.status_code)
    except Exception as exc:
        log.warning("pipeline_alert_slack_error", error=str(exc))


def _send_email(settings: dict, message: str) -> None:
    """Send a failure alert email via SMTP."""
    try:
        host = settings.get("alert_smtp_host", "")
        port = int(settings.get("alert_smtp_port", 587))
        user = settings.get("alert_smtp_user", "")
        password = settings.get("alert_smtp_pass", "")
        sender = settings.get("alert_smtp_from", user)
        recipients = settings.get("alert_recipients", "")

        if not host or not recipients:
            return

        msg = MIMEText(message)
        msg["Subject"] = "DURC Triage — Pipeline Failure Alert"
        msg["From"] = sender
        msg["To"] = recipients

        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(sender, recipients.split(","), msg.as_string())

        log.info("pipeline_alert_email_sent", recipients=recipients)
    except Exception as exc:
        log.warning("pipeline_alert_email_error", error=str(exc))
