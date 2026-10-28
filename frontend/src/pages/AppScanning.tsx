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
    <section className="card" aria-labelledby="app-limits">
      <h2 id="app-limits">What this scan does not cover</h2>
      <ul>
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

function Result({ scan }: { scan: api.AppScan }) {
  const tone =
    scan.result === "completed_findings" ||
    scan.result === "completed_no_findings"
      ? "notice"
      : "notice notice-error";
  return (
    <div className="stack" aria-live="polite">
      <div className={tone} role="status">
        <strong>{scan.result_text}</strong>
        {scan.replayed && (
          <span className="muted">
            {" "}
            This is the result of your earlier request.
          </span>
        )}
      </div>
      {SEVERITY_ORDER.some((k) => (scan.counts[k] ?? 0) > 0) && (
        <p>
          {SEVERITY_ORDER.filter((k) => (scan.counts[k] ?? 0) > 0)
            .map((k) => `${scan.counts[k]} ${k}`)
            .join(", ")}
        </p>
      )}
      {scan.checks_skipped.length > 0 && (
        <section className="card" aria-labelledby="app-skipped">
          <h2 id="app-skipped">Not checked</h2>
          <ul>
            {scan.checks_skipped.map((c, i) => (
              <li key={i}>{c.reason ?? c.name ?? "Skipped"}</li>
            ))}
          </ul>
        </section>
      )}
      {scan.findings.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Dependency findings</caption>
            <thead>
              <tr>
                <th scope="col">Severity</th>
                <th scope="col">Package</th>
                <th scope="col">Advisory</th>
                <th scope="col">Fixed in</th>
              </tr>
            </thead>
            <tbody>
              {scan.findings.map((f, i) => (
                <tr key={`${f.rule_id}-${i}`}>
                  <td>
                    <SeverityBadge severity={f.severity} />
                  </td>
                  <td>
                    {f.package_name} {f.package_version}
                  </td>
                  <td>
                    <strong>{f.title}</strong>
                    <div className="muted small">{f.description}</div>
                    {f.references
                      .filter(safeLink)
                      .slice(0, 3)
                      .map((url) => (
                        <div key={url} className="small">
                          <a
                            href={url}
                            rel="noreferrer noopener"
                            target="_blank"
                          >
                            {url}
                          </a>
                        </div>
                      ))}
                  </td>
                  <td>
                    {f.fixed_versions.length
                      ? f.fixed_versions.join(", ")
                      : "No fixed version listed"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
    <div className="stack">
      <h1>App Scanning</h1>
      <p className="muted">
        Reads the exact package versions in your dependency files. The
        vulnerability database is not connected yet, so a browser scan cannot
        report vulnerabilities today and ends as failed, not as clean. Your
        files are read in memory and are not stored.
      </p>
      {error && <ErrorNotice message={error} />}
      {usage ? (
        <p>
          Runs this month: {usage.runs}. Projects: {usage.projects}.
          {usage.resets ? ` Runs reset on ${usage.resets} (UTC).` : ""}
        </p>
      ) : (
        <div className="notice" role="status">
          Your usage figures are unavailable right now. The server still
          enforces your plan's limits.
        </div>
      )}

      {!canCreate ? (
        <div className="notice" role="status">
          Your role can view App Scanning results but cannot start scans.
        </div>
      ) : (
        <>
          <form className="form-stack" onSubmit={(e) => void addProject(e)}>
            <label className="toolbar-field">
              <span className="field-label">New project name</span>
              <input
                className="input"
                value={newName}
                maxLength={80}
                required
                onChange={(e) => setNewName(e.target.value)}
              />
            </label>
            <button className="btn" type="submit" disabled={busy}>
              Add project
            </button>
          </form>

          {projects.length === 0 ? (
            <EmptyState title="No projects yet">
              Add a project, then upload a package-lock.json, package.json or
              requirements.txt to check it.
            </EmptyState>
          ) : (
            <form className="form-stack" onSubmit={(e) => void submit(e)}>
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
              <label className="toolbar-field">
                <span className="field-label">Dependency files</span>
                <input
                  className="input"
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
              <button
                className="btn"
                type="submit"
                disabled={busy || files.length === 0 || !projectId}
              >
                {busy ? "Checking…" : "Check dependencies"}
              </button>
            </form>
          )}
        </>
      )}

      {result && <Result scan={result} />}
      {!result && <Limitations items={overview.limitations} />}

      <section aria-labelledby="app-history">
        <h2 id="app-history">Recent runs</h2>
        {history.length === 0 ? (
          <p className="muted">No runs yet.</p>
        ) : (
          <ul>
            {history.slice(0, 20).map((h) => {
              const run = describeRun(h);
              return (
                <li key={h.id}>
                  {formatDate(h.created_at)} ({run.origin}
                  {run.ref ? `, ${run.ref}` : ""}): {h.result_text}
                  {run.findings ? ` ${run.findings}.` : ""}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
