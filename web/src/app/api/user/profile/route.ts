import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });
  const res = await apiFetch("/users/me/profile", session.user.email);
  if (!res.ok) return NextResponse.json(null);
  return NextResponse.json(await res.json());
}

export async function PUT(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });
  const body = await req.json();
  const res = await apiFetch("/users/me/profile", session.user.email, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  return NextResponse.json(await res.json());
}
