import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json([], { status: 401 });
  const res = await apiFetch("/users/me/notifications", session.user.email);
  if (!res.ok) return NextResponse.json([]);
  return NextResponse.json(await res.json());
}

export async function PUT(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json(null, { status: 401 });
  const { id } = await req.json();
  const path = id ? `/users/me/notifications/${id}/read` : "/users/me/notifications/read-all";
  const res = await apiFetch(path, session.user.email, { method: "PUT" });
  return NextResponse.json(await res.json());
}
