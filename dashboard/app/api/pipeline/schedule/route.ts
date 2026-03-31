import { NextRequest } from "next/server";
import { updatePipelineSchedule } from "@/lib/pipeline-api";

export async function PUT(request: NextRequest) {
  // Parse JSON body
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { error: "Invalid request body" },
      { status: 400 }
    );
  }

  // Validate input
  if (typeof body !== "object" || body === null) {
    return Response.json(
      { error: "Invalid request body" },
      { status: 400 }
    );
  }

  const { hour, minute } = body as Record<string, unknown>;

  // Validate hour
  if (
    typeof hour !== "number" ||
    !Number.isInteger(hour) ||
    hour < 0 ||
    hour > 23
  ) {
    return Response.json(
      { error: "hour must be an integer between 0 and 23" },
      { status: 400 }
    );
  }

  // Validate minute
  const minuteValue = minute ?? 0;
  if (
    typeof minuteValue !== "number" ||
    !Number.isInteger(minuteValue) ||
    minuteValue < 0 ||
    minuteValue > 59
  ) {
    return Response.json(
      { error: "minute must be an integer between 0 and 59" },
      { status: 400 }
    );
  }

  // Call pipeline sidecar
  try {
    const result = await updatePipelineSchedule(hour, minuteValue);
    return Response.json(result);
  } catch {
    return Response.json(
      { error: "Pipeline unreachable" },
      { status: 502 }
    );
  }
}
