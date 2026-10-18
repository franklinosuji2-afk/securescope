import { useState } from "react";
import FindingList from "../components/FindingList";
import { ReportButtons } from "../components/ScanView";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import { severityLabel } from "../format";
import type { Route } from "../router";
import type { Severity } from "../types";
import { SEVERITIES } from "../types";
import { useScan } from "../useScan";

export default function Findings({ route }: { route: Route }) {
  const { scan, loading, error } = useScan(route.scanId);
  const [filter, setFilter] = useState<Severity | "all">("all");

  const findings = scan?.findings ?? [];
  const shown = filter === "all" ? findings : findings.filter((f) => f.severity === filter);

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Findings</h1>
        <p>Each finding lists what was observed, safe evidence and how to fix it.</p>
      </header>
      {!route.scanId && (
        <EmptyState title="No scan selected">Start a scan from Overview or open one from Scan History.</EmptyState>
      )}
      {error && <ErrorNotice message={error} />}
      {loading && !scan && <Loading label="Loading findings…" />}
      {scan && (
        <>
          <div className="chips" role="group" aria-label="Filter by severity">
            <button className="chip" type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
              All ({findings.length})
            </button>
            {SEVERITIES.map((s) => {
              const n = findings.filter((f) => f.severity === s).length;
              return n ? (
                <button key={s} className="chip" type="button" aria-pressed={filter === s} onClick={() => setFilter(s)}>
                  {severityLabel(s)} ({n})
                </button>
              ) : null;
            })}
          </div>
          {scan.status !== "completed" && scan.status !== "failed" && <Loading label="Scan in progress…" />}
          {scan.status === "completed" && findings.length === 0 && (
            <EmptyState title="No findings from these checks">
              That is not proof the site is secure – these checks are limited and passive.
            </EmptyState>
          )}
          {shown.length > 0 && <FindingList findings={shown} />}
          {scan.status === "completed" && <ReportButtons scanId={scan.id} />}
        </>
      )}
    </div>
  );
}
