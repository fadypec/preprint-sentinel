import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { ReviewStatus } from "@prisma/client";

type RouteParams = { params: Promise<{ id: string }> };

const validStatuses = new Set(Object.values(ReviewStatus));

export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;
    const paper = await prisma.paper.findUnique({
      where: { id },
      include: {
        assessmentLogs: { orderBy: { createdAt: "desc" } },
      },
    });
    if (!paper) {
      return Response.json({ error: "Not found" }, { status: 404 });
    }
    return Response.json(paper);
  } catch (err) {
    console.error("Paper GET error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;
    const body = await request.json();

    const data: Record<string, unknown> = {};
    if (body.reviewStatus) {
      if (!validStatuses.has(body.reviewStatus)) {
        return Response.json(
          { error: `Invalid reviewStatus. Must be one of: ${[...validStatuses].join(", ")}` },
          { status: 400 },
        );
      }
      data.reviewStatus = body.reviewStatus;
    }

    if (Object.keys(data).length === 0) {
      return Response.json({ error: "No valid fields to update" }, { status: 400 });
    }

    const paper = await prisma.paper.update({
      where: { id },
      data,
    });
    return Response.json(paper);
  } catch (err) {
    console.error("Paper PATCH error:", err);
    return Response.json({ error: "Internal server error" }, { status: 500 });
  }
}
