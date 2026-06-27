"use client";
import { useCallback, useEffect, useState } from "react";

const KEY = "folio_bookmarks";

export function useBookmarks() {
  const [bookmarks, setBookmarks] = useState<Set<number>>(new Set());

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setBookmarks(new Set(JSON.parse(raw)));
    } catch {}
  }, []);

  const toggle = useCallback((id: number) => {
    setBookmarks((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      try {
        localStorage.setItem(KEY, JSON.stringify(Array.from(next)));
      } catch {}
      return next;
    });
  }, []);

  const isBookmarked = useCallback((id: number) => bookmarks.has(id), [bookmarks]);

  return { bookmarks, toggle, isBookmarked };
}
