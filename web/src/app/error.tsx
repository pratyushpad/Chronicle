"use client";

export default function Error({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <span className="font-display text-5xl text-muted-foreground">Oops</span>
      <p className="mt-4 font-body text-lg text-muted-foreground">
        Something went wrong loading this page.
      </p>
      <button
        onClick={reset}
        className="mt-8 inline-flex min-h-[44px] items-center justify-center rounded-md border border-border px-6 font-body text-sm text-muted-foreground transition-colors hover:border-accent hover:text-accent touch-manipulation"
      >
        Try again
      </button>
    </main>
  );
}
