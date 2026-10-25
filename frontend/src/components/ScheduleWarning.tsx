import { useEffect, useState } from "react";
import * as api from "../api";
import type { Schedule } from "../types";

/** What is wrong with a schedule, in words; null when nothing is. */
export function scheduleProblem(s: Schedule): string | null {
  if (s.health === "overdue") {
    return "The scheduled scan is late. It should have run already; it will run as soon as the service is back.";
  }
  if (s.health === "problem") {
    return `The last scheduled scan did not complete${s.last_outcome ? ` (${s.last_outcome})` : ""}.`;
  }
  return null;
}

/** A short notice on the Overview when a scheduled scan is late or failed. It shows nothing otherwise. */
export default function ScheduleWarning() {
  const [late, setLate] = useState<Schedule[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .listSchedules()
      .then((list) => {
        const items: unknown = list?.items;
        if (cancelled || !Array.isArray(items)) return;
        setLate(
          (items as Schedule[]).filter(
            (s) => s.health === "overdue" || s.health === "problem",
          ),
        );
      })
      .catch(() => undefined); // a warning is optional; never block the page on it
    return () => {
      cancelled = true;
    };
  }, []);

  if (late.length === 0) return null;
  return (
    <div
      className="notice notice-info"
      role="note"
      data-testid="schedule-warning"
    >
      <strong>
        {late.length === 1
          ? "A scheduled scan needs attention."
          : `${late.length} scheduled scans need attention.`}
      </strong>{" "}
      {late.map((s) => s.hostname).join(", ")}.{" "}
      <a href="#/targets">See scheduled scans</a>
    </div>
  );
}
