import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json([], { status: 401 });
  const res = await apiFetch("/users/me/applications", session.user.email);
  if (!res.ok) return NextResponse.json([]);
  return NextResponse.json(await res.json());
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
  const body = await req.json();
  const res = await apiFetch("/users/me/applications", session.user.email, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
