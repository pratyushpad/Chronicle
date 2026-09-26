"use client";
import { useRef, type CSSProperties } from "react";
import { useInView } from "motion/react";
import type { CompanyVelocity } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";
import { CountUp } from "@/components/motion/CountUp";

// Hand-rolled SVG — no chart dependency, matches the monochrome aesthetic.
// Each week is a paired column: a filled bar for roles opened, a hollow bar for
// roles closed, drawn on a shared scale. Bars grow (scaleY) from the baseline on
// scroll-into-view; the summary stats count up.
export function HiringVelocity({ data }: { data: CompanyVelocity }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const inView = useInView(svgRef, { once: true, margin: "-10%" });
  const weeks = data.weeks;
  if (!weeks.length) return null;

  const max = Math.max(1, ...weeks.map((w) => Math.max(w.opened, w.closed)));
  const W = 640;
  const H = 120;
  const padB = 2; // week labels are HTML below the SVG
  const chartH = H - padB;
  const slot = W / weeks.length;
  const barW = Math.min(14, slot * 0.28);

  const monthLabel = (iso: string) => {
    const d = new Date(iso + "T00:00:00Z");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  };

  // Grow from the bar's own baseline. `fill-box` makes transform-origin resolve
  // against the rect rather than the SVG viewport. The server renders every bar at full
  // height; the `data-reveal="grow-y"` rules in globals.css hold them at scaleY(0) only
  // for readers who allow motion and have JS, until the chart scrolls into view.
  const barReveal = (i: number) => ({
    "data-reveal": "grow-y",
    "data-revealed": inView ? "" : undefined,
    style: {
      transformBox: "fill-box",
      transformOrigin: "bottom",
      "--reveal-delay": `${Math.min(i * 0.03, 0.3)}s`,
    } as CSSProperties,
  });

  return (
    <section className="mb-10">
      <SectionLabel className="mb-6">Hiring Velocity</SectionLabel>

      <div className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Open now" value={data.active_now} />
        <Stat label="New this week" value={data.new_this_week} />
        <Stat label="Opened / 30d" value={data.opened_last_30d} />
        <Stat label="Closed / 30d" value={data.closed_last_30d} />
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label="Roles opened and closed per week"
      >
        {/* baseline */}
        <line x1="0" y1={chartH} x2={W} y2={chartH} stroke="currentColor" strokeWidth="1" opacity="0.25" />
        {weeks.map((w, i) => {
          const cx = i * slot + slot / 2;
          const oh = (w.opened / max) * (chartH - 6);
          const ch = (w.closed / max) * (chartH - 6);
          return (
            <g key={w.week}>
              {/* opened — filled */}
              <rect x={cx - barW - 1} y={chartH - oh} width={barW} height={oh} fill="currentColor" {...barReveal(i)} />
              {/* closed — hollow */}
              <rect
                x={cx + 1}
                y={chartH - ch}
                width={barW}
                height={ch}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.25"
                {...barReveal(i)}
              />
            </g>
          );
        })}
      </svg>
      {/* Week labels in HTML, not SVG text: SVG text scales with the viewBox and fell to
          ~4.5px on a phone. */}
      <div className="mt-1 flex" aria-hidden>
        {weeks.map((w) => (
          <span key={w.week} className="flex-1 text-center font-sans text-[11px] text-muted-foreground">
            {monthLabel(w.week)}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-5">
        <Legend filled label="Opened" />
        <Legend label="Closed" />
      </div>
      <p className="mt-3 max-w-prose font-sans text-xs leading-relaxed text-muted-foreground">
        How this is counted: a role counts as opened in the week the company&rsquo;s board says
        it was posted, or, when the board gives no date, the week Chronicle first saw it.
        Roles that were already open when Chronicle first read this board aren&rsquo;t counted
        as openings
        {data.first_ingest_excluded ? ` (${data.first_ingest_excluded} left out)` : ""}. Closed
        is the week a role was last seen before it left the board.
      </p>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-input p-3">
      <CountUp value={value} className="font-display text-2xl text-foreground" />
      <div className="font-sans text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{label}</div>
    </div>
  );
}

function Legend({ filled, label }: { filled?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2 font-sans text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
      <span
        className={`inline-block h-2.5 w-2.5 ${filled ? "bg-foreground" : "border border-input"}`}
        aria-hidden
      />
      {label}
    </span>
  );
}
