"""Tests for pipeline.alerts -- Slack and email failure alerting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


class TestSendPipelineFailureAlert:
    """Tests for send_pipeline_failure_alert orchestration."""

    async def test_sends_slack_when_webhook_configured(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {
            "alert_slack_webhook": "https://hooks.slack.com/test/webhook",
        }
        with patch("pipeline.alerts._send_slack", new_callable=AsyncMock) as mock_slack:
            await send_pipeline_failure_alert(
                errors=["Stage failed"],
                settings_json=settings,
                run_duration_s=120.0,
                papers_ingested=50,
            )
            mock_slack.assert_called_once()
            # Verify message content
            message = mock_slack.call_args[0][1]
            assert "1 error(s)" in message
            assert "Stage failed" in message

    async def test_sends_email_when_smtp_configured(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {
            "alert_smtp_host": "smtp.example.com",
            "alert_recipients": "analyst@example.com",
        }
        with patch("pipeline.alerts._send_email") as mock_email:
            await send_pipeline_failure_alert(
                errors=["Ingest timeout"],
                settings_json=settings,
                run_duration_s=300.0,
                papers_ingested=0,
            )
            mock_email.assert_called_once()

    async def test_skips_slack_when_no_webhook(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {"alert_slack_webhook": ""}
        with patch("pipeline.alerts._send_slack", new_callable=AsyncMock) as mock_slack:
            await send_pipeline_failure_alert(
                errors=["Error"],
                settings_json=settings,
                run_duration_s=60.0,
                papers_ingested=10,
            )
            mock_slack.assert_not_called()

    async def test_skips_email_when_no_smtp_host(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {"alert_smtp_host": "", "alert_recipients": "user@example.com"}
        with patch("pipeline.alerts._send_email") as mock_email:
            await send_pipeline_failure_alert(
                errors=["Error"],
                settings_json=settings,
                run_duration_s=60.0,
                papers_ingested=10,
            )
            mock_email.assert_not_called()

    async def test_skips_email_when_no_recipients(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {"alert_smtp_host": "smtp.example.com", "alert_recipients": ""}
        with patch("pipeline.alerts._send_email") as mock_email:
            await send_pipeline_failure_alert(
                errors=["Error"],
                settings_json=settings,
                run_duration_s=60.0,
                papers_ingested=10,
            )
            mock_email.assert_not_called()

    async def test_truncates_errors_at_10(self):
        from pipeline.alerts import send_pipeline_failure_alert

        errors = [f"Error {i}" for i in range(15)]
        settings = {"alert_slack_webhook": "https://hooks.slack.com/test"}

        with patch("pipeline.alerts._send_slack", new_callable=AsyncMock) as mock_slack:
            await send_pipeline_failure_alert(
                errors=errors,
                settings_json=settings,
                run_duration_s=60.0,
                papers_ingested=0,
            )
            message = mock_slack.call_args[0][1]
            assert "15 error(s)" in message
            assert "and 5 more" in message

    async def test_skips_slack_when_webhook_not_http(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {"alert_slack_webhook": "not-a-url"}
        with patch("pipeline.alerts._send_slack", new_callable=AsyncMock) as mock_slack:
            await send_pipeline_failure_alert(
                errors=["Error"],
                settings_json=settings,
                run_duration_s=60.0,
                papers_ingested=0,
            )
            mock_slack.assert_not_called()

    async def test_message_includes_duration_and_count(self):
        from pipeline.alerts import send_pipeline_failure_alert

        settings = {"alert_slack_webhook": "https://hooks.slack.com/test"}
        with patch("pipeline.alerts._send_slack", new_callable=AsyncMock) as mock_slack:
            await send_pipeline_failure_alert(
                errors=["Timeout"],
                settings_json=settings,
                run_duration_s=542.7,
                papers_ingested=123,
            )
            message = mock_slack.call_args[0][1]
            assert "543s" in message  # rounded
            assert "123 papers ingested" in message


class TestSendSlack:
    """Tests for _send_slack webhook posting."""

    async def test_successful_post(self):
        from pipeline.alerts import _send_slack

        mock_response = httpx.Response(200)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _send_slack("https://hooks.slack.com/test", "Test message")

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert "Pipeline Failure" in call_kwargs.kwargs["json"]["text"]

    async def test_handles_non_200_gracefully(self):
        from pipeline.alerts import _send_slack

        mock_response = httpx.Response(500)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Should not raise
            await _send_slack("https://hooks.slack.com/test", "Test message")

    async def test_handles_network_error_gracefully(self):
        from pipeline.alerts import _send_slack

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Should not raise
            await _send_slack("https://hooks.slack.com/test", "Test message")


class TestSendEmail:
    """Tests for _send_email SMTP sending."""

    def test_successful_email(self):
        from pipeline.alerts import _send_email

        settings = {
            "alert_smtp_host": "smtp.example.com",
            "alert_smtp_port": "587",
            "alert_smtp_user": "user@example.com",
            "alert_smtp_pass": "password",
            "alert_smtp_from": "alerts@example.com",
            "alert_recipients": "analyst@example.com",
        }

        with patch("pipeline.alerts.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp_cls.return_value = mock_smtp

            _send_email(settings, "Pipeline failed with errors")

            mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)
            mock_smtp.starttls.assert_called_once()
            mock_smtp.login.assert_called_once_with("user@example.com", "password")
            mock_smtp.sendmail.assert_called_once()

    def test_skips_login_when_no_credentials(self):
        from pipeline.alerts import _send_email

        settings = {
            "alert_smtp_host": "smtp.example.com",
            "alert_smtp_port": "25",
            "alert_smtp_user": "",
            "alert_smtp_pass": "",
            "alert_recipients": "analyst@example.com",
        }

        with patch("pipeline.alerts.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp_cls.return_value = mock_smtp

            _send_email(settings, "Pipeline failed")

            mock_smtp.login.assert_not_called()
            mock_smtp.sendmail.assert_called_once()

    def test_handles_smtp_error_gracefully(self):
        from pipeline.alerts import _send_email

        settings = {
            "alert_smtp_host": "smtp.example.com",
            "alert_recipients": "analyst@example.com",
        }

        with patch("pipeline.alerts.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

            # Should not raise
            _send_email(settings, "Pipeline failed")

    def test_returns_early_when_no_host(self):
        from pipeline.alerts import _send_email

        settings = {"alert_smtp_host": "", "alert_recipients": "analyst@example.com"}

        with patch("pipeline.alerts.smtplib.SMTP") as mock_smtp_cls:
            _send_email(settings, "Pipeline failed")
            mock_smtp_cls.assert_not_called()

    def test_returns_early_when_no_recipients(self):
        from pipeline.alerts import _send_email

        settings = {"alert_smtp_host": "smtp.example.com", "alert_recipients": ""}

        with patch("pipeline.alerts.smtplib.SMTP") as mock_smtp_cls:
            _send_email(settings, "Pipeline failed")
            mock_smtp_cls.assert_not_called()

    def test_multiple_recipients(self):
        from pipeline.alerts import _send_email

        settings = {
            "alert_smtp_host": "smtp.example.com",
            "alert_smtp_port": "587",
            "alert_smtp_user": "",
            "alert_smtp_pass": "",
            "alert_recipients": "analyst1@example.com,analyst2@example.com",
        }

        with patch("pipeline.alerts.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp_cls.return_value = mock_smtp

            _send_email(settings, "Pipeline failed")

            sendmail_args = mock_smtp.sendmail.call_args[0]
            assert sendmail_args[1] == ["analyst1@example.com", "analyst2@example.com"]
