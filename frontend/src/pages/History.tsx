import { useCallback, useEffect, useState } from "react";
import { ApiError, listScans } from "../api";
import { EmptyState, ErrorNotice, Loading, StatusPill } from "../components/ui";
import { formatDate } from "../format";
import type { ScanSummary } from "../types";

const PAGE = 25;

export default function History({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<ScanSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMore = useCallback(async (offset: number) => {
    try {
      const page = await listScans(PAGE, offset);
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load scan history.");
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
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load scan history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Scan history</h1>
        <p>Saved scans include the target, score and finding details – never page bodies.</p>
      </header>
      {error && <ErrorNotice message={error} />}
      {loading && items.length === 0 && <Loading label="Loading history…" />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title="No scans yet">Completed scans will be listed here.</EmptyState>
      )}
      {items.length > 0 && (
        <div className="card table-wrap">
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
                  <td style={{ overflowWrap: "anywhere" }}>{s.host}</td>
                  <td>
                    <StatusPill status={s.status} />
                  </td>
                  <td>{s.score != null ? `${s.score} (${s.grade})` : "–"}</td>
                  <td>{Object.values(s.counts).reduce((a, b) => a + (b ?? 0), 0)}</td>
                  <td>{formatDate(s.created_at)}</td>
                  <td>
                    <button className="btn-ghost" type="button" onClick={() => onOpen(s.id)} aria-label={`Open scan of ${s.host}`}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {items.length < total && (
        <button className="btn-ghost" type="button" disabled={loading} onClick={() => {
            setLoading(true);
            void loadMore(items.length);
          }}>
          Load more
        </button>
      )}
    </div>
  );
}
