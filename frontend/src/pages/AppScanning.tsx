import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import {
  EmptyState,
  ErrorNotice,
  Loading,
  SeverityBadge,
} from "../components/ui";
import { formatDate } from "../format";
import { describeRun, describeUsage } from "../appScanning";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "../appscan.css";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"] as const;

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function newKey(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function Limitations({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="as-block" aria-labelledby="app-limits">
      <h2 id="app-limits" className="as-h2">
        What this scan does not cover
      </h2>
      <ul className="as-plain as-quiet">
        {items.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </section>
  );
}

function safeLink(url: string): boolean {
  return /^https:\/\//.test(url);
}

const VERDICT_LABEL: Partial<Record<api.AppResult, string>> = {
  completed_findings: "Findings detected",
  completed_no_findings: "Completed",
  incomplete: "Incomplete",
};

const KIND_LABEL: Record<string, string> = {
  dependency: "Dependency check",
  sast: "Static analysis",
  secrets: "Secret detection",
};

/** Where a finding is: the package for a dependency, the file and line for a finding in code. */
function findingPlace(f: api.AppFinding): string {
  if (f.kind === "dependency" || f.package_name)
    return [f.package_name, f.package_version].filter(Boolean).join(" ");
  if (!f.path) return "";
  return f.line ? `${f.path}:${f.line}` : f.path;
}

function formatSize(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} kB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function Result({ scan }: { scan: api.AppScan }) {
  const completed =
    scan.result === "completed_findings" ||
    scan.result === "completed_no_findings";
  const tone = completed ? "notice" : "notice notice-error";
  const withFindings = SEVERITY_ORDER.some((k) => (scan.counts[k] ?? 0) > 0);
  const onlyDependencies = scan.findings.every((f) => f.kind === "dependency");
  const dependencyRun =
    (scan.kinds ?? []).length === 0 ||
    (scan.kinds ?? []).every((k) => k === "dependency");
  return (
    <div className="as-result stack" aria-live="polite">
      <div
        className={`${tone} as-verdict${completed ? " as-verdict-ok" : ""}`}
        role="status"
      >
        <span className="as-verdict-label">
          {VERDICT_LABEL[scan.result] ?? "Did not complete"}
        </span>
        <strong>{scan.result_text}</strong>
        {scan.replayed && (
          <span className="muted">
            {" "}
            This is the result of your earlier request.
          </span>
        )}
        {!completed && scan.error && (
          <span className="as-verdict-reason">{scan.error}</span>
        )}
      </div>
      {withFindings && (
        <dl className="as-counts">
          {SEVERITY_ORDER.map((k) => (
            <div
              key={k}
              className={`as-count as-count-${k}${(scan.counts[k] ?? 0) === 0 ? " as-count-zero" : ""}`}
            >
              <dt>{k.charAt(0).toUpperCase() + k.slice(1)}</dt>
              <dd>{scan.counts[k] ?? 0}</dd>
            </div>
          ))}
        </dl>
      )}
      {scan.checks_skipped.length > 0 && (
        <section className="as-block" aria-labelledby="app-skipped">
          <h2 id="app-skipped" className="as-h2">
            Not checked
          </h2>
          <ul className="as-plain as-skipped">
            {scan.checks_skipped.map((c, i) => (
              <li key={i}>{c.reason ?? c.name ?? "Skipped"}</li>
            ))}
          </ul>
        </section>
      )}
      {scan.findings.length > 0 && (
        <section className="as-block" aria-labelledby="app-findings">
          <h2 id="app-findings" className="as-h2">
            {onlyDependencies ? "Dependency findings" : "Findings"}
          </h2>
          <ul className="as-findings">
            {scan.findings.map((f, i) => (
              <li
                key={`${f.rule_id}-${i}`}
                className={`as-finding as-finding-${f.severity}`}
              >
                <div className="as-finding-sev">
                  <SeverityBadge severity={f.severity} />
                </div>
                <div className="as-finding-body">
                  {findingPlace(f) && (
                    <div className="as-pkg">{findingPlace(f)}</div>
                  )}
                  <strong className="as-finding-title">{f.title}</strong>
                  <div className="muted small">{f.description}</div>
                  {f.remediation && (
                    <div className="small as-remedy">
                      <span className="as-fix-label">How to fix</span>{" "}
                      {f.remediation}
                    </div>
                  )}
                  {f.references
                    .filter(safeLink)
                    .slice(0, 3)
                    .map((url) => (
                      <div key={url} className="small as-ref">
                        <a href={url} rel="noreferrer noopener" target="_blank">
                          {url}
                        </a>
                      </div>
                    ))}
                </div>
                {f.kind === "dependency" ? (
                  <div className="as-fix">
                    <span className="as-fix-label">Fixed in</span>
                    <span className="as-fix-value">
                      {f.fixed_versions.length
                        ? f.fixed_versions.join(", ")
                        : "No fixed version listed"}
                    </span>
                  </div>
                ) : (
                  <div className="as-fix">
                    <span className="as-fix-label">Found by</span>
                    <span>{KIND_LABEL[f.kind] ?? f.kind}</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {completed && !withFindings && dependencyRun && (
        <EmptyState title="No known vulnerabilities in these packages">
          Every listed package version was checked and no published advisory
          names it. Check again after you change your dependencies.
        </EmptyState>
      )}
      {completed && !withFindings && !dependencyRun && (
        <EmptyState title="No findings from these checks">
          {(scan.kinds ?? []).map((k) => KIND_LABEL[k] ?? k).join(" and ")} ran
          on your pipeline and reported nothing.
        </EmptyState>
      )}
      {scan.attribution && (
        <p className="muted small as-attribution">{scan.attribution}</p>
      )}
      <Limitations items={scan.limitations} />
    </div>
  );
}

export default function AppScanning({ canCreate }: { canCreate: boolean }) {
  const [overview, setOverview] = useState<api.AppOverview | null>(null);
  const [projects, setProjects] = useState<api.AppProject[]>([]);
  const [history, setHistory] = useState<api.AppScanSummary[]>([]);
  const [projectId, setProjectId] = useState("");
  const [newName, setNewName] = useState("");
  const [files, setFiles] = useState<{ name: string; content: string }[]>([]);
  const [result, setResult] = useState<api.AppScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [key, setKey] = useState(newKey);

  const fetchAll = useCallback(
    () =>
      Promise.all([
        api.getAppOverview(),
        api.listAppProjects(),
        api.listAppScans(),
      ]),
    [],
  );
  const apply = useCallback(
    ([o, p, h]: [api.AppOverview, api.AppProject[], api.AppScanSummary[]]) => {
      setOverview(o);
      setProjects(p);
      setHistory(h);
      setProjectId((current) => current || p[0]?.id || "");
    },
    [],
  );
  const load = useCallback(
    async () => apply(await fetchAll()),
    [apply, fetchAll],
  );

  useEffect(() => {
    let live = true;
    fetchAll()
      .then((all) => {
        if (live) apply(all);
      })
      .catch((err: unknown) => {
        if (live) setError(message(err));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [fetchAll, apply]);

  const addProject = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createAppProject(newName.trim());
      setNewName("");
      await load();
      setProjectId(created.id);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  const archiveProject = async () => {
    const project = projects.find((p) => p.id === projectId);
    if (!project) return;
    if (
      !window.confirm(
        `Archive ${project.name}? It leaves the project list and frees its place in your plan. Its past runs stay in Recent runs.`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api.archiveAppProject(project.id);
      setProjectId("");
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  const chooseFiles = async (list: FileList | null) => {
    setError(null);
    setKey(newKey());
    if (!list) return;
    const max = overview?.max_file_bytes ?? 2_000_000;
    const picked: { name: string; content: string }[] = [];
    for (const file of Array.from(list)) {
      if (file.size > max) {
        setError(
          `${file.name} is larger than ${Math.round(max / 1_000_000)} MB.`,
        );
        setFiles([]);
        return;
      }
      picked.push({ name: file.name, content: await file.text() });
    }
    setFiles(picked);
  };

  const openRun = async (id: string) => {
    setOpening(id);
    setError(null);
    try {
      setResult(await api.getAppScan(id));
    } catch (err) {
      setError(message(err));
    } finally {
      setOpening(null);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.createAppScan(projectId, files, key));
      setKey(newKey());
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading label="Loading App Scanning…" />;
  if (!overview)
    return <ErrorNotice message={error ?? "App Scanning is not available."} />;
  const u = overview.usage;
  const usage = describeUsage(overview.plan, u);

  return (
    <div className="as-page">
      <header className="as-head">
        <h1 className="as-title">App Scanning</h1>
        {overview.lookups_available ? (
          <p className="as-lead">
            Reads the exact package versions in your dependency files and looks
            each one up in the OSV.dev vulnerability database. Only the package
            ecosystem, name and version are sent; your files are read in memory
            and are not stored.
          </p>
        ) : (
          <p className="as-lead">
            Reads the exact package versions in your dependency files. The
            vulnerability database is not connected on this server, so a browser
            scan cannot report vulnerabilities and ends as failed, not as clean.
            Failed runs are not counted. Your files are read in memory and are
            not stored.
          </p>
        )}
      </header>
      {error && <ErrorNotice message={error} />}

      <div className="as-layout">
        <div className="as-panel">
          {!canCreate ? (
            <div className="notice" role="status">
              Your role can view App Scanning results but cannot start scans.
            </div>
          ) : (
            <>
              <h2 className="as-h2">Check a project</h2>
              {projects.length === 0 ? (
                <EmptyState title="No projects yet">
                  Add a project, then upload a package-lock.json, package.json
                  or requirements.txt to check it.
                </EmptyState>
              ) : (
                <form className="as-form" onSubmit={(e) => void submit(e)}>
                  <label className="toolbar-field">
                    <span className="field-label">Project</span>
                    <select
                      className="input"
                      value={projectId}
                      onChange={(e) => setProjectId(e.target.value)}
                    >
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className="as-run-open as-archive"
                    disabled={busy || !projectId}
                    onClick={() => void archiveProject()}
                  >
                    Archive this project
                  </button>
                  <label className="as-drop">
                    <span className="field-label">Dependency files</span>
                    <input
                      className="as-file"
                      type="file"
                      multiple
                      accept=".json,.txt"
                      aria-describedby="app-files-hint"
                      onChange={(e) => void chooseFiles(e.target.files)}
                    />
                    <span id="app-files-hint" className="muted small">
                      Up to {overview.max_files} files:{" "}
                      {overview.supported_files.join(", ")}.
                    </span>
                  </label>
                  {files.length > 0 && (
                    <ul className="as-picked" aria-label="Selected files">
                      {files.map((f) => (
                        <li key={f.name}>
                          <span className="as-pkg">{f.name}</span>
                          <span className="muted small">
                            {formatSize(new Blob([f.content]).size)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <button
                    className="btn as-run"
                    type="submit"
                    disabled={busy || files.length === 0 || !projectId}
                  >
                    {busy ? "Checking…" : "Check dependencies"}
                  </button>
                  {busy && (
                    <p className="as-progress" role="status">
                      <span className="as-spinner" aria-hidden="true" />
                      Checking {files.length}{" "}
                      {files.length === 1 ? "file" : "files"}. This usually
                      takes a few seconds and stops after one minute at most.
                    </p>
                  )}
                </form>
              )}
              <form
                className="as-newproject"
                onSubmit={(e) => void addProject(e)}
              >
                <label className="field-label" htmlFor="app-new-project">
                  New project name
                </label>
                <span className="as-inline">
                  <input
                    id="app-new-project"
                    className="input"
                    value={newName}
                    maxLength={80}
                    required
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <button
                    className="btn btn-ghost"
                    type="submit"
                    disabled={busy}
                  >
                    Add project
                  </button>
                </span>
              </form>
            </>
          )}
          {usage ? (
            <p className="as-usage">
              Runs this month: {usage.runs}. Projects: {usage.projects}.
              {usage.resets ? ` Runs reset on ${usage.resets} (UTC).` : ""}
            </p>
          ) : (
            <div className="notice" role="status">
              Your usage figures are unavailable right now. The server still
              enforces your plan's limits.
            </div>
          )}
        </div>

        <div className="as-main stack">
          {result && <Result scan={result} />}
          {!result && <Limitations items={overview.limitations} />}

          <section className="as-block" aria-labelledby="app-history">
            <h2 id="app-history" className="as-h2">
              Recent runs
            </h2>
            {history.length === 0 ? (
              <p className="muted">No runs yet.</p>
            ) : (
              <ul className="as-runs">
                {history.slice(0, 20).map((h) => {
                  const run = describeRun(h);
                  return (
                    <li key={h.id} className="as-run-row">
                      <span className="as-run-date">
                        {formatDate(h.created_at)}
                      </span>{" "}
                      <span className="as-run-src">
                        <span className="visually-hidden">(</span>
                        {run.origin}
                        {run.ref ? `, ${run.ref}` : ""}
                        <span className="visually-hidden">)</span>
                      </span>
                      <span className="visually-hidden">: </span>
                      <span className="as-run-text">
                        {h.result_text}
                        {run.findings ? (
                          <strong className="as-run-count">{` ${run.findings}.`}</strong>
                        ) : null}{" "}
                        <button
                          type="button"
                          className="as-run-open"
                          disabled={opening !== null}
                          aria-current={
                            result?.id === h.id ? "true" : undefined
                          }
                          onClick={() => void openRun(h.id)}
                        >
                          {opening === h.id
                            ? "Opening…"
                            : result?.id === h.id
                              ? "Shown above"
                              : "View result"}
                          <span className="visually-hidden">
                            {" "}
                            from {formatDate(h.created_at)}
                          </span>
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
