import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Preprint Sentinel",
  description: "Biosecurity preprint monitoring and triage system",
  icons: {
    icon: [
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

async function getPipelineStatusSafe() {
  try {
    const runningRun = await prisma.pipelineRun.findFirst({
      where: { finishedAt: null },
      orderBy: { startedAt: "desc" },
    });
    return {
      running: !!runningRun,
      paused: false,
      next_run_time: null,
    };
  } catch {
    return null;
  }
}

/** Auth is optional in dev when no OAuth providers are configured */
function authConfigured(): boolean {
  return !!(process.env.AUTH_GITHUB_ID || process.env.AUTH_GOOGLE_ID);
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  const isAuthRequired = authConfigured();
  const session = isAuthRequired ? await auth() : null;
  // Show dashboard only if: auth not required (dev), OR user is authenticated AND approved
  const isApproved = !isAuthRequired || session?.user?.status === "approved";
  const showDashboard = isApproved;
  const pipelineStatus = showDashboard ? await getPipelineStatusSafe() : null;

  const fontClasses = `${geistSans.variable} ${geistMono.variable} antialiased`;

  // Login/pending pages render without sidebar
  if (!showDashboard) {
    return (
      <html lang="en" suppressHydrationWarning className={fontClasses}>
        <body>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem nonce={nonce}>
            <NuqsAdapter>
              {children}
            </NuqsAdapter>
          </ThemeProvider>
        </body>
      </html>
    );
  }

  return (
    <html lang="en" suppressHydrationWarning className={fontClasses}>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem nonce={nonce}>
          <NuqsAdapter>
            <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:bg-blue-600 focus:px-4 focus:py-2 focus:text-white">
              Skip to main content
            </a>
            <div className="flex h-screen bg-slate-50 dark:bg-slate-900">
              <Sidebar
                pipelineStatus={pipelineStatus}
                userName={session?.user?.name ?? "Dev User"}
                userRole={session?.user?.role ?? null}
              />
              <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto p-6">
                {children}
              </main>
            </div>
          </NuqsAdapter>
        </ThemeProvider>
      </body>
    </html>
  );
}
