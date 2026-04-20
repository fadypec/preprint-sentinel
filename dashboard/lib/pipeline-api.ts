const PIPELINE_URL = process.env.PIPELINE_API_URL ?? "http://localhost:8000";

if (!process.env.PIPELINE_API_SECRET && process.env.NODE_ENV === "production") {
  console.error(
    "[SECURITY] PIPELINE_API_SECRET is not set in production. " +
    "Pipeline API calls will be rejected.",
  );
  throw new Error("PIPELINE_API_SECRET must be set in production");
}

const PIPELINE_SECRET = process.env.PIPELINE_API_SECRET ?? "";

async function pipelineFetch(path: string, options: RequestInit = {}) {
  const res = await fetch(`${PIPELINE_URL}${path}`, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${PIPELINE_SECRET}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Pipeline API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getPipelineStatus() {
  return pipelineFetch("/status");
}

export async function triggerPipelineRun() {
  return pipelineFetch("/run", { method: "POST" });
}

export async function pausePipeline() {
  return pipelineFetch("/pause", { method: "POST" });
}

export async function resumePipeline() {
  return pipelineFetch("/resume", { method: "POST" });
}

export async function updatePipelineSchedule(hour: number, minute: number) {
  return pipelineFetch("/schedule", {
    method: "PUT",
    body: JSON.stringify({ hour, minute }),
  });
}
