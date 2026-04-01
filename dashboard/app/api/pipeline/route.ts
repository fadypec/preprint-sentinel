import { NextRequest } from "next/server";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";

/**
 * Derive pipeline status from the pipeline_runs table.
 * No sidecar needed.
 */
async function getDbStatus() {
  const runningRun = await prisma.pipelineRun.findFirst({
    where: { finishedAt: null },
    orderBy: { startedAt: "desc" },
  });
  const lastRun = runningRun
    ? null
    : await prisma.pipelineRun.findFirst({
        orderBy: { startedAt: "desc" },
      });

  return {
    running: !!runningRun,
    paused: false,
    runningRunId: runningRun?.id ?? null,
    lastRunAt: (runningRun?.startedAt ?? lastRun?.startedAt)?.toISOString() ?? null,
  };
}

export async function GET() {
  const status = await getDbStatus();
  return Response.json(status);
}

export async function POST(request: NextRequest) {
  // Check if already running
  const status = await getDbStatus();
  if (status.running) {
    return Response.json(
      { error: "Pipeline is already running" },
      { status: 409 },
    );
  }

  // Parse optional date range from request body
  let fromDate: string | undefined;
  let toDate: string | undefined;
  try {
    const body = await request.json();
    if (body.fromDate) fromDate = body.fromDate;
    if (body.toDate) toDate = body.toDate;
  } catch {
    // No body or invalid JSON — run with defaults
  }

  // Build CLI args
  const args = ["-m", "pipeline"];
  if (fromDate) args.push("--from-date", fromDate);
  if (toDate) args.push("--to-date", toDate);

  // Resolve the project root (dashboard is in <root>/dashboard)
  const projectRoot = path.resolve(process.cwd(), "..");

  // Find Python — prefer venv, fall back to system
  const pythonCmd =
    process.env.PIPELINE_PYTHON ??
    path.join(projectRoot, ".venv", "bin", "python");

  // Log file for debugging pipeline output
  const logDir = path.join(projectRoot, "logs");
  if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
  const logFile = path.join(
    logDir,
    `pipeline-${new Date().toISOString().replace(/[:.]/g, "-")}.log`,
  );

  try {
    const out = fs.openSync(logFile, "a");
    const child = spawn(pythonCmd, args, {
      cwd: projectRoot,
      detached: true,
      stdio: ["ignore", out, out],
      // Strip dashboard-specific DATABASE_URL so the pipeline loads its
      // own (postgresql+asyncpg://...) from the project-root .env file.
      env: Object.fromEntries(
        Object.entries(process.env).filter(
          ([k]) => k !== "DATABASE_URL",
        ),
      ) as NodeJS.ProcessEnv,
    });
    child.unref();
    fs.closeSync(out);

    return Response.json({
      started: true,
      pid: child.pid,
      logFile,
      fromDate: fromDate ?? "default (2 days ago)",
      toDate: toDate ?? "default (today)",
    });
  } catch (err) {
    return Response.json(
      {
        error: `Failed to start pipeline: ${err instanceof Error ? err.message : String(err)}`,
      },
      { status: 500 },
    );
  }
}
