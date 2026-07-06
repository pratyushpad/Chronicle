export function JobCardSkeleton() {
  return (
    <article className="relative border border-foreground border-l-4 bg-card">
      <div className="p-5">
        <div className="flex items-start gap-3">
          <div className="shrink-0 h-10 w-10 border border-border-light animate-shimmer" />
          <div className="flex-1 min-w-0 space-y-2">
            <div className="h-4 w-2/3 animate-shimmer" />
            <div className="h-3 w-1/3 animate-shimmer" />
          </div>
        </div>
        <div className="mt-4 flex gap-2">
          <div className="h-4 w-16 animate-shimmer" />
          <div className="h-4 w-20 animate-shimmer" />
          <div className="h-4 w-12 animate-shimmer" />
        </div>
        <div className="mt-3 h-3 w-24 animate-shimmer" />
      </div>
    </article>
  );
}

export function JobListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="mt-6 flex flex-col gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <JobCardSkeleton key={i} />
      ))}
    </div>
  );
}
