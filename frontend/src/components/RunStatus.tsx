import type { SessionSummary } from "@/lib/types";
import { RunSpinner } from "./RunSpinner";

export function RunStatus({
  session,
  compact = false,
}: {
  session: SessionSummary;
  compact?: boolean;
}) {
  if (session.run_status === "running")
    return (
      <span
        role="img"
        aria-label="Running"
        title="Running — unfinished turn with progress recorded within the last ten minutes"
        className="inline-flex shrink-0 items-center text-add"
      >
        <RunSpinner />
      </span>
    );
  if (compact) return null;
  return (
    <span
      className="text-[11px] text-muted-foreground"
      title={
        session.run_status === "idle"
          ? "The latest recorded turn ended"
          : "Live status is unavailable, or the last unfinished turn has gone quiet"
      }
    >
      {session.run_status === "idle" ? "Idle" : "Status unknown"}
    </span>
  );
}
