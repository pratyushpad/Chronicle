/**
 * Server-side fetch helper for authenticated FastAPI calls.
 * Signs an X-Internal-Auth token asserting the caller's email; FastAPI
 * verifies the HMAC signature and expiry (see api/app/internal_auth.py).
 * Only call from Next.js API routes (server-side); never from client components.
 */

import { signInternalToken } from "./internal-token";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch(
  path: string,
  userEmail: string,
  options: RequestInit = {}
): Promise<Response> {
  return fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Auth": signInternalToken(userEmail),
      ...(options.headers ?? {}),
    },
    cache: "no-store",
  });
}
