"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { SectionLabel } from "./SectionLabel";
import { cn, formatLocation, formatDepartment } from "@/lib/utils";

interface FilterBarProps {
  departments: string[];
  locations: string[];
  employmentTypes: string[];
  experienceLevels: string[];
  industries: string[];
  companies: { id: number; name: string }[];
  selectedCompanyName?: string;
}

const QUICK_PILLS = [
  { label: "Internships", params: { level: "intern" } },
  { label: "New Grad", params: { level: "new_grad" } },
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
  locations,
  employmentTypes,
  industries,
  companies,
  selectedCompanyName,
  onChange,
  current,
}: FilterBarProps & {
  onChange: (key: string, value: string) => void;
  current: URLSearchParams;
}) {
  // Local, debounced search so typing stays smooth while the URL updates lazily.
  const [search, setSearch] = useState(current.get("q") ?? "");
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep local search in sync when the URL is cleared/changed externally (e.g. Clear).
  useEffect(() => {
    setSearch(current.get("q") ?? "");
  }, [current]);

  const onSearch = (value: string) => {
    setSearch(value);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => onChange("q", value), 300);
  };

  const inputClass =
    "h-11 w-full border border-foreground bg-background px-3 font-body text-sm text-foreground placeholder:italic placeholder:text-muted-foreground transition-all duration-100 focus:outline-none focus:border-2";
  const selectClass = cn(inputClass, "cursor-pointer appearance-none");

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <input
        type="text"
        placeholder="Search roles…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        className={inputClass}
        aria-label="Search roles"
      />

      <select
        value={selectedCompanyName ?? current.get("company") ?? ""}
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
        value={current.get("industry") ?? ""}
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
        value={current.get("experience_level") ?? ""}
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
        value={current.get("location") ?? ""}
        onChange={(e) => onChange("location", e.target.value)}
        className={selectClass}
        aria-label="Filter by location"
      >
        <option value="">All Locations</option>
        {locations.map((l) => (
          <option key={l} value={l}>{formatLocation(l) || l}</option>
        ))}
      </select>

      <select
        value={current.get("department") ?? ""}
        onChange={(e) => onChange("department", e.target.value)}
        className={selectClass}
        aria-label="Filter by department"
      >
        <option value="">All Departments</option>
        {departments.map((d) => (
          <option key={d} value={d}>{formatDepartment(d) || d}</option>
        ))}
      </select>

      <select
        value={current.get("employment_type") ?? ""}
        onChange={(e) => onChange("employment_type", e.target.value)}
        className={selectClass}
        aria-label="Filter by type"
      >
        <option value="">All Job Types</option>
        {employmentTypes.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>

      <label className="flex h-11 cursor-pointer items-center gap-3 border border-foreground px-3 transition-colors hover:bg-muted">
        <input
          type="checkbox"
          checked={current.get("remote") === "true"}
          onChange={(e) => onChange("remote", e.target.checked ? "true" : "")}
          className="h-4 w-4 accent-[var(--foreground)]"
        />
        <span className="font-mono text-xs uppercase tracking-[0.1em] text-foreground">Remote only</span>
      </label>

      <label className="flex h-11 cursor-pointer items-center gap-3 border border-foreground px-3 transition-colors hover:bg-muted">
        <input
          type="checkbox"
          checked={current.get("since_last_run") === "true"}
          onChange={(e) => onChange("since_last_run", e.target.checked ? "true" : "")}
          className="h-4 w-4 accent-[var(--foreground)]"
        />
        <span className="font-mono text-xs uppercase tracking-[0.1em] text-foreground">New this run</span>
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
      // company name and company_id are mutually exclusive
      if (key === "company") params.delete("company_id");
      if (key === "company_id") params.delete("company");
      // experience_level (select) and level (intern/new-grad pills) are mutually exclusive
      if (key === "experience_level" && value) params.delete("level");
      params.delete("page");
      startTransition(() => { router.push(`${pathname}?${params.toString()}`); });
    },
    [pathname, router, searchParams]
  );

  const applyPill = useCallback(
    (pillParams: Record<string, string>) => {
      const params = new URLSearchParams(searchParams.toString());
      const isActive = Object.entries(pillParams).every(([k, v]) => params.get(k) === v);
      if (isActive) {
        for (const k of Object.keys(pillParams)) params.delete(k);
      } else {
        for (const [k, v] of Object.entries(pillParams)) params.set(k, v);
        // selecting a level pill clears the experience_level select (mutually exclusive)
        if ("level" in pillParams) params.delete("experience_level");
      }
      params.delete("page");
      startTransition(() => { router.push(`${pathname}?${params.toString()}`); });
    },
    [pathname, router, searchParams]
  );

  return (
    <div className="sticky top-16 z-40 -mx-6 border-b-2 border-foreground bg-background px-6 py-4 md:-mx-8 md:px-8 lg:-mx-12 lg:px-12">
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
                "min-h-[32px] border px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em] transition-colors duration-100 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2",
                isActive
                  ? "border-foreground bg-foreground text-background"
                  : "border-foreground text-foreground hover:bg-foreground hover:text-background"
              )}
            >
              {pill.label}
            </button>
          );
        })}
        {searchParams.toString() && (
          <button
            onClick={() => startTransition(() => router.push(pathname))}
            className="min-h-[32px] border border-foreground px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
          >
            ✕ Clear
          </button>
        )}
      </div>

      {/* Desktop filters */}
      <div className="mt-4 hidden md:block">
        <Filters {...props} selectedCompanyName={props.selectedCompanyName} onChange={handleChange} current={searchParams} />
      </div>

      {/* Mobile Sheet */}
      <div className="mt-4 md:hidden">
        <Sheet>
          <SheetTrigger className="flex h-11 w-full items-center justify-center gap-2 border border-foreground font-mono text-xs uppercase tracking-[0.1em] text-foreground transition-colors hover:bg-foreground hover:text-background">
            <FilterIcon />
            All Filters
          </SheetTrigger>
          <SheetContent side="bottom" className="h-[85vh] overflow-y-auto border-t-2 border-foreground bg-background p-6">
            <SheetTitle className="sr-only">Filters</SheetTitle>
            <SectionLabel className="mb-6">Filters</SectionLabel>
            <Filters {...props} selectedCompanyName={props.selectedCompanyName} onChange={handleChange} current={searchParams} />
          </SheetContent>
        </Sheet>
      </div>
    </div>
  );
}
