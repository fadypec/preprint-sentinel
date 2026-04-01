import { requireAdmin } from "@/lib/auth-guard";
import { prisma } from "@/lib/prisma";
import { SettingsForm } from "@/components/settings-form";

export default async function SettingsPage() {
  await requireAdmin();

  const row = await prisma.pipelineSettings.findUnique({ where: { id: 1 } });
  const settings = (row?.settings as Record<string, unknown>) ?? {};

  return (
    <div>
      <h1 className="mb-6 text-xl font-bold text-slate-900 dark:text-slate-100">
        Settings
      </h1>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Configure pipeline parameters. Changes take effect on the next pipeline
        run.
      </p>
      <SettingsForm initialSettings={settings} />
    </div>
  );
}
