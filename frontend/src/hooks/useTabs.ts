import { useCallback, useEffect, useState } from "react";
import type { SessionSummary } from "@/lib/types";

export interface Tab {
  /** Global session id — also the tab's identity, so a session can't open twice. */
  id: string;
  title: string;
  source: string;
  /** True while the tab is a preview: single-click opens preview, double-click or
   *  edit pins it. Mirrors how editors avoid tab explosion during browsing. */
  preview: boolean;
}

const STORAGE_KEY = "ccsweb.tabs.v1";
const MAX_TABS = 12;

interface Persisted {
  tabs: Tab[];
  activeId: string | null;
}

function load(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { tabs: [], activeId: null };
    const parsed = JSON.parse(raw) as Persisted;
    if (!Array.isArray(parsed.tabs)) return { tabs: [], activeId: null };
    return parsed;
  } catch {
    return { tabs: [], activeId: null };
  }
}

/**
 * Browser-style tabs over sessions.
 *
 * Restored from localStorage on load so the working set survives a refresh,
 * which is the whole point of keeping many chats open for cross-referencing.
 */
export function useTabs() {
  const [{ tabs, activeId }, setState] = useState<Persisted>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ tabs, activeId }));
    } catch {
      // Quota or private mode — tabs simply won't persist.
    }
  }, [tabs, activeId]);

  const open = useCallback(
    (session: Pick<SessionSummary, "id" | "title" | "source">, pin = false) => {
      setState((current) => {
        const existing = current.tabs.find((t) => t.id === session.id);
        if (existing) {
          return {
            tabs: pin
              ? current.tabs.map((t) =>
                  t.id === session.id ? { ...t, preview: false } : t,
                )
              : current.tabs,
            activeId: session.id,
          };
        }

        const fresh: Tab = {
          id: session.id,
          title: session.title || session.id,
          source: session.source,
          preview: !pin,
        };

        // A new preview replaces the outgoing preview rather than stacking up.
        const withoutPreview = pin
          ? current.tabs
          : current.tabs.filter((t) => !t.preview);

        const next = [...withoutPreview, fresh].slice(-MAX_TABS);
        return { tabs: next, activeId: fresh.id };
      });
    },
    [],
  );

  const close = useCallback((id: string) => {
    setState((current) => {
      const index = current.tabs.findIndex((t) => t.id === id);
      if (index === -1) return current;
      const tabs = current.tabs.filter((t) => t.id !== id);
      let next = current.activeId;
      if (current.activeId === id) {
        // Prefer the tab to the right, matching browser behaviour.
        next = tabs[index]?.id ?? tabs[index - 1]?.id ?? null;
      }
      return { tabs, activeId: next };
    });
  }, []);

  const closeOthers = useCallback((id: string) => {
    setState((current) => ({
      tabs: current.tabs.filter((t) => t.id === id).map((t) => ({ ...t, preview: false })),
      activeId: id,
    }));
  }, []);

  const activate = useCallback((id: string) => {
    setState((current) => ({ ...current, activeId: id }));
  }, []);

  const pin = useCallback((id: string) => {
    setState((current) => ({
      ...current,
      tabs: current.tabs.map((t) => (t.id === id ? { ...t, preview: false } : t)),
    }));
  }, []);

  const cycle = useCallback((delta: number) => {
    setState((current) => {
      if (current.tabs.length === 0) return current;
      const index = current.tabs.findIndex((t) => t.id === current.activeId);
      const next = (index + delta + current.tabs.length) % current.tabs.length;
      return { ...current, activeId: current.tabs[next].id };
    });
  }, []);

  return { tabs, activeId, open, close, closeOthers, activate, pin, cycle };
}
