import Link from "next/link";
import { cn } from "@/lib/utils";

interface PaginationProps {
  page: number;
  totalPages: number;
  basePath: string;
  searchParams?: Record<string, string>;
}

function buildHref(
  basePath: string,
  page: number,
  searchParams: Record<string, string>
): string {
  const params = new URLSearchParams({ ...searchParams, page: String(page) });
  return `${basePath}?${params.toString()}`;
}

export function Pagination({
  page,
  totalPages,
  basePath,
  searchParams = {},
}: PaginationProps) {
  if (totalPages <= 1) return null;

  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  // Show at most 7 page numbers: first, last, current ±2, with ellipses
  const visible = new Set<number>();
  visible.add(1);
  visible.add(totalPages);
  for (let i = Math.max(1, page - 2); i <= Math.min(totalPages, page + 2); i++) {
    visible.add(i);
  }
  const sorted = Array.from(visible).sort((a, b) => a - b);

  return (
    <nav
      className="flex items-center justify-center gap-1 py-8"
      aria-label="Pagination"
    >
      {/* Prev */}
      {page > 1 ? (
        <Link
          href={buildHref(basePath, page - 1, searchParams)}
          className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md border border-border px-3 font-mono text-xs uppercase tracking-[0.1em] text-muted-foreground transition-colors hover:border-accent hover:text-accent"
        >
          ← Prev
        </Link>
      ) : (
        <span className="flex min-h-[44px] min-w-[44px] cursor-not-allowed items-center justify-center rounded-md border border-border px-3 font-mono text-xs uppercase tracking-[0.1em] text-border">
          ← Prev
        </span>
      )}

      {/* Page numbers — hidden on mobile */}
      <div className="hidden sm:flex items-center gap-1">
        {sorted.map((p, idx) => {
          const prev = sorted[idx - 1];
          return (
            <span key={p} className="flex items-center gap-1">
              {prev && p - prev > 1 && (
                <span className="font-mono text-xs text-muted-foreground px-1">…</span>
              )}
              {p === page ? (
                <span className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md font-mono text-xs font-medium text-accent">
                  {p}
                </span>
              ) : (
                <Link
                  href={buildHref(basePath, p, searchParams)}
                  className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md font-mono text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  {p}
                </Link>
              )}
            </span>
          );
        })}
      </div>

      {/* Mobile: just page count */}
      <span className="sm:hidden font-mono text-xs text-muted-foreground px-3">
        {page} / {totalPages}
      </span>

      {/* Next */}
      {page < totalPages ? (
        <Link
          href={buildHref(basePath, page + 1, searchParams)}
          className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md border border-border px-3 font-mono text-xs uppercase tracking-[0.1em] text-muted-foreground transition-colors hover:border-accent hover:text-accent"
        >
          Next →
        </Link>
      ) : (
        <span className="flex min-h-[44px] min-w-[44px] cursor-not-allowed items-center justify-center rounded-md border border-border px-3 font-mono text-xs uppercase tracking-[0.1em] text-border">
          Next →
        </span>
      )}
    </nav>
  );
}
