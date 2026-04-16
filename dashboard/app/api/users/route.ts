import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { apiRequireAdmin, csrfCheck } from "@/lib/auth-guard";

/**
 * GET /api/users — list all users (admin only)
 * PATCH /api/users — approve/reject a user (admin only)
 */

export async function GET() {
  const denied = await apiRequireAdmin();
  if (denied) return denied;

  const users = await prisma.user.findMany({
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      email: true,
      name: true,
      image: true,
      role: true,
      status: true,
      createdAt: true,
    },
  });

  return Response.json(users);
}

export async function PATCH(request: NextRequest) {
  const csrf = await csrfCheck(request);
  if (csrf) return csrf;
  const denied = await apiRequireAdmin();
  if (denied) return denied;

  const body = await request.json();
  const { userId, status } = body;

  if (!userId || !["approved", "rejected", "pending"].includes(status)) {
    return Response.json(
      { error: "userId and status (approved/rejected/pending) required" },
      { status: 400 },
    );
  }

  const user = await prisma.user.update({
    where: { id: userId },
    data: { status },
    select: { id: true, email: true, status: true },
  });

  return Response.json(user);
}
