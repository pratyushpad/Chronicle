"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback, useTransition } from "react";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { SectionLabel } from "./SectionLabel";
import { cn } from "@/lib/utils";

interface FilterBarProps {
  departments: string[];
  locations: string[];
  employmentTypes: string[];
  experienceLevels: string[];
  industries: string[];
  companies: { id: number; name: string }[];
}

const QUICK_PILLS = [
  { label: "Internships", params: { q: "intern" } },
  { label: "New Grad", params: { q: "new grad" } },
  { label: "Remote", params: { remote: "true" } },
  { label: "Full-time", params: { employment_type: "Full-time" } },
  { label: "Engineering", params: { department: "Engineering" } },
  { label: "AI / ML", params: { industry: "AI/ML" } },
  { label: "FinTech", params: { industry: "FinTech" } },
  { label: "New since last run", params: { since_last_run: "true" } },
] as const;

function FilterIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M2 4h12M4 8h8M6 12h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function Filters({
  departments,
  employmentTypes,
  experienceLevels,
  industries,
  companies,
  onChange,
  current,
}: FilterBarProps & {
  onChange: (key: string, value: string) => void;
  current: URLSearchParams;
}) {
  const inputClass =
    "h-11 w-full rounded-md border border-border bg-transparent px-3 font-body text-sm text-foreground placeholder:text-muted-foreground/60 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:border-accent hover:border-foreground/40";
  const selectClass = cn(inputClass, "cursor-pointer appearance-none");

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <input
        type="text"
        placeholder="Search roles…"
        defaultValue={current.get("q") ?? ""}
        onChange={(e) => onChange("q", e.target.value)}
        className={inputClass}
        aria-label="Search roles"
      />

      <select
        defaultValue={current.get("company") ?? ""}
        onChange={(e) => onChange("company", e.target.value)}
        className={selectClass}
        aria-label="Filter by company"
      >
        <option value="">All Companies</option>
        {companies.map((c) => (
          <option key={c.id} value={c.name}>{c.name}</option>
        ))}
      </select>

      <select
        defaultValue={current.get("industry") ?? ""}
        onChange={(e) => onChange("industry", e.target.value)}
        className={selectClass}
        aria-label="Filter by industry"
      >
        <option value="">All Industries</option>
        {industries.map((i) => (
          <option key={i} value={i}>{i}</option>
        ))}
      </select>

      <select
        defaultValue={current.get("experience_level") ?? ""}
        onChange={(e) => onChange("experience_level", e.target.value)}
        className={selectClass}
        aria-label="Filter by experience"
      >
        <option value="">All Experience Levels</option>
        {["Internship", "Entry Level", "Mid Level", "Senior", "Management"].map((lvl) => (
          <option key={lvl} value={lvl}>{lvl}</option>
        ))}
      </select>

      <select
        defaultValue={current.get("department") ?? ""}
        onChange={(e) => onChange("department", e.target.value)}
        className={selectClass}
        aria-label="Filter by department"
      >
        <option value="">All Departments</option>
        {departments.map((d) => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>

      <select
        defaultValue={current.get("employment_type") ?? ""}
        onChange={(e) => onChange("employment_type", e.target.value)}
        className={selectClass}
        aria-label="Filter by type"
      >
        <option value="">All Job Types</option>
        {employmentTypes.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>

      <label className="flex h-11 cursor-pointer items-center gap-3 rounded-md border border-border px-3 transition-colors hover:border-foreground/40">
        <input
          type="checkbox"
          defaultChecked={current.get("remote") === "true"}
          onChange={(e) => onChange("remote", e.target.checked ? "true" : "")}
          className="h-4 w-4 accent-[var(--accent)] rounded"
        />
        <span className="font-mono text-xs uppercase tracking-[0.1em] text-muted-foreground">Remote only</span>
      </label>

      <label className="flex h-11 cursor-pointer items-center gap-3 rounded-md border border-border px-3 transition-colors hover:border-foreground/40">
        <input
          type="checkbox"
          defaultChecked={current.get("since_last_run") === "true"}
          onChange={(e) => onChange("since_last_run", e.target.checked ? "true" : "")}
          className="h-4 w-4 accent-[var(--accent)] rounded"
        />
        <span className="font-mono text-xs uppercase tracking-[0.1em] text-muted-foreground">New this run</span>
      </label>
    </div>
  );
}

export function FilterBar(props: FilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

  const handleChange = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) { params.set(key, value); } else { params.delete(key); }
      params.delete("page");
      startTransition(() => { router.push(`${pathname}?${params.toString()}`); });
    },
    [pathname, router, searchParams]
  );

  const applyPill = useCallback(
    (pillParams: Record<string, string>) => {
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(pillParams)) { params.set(k, v); }
      startTransition(() => { router.push(`/jobs?${params.toString()}`); });
    },
    [router]
  );

  return (
    <div className="space-y-4">
      {/* Quick filter pills */}
      <div className="flex flex-wrap gap-2">
        {QUICK_PILLS.map((pill) => {
          const isActive = Object.entries(pill.params).every(
            ([k, v]) => searchParams.get(k) === v
          );
          return (
            <button
              key={pill.label}
              onClick={() => applyPill(pill.params as Record<string, string>)}
              className={cn(
                "font-mono text-xs border rounded-full px-3 py-1.5 transition-all duration-150 min-h-[32px]",
                isActive
                  ? "bg-accent text-white border-accent"
                  : "border-border text-muted-foreground hover:border-accent hover:text-accent"
              )}
            >
              {pill.label}
            </button>
          );
        })}
        {searchParams.toString() && (
          <button
            onClick={() => startTransition(() => router.push("/jobs"))}
            className="font-mono text-xs border border-red-200 text-red-500 rounded-full px-3 py-1.5 hover:bg-red-50 transition-colors min-h-[32px]"
          >
            ✕ Clear
          </button>
        )}
      </div>

      {/* Desktop filters */}
      <div className="hidden md:block">
        <Filters {...props} onChange={handleChange} current={searchParams} />
      </div>

      {/* Mobile Sheet */}
      <div className="md:hidden">
        <Sheet>
          <SheetTrigger className="flex h-11 w-full items-center justify-center gap-2 rounded-md border border-border font-mono text-xs uppercase tracking-[0.1em] text-muted-foreground transition-colors hover:border-accent hover:text-accent">
            <FilterIcon />
            All Filters
          </SheetTrigger>
          <SheetContent side="bottom" className="h-[85vh] rounded-t-xl bg-background p-6 overflow-y-auto">
            <SheetTitle className="sr-only">Filters</SheetTitle>
            <SectionLabel className="mb-6">Filters</SectionLabel>
            <Filters {...props} onChange={handleChange} current={searchParams} />
          </SheetContent>
        </Sheet>
      </div>
    </div>
  );
}
