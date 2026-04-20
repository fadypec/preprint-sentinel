"""Tests for pipeline.http_retry -- HTTP request retry with exponential backoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


class TestRequestWithRetry:
    """Tests for request_with_retry."""

    async def test_successful_request_no_retry(self):
        """A 200 response should be returned immediately without retrying."""
        from pipeline.http_retry import request_with_retry

        mock_response = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await request_with_retry(
            client,
            "https://example.com/api",
            request_delay=0,
            max_retries=3,
            source="test",
        )

        assert result is not None
        assert result.status_code == 200
        assert client.get.call_count == 1

    async def test_retry_on_429_rate_limit(self):
        """Should retry on 429 (rate limited) with backoff."""
        from pipeline.http_retry import request_with_retry

        rate_limited = httpx.Response(429)
        success = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[rate_limited, success])

        with patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=3,
                source="test",
            )

        assert result is not None
        assert result.status_code == 200
        assert client.get.call_count == 2

    async def test_retry_on_503_server_error(self):
        """Should retry on 503 (service unavailable)."""
        from pipeline.http_retry import request_with_retry

        server_error = httpx.Response(503)
        success = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[server_error, success])

        with patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=3,
                source="test",
            )

        assert result is not None
        assert result.status_code == 200
        assert client.get.call_count == 2

    async def test_max_retries_exhausted_on_429(self):
        """Should raise RuntimeError when all retries fail on 429."""
        from pipeline.http_retry import request_with_retry

        rate_limited = httpx.Response(429)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=rate_limited)

        with (
            patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(RuntimeError, match="failed after 2 retries"),
        ):
            await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=2,
                source="test",
            )

        assert client.get.call_count == 2

    async def test_non_retryable_400_raises_immediately(self):
        """A 400 Bad Request should raise immediately without retrying."""
        from pipeline.http_retry import request_with_retry

        bad_request = httpx.Response(400, request=httpx.Request("GET", "https://example.com/api"))
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=bad_request)

        with pytest.raises(httpx.HTTPStatusError):
            await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=3,
                source="test",
            )

        assert client.get.call_count == 1

    async def test_non_retryable_404_raises_by_default(self):
        """A 404 should raise immediately when none_on_404 is False (default)."""
        from pipeline.http_retry import request_with_retry

        not_found = httpx.Response(404, request=httpx.Request("GET", "https://example.com/api"))
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=not_found)

        with pytest.raises(httpx.HTTPStatusError):
            await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=3,
                source="test",
            )

        assert client.get.call_count == 1

    async def test_404_returns_none_when_enabled(self):
        """A 404 should return None when none_on_404=True."""
        from pipeline.http_retry import request_with_retry

        not_found = httpx.Response(404)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=not_found)

        result = await request_with_retry(
            client,
            "https://example.com/api",
            request_delay=0,
            max_retries=3,
            none_on_404=True,
            source="test",
        )

        assert result is None
        assert client.get.call_count == 1

    async def test_retry_on_timeout_exception(self):
        """Should retry on httpx.TimeoutException (default retry_on)."""
        from pipeline.http_retry import request_with_retry

        success = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(
            side_effect=[httpx.ReadTimeout("read timed out"), success]
        )

        with patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=3,
                source="test",
            )

        assert result is not None
        assert result.status_code == 200
        assert client.get.call_count == 2

    async def test_timeout_raises_after_max_retries(self):
        """TimeoutException should propagate after all retries exhausted."""
        from pipeline.http_retry import request_with_retry

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))

        with (
            patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(httpx.ReadTimeout),
        ):
            await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=2,
                source="test",
            )

        assert client.get.call_count == 2

    async def test_params_passed_to_client(self):
        """Query parameters should be forwarded to the HTTP client."""
        from pipeline.http_retry import request_with_retry

        success = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=success)

        await request_with_retry(
            client,
            "https://example.com/api",
            params={"page": "1", "limit": "100"},
            request_delay=0,
            source="test",
        )

        call_kwargs = client.get.call_args
        assert call_kwargs.kwargs["params"] == {"page": "1", "limit": "100"}

    async def test_custom_retry_on_exception(self):
        """Should retry on custom exception types specified in retry_on."""
        from pipeline.http_retry import request_with_retry

        success = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(
            side_effect=[httpx.RemoteProtocolError("protocol error"), success]
        )

        with patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=3,
                retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
                source="test",
            )

        assert result is not None
        assert result.status_code == 200

    async def test_backoff_capped_at_max(self):
        """Backoff delay should not exceed max_backoff."""
        from pipeline.http_retry import request_with_retry

        rate_limited = httpx.Response(429)
        success = httpx.Response(200, json={"ok": True})
        client = AsyncMock(spec=httpx.AsyncClient)
        # 3 rate limits then success
        client.get = AsyncMock(
            side_effect=[rate_limited, rate_limited, rate_limited, success]
        )

        sleep_calls = []

        async def track_sleep(delay):
            sleep_calls.append(delay)

        with patch("pipeline.http_retry.asyncio.sleep", side_effect=track_sleep):
            await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=5,
                max_backoff=5.0,
                source="test",
            )

        # Backoff values: 2^1=2, 2^2=4, 2^3=8->capped to 5
        # Plus request_delay=0 calls
        backoff_delays = [d for d in sleep_calls if d > 0]
        assert all(d <= 5.0 for d in backoff_delays)

    async def test_multiple_429s_then_success(self):
        """Should handle multiple consecutive 429s before succeeding."""
        from pipeline.http_retry import request_with_retry

        rate_limited = httpx.Response(429)
        success = httpx.Response(200, json={"data": "found"})
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[rate_limited, rate_limited, success])

        with patch("pipeline.http_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await request_with_retry(
                client,
                "https://example.com/api",
                request_delay=0,
                max_retries=5,
                source="test",
            )

        assert result is not None
        assert result.json() == {"data": "found"}
        assert client.get.call_count == 3
