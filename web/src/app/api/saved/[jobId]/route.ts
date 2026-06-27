import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function POST(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
  const { jobId } = await params;
  const res = await apiFetch(`/users/me/saved/${jobId}`, session.user.email, { method: "POST" });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
  const { jobId } = await params;
  const res = await apiFetch(`/users/me/saved/${jobId}`, session.user.email, { method: "DELETE" });
  return NextResponse.json(await res.json());
}
