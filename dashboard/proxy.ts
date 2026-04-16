import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";

/**
 * Proxy handles two concerns:
 * 1. CSP nonce generation (per-request nonce replaces unsafe-inline)
 * 2. Auth enforcement (redirects unauthenticated users to /login)
 *
 * In dev mode without OAuth providers, auth is skipped so the
 * dashboard remains accessible for local development.
 */

const isDev = process.env.NODE_ENV !== "production";

const PUBLIC_ROUTES = ["/login", "/pending", "/api/auth", "/api/health"];

function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTES.some((route) => pathname.startsWith(route));
}

export const proxy = auth((req) => {
  const { pathname } = req.nextUrl;

  // --- Auth enforcement ---
  if (!isPublicRoute(pathname)) {
    const authRequired = !!(
      process.env.AUTH_GITHUB_ID || process.env.AUTH_GOOGLE_ID
    );

    if (authRequired) {
      // Not logged in → login page
      if (!req.auth) {
        return NextResponse.redirect(new URL("/login", req.url));
      }

      // Logged in but not approved → pending page
      const userStatus = (req.auth as { user?: { status?: string } })?.user
        ?.status;
      if (userStatus && userStatus !== "approved") {
        return NextResponse.redirect(new URL("/pending", req.url));
      }
    }
  }

  // --- CSP nonce ---
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self'",
    "connect-src 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set("Content-Security-Policy", csp);
  return response;
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
