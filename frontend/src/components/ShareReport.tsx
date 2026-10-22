import { useCallback, useEffect, useState } from "react";
import * as api from "../api";
import { formatDate } from "../format";
import type { CreatedShare, ShareLink } from "../types";
import { ErrorNotice } from "./ui";

const LENGTHS: readonly (7 | 30 | 90)[] = [7, 30, 90];

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/** Read-only links to one report. The secret is shown once, right after it is made; afterwards only the
 * link's dates and status are listed, and it can be revoked at any time. */
export default function ShareReport({ scanId }: { scanId: string }) {
  const [links, setLinks] = useState<ShareLink[] | null>(null);
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [created, setCreated] = useState<CreatedShare | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .listShares(scanId)
      .then(setLinks)
      .catch((err: unknown) => setError(message(err)));
  }, [scanId]);
  // The parent keys this component by scan, so a different scan starts from a clean state.
  useEffect(() => {
    let live = true;
    api
      .listShares(scanId)
      .then((items) => live && setLinks(items))
      .catch((err: unknown) => live && setError(message(err)));
    return () => {
      live = false;
    };
  }, [scanId]);

  const make = async () => {
    setBusy(true);
    setError(null);
    try {
      setCreated(await api.createShare(scanId, days));
      load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };
  const revoke = async (id: string) => {
    setError(null);
    try {
      await api.revokeShare(scanId, id);
      if (created?.id === id) setCreated(null);
      load();
    } catch (err) {
      setError(message(err));
    }
  };
  const url = created ? `${window.location.origin}${created.path}` : "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setNote("Link copied.");
    } catch {
      setNote("Copying was blocked. Select the link and copy it yourself.");
    }
  };

  return (
    <details className="card share-panel">
      <summary>Share this report with a client</summary>
      <p className="muted small">
        Anyone with the link can read this one report, without an account. It
        shows the report only: no client details, notes or other scans. It stops
        working on the date shown, or when you revoke it.
      </p>
      {error && <ErrorNotice message={error} />}
      <div className="row">
        <label className="toolbar-field">
          <span className="field-label">Link stays valid for</span>
          <select
            className="input"
            value={days}
            onChange={(e) => setDays(Number(e.target.value) as 7 | 30 | 90)}
          >
            {LENGTHS.map((d) => (
              <option key={d} value={d}>
                {d} days
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => void make()}
        >
          {busy ? "Creating…" : "Create link"}
        </button>
      </div>
      {created && (
        <div className="notice share-new">
          <p>
            <strong>Copy this link now.</strong> For your security it is only
            shown once.
          </p>
          <input
            className="input"
            readOnly
            value={url}
            aria-label="Share link"
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="row">
            <button type="button" className="btn-ghost" onClick={copy}>
              Copy link
            </button>
            {note && (
              <span role="status" className="muted small">
                {note}
              </span>
            )}
          </div>
        </div>
      )}
      {links && links.length > 0 && (
        <div
          className="table-wrap"
          role="region"
          tabIndex={0}
          aria-label="Links for this report (scrolls sideways on small screens)"
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Created</th>
                <th scope="col">Expires</th>
                <th scope="col">Opened</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {links.map((l) => (
                <tr key={l.id}>
                  <td>{formatDate(l.created_at)}</td>
                  <td>{formatDate(l.expires_at)}</td>
                  <td>{l.view_count} times</td>
                  <td>
                    {l.status === "active"
                      ? "Active"
                      : l.status === "revoked"
                        ? "Revoked"
                        : "Expired"}
                  </td>
                  <td>
                    {l.status === "active" && (
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => void revoke(l.id)}
                        aria-label={`Revoke link created ${formatDate(l.created_at)}`}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {links && links.length === 0 && (
        <p className="muted small">No links yet for this report.</p>
      )}
    </details>
  );
}
