import { useState, type FormEvent } from "react";
import { ApiError, createScan } from "../api";
import { ErrorNotice } from "./ui";

export default function ScanForm({ onStarted }: { onStarted: (scanId: string) => void }) {
  const [url, setUrl] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const scan = await createScan(url.trim(), authorized);
      onStarted(scan.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the scan.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card scan-form" onSubmit={submit} aria-labelledby="scan-form-title">
      <h2 id="scan-form-title">Start a scan</h2>
      <div>
        <label className="field-label" htmlFor="target-url">
          Target URL
        </label>
        <div className="input-row" style={{ marginTop: 6 }}>
          <input
            id="target-url"
            className="input"
            type="url"
            inputMode="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "scan-error" : undefined}
            autoComplete="off"
          />
          <button className="btn" type="submit" disabled={busy || !authorized || url.trim() === ""}>
            {busy ? "Starting…" : "Start scan"}
          </button>
        </div>
      </div>
      <label className="check">
        <input type="checkbox" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} />
        <span>
          I own this website or have written authorization to test it. Ownership of the domain must also be verified
          under Targets before a scan can run.
        </span>
      </label>
      {error && (
        <div id="scan-error">
          <ErrorNotice message={error} />
          {/verified/i.test(error) && (
            <p className="small">
              <a href="#/targets">Go to Targets</a> to add and verify this domain.
            </p>
          )}
        </div>
      )}
    </form>
  );
}
