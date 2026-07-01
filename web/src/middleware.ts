import { auth } from "@/auth";
import { NextResponse } from "next/server";

const PROTECTED = ["/tracker", "/saved", "/for-you", "/onboarding", "/settings"];

export default auth((req) => {
  const isProtected = PROTECTED.some((p) => req.nextUrl.pathname.startsWith(p));
  if (isProtected && !req.auth) {
    const url = req.nextUrl.clone();
    url.pathname = "/";
    url.searchParams.set("signin", "required");
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
