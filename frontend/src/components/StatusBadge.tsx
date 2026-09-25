import { STATUS_COPY } from "../format";
import type { Status } from "../types";

export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS_COPY[status];
  return <span className={`badge badge-${s.tone}`}>{s.label}</span>;
}

const STATE_COPY = {
  pass: { label: "Pass", tone: "ok", icon: "✓" },
  fail: { label: "Fail", tone: "bad", icon: "✕" },
  insufficient: { label: "Insufficient evidence", tone: "neutral", icon: "?" },
} as const;

/** In fixture runs the state is shown with a neutral demo style so it never reads as evidence. */
export function StateBadge({ state, demo = false }: { state: keyof typeof STATE_COPY; demo?: boolean }) {
  const s = STATE_COPY[state];
  return (
    <span className={`badge badge-${demo ? "demo" : s.tone}`} title={demo ? "Computed on fixture data; not evidence" : undefined}>
      <span aria-hidden="true">{s.icon}</span> {demo ? `Demo: ${s.label.toLowerCase()}` : s.label}
    </span>
  );
}
