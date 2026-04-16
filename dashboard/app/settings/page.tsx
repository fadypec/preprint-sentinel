import { requireAdmin } from "@/lib/auth-guard";
import { prisma } from "@/lib/prisma";
import { SettingsForm } from "@/components/settings-form";
import { UserManagement } from "@/components/user-management";
import { Card } from "@/components/ui/card";

export default async function SettingsPage() {
  await requireAdmin();

  const row = await prisma.pipelineSettings.findUnique({ where: { id: 1 } });
  const settings = (row?.settings as Record<string, unknown>) ?? {};

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Settings
      </h1>

      {/* User management */}
      <Card className="mb-6 p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          User Access Control
        </h2>
        <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          New users who sign in are placed in &quot;pending&quot; status. Approve
          or reject them below. Only approved users can access the dashboard.
        </p>
        <UserManagement />
      </Card>

      {/* Pipeline settings */}
      <Card className="p-4">
        <h2 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Pipeline Configuration
        </h2>
        <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          Configure pipeline parameters. Changes take effect on the next pipeline run.
        </p>
        <SettingsForm initialSettings={settings} />
      </Card>
    </div>
  );
}
