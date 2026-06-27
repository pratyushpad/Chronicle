"use client";
import { useCallback, useEffect, useState } from "react";
import type { JobListItem } from "@/lib/api";

export type AppStatus = "saved" | "applied" | "interviewing" | "offer" | "rejected";

export interface TrackedJob {
  job: JobListItem;
  status: AppStatus;
  addedAt: string;
  notes?: string;
}

const KEY = "folio_tracker";

function load(): TrackedJob[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save(items: TrackedJob[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {}
}

export function useTracker() {
  const [tracked, setTracked] = useState<TrackedJob[]>([]);

  useEffect(() => {
    setTracked(load());
  }, []);

  const addJob = useCallback((job: JobListItem, status: AppStatus = "saved") => {
    setTracked((prev) => {
      if (prev.some((t) => t.job.id === job.id)) return prev;
      const next = [{ job, status, addedAt: new Date().toISOString() }, ...prev];
      save(next);
      return next;
    });
  }, []);

  const updateStatus = useCallback((jobId: number, status: AppStatus) => {
    setTracked((prev) => {
      const next = prev.map((t) => (t.job.id === jobId ? { ...t, status } : t));
      save(next);
      return next;
    });
  }, []);

  const updateNotes = useCallback((jobId: number, notes: string) => {
    setTracked((prev) => {
      const next = prev.map((t) => (t.job.id === jobId ? { ...t, notes } : t));
      save(next);
      return next;
    });
  }, []);

  const removeJob = useCallback((jobId: number) => {
    setTracked((prev) => {
      const next = prev.filter((t) => t.job.id !== jobId);
      save(next);
      return next;
    });
  }, []);

  const isTracked = useCallback(
    (jobId: number) => tracked.some((t) => t.job.id === jobId),
    [tracked]
  );

  const getStatus = useCallback(
    (jobId: number): AppStatus | null =>
      tracked.find((t) => t.job.id === jobId)?.status ?? null,
    [tracked]
  );

  return { tracked, addJob, updateStatus, updateNotes, removeJob, isTracked, getStatus };
}
