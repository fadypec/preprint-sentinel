import { apiRequireAdmin, csrfCheck } from "@/lib/auth-guard";
import {
  getAlertSettings,
  getDigestPapers,
  sendSlack,
  sendEmail,
} from "@/lib/alerts";

export async function POST(request: Request) {
  const csrf = await csrfCheck(request);
  if (csrf) return csrf;
  const denied = await apiRequireAdmin();
  if (denied) return denied;

  try {
    const settings = await getAlertSettings();
    const papers = await getDigestPapers(
      settings.alert_tier_threshold,
      settings.alert_digest_frequency,
    );

    if (papers.length === 0) {
      return Response.json({
        sent: false,
        message: "No papers match threshold in this period",
        papers: 0,
      });
    }

    const dashboardUrl =
      process.env.NEXT_PUBLIC_BASE_URL ||
      request.headers.get("origin") ||
      "http://localhost:3000";

    const results: Record<string, { ok: boolean; error?: string }> = {};

    if (settings.alert_slack_webhook) {
      results.slack = await sendSlack(
        settings.alert_slack_webhook,
        papers,
        dashboardUrl,
      );
    }

    if (settings.alert_email_recipients) {
      results.email = await sendEmail(
        settings.alert_email_recipients,
        papers,
        dashboardUrl,
      );
    }

    return Response.json({ sent: true, papers: papers.length, results });
  } catch (err) {
    console.error("Digest API error:", err);
    return Response.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
