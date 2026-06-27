import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <span className="font-display text-7xl text-accent">404</span>
      <p className="mt-4 font-body text-lg text-muted-foreground">
        This page doesn&apos;t exist.
      </p>
      <Link
        href="/jobs"
        className="mt-8 inline-flex min-h-[44px] items-center justify-center font-body text-sm text-muted-foreground transition-colors hover:text-accent hover:underline underline-offset-4"
      >
        ← All Roles
      </Link>
    </main>
  );
}
