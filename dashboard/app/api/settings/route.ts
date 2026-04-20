import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { apiRequireAuth, apiRequireAdmin, csrfCheck } from "@/lib/auth-guard";

/** Keys that contain secrets — redacted on read, preserved on write. */
const SECRET_KEYS = ["alert_slack_webhook"];
const REDACTED = "••••••••";

/** Allowed settings keys and their expected types. Rejects unknown keys. */
const SETTINGS_SCHEMA: Record<string, "string" | "number" | "boolean"> = {
  stage1_model: "string",
  stage2_model: "string",
  stage3_model: "string",
  coarse_filter_threshold: "number",
  adjudication_min_tier: "string",
  pubmed_query_mode: "string",
  process_backlog: "boolean",
  alert_slack_webhook: "string",
  alert_email_recipients: "string",
  digest_frequency: "string",
  alert_tier_threshold: "string",
};

function redactSecrets(settings: Record<string, unknown>): Record<string, unknown> {
  const result = { ...settings };
  for (const key of SECRET_KEYS) {
    if (result[key] && typeof result[key] === "string" && (result[key] as string).length > 0) {
      result[key] = REDACTED;
    }
  }
  return result;
}

export async function GET() {
  const denied = await apiRequireAuth();
  if (denied) return denied;
  try {
    const row = await prisma.pipelineSettings.findUnique({ where: { id: 1 } });
    const settings = (row?.settings ?? {}) as Record<string, unknown>;
    return Response.json(redactSecrets(settings));
  } catch (err) {
    console.error("Settings GET error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  const csrf = await csrfCheck(request);
  if (csrf) return csrf;
  const adminDenied = await apiRequireAdmin();
  if (adminDenied) return adminDenied;
  try {
    const incoming = await request.json();

    // Validate: reject unknown keys and wrong types
    if (typeof incoming !== "object" || incoming === null || Array.isArray(incoming)) {
      return Response.json({ error: "Body must be a JSON object" }, { status: 400 });
    }
    const unknownKeys = Object.keys(incoming).filter((k) => !(k in SETTINGS_SCHEMA));
    if (unknownKeys.length > 0) {
      return Response.json(
        { error: `Unknown settings keys: ${unknownKeys.join(", ")}` },
        { status: 400 },
      );
    }
    for (const [key, expectedType] of Object.entries(SETTINGS_SCHEMA)) {
      if (key in incoming && incoming[key] !== null && incoming[key] !== undefined) {
        if (typeof incoming[key] !== expectedType) {
          return Response.json(
            { error: `Setting "${key}" must be ${expectedType}, got ${typeof incoming[key]}` },
            { status: 400 },
          );
        }
      }
    }

    // Merge with existing settings so redacted values aren't overwritten
    const existing = await prisma.pipelineSettings.findUnique({ where: { id: 1 } });
    const current = (existing?.settings ?? {}) as Record<string, unknown>;
    const merged = { ...current, ...incoming };

    // If client sent the redacted placeholder, keep the original value
    for (const key of SECRET_KEYS) {
      if (merged[key] === REDACTED) {
        merged[key] = current[key] ?? "";
      }
    }

    const row = await prisma.pipelineSettings.upsert({
      where: { id: 1 },
      create: { id: 1, settings: merged },
      update: { settings: merged },
    });
    return Response.json(redactSecrets(row.settings as Record<string, unknown>));
  } catch (err) {
    console.error("Settings PUT error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
