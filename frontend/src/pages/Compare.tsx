import { useEffect, useState } from "react";
import * as api from "../api";
import {
  EmptyState,
  ErrorNotice,
  Loading,
  SeverityBadge,
} from "../components/ui";
import { formatDate } from "../format";
import { buildHash, compareHash, type Route } from "../router";
import type { Finding, ScanComparison, ScanSummary } from "../types";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function Group({
  title,
  empty,
  items,
}: {
  title: string;
  empty: string;
  items: Finding[];
}) {
  return (
    <section className="card" aria-label={title}>
      <h2 className="card-title">
        {title} ({items.length})
      </h2>
      {items.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className="plain-list">
          {items.map((f) => (
            <li key={f.fingerprint ?? f.id} className="row">
              <SeverityBadge severity={f.severity} />
              <span>{f.title}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function scanLabel(s: ScanSummary): string {
  return `${formatDate(s.created_at)}, score ${s.score ?? "n/a"}`;
}

function CompareFor({
  scanId,
  other,
}: {
  scanId: string;
  other: string | null;
}) {
  const [candidates, setCandidates] = useState<ScanSummary[] | null>(null);
  const [host, setHost] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    key: string;
    data: ScanComparison;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getScan(scanId), api.listScans(100, 0)])
      .then(([scan, list]) => {
        if (cancelled) return;
        setHost(scan.host);
        setCandidates(
          list.items
            .filter(
              (s) =>
                s.host === scan.host &&
                s.status === "completed" &&
                s.id !== scanId,
            )
            .sort((a, b) => b.created_at.localeCompare(a.created_at)),
        );
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err));
      });
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  const selected = other ?? candidates?.[0]?.id ?? null;

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api
      .compareScans(scanId, selected)
      .then((data) => {
        if (cancelled) return;
        setResult({ key: selected, data });
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err));
      });
    return () => {
      cancelled = true;
    };
  }, [scanId, selected]);

  const ready = result !== null && result.key === selected;
  const data = ready ? result.data : null;

  return (
    <>
      <h1>Compare scans</h1>
      <p className="muted">
        See what changed between two scans of the same site. Findings are
        matched by their fingerprint, nothing is estimated.
      </p>
      <p>
        <a className="back-link" href={buildHash("findings", scanId)}>
          Back to the scan
        </a>
      </p>
      {error && <ErrorNotice message={error} />}
      {candidates === null && !error && <Loading label="Loading scans…" />}
      {candidates !== null && candidates.length === 0 && (
        <EmptyState title="Nothing to compare yet">
          There is no other completed scan of {host ?? "this site"}. Run another
          scan, then come back to see what changed.
        </EmptyState>
      )}
      {candidates !== null && candidates.length > 0 && (
        <div className="card form-stack">
          <label htmlFor="compare-with">Compare with</label>
          <select
            id="compare-with"
            className="input"
            value={selected ?? ""}
            onChange={(e) => {
              window.location.hash = compareHash(scanId, e.target.value);
            }}
          >
            {candidates.map((s) => (
              <option key={s.id} value={s.id}>
                {scanLabel(s)}
              </option>
            ))}
          </select>
        </div>
      )}
      {selected && !ready && !error && <Loading label="Comparing…" />}
      {data && (
        <>
          <div className="card" role="group" aria-label="Score change">
            <p>
              <strong>{data.host}</strong>
            </p>
            <p>
              Earlier: {formatDate(data.older.scanned_at)}, score{" "}
              {data.older.score ?? "n/a"}
              {data.older.grade ? ` (${data.older.grade})` : ""}
            </p>
            <p>
              Later: {formatDate(data.newer.scanned_at)}, score{" "}
              {data.newer.score ?? "n/a"}
              {data.newer.grade ? ` (${data.newer.grade})` : ""}
            </p>
            <p>
              <strong>
                {data.score_change === null
                  ? "Score change not available"
                  : data.score_change === 0
                    ? "No change in score"
                    : `${data.score_change > 0 ? "+" : ""}${data.score_change} points`}
              </strong>
            </p>
          </div>
          <Group
            title="New in the later scan"
            empty="Nothing new."
            items={data.new_findings}
          />
          <Group
            title="No longer detected"
            empty="Nothing went away."
            items={data.resolved_findings}
          />
          <Group
            title="Still present"
            empty="Nothing carried over."
            items={data.unchanged_findings}
          />
          <p className="muted small">{data.note}</p>
        </>
      )}
    </>
  );
}

export default function Compare({ route }: { route: Route }) {
  if (!route.scanId) {
    return (
      <>
        <h1>Compare scans</h1>
        <EmptyState title="Pick a scan first">
          Open a scan and choose “Compare with another scan”.
        </EmptyState>
      </>
    );
  }
  return (
    <CompareFor
      key={route.scanId}
      scanId={route.scanId}
      other={route.compareWith}
    />
  );
}
