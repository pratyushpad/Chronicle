import { auth } from "@/auth";
import { NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
  }

  const body = await req.text();
  const res = await apiFetch("/interactions/batch", session.user.email, {
    method: "POST",
    body,
  });

  return new NextResponse(null, { status: res.ok ? 204 : res.status });
}
