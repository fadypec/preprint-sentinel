"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, FileText, Settings, Workflow } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

type NavItem = { href: string; label: string; icon: typeof FileText; adminOnly?: boolean };

const navItems: NavItem[] = [
  { href: "/", label: "Daily Feed", icon: FileText },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/pipeline", label: "Pipeline", icon: Workflow, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

type SidebarProps = {
  pipelineStatus?: {
    running: boolean;
    paused: boolean;
    next_run_time: string | null;
  } | null;
  userName?: string | null;
  userRole?: string | null;
};

export function Sidebar({ pipelineStatus, userName, userRole }: SidebarProps) {
  const pathname = usePathname();
  const isAdmin = userRole === "admin";

  const visibleItems = navItems.filter((item) => !item.adminOnly || isAdmin);

  const statusDot = pipelineStatus
    ? pipelineStatus.paused
      ? "bg-yellow-500"
      : pipelineStatus.running
        ? "bg-green-500"
        : "bg-slate-400"
    : "bg-slate-400";

  const statusLabel = pipelineStatus
    ? pipelineStatus.paused
      ? "Paused"
      : pipelineStatus.running
        ? "Running"
        : "Idle"
    : "Unknown";

  return (
    <aside suppressHydrationWarning className="relative z-50 flex h-screen w-56 flex-col border-r border-slate-200 bg-white pb-16 dark:border-slate-700 dark:bg-slate-800">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5">
        <div aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
          PS
        </div>
        <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
          Preprint Sentinel
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2" aria-label="Main navigation">
        <ul className="flex flex-col gap-1">
          {visibleItems.map((item) => {
            const isActive = item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "border-l-2 border-blue-500 bg-slate-100 text-blue-600 dark:bg-slate-700 dark:text-blue-400"
                      : "text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-700"
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Pipeline status — only show for admins */}
      {isAdmin && (
        <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <div className={cn("h-2 w-2 rounded-full", statusDot)} aria-hidden="true" />
            <span>Pipeline {statusLabel}</span>
          </div>
          {pipelineStatus?.next_run_time && (
            <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              Next: {new Date(pipelineStatus.next_run_time).toLocaleTimeString()}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-700">
        <span className="truncate text-xs text-slate-500 dark:text-slate-400">
          {userName ?? "User"}
        </span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
