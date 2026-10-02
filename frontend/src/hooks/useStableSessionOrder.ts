import { useEffect, useState } from "react";
import type { SessionSummary } from "@/lib/types";
import { reconcileHistoryOrder } from "@/lib/historyOrder";

export function useStableSessionOrder(
  sessions: SessionSummary[] | undefined,
  view: string,
) {
  const [saved, setSaved] = useState<Record<string, string[]>>({});
  const latest = sessions?.map((session) => session.id) ?? [];
  const ids = reconcileHistoryOrder(saved[view] ?? [], latest);
  const signature = JSON.stringify(ids);
  useEffect(() => {
    if (sessions)
      setSaved((previous) => ({ ...previous, [view]: JSON.parse(signature) }));
  }, [sessions, view, signature]);
  const byId = new Map(sessions?.map((session) => [session.id, session]));
  return {
    sessions: ids.map((id) => byId.get(id)!),
    canSortByLatest: ids.some((id, index) => id !== latest[index]),
    sortByLatest: () =>
      setSaved((previous) => ({ ...previous, [view]: latest })),
  };
}
