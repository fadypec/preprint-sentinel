import { apiRequireAdmin } from "@/lib/auth-guard";
import { getAlertSettings, testSlack, testEmail } from "@/lib/alerts";

export async function POST(request: Request) {
  const denied = await apiRequireAdmin();
  if (denied) return denied;

  try {
    const body = await request.json();
    const channel = body.channel as string;

    const settings = await getAlertSettings();

    let result: { ok: boolean; error?: string };

    if (channel === "slack") {
      result = await testSlack(settings.alert_slack_webhook);
    } else if (channel === "email") {
      result = await testEmail(settings.alert_email_recipients);
    } else {
      return Response.json(
        { error: "Invalid channel (use 'slack' or 'email')" },
        { status: 400 },
      );
    }

    return Response.json(result);
  } catch (err) {
    console.error("Alert test error:", err);
    return Response.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
