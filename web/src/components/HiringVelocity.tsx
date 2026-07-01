import type { CompanyVelocity } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";

// Hand-rolled SVG — no chart dependency, matches the monochrome aesthetic.
// Each week is a paired column: a filled bar for roles opened, a hollow bar for
// roles closed, drawn on a shared scale.
export function HiringVelocity({ data }: { data: CompanyVelocity }) {
  const weeks = data.weeks;
  if (!weeks.length) return null;

  const max = Math.max(1, ...weeks.map((w) => Math.max(w.opened, w.closed)));
  const W = 640;
  const H = 140;
  const padB = 22; // room for x labels
  const chartH = H - padB;
  const slot = W / weeks.length;
  const barW = Math.min(14, slot * 0.28);

  const monthLabel = (iso: string) => {
    const d = new Date(iso + "T00:00:00Z");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  };

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
              <rect x={cx - barW - 1} y={chartH - oh} width={barW} height={oh} fill="currentColor" />
              {/* closed — hollow */}
              <rect
                x={cx + 1}
                y={chartH - ch}
                width={barW}
                height={ch}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.25"
              />
              <text
                x={cx}
                y={H - 6}
                textAnchor="middle"
                className="fill-current font-mono"
                fontSize="8"
                opacity="0.55"
              >
                {monthLabel(w.week)}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="mt-3 flex items-center gap-5">
        <Legend filled label="Opened" />
        <Legend label="Closed" />
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-foreground p-3">
      <div className="font-display text-2xl text-foreground">{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{label}</div>
    </div>
  );
}

function Legend({ filled, label }: { filled?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
      <span
        className={`inline-block h-2.5 w-2.5 ${filled ? "bg-foreground" : "border border-foreground"}`}
        aria-hidden
      />
      {label}
    </span>
  );
}
