import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { auth } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "DURC Triage Dashboard",
  description: "Biosecurity paper review and triage system",
};

async function getPipelineStatusSafe() {
  try {
    const url = process.env.PIPELINE_API_URL ?? "http://localhost:8000";
    const secret = process.env.PIPELINE_API_SECRET ?? "";
    const res = await fetch(`${url}/status`, {
      headers: { Authorization: `Bearer ${secret}` },
      cache: "no-store",
    });
    if (res.ok) return res.json();
  } catch {
    // Pipeline sidecar may not be running
  }
  return null;
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  const pipelineStatus = session ? await getPipelineStatusSafe() : null;

  // Login page renders without sidebar
  if (!session) {
    return (
      <html lang="en" suppressHydrationWarning>
        <body>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
            <NuqsAdapter>
              {children}
            </NuqsAdapter>
          </ThemeProvider>
        </body>
      </html>
    );
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <NuqsAdapter>
            <div className="flex h-screen bg-slate-50 dark:bg-slate-900">
              <Sidebar
                pipelineStatus={pipelineStatus}
                userName={session.user?.name}
              />
              <main className="flex-1 overflow-y-auto p-6">
                {children}
              </main>
            </div>
          </NuqsAdapter>
        </ThemeProvider>
      </body>
    </html>
  );
}
