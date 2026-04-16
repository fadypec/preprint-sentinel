import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";

export const { handlers, signIn, signOut, auth } = NextAuth({
  // Trust the host header — required when deployed behind a reverse proxy
  // (Railway, Vercel, Docker, etc.). Without this, NextAuth rejects
  // requests because the forwarded host doesn't match the server's hostname.
  trustHost: true,
  adapter: PrismaAdapter(prisma),
  providers: [GitHub, Google],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async session({ session, user }) {
      // Fetch role and approval status from our users table
      const dbUser = await prisma.user.findUnique({
        where: { email: user.email! },
        select: { role: true, id: true, status: true },
      });
      if (dbUser) {
        session.user.role = dbUser.role;
        session.user.id = dbUser.id;
        session.user.status = dbUser.status;
      }
      return session;
    },
  },
});
