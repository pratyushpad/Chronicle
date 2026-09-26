import { JobListSkeleton } from "@/components/JobCardSkeleton";

// Route-level loading states for the list routes (app/jobs/(feed), app/companies/(list)).
// Shapes mirror the pages they stand in for, so content doesn't jump when it arrives.
// The [id] routes deliberately have none: a loading boundary makes a route stream, and a
// streamed response has already sent 200 by the time notFound() runs (a soft 404).
// The route groups keep these boundaries off the [id] pages below them.

function Bar({ className }: { className: string }) {
  return <div className={`animate-shimmer ${className}`} />;
}

export function FeedSkeleton() {
  return (
    <main id="main" aria-busy="true" className="mx-auto max-w-6xl px-6 py-12 md:px-8 lg:px-12">
      <Bar className="mx-auto mb-6 h-3 w-32" />
      <Bar className="h-11 w-full" />
      <JobListSkeleton count={5} />
    </main>
  );
}

export function CompaniesSkeleton() {
  return (
    <main id="main" aria-busy="true" className="mx-auto max-w-6xl px-6 py-12 md:px-8 lg:px-12">
      <Bar className="mx-auto mb-10 h-3 w-32" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="border border-border-light p-5">
            <Bar className="h-5 w-2/3" />
            <Bar className="mt-3 h-3 w-1/3" />
          </div>
        ))}
      </div>
    </main>
  );
}
