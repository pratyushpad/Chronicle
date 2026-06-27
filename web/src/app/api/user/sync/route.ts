import { auth } from "@/auth";
import { NextResponse } from "next/server";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

export async function POST() {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
  }

  const { email, name, image } = session.user;
  const user = session.user as any;

  const res = await fetch(`${API}/users/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      name: name ?? null,
      avatar_url: image ?? null,
      provider: user.provider ?? "google",
      provider_id: user.providerAccountId ?? email,
    }),
    cache: "no-store",
  });

  if (!res.ok) {
    return NextResponse.json({ error: "Sync failed" }, { status: 500 });
  }

  return NextResponse.json(await res.json());
}

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json(null);
  }

  const res = await fetch(`${API}/users/me`, {
    headers: { "X-User-Email": session.user.email },
    cache: "no-store",
  });

  if (!res.ok) return NextResponse.json(null);
  return NextResponse.json(await res.json());
}
