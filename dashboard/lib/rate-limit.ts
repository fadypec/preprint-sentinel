/**
 * Simple in-memory sliding-window rate limiter.
 *
 * Not suitable for multi-instance deployments (use Redis there),
 * but effective for a single-server dashboard.
 */

const store = new Map<string, number[]>();

const WINDOW_MS = 60_000; // 1 minute
const MAX_REQUESTS = 60; // per window per key

/** Prune entries older than the window. Runs periodically to avoid unbounded growth. */
function prune() {
  const cutoff = Date.now() - WINDOW_MS;
  for (const [key, timestamps] of store) {
    const fresh = timestamps.filter((t) => t > cutoff);
    if (fresh.length === 0) store.delete(key);
    else store.set(key, fresh);
  }
}

// Prune every 5 minutes
setInterval(prune, 5 * 60_000).unref();

/**
 * Check rate limit for a key (typically IP address).
 * Returns null if allowed, or a 429 Response if rate-limited.
 */
export function checkRateLimit(key: string): Response | null {
  const now = Date.now();
  const cutoff = now - WINDOW_MS;
  const timestamps = (store.get(key) ?? []).filter((t) => t > cutoff);
  timestamps.push(now);
  store.set(key, timestamps);

  if (timestamps.length > MAX_REQUESTS) {
    return Response.json(
      { error: "Too many requests. Try again later." },
      {
        status: 429,
        headers: { "Retry-After": "60" },
      },
    );
  }
  return null;
}
