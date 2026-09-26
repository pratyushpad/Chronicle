"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { cn, formatLocation, formatDepartment } from "@/lib/utils";
import { INTERN_DEFAULT_HIDES, RELEASED, countryName, isInternView, termLabel } from "@/lib/eligibility";

interface FilterBarProps {
  departments: string[];
  locations: string[];
  employmentTypes: string[];
  industries: string[];
  terms: string[];
  countries: string[];
}

// Level folds the two level params into one control: `level` (intern / new_grad, which
// also match titles) and `experience_level` (the posting's own level).
const LEVELS = [
  { value: "", label: "Any level" },
  { value: "level:intern", label: "Internship" },
  { value: "level:new_grad", label: "New grad" },
  { value: "exp:Mid Level", label: "Mid level" },
  { value: "exp:Senior", label: "Senior" },
  { value: "exp:Management", label: "Management" },
] as const;

const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "relevance", label: "Best match" },
  { value: "pay", label: "Highest pay" },
] as const;

const SEARCH_MODES = [
  { value: "keyword", label: "Keyword", title: "Matches words in the title, team and location" },
  { value: "hybrid", label: "Hybrid", title: "Keyword and meaning-based matches, combined" },
  { value: "semantic", label: "Semantic", title: "Meaning-based matches via embeddings" },
] as const;

// Params the drawer owns (its button shows how many are set).
const DRAWER_KEYS = ["company", "company_id", "industry", "employment_type", "since_last_run", "mode", "term", "workplace", "country"];

const control =
  "h-11 w-full min-w-0 border border-input bg-background px-3 font-sans text-sm text-foreground placeholder:text-muted-foreground focus:border-foreground focus:outline-none";
const selectClass = cn(control, "cursor-pointer");
const labelClass = "mb-1.5 block font-sans text-xs text-muted-foreground";

// Values older links and bookmarks carry for levels the Level control now covers.
const LEGACY_EXPERIENCE: Record<string, string> = { Internship: "level:intern", "Entry Level": "level:new_grad" };

function levelValue(p: URLSearchParams): string {
  const level = p.get("level");
  if (level) return `level:${level}`;
  const exp = p.get("experience_level");
  if (!exp) return "";
  return LEGACY_EXPERIENCE[exp] ?? `exp:${exp}`;
}

/** Local input state that commits to the URL after a pause. It re-syncs from the URL
 *  only on an outside change (Clear all, back button), never on the echo of its own
 *  commit, so keystrokes typed while a commit is in flight aren't overwritten. */
function useDebounced(initial: string, onCommit: (v: string) => void) {
  const [value, setValue] = useState(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const committed = useRef(initial);
  // The latest onCommit, so a timer set several renders ago commits against current state.
  const commitRef = useRef(onCommit);
  commitRef.current = onCommit;
  useEffect(() => {
    if (initial !== committed.current) {
      committed.current = initial;
      setValue(initial);
    }
  }, [initial]);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const change = (v: string) => {
    setValue(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      committed.current = v.trim();
      commitRef.current(v);
    }, 350);
  };
  const cancel = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  return [value, change, cancel] as const;
}

