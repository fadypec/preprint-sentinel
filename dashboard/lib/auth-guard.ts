import { auth } from "@/lib/auth";
import { UserRole } from "@prisma/client";
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { checkRateLimit } from "@/lib/rate-limit";

/**
 * Auth is optional in dev when no OAuth providers are configured.
 * In production (NODE_ENV=production), auth is ALWAYS required —
 * the app will reject requests rather than silently running open.
 */
function authConfigured(): boolean {
  const configured = !!(process.env.AUTH_GITHUB_ID || process.env.AUTH_GOOGLE_ID);
  if (configured) return true;

  // In production, never allow unauthenticated access
  if (process.env.NODE_ENV === "production") {
    if (!authWarned) {
      authWarned = true;
      console.error(
        "[SECURITY] CRITICAL: No OAuth providers configured in production. " +
        "Set AUTH_GITHUB_ID/AUTH_GOOGLE_ID. Auth is ENFORCED — requests will be rejected.",
      );
    }
    return true; // Force auth checks even though no provider exists (will 401 everything)
  }

  // Dev mode — allow open access with warning
  if (!authWarned) {
    authWarned = true;
    console.warn(
      "[SECURITY] No OAuth providers configured. " +
      "Authentication is DISABLED (dev mode only).",
    );
  }
  return false;
}

let authWarned = false;

// ---------------------------------------------------------------------------
// Page guards (redirect on failure)
// ---------------------------------------------------------------------------

export async function requireAuth() {
  if (!authConfigured()) return null;
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }
  return session;
}

export async function requireAdmin() {
  if (!authConfigured()) return null;
  const session = await requireAuth();
  if (session && session.user.role !== UserRole.admin) {
    redirect("/");
  }
  return session;
}

// ---------------------------------------------------------------------------
// API guards (return Response on failure — never redirect)
// ---------------------------------------------------------------------------

/** Get client IP for rate limiting. */
async function getClientIp(): Promise<string> {
  const h = await headers();
  return h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
}

/**
 * CSRF protection via Origin header verification.
 *
 * For state-changing requests (PUT, PATCH, POST, DELETE), verifies that
 * the Origin header matches the expected host. This prevents cross-site
 * request forgery since browsers always send the Origin header on
 * cross-origin requests and it cannot be spoofed by JavaScript.
 *
 * Returns a 403 Response if the origin doesn't match, or null if OK.
 */
export async function csrfCheck(request: Request): Promise<Response | null> {
  const method = request.method.toUpperCase();
  // Only check state-changing methods
  if (method === "GET" || method === "HEAD" || method === "OPTIONS") {
    return null;
  }

  const origin = request.headers.get("origin");
  const host = request.headers.get("host");

  // If no origin header, this is likely a same-origin request (fetch API
  // from same page). Browsers always send Origin on cross-origin requests.
  if (!origin) return null;

  // Verify origin matches host
  try {
    const originUrl = new URL(origin);
    if (host && originUrl.host === host) {
      return null; // Same origin — safe
    }
  } catch {
    // Malformed origin — reject
  }

  return Response.json(
    { error: "CSRF validation failed: origin mismatch" },
    { status: 403 },
  );
}

/** Returns null if the request is authorised, or a 401/429 Response if not. */
export async function apiRequireAuth(): Promise<Response | null> {
  const rateLimited = checkRateLimit(await getClientIp());
  if (rateLimited) return rateLimited;
  if (!authConfigured()) return null; // dev mode — allow all
  const session = await auth();
  if (!session?.user) {
    return Response.json({ error: "Authentication required" }, { status: 401 });
  }
  return null;
}

/** Returns null if the request is from an admin, or a 401/403/429 Response. */
export async function apiRequireAdmin(): Promise<Response | null> {
  const rateLimited = checkRateLimit(await getClientIp());
  if (rateLimited) return rateLimited;
  if (!authConfigured()) return null;
  const session = await auth();
  if (!session?.user) {
    return Response.json({ error: "Authentication required" }, { status: 401 });
  }
  if (session.user.role !== UserRole.admin) {
    return Response.json({ error: "Admin access required" }, { status: 403 });
  }
  return null;
}
