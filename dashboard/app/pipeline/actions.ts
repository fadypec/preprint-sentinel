"use server";

import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";

export async function triggerPipeline(
  fromDate: string,
  toDate: string,
): Promise<{ ok: true; message: string } | { ok: false; error: string }> {
  // Check if already running
  const running = await prisma.pipelineRun.findFirst({
    where: { finishedAt: null },
  });
  if (running) {
    return { ok: false, error: "Pipeline is already running" };
  }

  const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  if (fromDate && !DATE_RE.test(fromDate)) {
    return { ok: false, error: "fromDate must be YYYY-MM-DD" };
  }
  if (toDate && !DATE_RE.test(toDate)) {
    return { ok: false, error: "toDate must be YYYY-MM-DD" };
  }

  // Read pubmed_query_mode from dashboard settings
  const settingsRow = await prisma.pipelineSettings.findUnique({
    where: { id: 1 },
  });
  const dashSettings = (settingsRow?.settings as Record<string, unknown>) ?? {};
  const pubmedMode =
    typeof dashSettings.pubmed_query_mode === "string"
      ? dashSettings.pubmed_query_mode
      : "mesh_filtered";

  const args = ["-m", "pipeline"];
  if (fromDate) args.push("--from-date", fromDate);
  if (toDate) args.push("--to-date", toDate);
  args.push("--pubmed-query-mode", pubmedMode);

  const projectRoot = path.resolve(process.cwd(), "..");
  const pythonCmd =
    process.env.PIPELINE_PYTHON ??
    path.join(projectRoot, ".venv", "bin", "python");

  if (!fs.existsSync(pythonCmd)) {
    return {
      ok: false,
      error: `Python not found at ${pythonCmd}. Set PIPELINE_PYTHON.`,
    };
  }

  const logDir = path.join(projectRoot, "logs");
  if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
  const logFile = path.join(
    logDir,
    `pipeline-${new Date().toISOString().replace(/[:.]/g, "-")}.log`,
  );

  const out = fs.openSync(logFile, "a");
  const child = spawn(pythonCmd, args, {
    cwd: projectRoot,
    detached: true,
    stdio: ["ignore", out, out],
    env: Object.fromEntries(
      Object.entries(process.env).filter(([k]) => k !== "DATABASE_URL"),
    ) as NodeJS.ProcessEnv,
  });

  const spawnOk = await new Promise<boolean>((resolve) => {
    child.on("error", (err) => {
      fs.writeSync(out, `SPAWN ERROR: ${err.message}\n`);
      resolve(false);
    });
    setTimeout(() => resolve(true), 500);
  });

  child.unref();
  fs.closeSync(out);

  if (!spawnOk) {
    return { ok: false, error: "Pipeline process failed to start" };
  }

  const modeLabel = pubmedMode === "all" ? "Full" : "MeSH";
  return {
    ok: true,
    message: `Pipeline started (${fromDate || "2 days ago"} \u2192 ${toDate || "today"}, PubMed: ${modeLabel})`,
  };
}

export async function cancelPipeline(): Promise<
  { ok: true; message: string } | { ok: false; error: string }
> {
  // Use raw SQL to read pid (column may not be in Prisma client yet)
  const rows = await prisma.$queryRaw<
    { id: string; pid: number | null }[]
  >`SELECT id, pid FROM pipeline_runs WHERE finished_at IS NULL ORDER BY started_at DESC LIMIT 1`;

  if (rows.length === 0) {
    return { ok: false, error: "No running pipeline to cancel" };
  }

  const run = rows[0];

  // Try to kill the process
  if (run.pid) {
    try {
      process.kill(run.pid, "SIGTERM");
    } catch {
      // Process may have already exited — that's fine
    }
  }

  // Mark the run as finished/cancelled
  await prisma.$executeRaw`UPDATE pipeline_runs SET finished_at = NOW(), current_stage = 'cancelled' WHERE id = ${run.id}::uuid`;

  return { ok: true, message: "Pipeline cancelled" };
}

export async function togglePubmedQueryMode(): Promise<string> {
  const row = await prisma.pipelineSettings.findUnique({ where: { id: 1 } });
  const current = (row?.settings as Record<string, unknown>) ?? {};
  const oldMode =
    typeof current.pubmed_query_mode === "string"
      ? current.pubmed_query_mode
      : "mesh_filtered";
  const newMode = oldMode === "all" ? "mesh_filtered" : "all";

  await prisma.pipelineSettings.upsert({
    where: { id: 1 },
    update: { settings: { ...current, pubmed_query_mode: newMode } },
    create: { id: 1, settings: { pubmed_query_mode: newMode } },
  });

  return newMode;
}
