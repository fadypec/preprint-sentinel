import { auth } from "@/lib/auth";
import { UserRole } from "@prisma/client";
import { redirect } from "next/navigation";

/** Auth is optional in dev when no OAuth providers are configured */
function authConfigured(): boolean {
  return !!(process.env.AUTH_GITHUB_ID || process.env.AUTH_GOOGLE_ID);
}

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
