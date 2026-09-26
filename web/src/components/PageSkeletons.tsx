import { JobCardSkeleton, JobListSkeleton } from "@/components/JobCardSkeleton";

// Route-level loading states (app/**/loading.tsx). Shapes mirror the pages they stand in
// for, so content doesn't jump when it arrives. aria-busy tells assistive tech to wait.

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

export function JobDetailSkeleton() {
  return (
    <main id="main" aria-busy="true" className="mx-auto max-w-6xl px-4 pb-32 pt-10 sm:px-6 lg:pb-20 lg:pt-16">
      <Bar className="h-4 w-40" />
      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-14">
        <div className="min-w-0">
          <Bar className="h-3 w-28" />
          <Bar className="mt-4 h-9 w-5/6" />
          <Bar className="mt-3 h-9 w-1/2" />
          <div className="mt-8 grid grid-cols-2 gap-4 border-y border-border-light py-5 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i}>
                <Bar className="h-2.5 w-12" />
                <Bar className="mt-2 h-4 w-24" />
              </div>
            ))}
          </div>
          {Array.from({ length: 8 }).map((_, i) => (
            <Bar key={i} className={`mt-4 h-4 ${i % 3 === 2 ? "w-2/3" : "w-full"}`} />
          ))}
        </div>
        <div className="hidden lg:block">
          <div className="border border-border-light p-6">
            <Bar className="h-7 w-32" />
            <Bar className="mt-4 h-11 w-full" />
            <Bar className="mt-5 h-4 w-full" />
            <Bar className="mt-2 h-4 w-full" />
          </div>
        </div>
      </div>
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

export function CompanySkeleton() {
  return (
    <main id="main" aria-busy="true" className="mx-auto max-w-5xl px-6 py-12">
      <Bar className="h-4 w-32" />
      <Bar className="mt-8 h-10 w-1/2" />
      <Bar className="mt-3 h-3 w-40" />
      <Bar className="mt-10 h-40 w-full" />
      <div className="mt-10 flex flex-col gap-4">
        <JobCardSkeleton />
        <JobCardSkeleton />
        <JobCardSkeleton />
      </div>
    </main>
  );
}
