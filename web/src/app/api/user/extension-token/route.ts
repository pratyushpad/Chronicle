import { auth } from "@/auth";
import { NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

// GET → { connected: boolean }
export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });
  const res = await apiFetch("/users/me/extension-token", session.user.email);
  if (!res.ok) return NextResponse.json({ connected: false });
  return NextResponse.json(await res.json());
}

// POST → { token } (plaintext, shown once)
export async function POST() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });
  const res = await apiFetch("/users/me/extension-token", session.user.email, {
    method: "POST",
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  return NextResponse.json(await res.json());
}

// DELETE → revoke
export async function DELETE() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });
  const res = await apiFetch("/users/me/extension-token", session.user.email, {
    method: "DELETE",
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  return NextResponse.json(await res.json());
}
