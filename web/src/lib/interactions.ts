/**
 * Fire-and-forget interaction logging (impressions, clicks, saves).
 * Events are queued client-side and flushed in batches — debounced ~3 s,
 * plus on tab hide — to POST /api/interactions (Next proxy → FastAPI).
 * Best-effort: failures are dropped silently; if the user isn't signed in
 * (first flush 401s) logging disables itself for the session.
 */

export type InteractionEvent = "impression" | "click" | "save" | "apply" | "dismiss";
export type InteractionSurface = "feed" | "search" | "alert";

interface QueuedEvent {
  job_id: number;
  event: InteractionEvent;
  surface: InteractionSurface;
}

const FLUSH_DELAY_MS = 3000;
const MAX_BATCH = 100;

let queue: QueuedEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let disabled = false;
let listenerInstalled = false;
const seenImpressions = new Set<string>();

async function flush(): Promise<void> {
  if (disabled || queue.length === 0) return;
  const batch = queue.slice(0, MAX_BATCH);
  queue = queue.slice(batch.length);
  try {
    const res = await fetch("/api/interactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
    if (res.status === 401) disabled = true; // anonymous session — stop trying
  } catch {
    // network hiccup: drop the batch, this is telemetry not truth
  }
}

export function logInteraction(
  jobId: number,
  event: InteractionEvent,
  surface: InteractionSurface
): void {
  if (disabled || typeof window === "undefined") return;
  if (event === "impression") {
    // one impression per job+surface per page lifetime
    const key = `${jobId}:${surface}`;
    if (seenImpressions.has(key)) return;
    seenImpressions.add(key);
  }
  queue.push({ job_id: jobId, event, surface });

  if (!listenerInstalled) {
    listenerInstalled = true;
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") void flush();
    });
  }
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => void flush(), FLUSH_DELAY_MS);
}
