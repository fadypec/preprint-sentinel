"use server";

import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guard";

/**
 * All server actions in this file require admin privileges.
 * They control pipeline execution and modify paper state.
 */

/**
 * Trigger a pipeline run. Uses Railway API when deployed (RAILWAY_API_TOKEN
 * and RAILWAY_PIPELINE_SERVICE_ID set), falls back to local subprocess spawn
 * for development.
 */
export async function triggerPipeline(
  fromDate: string,
  toDate: string,
  includeBacklog: boolean = true,
): Promise<{ ok: true; message: string } | { ok: false; error: string }> {
  await requireAdmin();

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

  // --- Railway deployment: trigger via Railway API ---
  const railwayToken = process.env.RAILWAY_API_TOKEN;
  const railwayServiceId = process.env.RAILWAY_PIPELINE_SERVICE_ID;

  if (railwayToken && railwayServiceId) {
    return triggerViaRailway(railwayToken, railwayServiceId);
  }

  // --- Local development: spawn subprocess ---
  return triggerViaSubprocess(fromDate, toDate, pubmedMode, includeBacklog);
}

/** Trigger pipeline by restarting the Railway pipeline service. */
async function triggerViaRailway(
  token: string,
  serviceId: string,
): Promise<{ ok: true; message: string } | { ok: false; error: string }> {
  try {
    // Step 1: Get the latest deployment for this service
    const query = `
      query {
        deployments(
          input: { serviceId: "${serviceId}" }
          first: 1
        ) {
          edges {
            node { id status }
          }
        }
      }
    `;

    const resp = await fetch("https://backboard.railway.com/graphql/v2", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ query }),
    });

    if (!resp.ok) {
      return { ok: false, error: `Railway API error: ${resp.status}` };
    }

    const data = await resp.json();
    const edges = data?.data?.deployments?.edges;
    if (!edges || edges.length === 0) {
      return { ok: false, error: "No deployments found for pipeline service" };
    }

    const deploymentId = edges[0].node.id;

    // Step 2: Restart the deployment
    const restartQuery = `
      mutation {
        deploymentRestart(id: "${deploymentId}")
      }
    `;

    const restartResp = await fetch(
      "https://backboard.railway.com/graphql/v2",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query: restartQuery }),
      },
    );

    if (!restartResp.ok) {
      return { ok: false, error: `Railway restart failed: ${restartResp.status}` };
    }

    return { ok: true, message: "Pipeline triggered via Railway (restarting service)" };
  } catch (err) {
    return {
      ok: false,
      error: `Railway API error: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

/** Trigger pipeline by spawning a local Python subprocess (dev mode). */
function triggerViaSubprocess(
  fromDate: string,
  toDate: string,
  pubmedMode: string,
  includeBacklog: boolean,
): { ok: true; message: string } | { ok: false; error: string } {
  const args = ["-m", "pipeline"];
  if (fromDate) args.push("--from-date", fromDate);
  if (toDate) args.push("--to-date", toDate);
  args.push("--pubmed-query-mode", pubmedMode);
  if (!includeBacklog) args.push("--skip-backlog");

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

  const spawnOk = child.pid !== undefined;
  child.unref();
  fs.closeSync(out);

  if (!spawnOk) {
    return { ok: false, error: "Pipeline process failed to start" };
  }

  const modeLabel = pubmedMode === "all" ? "Full" : "MeSH";
  const backlogLabel = includeBacklog ? "" : ", no backlog";
  return {
    ok: true,
    message: `Pipeline started (${fromDate || "2 days ago"} \u2192 ${toDate || "today"}, PubMed: ${modeLabel}${backlogLabel})`,
  };
}

export async function cancelPipeline(): Promise<
  { ok: true; message: string } | { ok: false; error: string }
> {
  await requireAdmin();

  // Use raw SQL to read pid (column may not be in Prisma client yet)
  const rows = await prisma.$queryRaw<
    { id: string; pid: number | null }[]
  >`SELECT id, pid FROM pipeline_runs WHERE finished_at IS NULL ORDER BY started_at DESC LIMIT 1`;

  if (rows.length === 0) {
    return { ok: false, error: "No running pipeline to cancel" };
  }

  const run = rows[0];

  // Try to kill the process (only works locally)
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

export async function clearRunHistory(): Promise<
  { ok: true; message: string } | { ok: false; error: string }
> {
  await requireAdmin();

  // Don't allow clearing while a run is in progress
  const running = await prisma.pipelineRun.findFirst({
    where: { finishedAt: null },
  });
  if (running) {
    return { ok: false, error: "Cannot clear history while a pipeline is running" };
  }

  const { count } = await prisma.pipelineRun.deleteMany({});
  return { ok: true, message: `Cleared ${count} run${count !== 1 ? "s" : ""}` };
}

export async function reprocessErrors(): Promise<
  { ok: true; message: string } | { ok: false; error: string }
> {
  await requireAdmin();

  try {
    // Reset papers with errors back to their previous stage so the
    // next pipeline run (with backlog) will reprocess them.
    // Papers at methods_analysed with errors → reset to fulltext_retrieved
    const methodsReset = await prisma.$executeRaw`
      UPDATE papers
      SET pipeline_stage = 'fulltext_retrieved',
          needs_manual_review = false,
          stage2_result = NULL,
          risk_tier = NULL,
          aggregate_score = NULL,
          recommended_action = NULL
      WHERE pipeline_stage = 'methods_analysed'
        AND (stage2_result::text LIKE '%_error%' OR needs_manual_review = true)
        AND is_duplicate_of IS NULL
    `;

    // Papers at adjudicated with errors → reset to methods_analysed
    const adjReset = await prisma.$executeRaw`
      UPDATE papers
      SET pipeline_stage = 'methods_analysed',
          needs_manual_review = false,
          stage3_result = NULL
      WHERE pipeline_stage = 'adjudicated'
        AND (stage3_result::text LIKE '%_error%' OR needs_manual_review = true)
        AND is_duplicate_of IS NULL
    `;

    const total = Number(methodsReset) + Number(adjReset);
    return {
      ok: true,
      message: `Reset ${total} papers for reprocessing (${methodsReset} methods, ${adjReset} adjudication). Run pipeline with backlog to reprocess.`,
    };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Failed to reset papers",
    };
  }
}

export async function togglePubmedQueryMode(): Promise<string> {
  await requireAdmin();

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
