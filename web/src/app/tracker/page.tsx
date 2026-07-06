"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  type UniqueIdentifier,
  type DragStartEvent,
  type DragOverEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { CountUp } from "@/components/motion/CountUp";

type AppStatus = "saved" | "applied" | "interviewing" | "offer" | "rejected" | "archived";

interface TrackedApp {
  id: number;
  job_id: number;
  status: AppStatus;
  notes: string | null;
  next_action: string | null;
  applied_at: string | null;
  updated_at: string;
  job: { id: number; title: string; company_name: string; apply_url: string };
}

const COLUMNS: { key: AppStatus; label: string }[] = [
  { key: "saved", label: "Saved" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
];

const NEXT_STATUS: Partial<Record<AppStatus, AppStatus>> = {
  saved: "applied",
  applied: "interviewing",
  interviewing: "offer",
};

const CTA_BUTTON =
  "inline-flex min-h-[44px] items-center border-2 border-foreground bg-foreground px-8 font-mono text-xs font-medium uppercase tracking-[0.2em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px]";

export default function TrackerPage() {
  const { data: session, status } = useSession();
  const [apps, setApps] = useState<TrackedApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null);
  // Status the dragged card started in — lets us persist only real moves and revert on failure.
  const dragOrigin = useRef<AppStatus | null>(null);

  const sensors = useSensors(
    // Small distance so taps on the notes/buttons don't start a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const load = useCallback(async () => {
    if (status !== "authenticated") { setLoading(false); return; }
    const res = await fetch("/api/applications");
    if (res.ok) setApps(await res.json());
    setLoading(false);
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const persistStatus = async (appId: number, newStatus: AppStatus, revertTo: AppStatus) => {
    const res = await fetch(`/api/applications/${appId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) {
      // Roll back the optimistic move.
      setApps((prev) => prev.map((a) => (a.id === appId ? { ...a, status: revertTo } : a)));
    }
  };

  const updateStatus = async (appId: number, newStatus: AppStatus) => {
    const prevStatus = apps.find((a) => a.id === appId)?.status ?? "saved";
    setApps((prev) => prev.map((a) => (a.id === appId ? { ...a, status: newStatus } : a)));
    await persistStatus(appId, newStatus, prevStatus);
  };

  const saveNotes = async (appId: number) => {
    const note = notes[appId];
    if (note === undefined) return;
    await fetch(`/api/applications/${appId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: note }),
    });
    setApps((prev) => prev.map((a) => a.id === appId ? { ...a, notes: note } : a));
    setNotes((p) => { const n = { ...p }; delete n[appId]; return n; });
  };

  const remove = async (appId: number) => {
    const snapshot = apps;
    setApps((prev) => prev.filter((a) => a.id !== appId));
    const res = await fetch(`/api/applications/${appId}`, { method: "DELETE" });
    if (!res.ok) setApps(snapshot); // restore on failure
  };

  // ── Drag-and-drop wiring ──
  const containerOf = (id: UniqueIdentifier): AppStatus | undefined => {
    if (COLUMNS.some((c) => c.key === id)) return id as AppStatus;
    return apps.find((a) => a.id === id)?.status;
  };

  const onDragStart = (e: DragStartEvent) => {
    setActiveId(e.active.id);
    dragOrigin.current = containerOf(e.active.id) ?? null;
  };

  const onDragOver = (e: DragOverEvent) => {
    const { active, over } = e;
    if (!over) return;
    const from = containerOf(active.id);
    const to = containerOf(over.id);
    if (!from || !to || from === to) return;
    // Move the card into the hovered column live, so it visually follows the pointer.
    setApps((prev) => prev.map((a) => (a.id === active.id ? { ...a, status: to } : a)));
  };

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    setActiveId(null);
    const origin = dragOrigin.current;
    dragOrigin.current = null;
    if (!over) return;

    const final = containerOf(active.id);
    if (!final) return;

    // Reorder within a column (cosmetic — backend has no explicit order field).
    const overContainer = containerOf(over.id);
    if (final === overContainer && active.id !== over.id) {
      setApps((prev) => {
        const ids = prev.filter((a) => a.status === final).map((a) => a.id);
        const oldIndex = ids.indexOf(active.id as number);
        const newIndex = ids.indexOf(over.id as number);
        if (oldIndex === -1 || newIndex === -1) return prev;
        const reordered = arrayMove(ids, oldIndex, newIndex);
        // Rebuild apps with the column's cards in their new order.
        const others = prev.filter((a) => a.status !== final);
        const byId = new Map(prev.map((a) => [a.id, a]));
        const columnApps = reordered.map((id) => byId.get(id)!).filter(Boolean);
        return [...others, ...columnApps];
      });
    }

    if (origin && final !== origin) {
      persistStatus(active.id as number, final, origin);
    }
  };

  if (status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-32 text-center">
        <p className="font-display text-3xl text-foreground mb-4">Sign in to track applications</p>
        <p className="font-body text-muted-foreground mb-8">Your tracker syncs across devices when you're signed in.</p>
        <button onClick={() => signIn("google")} className={CTA_BUTTON}>
          Sign in with Google
        </button>
      </main>
    );
  }

  const funnel = {
    total: apps.length,
    applied: apps.filter((a) => a.status === "applied").length,
    interviewing: apps.filter((a) => a.status === "interviewing").length,
    offers: apps.filter((a) => a.status === "offer").length,
  };
  const activeApp = activeId != null ? apps.find((a) => a.id === activeId) ?? null : null;

  return (
    <main className="px-4 py-12">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center justify-between mb-6">
          <h1 className="font-display text-3xl text-foreground">Application Tracker</h1>
          <Link href="/jobs" className="font-mono text-xs uppercase tracking-[0.12em] text-foreground underline-offset-4 hover:underline">+ Add roles →</Link>
        </div>

        {funnel.total > 0 && (
          <div className="mb-10 grid grid-cols-4 divide-x divide-border-light border-y border-foreground">
            {[{ label: "Total", v: funnel.total }, { label: "Applied", v: funnel.applied }, { label: "Interviewing", v: funnel.interviewing }, { label: "Offers", v: funnel.offers }].map(({ label, v }) => (
              <div key={label} className="px-4 py-5 text-center">
                <CountUp value={v} className="justify-center font-display text-3xl text-foreground" />
                <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{label}</div>
              </div>
            ))}
          </div>
        )}

        {loading ? (
          <div className="font-body text-muted-foreground">Loading…</div>
        ) : apps.length === 0 ? (
          <div className="border-y-2 border-foreground py-24 text-center">
            <p className="font-display text-2xl text-foreground mb-2">No applications yet</p>
            <p className="font-body text-muted-foreground mb-6">Bookmark any role to start tracking — it lands in your Saved column.</p>
            <Link href="/jobs" className={CTA_BUTTON}>Browse Open Roles</Link>
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={onDragStart}
            onDragOver={onDragOver}
            onDragEnd={onDragEnd}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {COLUMNS.map(({ key, label }) => {
                const items = apps.filter((a) => a.status === key);
                return (
                  <Column key={key} id={key} label={label} count={items.length}>
                    <SortableContext items={items.map((a) => a.id)} strategy={verticalListSortingStrategy}>
                      <div className="space-y-3">
                        {items.map((app) => (
                          <SortableCard
                            key={app.id}
                            app={app}
                            notes={notes}
                            setNotes={setNotes}
                            saveNotes={saveNotes}
                            updateStatus={updateStatus}
                            remove={remove}
                          />
                        ))}
                      </div>
                    </SortableContext>
                  </Column>
                );
              })}
            </div>

            {/* Lifted preview while dragging — dnd-kit owns this transform. */}
            <DragOverlay>
              {activeApp ? <CardShell app={activeApp} dragging /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </main>
  );
}

function Column({ id, label, count, children }: { id: AppStatus; label: string; count: number; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div ref={setNodeRef}>
      <div className="mb-3 flex items-center gap-2 border-b border-foreground pb-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-foreground">{label}</span>
        <span className="font-mono text-[9px] text-muted-foreground">({count})</span>
      </div>
      <div className={`min-h-[80px] transition-colors duration-100 ${isOver ? "bg-muted" : ""}`}>
        {children}
      </div>
    </div>
  );
}

interface CardProps {
  app: TrackedApp;
  notes: Record<number, string>;
  setNotes: React.Dispatch<React.SetStateAction<Record<number, string>>>;
  saveNotes: (id: number) => void;
  updateStatus: (id: number, s: AppStatus) => void;
  remove: (id: number) => void;
}

function SortableCard({ app, notes, setNotes, saveNotes, updateStatus, remove }: CardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: app.id });
  // dnd-kit is the sole writer of `transform`/`transition` on the card — no Framer
  // layout here, so the two never fight over the same property.
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0 : 1,
  };
  const next = NEXT_STATUS[app.status];

  return (
    <div ref={setNodeRef} style={style} className="border border-foreground border-t-2 bg-card p-4">
      {/* Drag handle = the title block. Keyboard users can pick up and move it;
          the notes/buttons below stay fully interactive. */}
      <div
        {...attributes}
        {...listeners}
        className="cursor-grab touch-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
        aria-label={`Drag ${app.job.title} to another column`}
      >
        <p className="font-display text-sm leading-snug text-foreground line-clamp-2">{app.job.title}</p>
        <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">{app.job.company_name}</p>
      </div>
      <Link href={`/jobs/${app.job.id}`} className="mt-1 inline-block font-mono text-[9px] uppercase tracking-[0.1em] text-foreground underline-offset-4 hover:underline">
        View role →
      </Link>
      <textarea
        placeholder="Notes…"
        value={notes[app.id] ?? app.notes ?? ""}
        onChange={(e) => setNotes((p) => ({ ...p, [app.id]: e.target.value }))}
        onBlur={() => saveNotes(app.id)}
        rows={2}
        className="mt-3 w-full resize-none border border-border-light bg-background px-2 py-1.5 font-body text-xs text-foreground placeholder:italic placeholder:text-muted-foreground focus:outline-none focus:border-foreground"
      />
      <div className="mt-2 flex items-center gap-1.5 flex-wrap">
        {/* Accessible fallback to drag: advance/reject by click or keyboard. */}
        {next && (
          <button onClick={() => updateStatus(app.id, next)}
            className="font-mono text-[9px] uppercase tracking-[0.1em] px-2 py-1 border border-foreground text-foreground hover:bg-foreground hover:text-background transition-colors duration-100">
            → {next}
          </button>
        )}
        {app.status !== "rejected" && (
          <button onClick={() => updateStatus(app.id, "rejected")}
            className="font-mono text-[9px] uppercase tracking-[0.1em] px-2 py-1 border border-border-light text-muted-foreground hover:border-foreground hover:text-foreground transition-colors duration-100">
            Reject
          </button>
        )}
        <a href={app.job.apply_url} target="_blank" rel="noopener noreferrer"
          className="ml-auto font-mono text-[9px] uppercase tracking-[0.1em] text-foreground underline-offset-4 hover:underline">Apply →</a>
        <button onClick={() => remove(app.id)} aria-label="Remove" className="font-mono text-[11px] text-muted-foreground hover:text-foreground transition-colors">✕</button>
      </div>
    </div>
  );
}

// Static card used inside DragOverlay (no interactive controls needed).
function CardShell({ app, dragging }: { app: TrackedApp; dragging?: boolean }) {
  return (
    <div className={`bg-card p-4 ${dragging ? "cursor-grabbing border-2 border-foreground" : "border border-foreground border-t-2"}`}>
      <p className="font-display text-sm leading-snug text-foreground line-clamp-2">{app.job.title}</p>
      <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">{app.job.company_name}</p>
    </div>
  );
}
