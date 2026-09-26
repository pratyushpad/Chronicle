import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account && profile) {
        token.provider = account.provider;
        token.providerAccountId = account.providerAccountId;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.provider = typeof token.provider === "string" ? token.provider : undefined;
        session.user.providerAccountId =
          typeof token.providerAccountId === "string" ? token.providerAccountId : undefined;
      }
      return session;
    },
  },
  pages: {
    signIn: "/",
  },
});