export function FilterBar({ departments, locations, employmentTypes, industries, terms, countries }: FilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();

  const push = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      // Start from the live URL, not this render's searchParams: a debounced search that
      // fires after another filter changed must not put the old filters back.
      const params = new URLSearchParams(window.location.search);
      mutate(params);
      params.delete("page");
      const qs = params.toString();
      startTransition(() => router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false }));
    },
    [pathname, router],
  );

  const set = useCallback(
    (key: string, value: string) =>
      push((p) => {
        if (value) p.set(key, value);
        else p.delete(key);
        if (key === "company") p.delete("company_id");
      }),
    [push],
  );

  const setLevel = (v: string) =>
    push((p) => {
      p.delete("level");
      p.delete("experience_level");
      if (v.startsWith("level:")) p.set("level", v.slice(6));
      else if (v.startsWith("exp:")) p.set("experience_level", v.slice(4));
    });

  const [q, setQ, cancelQ] = useDebounced(searchParams.get("q") ?? "", (v) => set("q", v.trim()));
  const hasQuery = !!searchParams.get("q");
  const defaultSort = hasQuery ? "relevance" : "newest";
  const sort = searchParams.get("sort") ?? defaultSort;
  const fusedSearch = hasQuery && ["semantic", "hybrid"].includes(searchParams.get("mode") ?? "");
  const compact = searchParams.get("density") === "compact";
  const drawerCount = DRAWER_KEYS.filter((k) => searchParams.get(k)).length;
  const anyFilter = Array.from(searchParams.keys()).some((k) => !["page", "density", "sort"].includes(k));

  return (
    <div
      className="border-b border-border-light bg-background pb-5 md:sticky md:top-16 md:z-30 md:pt-2"
      aria-busy={pending || undefined}
    >
      <div className="flex flex-col gap-3 md:flex-row">
        <div className="min-w-0 flex-1">
          <label htmlFor="feed-search" className="sr-only">
            Search roles
          </label>
          <input
            id="feed-search"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search roles, teams, places…"
            className={cn(control, "h-12 text-base")}
          />
        </div>
        <div className="flex gap-3">
          <label className="min-w-0 flex-1 md:w-48 md:flex-none">
            <span className="sr-only">Sort by</span>
            <select
              value={fusedSearch ? "relevance" : sort}
              onChange={(e) => set("sort", e.target.value === defaultSort ? "" : e.target.value)}
              className={cn(selectClass, "h-12 disabled:cursor-not-allowed disabled:opacity-60")}
              // Semantic and hybrid search always rank by match; the sort doesn't apply.
              disabled={fusedSearch}
              title={fusedSearch ? "Semantic and hybrid search are ordered by best match" : undefined}
            >
              {SORTS.filter((s) => s.value !== "relevance" || hasQuery).map((s) => (
                <option key={s.value} value={s.value}>
                  Sort: {s.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => set("density", compact ? "" : "compact")}
            aria-pressed={compact}
            className="h-12 shrink-0 border border-input px-3 font-sans text-sm text-foreground transition-colors hover:bg-muted"
            title="Show more roles per screen"
          >
            Compact view
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-[repeat(4,minmax(0,1fr))_auto]">
        <label className="min-w-0">
          <span className={labelClass}>Level</span>
          <select value={levelValue(searchParams)} onChange={(e) => setLevel(e.target.value)} className={selectClass}>
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className={labelClass}>Location</span>
          <select
            value={searchParams.get("location") ?? ""}
            onChange={(e) => set("location", e.target.value)}
            className={selectClass}
          >
            <option value="">Anywhere</option>
            {locations.map((l) => (
              <option key={l} value={l}>
                {formatLocation(l) || l}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className={labelClass}>Team</span>
          <select
            value={searchParams.get("department") ?? ""}
            onChange={(e) => set("department", e.target.value)}
            className={selectClass}
          >
            <option value="">Any team</option>
            {departments
              .filter((d) => formatDepartment(d))
              .map((d) => (
                <option key={d} value={d}>
                  {formatDepartment(d)}
                </option>
              ))}
          </select>
        </label>
        <div className="min-w-0">
          <span className={labelClass} aria-hidden>
            Workplace
          </span>
          <label className={cn(control, "flex cursor-pointer items-center gap-3 hover:bg-muted")}>
            <input
              type="checkbox"
              checked={searchParams.get("remote") === "true"}
              onChange={(e) => set("remote", e.target.checked ? "true" : "")}
              className="h-4 w-4 accent-[var(--foreground)]"
            />
            Remote only
          </label>
        </div>

        <div className="col-span-2 flex items-end gap-3 md:col-span-1">
          <Sheet>
            <SheetTrigger className="h-11 flex-1 whitespace-nowrap border border-input px-4 font-sans text-sm text-foreground transition-colors hover:bg-muted md:flex-none">
              More filters{drawerCount > 0 && ` (${drawerCount})`}
            </SheetTrigger>
            <SheetContent
              side="right"
              className="w-full overflow-y-auto border-l border-border-light bg-background p-6 sm:max-w-md"
            >
              <SheetTitle className="font-display text-2xl text-foreground">More filters</SheetTitle>
              <DrawerFilters
                industries={industries}
                employmentTypes={employmentTypes}
                terms={terms}
                countries={countries}
                current={searchParams}
                set={set}
              />
            </SheetContent>
          </Sheet>
          {anyFilter && (
            <button
              type="button"
              onClick={() => {
                setQ(""); // show the cleared box now…
                cancelQ(); // …without committing it (the push below clears q anyway)
                push((p) => {
                  for (const k of Array.from(p.keys())) if (!["density", "sort"].includes(k)) p.delete(k);
                });
              }}
              className="h-11 whitespace-nowrap px-2 font-sans text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              Clear all
            </button>
          )}
        </div>
      </div>
      <EligibilityToggles current={searchParams} set={set} />
    </div>
  );
}

/** Internship view: roles the posting restricts are hidden by default, and each rule is
 *  a visible, labelled toggle (checked = those roles are included). */
function EligibilityToggles({ current, set }: { current: URLSearchParams; set: (k: string, v: string) => void }) {
  const toggles = INTERN_DEFAULT_HIDES.filter((h) => RELEASED[h.key]);
  if (toggles.length === 0 || !isInternView(Object.fromEntries(current.entries()))) return null;
  return (
    <fieldset className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
      <legend className="sr-only">Include restricted internships</legend>
      <span className="font-sans text-xs text-muted-foreground">Hidden unless you include them:</span>
      {toggles.map((h) => (
        <label key={h.key} className="inline-flex min-h-[32px] cursor-pointer items-center gap-2 font-sans text-sm text-foreground">
          <input
            type="checkbox"
            checked={current.get(h.include) === "1"}
            onChange={(e) => set(h.include, e.target.checked ? "1" : "")}
            className="h-4 w-4 accent-[var(--foreground)]"
          />
          {h.label}
        </label>
      ))}
    </fieldset>
  );
}

function DrawerFilters({
  industries,
  employmentTypes,
  terms,
  countries,
  current,
  set,
}: {
  industries: string[];
  employmentTypes: string[];
  terms: string[];
  countries: string[];
  current: URLSearchParams;
  set: (key: string, value: string) => void;
}) {
  const [company, setCompany] = useDebounced(current.get("company") ?? "", (v) => set("company", v.trim()));
  const mode = current.get("mode") ?? "keyword";
  return (
    <div className="mt-6 flex flex-col gap-5">
      <label>
        <span className={labelClass}>Company</span>
        <input
          type="text"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder={current.get("company_id") ? "Filtered to one company" : "Any company"}
          className={control}
        />
      </label>
      <label>
        <span className={labelClass}>Industry</span>
        <select value={current.get("industry") ?? ""} onChange={(e) => set("industry", e.target.value)} className={selectClass}>
          <option value="">Any industry</option>
          {/* An older link's raw label (e.g. "AI/ML") still filters; show it rather than
              pretending no industry is set. */}
          {current.get("industry") && !industries.includes(current.get("industry")!) && (
            <option value={current.get("industry")!}>{current.get("industry")}</option>
          )}
          {industries.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className={labelClass}>Job type</span>
        <select
          value={current.get("employment_type") ?? ""}
          onChange={(e) => set("employment_type", e.target.value)}
          className={selectClass}
        >
          <option value="">Any type</option>
          {employmentTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      {RELEASED.term && terms.length > 0 && (
        <label>
          <span className={labelClass}>Term</span>
          <select value={current.get("term") ?? ""} onChange={(e) => set("term", e.target.value)} className={selectClass}>
            <option value="">Any term</option>
            {terms.map((t) => (
              <option key={t} value={t}>
                {termLabel(t)}
              </option>
            ))}
          </select>
        </label>
      )}
      {RELEASED.workplace && (
        <label>
          <span className={labelClass}>Workplace</span>
          <select value={current.get("workplace") ?? ""} onChange={(e) => set("workplace", e.target.value)} className={selectClass}>
            <option value="">Any workplace</option>
            <option value="onsite">On-site</option>
            <option value="hybrid">Hybrid</option>
            <option value="remote">Remote</option>
          </select>
        </label>
      )}
      {RELEASED.country && countries.length > 0 && (
        <label>
          <span className={labelClass}>Country</span>
          <select value={current.get("country") ?? ""} onChange={(e) => set("country", e.target.value)} className={selectClass}>
            <option value="">Any country</option>
            {countries.map((c) => (
              <option key={c} value={c}>
                {countryName(c)}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className={cn(control, "flex cursor-pointer items-center gap-3 hover:bg-muted")}>
        <input
          type="checkbox"
          checked={current.get("since_last_run") === "true"}
          onChange={(e) => set("since_last_run", e.target.checked ? "true" : "")}
          className="h-4 w-4 accent-[var(--foreground)]"
        />
        New since the last refresh
      </label>
      <fieldset>
        <legend className={labelClass}>Search matching</legend>
        <div className="flex">
          {SEARCH_MODES.map((opt) => {
            const active = mode === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => set("mode", opt.value === "keyword" ? "" : opt.value)}
                aria-pressed={active}
                title={opt.title}
                className={cn(
                  "-ml-px h-10 flex-1 border border-input font-sans text-sm transition-colors first:ml-0",
                  active ? "bg-foreground text-background" : "text-foreground hover:bg-muted",
                )}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <p className="mt-2 font-sans text-xs text-muted-foreground">Applies when you search.</p>
      </fieldset>
    </div>
  );
}
