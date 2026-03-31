import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";

type RouteParams = { params: Promise<{ id: string }> };

export async function PUT(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;
    const { notes } = await request.json();
    const paper = await prisma.paper.update({
      where: { id },
      data: { analystNotes: notes },
    });
    return Response.json({ success: true, analystNotes: paper.analystNotes });
  } catch (err) {
    console.error("Notes PUT error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
