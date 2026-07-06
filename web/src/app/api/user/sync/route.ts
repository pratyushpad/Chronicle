import { auth } from "@/auth";
import { NextResponse } from "next/server";
import { apiFetch } from "@/lib/server-api";

export async function POST() {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthenticated" }, { status: 401 });
  }

  const { email, name, image } = session.user;
  const user = session.user as any;

  const res = await apiFetch("/users/sync", email, {
    method: "POST",
    body: JSON.stringify({
      email,
      name: name ?? null,
      avatar_url: image ?? null,
      provider: user.provider ?? "google",
      provider_id: user.providerAccountId ?? email,
    }),
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

  const res = await apiFetch("/users/me", session.user.email);

  if (!res.ok) return NextResponse.json(null);
  return NextResponse.json(await res.json());
}
