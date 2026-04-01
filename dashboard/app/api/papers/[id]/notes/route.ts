import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma } from "@prisma/client";
import { apiRequireAuth } from "@/lib/auth-guard";

type RouteParams = { params: Promise<{ id: string }> };

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const denied = await apiRequireAuth();
  if (denied) return denied;
  try {
    const { id } = await params;
    const { notes } = await request.json();
    if (notes !== null && typeof notes !== "string") {
      return Response.json({ error: "notes must be a string or null" }, { status: 400 });
    }
    const paper = await prisma.paper.update({
      where: { id },
      data: { analystNotes: notes },
    });
    return Response.json({ success: true, analystNotes: paper.analystNotes });
  } catch (err) {
    console.error("Notes PUT error:", err);
    if (err instanceof Prisma.PrismaClientKnownRequestError && err.code === "P2025") {
      return Response.json({ error: "Not found" }, { status: 404 });
    }
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
