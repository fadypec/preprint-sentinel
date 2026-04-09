"""Shared HTTP request helper with exponential backoff retry.

Consolidates the retry/backoff pattern used across all ingest and enrichment
API clients into a single, well-tested function.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger()


async def request_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 30.0,
    request_delay: float = 0.1,
    max_retries: int = 3,
    max_backoff: float = 30.0,
    retry_on: tuple[type[Exception], ...] = (httpx.TimeoutException,),
    none_on_404: bool = False,
    source: str = "",
) -> httpx.Response | None:
    """Make a GET request with exponential backoff on transient failures.

    Args:
        client: The httpx.AsyncClient to use.
        url: Request URL.
        params: Optional query parameters.
        timeout: Per-request timeout in seconds.
        request_delay: Delay before each request (rate limiting).
        max_retries: Maximum number of attempts.
        max_backoff: Cap on backoff delay in seconds.
        retry_on: Exception types that trigger a retry (in addition to 429/503).
        none_on_404: If True, return None on HTTP 404 instead of raising.
        source: Name of the API source (for log context).

    Returns:
        The httpx.Response on success (status 200), or None if 404 and
        none_on_404 is True.

    Raises:
        RuntimeError: If all retries exhausted.
        httpx.HTTPStatusError: On non-retryable HTTP errors.
    """
    for attempt in range(1, max_retries + 1):
        await asyncio.sleep(request_delay)
        try:
            resp = await client.get(url, params=params, timeout=timeout)

            if resp.status_code == 200:
                return resp

            if resp.status_code == 404 and none_on_404:
                return None

            if resp.status_code in (429, 503):
                backoff = min(2**attempt, max_backoff)
                log.warning(
                    "rate_limited",
                    source=source,
                    status=resp.status_code,
                    attempt=attempt,
                    backoff=backoff,
                    url=url,
                )
                await asyncio.sleep(backoff)
                continue

            resp.raise_for_status()

        except retry_on as exc:
            if attempt == max_retries:
                raise
            backoff = min(2**attempt, max_backoff)
            log.warning(
                "request_error",
                source=source,
                error=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                attempt=attempt,
                backoff=backoff,
                url=url,
            )
            await asyncio.sleep(backoff)

    raise RuntimeError(f"{source} failed after {max_retries} retries: {url}")
