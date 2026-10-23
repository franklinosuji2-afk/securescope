import { useEffect, useState } from "react";
import * as api from "../api";
import type { Badge } from "../types";
import { ErrorNotice, Loading } from "./ui";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function snippet(url: string): string {
  return `[![SecureScope](${url})](https://getsecurescope.com)`;
}

function Row({
  badge,
  manage,
  onChange,
}: {
  badge: Badge;
  manage: boolean;
  onChange: (next: Badge) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await work();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };
  const text = badge.url ? snippet(badge.url) : "";
  return (
    <li className="card form-stack">
      <h3 className="break-all">{badge.hostname}</h3>
      {badge.enabled && badge.url ? (
        <>
          <p className="muted small">
            The badge is public. Anyone with its address can see this site's
            latest score and grade, and nothing else.
          </p>
          <img src={badge.url} alt={`Score badge for ${badge.hostname}`} />
          <label htmlFor={`badge-md-${badge.target_id}`}>Markdown</label>
          <input
            id={`badge-md-${badge.target_id}`}
            className="input"
            readOnly
            value={text}
            onFocus={(e) => e.currentTarget.select()}
          />
        </>
      ) : (
        <p className="muted small">The badge is off.</p>
      )}
      {manage && (
        <div className="actions">
          <button
            className="btn-ghost"
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                onChange(await api.setBadge(badge.target_id, !badge.enabled));
              })
            }
          >
            {badge.enabled ? "Switch badge off" : "Switch badge on"}
          </button>
          {badge.enabled && (
            <>
              <button
                className="btn-ghost"
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    try {
                      await navigator.clipboard.writeText(text);
                      setNote("Markdown copied.");
                    } catch {
                      setNote("Copying was blocked. Copy it from the box.");
                    }
                  })
                }
              >
                Copy Markdown
              </button>
              <button
                className="btn-ghost"
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    onChange(await api.setBadge(badge.target_id, true, true));
                    setNote(
                      "New address made. The old one no longer works, so update where you used it.",
                    );
                  })
                }
              >
                New address
              </button>
            </>
          )}
        </div>
      )}
      {note && (
        <p className="muted small" role="status">
          {note}
        </p>
      )}
      {error && <ErrorNotice message={error} />}
    </li>
  );
}

export default function ScoreBadges({ manage }: { manage: boolean }) {
  const [items, setItems] = useState<Badge[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listBadges()
      .then((list) => {
        if (!cancelled) setItems(list.items);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="stack" aria-labelledby="h-badges">
      <h2 id="h-badges">Score badge</h2>
      <p className="muted">
        A small image for your README or website that shows the latest scan
        score of a verified site. It is off until you switch it on, and it is
        public: anyone with the address sees the score and grade. It is a
        heuristic from passive checks, not a certificate of security.
      </p>
      {error && <ErrorNotice message={error} />}
      {!items && !error && <Loading label="Loading badges…" />}
      {items && items.length === 0 && (
        <p className="muted">No verified site yet.</p>
      )}
      {items && items.length > 0 && (
        <ul className="plain-list stack">
          {items.map((badge) => (
            <Row
              key={badge.target_id}
              badge={badge}
              manage={manage}
              onChange={(next) =>
                setItems(
                  items.map((i) => (i.target_id === next.target_id ? next : i)),
                )
              }
            />
          ))}
        </ul>
      )}
    </section>
  );
}
