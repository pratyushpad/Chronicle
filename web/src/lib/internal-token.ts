/**
 * Signs short-lived internal auth tokens for FastAPI calls.
 * Mirror of api/app/internal_auth.py — keep the two in sync.
 * Server-side only (uses node:crypto and a secret env var).
 */

import { createHmac } from "crypto";

const TOKEN_VERSION = "v1";
const TOKEN_TTL_SECONDS = 300;

export function signInternalToken(email: string, nowSeconds?: number): string {
  const secret = process.env.INTERNAL_API_SECRET;
  if (!secret) {
    throw new Error("INTERNAL_API_SECRET is not set");
  }
  if (!email) {
    throw new Error("email is required");
  }
  const iat = nowSeconds ?? Math.floor(Date.now() / 1000);
  const payload = JSON.stringify({ email, iat, exp: iat + TOKEN_TTL_SECONDS });
  const payloadB64 = Buffer.from(payload, "utf-8").toString("base64url");
  const signedPart = `${TOKEN_VERSION}.${payloadB64}`;
  const sig = createHmac("sha256", secret).update(signedPart, "ascii").digest("hex");
  return `${signedPart}.${sig}`;
}
