import { useEffect, useState } from "react";
import * as api from "../api";
import { formatDate } from "../format";
import type { Schedule, ScheduleFrequency, ScheduleList } from "../types";
import { scheduleProblem } from "./ScheduleWarning";
import { ErrorNotice, Loading } from "./ui";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function status(s: Schedule): string {
  if (s.frequency === "off") return "Not scheduled.";
  const parts: string[] = [];
  parts.push(
    s.last_run_at
      ? `Last run ${formatDate(s.last_run_at)}${s.last_outcome ? `: ${s.last_outcome}` : ""}.`
      : "Not run yet. The first scan starts within about 15 minutes.",
  );
  if (s.next_run_at) parts.push(`Next run after ${formatDate(s.next_run_at)}.`);
  return parts.join(" ");
}

function Row({
  site,
  manage,
  onChange,
}: {
  site: Schedule;
  manage: boolean;
  onChange: (next: Schedule) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async (frequency: ScheduleFrequency, notify: boolean) => {
    setBusy(true);
    try {
      onChange(await api.setSchedule(site.target_id, { frequency, notify }));
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };
  const id = `schedule-${site.target_id}`;
  return (
    <li className="card form-stack">
      <h3>{site.hostname}</h3>
      <label htmlFor={id}>How often</label>
      <select
        id={id}
        className="input"
        value={site.frequency}
        disabled={!manage || busy}
        onChange={(e) =>
          void save(e.target.value as ScheduleFrequency, site.notify)
        }
      >
        <option value="off">Off</option>
        <option value="daily">Every day</option>
        <option value="weekly">Every week</option>
      </select>
      <label className="check">
        <input
          type="checkbox"
          checked={site.notify}
          disabled={!manage || busy || site.frequency === "off"}
          onChange={(e) => void save(site.frequency, e.target.checked)}
        />
        <span>
          Email me when something new or worse appears (owners, admins and
          security analysts of this workspace)
        </span>
      </label>
      <p className="muted small">{status(site)}</p>
      {scheduleProblem(site) && (
        <div className="notice notice-info" role="note">
          {scheduleProblem(site)}
        </div>
      )}
      {error && <ErrorNotice message={error} />}
    </li>
  );
}

export default function ScheduledScans({ manage }: { manage: boolean }) {
  const [data, setData] = useState<ScheduleList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listSchedules()
      .then((list) => {
        if (!cancelled) setData(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="stack" aria-labelledby="h-schedules">
      <h2 id="h-schedules">Scheduled scans</h2>
      <p className="muted">
        Scan a verified site on its own, daily or weekly. You are emailed only
        when a scan finds something new or the score drops by 5 points or more.
        Scheduled scans count toward your monthly scan allowance.
      </p>
      {error && <ErrorNotice message={error} />}
      {!data && !error && <Loading label="Loading schedules…" />}
      {data && !data.available && (
        <div className="notice notice-info">
          Scheduled scans are part of the Professional and Agency plans, which
          are not on sale yet. Your plan does not include them.
        </div>
      )}
      {data && data.available && data.items.length === 0 && (
        <p className="muted">Verify a site first, then you can schedule it.</p>
      )}
      {data && data.available && data.items.length > 0 && (
        <ul className="plain-list stack">
          {data.items.map((site) => (
            <Row
              key={site.target_id}
              site={site}
              manage={manage}
              onChange={(next) =>
                setData({
                  ...data,
                  items: data.items.map((i) =>
                    i.target_id === next.target_id ? next : i,
                  ),
                })
              }
            />
          ))}
        </ul>
      )}
    </section>
  );
}
