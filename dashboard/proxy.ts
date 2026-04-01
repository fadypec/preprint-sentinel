import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

/** Skip auth proxy entirely when no OAuth providers are configured (dev mode) */
const authConfigured = !!(process.env.AUTH_GITHUB_ID || process.env.AUTH_GOOGLE_ID);

export const proxy = authConfigured
  ? auth
  : () => NextResponse.next();

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - /login
     * - /api/auth (Auth.js routes)
     * - /_next/static, /_next/image (Next.js internals)
     * - /favicon.ico
     */
    "/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
};
