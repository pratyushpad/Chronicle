"use client";

import { isApiUnavailable } from "@/lib/api-errors";

const REPO = "https://github.com/pratyushpad/Chronicle";

const button =
  "mt-8 inline-flex min-h-[44px] items-center justify-center rounded-md border border-border px-6 font-sans text-sm text-muted-foreground transition-colors hover:border-accent hover:text-accent touch-manipulation";

/** The route error page. A 503 from the API (database suspended or refreshing) gets a calm
 *  notice; every other error keeps the generic page. */
export function ErrorNotice({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  if (isApiUnavailable(error)) {
    return (
      <main className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
        <h1 className="font-display text-4xl text-foreground">Live job data is refreshing</h1>
        <p className="mt-4 max-w-prose font-sans text-lg text-muted-foreground">
          Roles will be back shortly. The code, evals and screenshots are on{" "}
          <a
            href={REPO}
            className="underline underline-offset-4 transition-colors hover:text-accent"
          >
            GitHub
          </a>
          .
        </p>
        <button onClick={reset} className={button}>
          Try again
        </button>
      </main>
    );
  }
  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <span className="font-display text-5xl text-muted-foreground">Oops</span>
      <p className="mt-4 font-sans text-lg text-muted-foreground">
        Something went wrong loading this page.
      </p>
      <button onClick={reset} className={button}>
        Try again
      </button>
    </main>
  );
}
