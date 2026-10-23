import { useRef, useState, type FormEvent } from "react";
import { ApiError, createScan } from "../api";
import { ErrorNotice } from "./ui";

let keyCounter = 0;

/** A fresh key for one scan request: sent again unchanged if the same request is repeated. */
function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto)
    return crypto.randomUUID();
  keyCounter += 1;
  return `k-${Date.now().toString(36)}-${keyCounter}`;
}

export default function ScanForm({
  onStarted,
  verifiedHosts = [],
}: {
  onStarted: (scanId: string) => void;
  /** Verified sites, offered as one-click choices so nobody has to type a URL first. */
  verifiedHosts?: string[];
}) {
  const [url, setUrl] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The same key is reused while the request is the same, so a double click or a retry after a lost
  // answer returns the scan already started instead of making a second one.
  const keyRef = useRef<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      keyRef.current ??= newIdempotencyKey();
      const scan = await createScan(url.trim(), authorized, keyRef.current);
      keyRef.current = null;
      onStarted(scan.id);
    } catch (err) {
      // A refused request made no scan, so it gets a new key; after a network or server error the outcome is
      // unknown, so the same key is kept for the retry.
      if (err instanceof ApiError && err.status >= 400 && err.status < 500)
        keyRef.current = null;
      setError(
        err instanceof ApiError ? err.message : "Could not start the scan.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="card scan-form"
      onSubmit={submit}
      aria-labelledby="scan-form-title"
    >
      <h2 id="scan-form-title">Start a scan</h2>
      {verifiedHosts.length > 0 && (
        <div className="row" role="group" aria-label="Your verified sites">
          <span className="muted small">Verified sites:</span>
          {verifiedHosts.map((host) => (
            <button
              key={host}
              type="button"
              className="chip"
              onClick={() => {
                keyRef.current = null;
                setUrl(`https://${host}/`);
              }}
            >
              {host}
            </button>
          ))}
        </div>
      )}
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
            onChange={(e) => {
              keyRef.current = null;
              setUrl(e.target.value);
            }}
            required
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "scan-error" : undefined}
            autoComplete="off"
          />
          <button
            className="btn"
            type="submit"
            disabled={busy || !authorized || url.trim() === ""}
          >
            {busy ? "Starting…" : "Start scan"}
          </button>
        </div>
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={authorized}
          onChange={(e) => setAuthorized(e.target.checked)}
        />
        <span>
          I own this website or have written authorization to test it. Ownership
          of the domain must also be verified under Targets before a scan can
          run.
        </span>
      </label>
      {error && (
        <div id="scan-error">
          <ErrorNotice message={error} />
          {/verified/i.test(error) && (
            <p className="small">
              <a href="#/targets">Go to Targets</a> to add and verify this
              domain.
            </p>
          )}
        </div>
      )}
    </form>
  );
}
