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

  const args = ["-m", "pipeline"];
  if (fromDate) args.push("--from-date", fromDate);
  if (toDate) args.push("--to-date", toDate);

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

  return {
    ok: true,
    message: `Pipeline started (${fromDate || "2 days ago"} \u2192 ${toDate || "today"})`,
  };
}
