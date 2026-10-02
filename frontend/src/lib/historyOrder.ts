/** Refresh metadata without moving existing rows under the reader's pointer. */
export function reconcileHistoryOrder(
  previous: string[],
  latest: string[],
): string[] {
  const present = new Set(latest);
  const kept = previous.filter((id) => present.has(id));
  const known = new Set(kept);
  return [...kept, ...latest.filter((id) => !known.has(id))];
}
