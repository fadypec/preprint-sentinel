import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

/**
 * Auth middleware — protects all routes except public ones.
 *
 * Unauthenticated users are redirected to /login. Public routes
 * (login page, auth callbacks, health check) are excluded.
 *
 * In dev mode without OAuth providers, auth is skipped entirely
 * so the dashboard remains accessible for local development.
 */
export default auth((req) => {
  const { pathname } = req.nextUrl;

  // Public routes that don't require authentication
  const isPublicRoute =
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/api/health") ||
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico";

  if (isPublicRoute) return NextResponse.next();

  // If no OAuth providers configured (dev mode), allow all
  if (!process.env.AUTH_GITHUB_ID && !process.env.AUTH_GOOGLE_ID) {
    return NextResponse.next();
  }

  // If not authenticated, redirect to login
  if (!req.auth) {
    const loginUrl = new URL("/login", req.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
});

export const config = {
  // Run middleware on all routes except static assets
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
