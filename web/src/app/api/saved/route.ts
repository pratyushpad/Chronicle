import { auth } from "@/auth";
import { NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json([], { status: 401 });
  const res = await apiFetch("/users/me/saved", session.user.email);
  if (!res.ok) return NextResponse.json([]);
  return NextResponse.json(await res.json());
}
