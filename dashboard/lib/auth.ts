import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";

export const { handlers, signIn, signOut, auth } = NextAuth({
  adapter: PrismaAdapter(prisma),
  providers: [GitHub, Google],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async session({ session, user }) {
      // Fetch role from our users table
      const dbUser = await prisma.user.findUnique({
        where: { email: user.email! },
        select: { role: true, id: true },
      });
      if (dbUser) {
        session.user.role = dbUser.role;
        session.user.id = dbUser.id;
      }
      return session;
    },
  },
});
