import { prisma } from "@/lib/prisma";
import type { Paper, RiskTier } from "@prisma/client";
import nodemailer from "nodemailer";

const TIER_ORDER: Record<string, number> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
};

export type AlertSettings = {
  alert_email_recipients: string;
  alert_slack_webhook: string;
  alert_digest_frequency: string;
  alert_tier_threshold: string;
};

export async function getAlertSettings(): Promise<AlertSettings> {
  const row = await prisma.pipelineSettings.findUnique({ where: { id: 1 } });
  const settings = (row?.settings ?? {}) as Record<string, unknown>;
  return {
    alert_email_recipients: (settings.alert_email_recipients as string) || "",
    alert_slack_webhook: (settings.alert_slack_webhook as string) || "",
    alert_digest_frequency:
      (settings.alert_digest_frequency as string) || "daily",
    alert_tier_threshold:
      (settings.alert_tier_threshold as string) || "high",
  };
}

/** Query papers matching the alert tier threshold within a time window. */
export async function getDigestPapers(
  threshold: string,
  frequency: string,
): Promise<Paper[]> {
  const cutoff = new Date();
  if (frequency === "weekly") {
    cutoff.setDate(cutoff.getDate() - 7);
  } else {
    cutoff.setDate(cutoff.getDate() - 1);
  }

  const minTier = TIER_ORDER[threshold] ?? TIER_ORDER.high;
  const matchingTiers = Object.entries(TIER_ORDER)
    .filter(([, v]) => v >= minTier)
    .map(([k]) => k) as RiskTier[];

  return prisma.paper.findMany({
    where: {
      riskTier: { in: matchingTiers },
      coarseFilterPassed: true,
      isDuplicateOf: null,
      updatedAt: { gte: cutoff },
    },
    orderBy: [
      { riskTier: { sort: "desc", nulls: "last" } },
      { aggregateScore: { sort: "desc", nulls: "last" } },
    ],
  });
}

// ---------------------------------------------------------------------------
// Slack
// ---------------------------------------------------------------------------

const TIER_EMOJI: Record<string, string> = {
  critical: ":red_circle:",
  high: ":orange_circle:",
  medium: ":large_yellow_circle:",
  low: ":white_circle:",
};

export async function sendSlack(
  webhookUrl: string,
  papers: Paper[],
  dashboardUrl: string,
): Promise<{ ok: boolean; error?: string }> {
  if (!webhookUrl) return { ok: false, error: "No Slack webhook configured" };

  const tierCounts: Record<string, number> = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };
  for (const p of papers) {
    if (p.riskTier && p.riskTier in tierCounts) tierCounts[p.riskTier]++;
  }

  const summary = Object.entries(tierCounts)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => `*${k[0].toUpperCase() + k.slice(1)}:* ${v}`)
    .join(" | ");

  const blocks: unknown[] = [
    {
      type: "header",
      text: {
        type: "plain_text",
        text: `DURC Digest: ${papers.length} paper${papers.length !== 1 ? "s" : ""} flagged`,
      },
    },
    { type: "section", text: { type: "mrkdwn", text: summary || "No papers" } },
    { type: "divider" },
  ];

  for (const p of papers.slice(0, 15)) {
    const emoji = TIER_EMOJI[p.riskTier ?? "low"] ?? ":white_circle:";
    const score =
      p.aggregateScore != null ? `${p.aggregateScore}/18` : "N/A";
    const link = `${dashboardUrl}/paper/${p.id}`;
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `${emoji} *${p.title.slice(0, 120)}*\nScore: ${score} | ${p.sourceServer} | <${link}|View>`,
      },
    });
  }

  if (papers.length > 15) {
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `_...and ${papers.length - 15} more. <${dashboardUrl}|View all>_`,
      },
    });
  }

  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });

  if (!response.ok) {
    return { ok: false, error: `Slack returned ${response.status}` };
  }
  return { ok: true };
}

