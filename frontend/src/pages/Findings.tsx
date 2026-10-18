import { useMemo, useState } from "react";
import FindingDetail from "../components/FindingDetail";
import FindingRows from "../components/FindingRows";
import { ReportButtons } from "../components/ScanView";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import { severityLabel, statusLabel } from "../format";
import type { Route } from "../router";
import type { Finding, FindingStatus, Severity } from "../types";
import { FINDING_STATUSES, SEVERITIES } from "../types";
import { useScan } from "../useScan";

type SortKey = "severity" | "title";

export function filterFindings(
  findings: Finding[],
  opts: { severity: Severity | "all"; category: string; query: string; sort: SortKey; status?: FindingStatus | "all" },
): Finding[] {
  const q = opts.query.trim().toLowerCase();
  const rank = (s: Severity) => SEVERITIES.indexOf(s);
  return findings
    .filter((f) => opts.severity === "all" || f.severity === opts.severity)
    .filter((f) => opts.category === "all" || f.category === opts.category)
    .filter((f) => !opts.status || opts.status === "all" || f.status === opts.status)
    .filter(
      (f) => !q || [f.title, f.id, f.category, f.description].some((text) => text.toLowerCase().includes(q)),
    )
    .sort((a, b) =>
      opts.sort === "title" ? a.title.localeCompare(b.title) : rank(a.severity) - rank(b.severity) || a.title.localeCompare(b.title),
    );
}

export default function Findings({ route }: { route: Route }) {
  const { scan, loading, error, reload } = useScan(route.scanId);
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<FindingStatus | "all">("all");
  const [sort, setSort] = useState<SortKey>("severity");

  const findings = useMemo(() => scan?.findings ?? [], [scan]);
  const categories = useMemo(() => [...new Set(findings.map((f) => f.category))].sort(), [findings]);
  const shown = useMemo(
    () => filterFindings(findings, { severity, category, query, sort, status }),
    [findings, severity, category, query, sort, status],
  );
  const filtering = severity !== "all" || category !== "all" || query !== "" || status !== "all";
  const reset = () => {
    setSeverity("all");
    setCategory("all");
    setQuery("");
    setStatus("all");
    setSort("severity");
  };

  if (route.scanId && route.findingId && scan) {
    const finding = findings.find((f) => f.id === route.findingId);
    if (finding) return <FindingDetail scan={scan} finding={finding} onChanged={reload} />;
  }

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Findings</h1>
        <p>What is wrong, how serious it is and how to fix it. Open a finding for the evidence and a fix you can adapt.</p>
      </header>
      {!route.scanId && (
        <EmptyState title="No scan selected">Start a scan from Overview or open one from Scan History.</EmptyState>
      )}
      {error && <ErrorNotice message={error} />}
      {loading && !scan && <Loading label="Loading findings…" />}
      {scan && route.findingId && !findings.some((f) => f.id === route.findingId) && (
        <ErrorNotice message="That finding is not part of this scan." />
      )}
      {scan && (
        <>
          {scan.status === "failed" && <ErrorNotice message={scan.error ?? "The scan failed, so there are no findings."} />}
          {scan.status === "cancelled" && (
            <div className="notice notice-info" role="note">
              This scan was cancelled before it finished, so there are no findings from it.
            </div>
          )}
          {(scan.status === "queued" || scan.status === "running") && <Loading label="Scan in progress…" />}
          {findings.length > 0 && (
            <form className="toolbar" role="search" aria-label="Filter findings" onSubmit={(e) => e.preventDefault()}>
              <label className="toolbar-field">
                <span className="field-label">Search</span>
                <input
                  className="input"
                  type="search"
                  value={query}
                  placeholder="Title, ID or text"
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <label className="toolbar-field">
                <span className="field-label">Category</span>
                <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="all">All categories</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="toolbar-field">
                <span className="field-label">Status</span>
                <select className="input" value={status} onChange={(e) => setStatus(e.target.value as FindingStatus | "all")}>
                  <option value="all">All statuses</option>
                  {FINDING_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {statusLabel(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="toolbar-field">
                <span className="field-label">Sort by</span>
                <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  <option value="severity">Severity</option>
                  <option value="title">Title (A–Z)</option>
                </select>
              </label>
            </form>
          )}
          {findings.length > 0 && (
            <div className="chips" role="group" aria-label="Filter by severity">
              <button className="chip" type="button" aria-pressed={severity === "all"} onClick={() => setSeverity("all")}>
                All ({findings.length})
              </button>
              {SEVERITIES.map((s) => {
                const n = findings.filter((f) => f.severity === s).length;
                return n ? (
                  <button key={s} className="chip" type="button" aria-pressed={severity === s} onClick={() => setSeverity(s)}>
                    {severityLabel(s)} ({n})
                  </button>
                ) : null;
              })}
            </div>
          )}
          {findings.length > 0 && (
            <p className="muted small" role="status">
              Showing {shown.length} of {findings.length} findings.{" "}
              {filtering && (
                <button className="link-btn" type="button" onClick={reset}>
                  Reset filters
                </button>
              )}
            </p>
          )}
          {scan.status === "completed" && findings.length === 0 && (
            <EmptyState title="No findings from these checks">
              That is not proof the site is secure – these checks are limited and passive.
            </EmptyState>
          )}
          {findings.length > 0 && shown.length === 0 && (
            <EmptyState title="No findings match these filters">
              <button className="btn-ghost" type="button" onClick={reset}>
                Reset filters
              </button>
            </EmptyState>
          )}
          {shown.length > 0 && <FindingRows scanId={scan.id} findings={shown} />}
          {scan.status === "completed" && <ReportButtons scanId={scan.id} />}
        </>
      )}
    </div>
  );
}
