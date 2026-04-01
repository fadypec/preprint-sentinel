import { auth } from "@/lib/auth";
import { UserRole } from "@prisma/client";
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { checkRateLimit } from "@/lib/rate-limit";

/** Auth is optional in dev when no OAuth providers are configured */
function authConfigured(): boolean {
  return !!(process.env.AUTH_GITHUB_ID || process.env.AUTH_GOOGLE_ID);
}

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
