/**
 * Server-side fetch helper for authenticated FastAPI calls.
 * Passes X-User-Email header so FastAPI can identify the caller.
 * Only call from Next.js API routes (server-side); never from client components.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

export async function apiFetch(
  path: string,
  userEmail: string,
  options: RequestInit = {}
): Promise<Response> {
  return fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-User-Email": userEmail,
      ...(options.headers ?? {}),
    },
    cache: "no-store",
  });
}
