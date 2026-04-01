import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { apiRequireAuth, apiRequireAdmin } from "@/lib/auth-guard";

/** Keys that contain secrets — redacted on read, preserved on write. */
const SECRET_KEYS = ["alert_slack_webhook"];
const REDACTED = "••••••••";

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
  const adminDenied = await apiRequireAdmin();
  if (adminDenied) return adminDenied;
  try {
    const incoming = await request.json();

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
