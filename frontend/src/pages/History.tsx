import { useCallback, useEffect, useState } from "react";
import { ApiError, cancelScan, listScans, retryScan } from "../api";
import { useAuth } from "../auth";
import { EmptyState, ErrorNotice, Loading, StatusPill } from "../components/ui";
import { formatDate } from "../format";
import type { ScanSummary } from "../types";
import { rescanLabel } from "../components/RescanButton";
import { canScan, isActive } from "../types";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "../history.css";

const PAGE = 25;

export default function History({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<ScanSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const { organization } = useAuth();
  const mayControl = organization ? canScan(organization.role) : false;

  async function control(scan: ScanSummary, action: "cancel" | "retry") {
    setBusyId(scan.id);
    try {
      if (action === "cancel") {
        await cancelScan(scan.id);
        setRefresh((n) => n + 1);
      } else {
        onOpen((await retryScan(scan.id)).id);
      }
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "That did not work. Try again.",
      );
    } finally {
      setBusyId(null);
    }
  }

  const loadMore = useCallback(async (offset: number) => {
    try {
      const page = await listScans(PAGE, offset);
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load scan history.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listScans(PAGE, 0)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? err.message
              : "Could not load scan history.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  return (
    <div className="stack hist">
      <header className="page-head">
        <h1>Scan history</h1>
        <p>
          Saved scans include the target, score and finding details, never page
          bodies.
        </p>
      </header>
      {error && <ErrorNotice message={error} />}
      {loading && items.length === 0 && <Loading label="Loading history…" />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title="No scans yet">
          Completed scans will be listed here.
        </EmptyState>
      )}
      {items.length > 0 && (
        <div
          className="table-wrap hist-table"
          role="region"
          tabIndex={0}
          aria-label="Scan history (scrolls sideways on small screens)"
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Target</th>
                <th scope="col">Status</th>
                <th scope="col">Score</th>
                <th scope="col">Findings</th>
                <th scope="col">Started</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td className="hist-host" data-label="Target">
                    {s.host}
                  </td>
                  <td data-label="Status">
                    <StatusPill status={s.status} />
                  </td>
                  <td className="hist-score" data-label="Score">
                    {s.score != null ? `${s.score} (${s.grade})` : "–"}
                  </td>
                  <td className="hist-count" data-label="Findings">
                    {Object.values(s.counts).reduce((a, b) => a + (b ?? 0), 0)}
                  </td>
                  <td data-label="Started">{formatDate(s.created_at)}</td>
                  <td>
                    <div className="row">
                      <button
                        className="btn-ghost"
                        type="button"
                        onClick={() => onOpen(s.id)}
                        aria-label={`Open scan of ${s.host}`}
                      >
                        Open
                      </button>
                      {mayControl && isActive(s.status) && (
                        <button
                          className="btn-ghost"
                          type="button"
                          disabled={busyId === s.id}
                          onClick={() => void control(s, "cancel")}
                          aria-label={`Cancel scan of ${s.host}`}
                        >
                          Cancel
                        </button>
                      )}
                      {mayControl && !isActive(s.status) && (
                        <button
                          className="btn-ghost"
                          type="button"
                          disabled={busyId === s.id}
                          onClick={() => void control(s, "retry")}
                          aria-label={`${rescanLabel(s.status)} of ${s.host}`}
                        >
                          {s.status === "failed" || s.status === "cancelled"
                            ? "Retry"
                            : "Scan again"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {items.length < total && (
        <button
          className="btn-ghost"
          type="button"
          disabled={loading}
          onClick={() => {
            setLoading(true);
            void loadMore(items.length);
          }}
        >
          Load more
        </button>
      )}
    </div>
  );
}
