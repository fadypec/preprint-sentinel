import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";

/**
 * Pending approval page — shown to authenticated users whose
 * account hasn't been approved by an admin yet.
 */
export default async function PendingPage() {
  const session = await auth();

  // If not logged in, go to login
  if (!session?.user?.email) {
    redirect("/login");
  }

  // If already approved, go to dashboard
  const user = await prisma.user.findUnique({
    where: { email: session.user.email },
    select: { status: true },
  });

  if (user?.status === "approved") {
    redirect("/");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-900">
      <div className="mx-4 max-w-md rounded-lg border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-4 text-4xl">&#128274;</div>
        <h1 className="mb-2 text-xl font-bold text-slate-900 dark:text-slate-100">
          Account Pending Approval
        </h1>
        <p className="mb-6 text-sm text-slate-600 dark:text-slate-400">
          Your account has been created, but access to the DURC Triage dashboard
          requires approval from an administrator. You&apos;ll be able to access
          the dashboard once your account is approved.
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-500">
          Signed in as {session.user.email}
        </p>
      </div>
    </div>
  );
}
