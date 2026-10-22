import { useEffect, useState } from "react";
import { ApiError, listAuditEvents } from "../api";
import { useAuth } from "../auth";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import { auditLabel, formatDate } from "../format";
import { buildHash } from "../router";
import type { AuditEntry } from "../types";
import { canReadAudit } from "../types";

const PAGE = 25;

function Resource({ entry }: { entry: AuditEntry }) {
  if (!entry.resource_type || !entry.resource_id)
    return <span className="muted">–</span>;
  const short = entry.resource_id.slice(0, 8);
  const label = `${entry.resource_type} ${short}`;
  if (entry.resource_type === "scan") {
    return (
      <a
        href={buildHash("findings", entry.resource_id)}
        aria-label={`Open scan ${short}`}
      >
        scan <code>{short}</code>
      </a>
    );
  }
  return (
    <span title={entry.resource_id}>
      {entry.resource_type} <code aria-label={label}>{short}</code>
    </span>
  );
}

export default function Audit() {
  const { organization } = useAuth();
  const allowed = organization ? canReadAudit(organization.role) : false;
  const [eventType, setEventType] = useState("");
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [types, setTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const orgId = organization?.id ?? null;
  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    listAuditEvents(PAGE, 0, eventType)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
        setTypes(page.event_types);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? err.message
              : "Could not load the audit log.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [allowed, eventType, orgId]);

  function choose(next: string) {
    setLoading(true);
    setItems([]);
    setEventType(next);
  }

  async function loadMore() {
    setLoading(true);
    try {
      const page = await listAuditEvents(PAGE, items.length, eventType);
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load more events.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Audit log</h1>
        <p>
          Who did what in this organization, newest first. Only owners and
          admins can see it.
        </p>
      </header>
      {!allowed ? (
        <div className="notice notice-info" role="note">
          Your role ({organization?.role ?? "none"}) cannot view the audit log.
          Ask an owner or admin.
        </div>
      ) : (
        <>
          <form
            className="toolbar"
            aria-label="Filter the audit log"
            onSubmit={(e) => e.preventDefault()}
          >
            <label className="toolbar-field">
              <span className="field-label">Event</span>
              <select
                className="input"
                value={eventType}
                onChange={(e) => choose(e.target.value)}
              >
                <option value="">All events</option>
                {types.map((t) => (
                  <option key={t} value={t}>
                    {auditLabel(t)}
                  </option>
                ))}
              </select>
            </label>
          </form>
          {error && <ErrorNotice message={error} />}
          {loading && items.length === 0 && (
            <Loading label="Loading the audit log…" />
          )}
          {!loading && !error && items.length === 0 && (
            <EmptyState title="No events">
              Nothing matches this filter yet.
            </EmptyState>
          )}
          {items.length > 0 && (
            <>
              <p className="muted small" role="status">
                Showing {items.length} of {total} events.
              </p>
              <div
                className="card table-wrap"
                role="region"
                tabIndex={0}
                aria-label="Audit events (scrolls sideways on small screens)"
              >
                <table>
                  <caption className="visually-hidden">
                    Audit events, newest first
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">When</th>
                      <th scope="col">Event</th>
                      <th scope="col">By</th>
                      <th scope="col">Resource</th>
                      <th scope="col">Request</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((e) => (
                      <tr key={e.id}>
                        <td>{formatDate(e.timestamp)}</td>
                        <td>{auditLabel(e.event_type)}</td>
                        <td style={{ overflowWrap: "anywhere" }}>
                          {e.actor_email ?? (
                            <span className="muted">
                              {e.event_type === "scan.scheduled"
                                ? "Automatic (schedule)"
                                : "No user recorded"}
                            </span>
                          )}
                        </td>
                        <td>
                          <Resource entry={e} />
                        </td>
                        <td>
                          {e.request_id ? (
                            <code title={e.request_id}>
                              {e.request_id.slice(0, 8)}
                            </code>
                          ) : (
                            <span className="muted">–</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {items.length < total && (
            <button
              className="btn-ghost"
              type="button"
              disabled={loading}
              onClick={() => void loadMore()}
            >
              Load more
            </button>
          )}
        </>
      )}
    </div>
  );
}
