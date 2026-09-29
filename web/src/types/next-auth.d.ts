import type { DefaultSession } from "next-auth";

// The OAuth account id the session carries (set in src/auth.ts), typed so no caller
// needs an `as any` cast to read it.
declare module "next-auth" {
  interface Session {
    user: {
      provider?: string;
      providerAccountId?: string;
    } & DefaultSession["user"];
  }
}
