"use client";

import { ErrorNotice } from "@/components/ErrorNotice";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <ErrorNotice error={error} reset={reset} />;
}
