import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
    const row = await prisma.pipelineSettings.findFirst({ where: { id: 1 } });
    return Response.json(row?.settings ?? {});
  } catch (err) {
    console.error("Settings GET error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const settings = await request.json();
    const row = await prisma.pipelineSettings.upsert({
      where: { id: 1 },
      create: { id: 1, settings },
      update: { settings },
    });
    return Response.json(row.settings);
  } catch (err) {
    console.error("Settings PUT error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
