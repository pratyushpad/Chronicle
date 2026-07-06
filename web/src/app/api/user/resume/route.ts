import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });

  // Forward the multipart body untouched — the boundary lives in the header.
  const body = await req.arrayBuffer();
  const res = await apiFetch("/users/me/resume", session.user.email, {
    method: "POST",
    body,
    headers: { "Content-Type": req.headers.get("content-type") ?? "" },
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}

export async function DELETE() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });

  const res = await apiFetch("/users/me/resume", session.user.email, { method: "DELETE" });
  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}
