import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import type { Target, VerificationMethod } from "../types";
import { canManageTargets } from "../types";

const STATUS_LABEL: Record<Target["status"], string> = {
  verified: "Verified",
  pending: "Not verified",
  expired: "Challenge expired",
};

function TargetCard({
  target,
  manage,
  busy,
  onVerify,
  onRegenerate,
  onDelete,
}: {
  target: Target;
  manage: boolean;
  busy: boolean;
  onVerify: (method: VerificationMethod) => void;
  onRegenerate: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const verified = target.status === "verified";
  return (
    <li className="card target" aria-label={target.hostname}>
      <div className="target-head">
        <h3>{target.hostname}</h3>
        <span className={`pill pill-${target.status}`}>
          {STATUS_LABEL[target.status]}
        </span>
      </div>
      {verified ? (
        <p className="muted small">
          Verified {target.verified_at ? formatDate(target.verified_at) : ""} by{" "}
          {target.verification_method === "dns_txt"
            ? "DNS TXT record"
            : "HTTP file"}
          . Scans of exactly <code>{target.hostname}</code> are allowed.
          Subdomains and <code>www.</code> variants need their own entry.
        </p>
      ) : (
        <details
          className="howto"
          open={target.status === "pending" && !target.last_check_error}
        >
          <summary>How to prove you control this domain</summary>
          <p className="small muted">
            Publish <em>one</em> of the following, then press the matching
            verify button. The challenge expires on{" "}
            {formatDate(target.challenge_expires_at)}.
          </p>
          <h4 className="small">Option A: DNS TXT record</h4>
          <dl className="small">
            <dt>Name</dt>
            <dd>
              <code>{target.dns_record_name}</code>
            </dd>
            <dt>Type</dt>
            <dd>TXT</dd>
            <dt>Value</dt>
            <dd>
              <code>{target.dns_record_value}</code>
            </dd>
          </dl>
          <h4 className="small">Option B: file on your website</h4>
          <dl className="small">
            <dt>URL</dt>
            <dd>
              <code>{target.http_file_url}</code>
            </dd>
            <dt>Content</dt>
            <dd>
              <code>{target.http_file_content}</code>
            </dd>
          </dl>
        </details>
      )}
      {target.last_check_error && !verified && (
        <ErrorNotice message={target.last_check_error} />
      )}
      {manage && (
        <div className="actions">
          {!verified && target.status === "pending" && (
            <>
              <button
                className="btn"
                type="button"
                disabled={busy}
                onClick={() => onVerify("dns_txt")}
              >
                Verify DNS record
              </button>
              <button
                className="btn-ghost"
                type="button"
                disabled={busy}
                onClick={() => onVerify("http_file")}
              >
                Verify HTTP file
              </button>
            </>
          )}
          <button
            className="btn-ghost"
            type="button"
            disabled={busy}
            onClick={onRegenerate}
          >
            New challenge
          </button>
          {confirming ? (
            <>
              <button
                className="btn-danger"
                type="button"
                disabled={busy}
                onClick={onDelete}
              >
                Confirm removal of {target.hostname}
              </button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              className="btn-ghost"
              type="button"
              disabled={busy}
              onClick={() => setConfirming(true)}
            >
              Remove
            </button>
          )}
        </div>
      )}
    </li>
  );
}

export default function Targets() {
  const { organization } = useAuth();
  const orgId = organization?.id ?? null;
  const [targets, setTargets] = useState<Target[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hostname, setHostname] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const manage = organization ? canManageTargets(organization.role) : false;

  const reload = useCallback(async () => {
    try {
      setTargets(await api.listTargets());
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load targets.",
      );
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (orgId) {
      api
        .listTargets()
        .then((items) => !cancelled && setTargets(items))
        .catch(
          (err: unknown) =>
            !cancelled &&
            setError(
              err instanceof ApiError ? err.message : "Could not load targets.",
            ),
        );
    }
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  async function add(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setAdding(true);
    try {
      const created = await api.createTarget(hostname.trim());
      setHostname("");
      setNotice(
        `${created.hostname} was added. Publish the challenge below, then verify it.`,
      );
      await reload();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not add the target.",
      );
    } finally {
      setAdding(false);
    }
  }

  async function act(
    id: string,
    action: () => Promise<Target | void>,
    success?: (t: Target) => string,
  ) {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      const result = await action();
      if (result && success) setNotice(success(result));
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That did not work.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Targets</h1>
        <p>
          SecureScope only scans domains your organization has proven it
          controls. Add a domain, publish a DNS TXT record or a small file, and
          verify it. Verification is checked by the server; nothing here is
          assumed.
        </p>
      </header>
      {error && <ErrorNotice message={error} />}
      {notice && (
        <div className="notice notice-info" role="status">
          {notice}
        </div>
      )}
      {manage ? (
        <form
          className="card scan-form"
          onSubmit={add}
          aria-labelledby="target-form-title"
        >
          <h2 id="target-form-title">Add a domain</h2>
          <div className="input-row">
            <input
              id="target-hostname"
              className="input"
              aria-label="Domain name"
              placeholder="example.com"
              value={hostname}
              onChange={(e) => setHostname(e.target.value)}
              autoComplete="off"
              required
            />
            <button
              className="btn"
              type="submit"
              disabled={adding || hostname.trim() === ""}
            >
              {adding ? "Adding…" : "Add domain"}
            </button>
          </div>
          <p className="muted small">
            Domain names only: no IP addresses, ports or paths.
          </p>
        </form>
      ) : (
        <div className="notice notice-info">
          Your role can view targets but not add or verify them.
        </div>
      )}
      {targets === null && !error && <Loading label="Loading targets…" />}
      {targets?.length === 0 && (
        <EmptyState title="No targets yet">
          Add a domain you control to enable scanning.
        </EmptyState>
      )}
      {targets && targets.length > 0 && (
        <ul
          className="stack"
          style={{ listStyle: "none", padding: 0, margin: 0 }}
        >
          {targets.map((t) => (
            <TargetCard
              key={t.id}
              target={t}
              manage={manage}
              busy={busyId === t.id}
              onVerify={(method) =>
                void act(
                  t.id,
                  () => api.verifyTarget(t.id, method),
                  (r) =>
                    r.status === "verified"
                      ? `${r.hostname} is verified.`
                      : `${r.hostname} is not verified yet. See the message below.`,
                )
              }
              onRegenerate={() =>
                void act(
                  t.id,
                  () => api.regenerateChallenge(t.id),
                  (r) => `New challenge issued for ${r.hostname}.`,
                )
              }
              onDelete={() => void act(t.id, () => api.deleteTarget(t.id))}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