export async function testSlack(
  webhookUrl: string,
): Promise<{ ok: boolean; error?: string }> {
  if (!webhookUrl) return { ok: false, error: "No Slack webhook configured" };
  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: "Preprint Sentinel Dashboard: Slack integration test successful.",
    }),
  });
  if (!response.ok) {
    return { ok: false, error: `Slack returned ${response.status}` };
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Email
// ---------------------------------------------------------------------------

function getMailTransport() {
  const host = process.env.SMTP_HOST;
  if (!host) return null;

  return nodemailer.createTransport({
    host,
    port: parseInt(process.env.SMTP_PORT || "587", 10),
    secure: process.env.SMTP_SECURE === "true",
    ...(process.env.SMTP_USER
      ? { auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } }
      : {}),
  });
}

function buildDigestHtml(papers: Paper[], dashboardUrl: string): string {
  const tierColors: Record<string, string> = {
    critical: "#dc2626",
    high: "#ea580c",
    medium: "#ca8a04",
    low: "#16a34a",
  };

  const rows = papers
    .map((p) => {
      const color = tierColors[p.riskTier ?? "low"] ?? "#6b7280";
      const score =
        p.aggregateScore != null ? `${p.aggregateScore}/18` : "N/A";
      return `<tr>
        <td style="padding:8px;border-bottom:1px solid #e5e7eb">
          <span style="display:inline-block;padding:2px 8px;border-radius:4px;background:${color};color:#fff;font-size:12px">${p.riskTier ?? "unknown"}</span>
        </td>
        <td style="padding:8px;border-bottom:1px solid #e5e7eb">
          <a href="${dashboardUrl}/paper/${p.id}" style="color:#2563eb;text-decoration:none">${escapeHtml(p.title.slice(0, 100))}</a>
        </td>
        <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center">${score}</td>
        <td style="padding:8px;border-bottom:1px solid #e5e7eb">${p.sourceServer}</td>
      </tr>`;
    })
    .join("\n");

  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;background:#f8fafc">
  <div style="max-width:700px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">
    <div style="background:#1e293b;padding:20px 24px">
      <h1 style="margin:0;color:#fff;font-size:18px">Preprint Sentinel Digest</h1>
      <p style="margin:4px 0 0;color:#94a3b8;font-size:14px">${papers.length} paper${papers.length !== 1 ? "s" : ""} flagged &middot; ${new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</p>
    </div>
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="background:#f1f5f9">
          <th style="padding:8px;text-align:left;font-size:12px;color:#64748b">Tier</th>
          <th style="padding:8px;text-align:left;font-size:12px;color:#64748b">Title</th>
          <th style="padding:8px;text-align:center;font-size:12px;color:#64748b">Score</th>
          <th style="padding:8px;text-align:left;font-size:12px;color:#64748b">Source</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
    <div style="padding:16px 24px;text-align:center">
      <a href="${dashboardUrl}" style="display:inline-block;padding:8px 20px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-size:14px">View Dashboard</a>
    </div>
  </div>
</body>
</html>`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export async function sendEmail(
  recipients: string,
  papers: Paper[],
  dashboardUrl: string,
): Promise<{ ok: boolean; error?: string }> {
  if (!recipients)
    return { ok: false, error: "No email recipients configured" };

  const transport = getMailTransport();
  if (!transport)
    return { ok: false, error: "SMTP not configured (set SMTP_HOST env var)" };

  const html = buildDigestHtml(papers, dashboardUrl);
  const from = process.env.SMTP_FROM || "alerts@durc-triage.local";

  try {
    await transport.sendMail({
      from,
      to: recipients,
      subject: `DURC Digest: ${papers.length} paper${papers.length !== 1 ? "s" : ""} flagged`,
      html,
    });
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: `Email send failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

export async function testEmail(
  recipients: string,
): Promise<{ ok: boolean; error?: string }> {
  if (!recipients)
    return { ok: false, error: "No email recipients configured" };

  const transport = getMailTransport();
  if (!transport)
    return { ok: false, error: "SMTP not configured (set SMTP_HOST env var)" };

  const from = process.env.SMTP_FROM || "alerts@durc-triage.local";

  try {
    await transport.sendMail({
      from,
      to: recipients,
      subject: "Preprint Sentinel Dashboard: Email test",
      text: "This is a test email from the Preprint Sentinel Dashboard. If you received this, email alerts are configured correctly.",
    });
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: `Email test failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
