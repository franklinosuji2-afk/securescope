import { useEffect, useState } from "react";
import * as api from "../api";
import { formatDate } from "../format";
import type { Webhook, WebhookList } from "../types";
import { ErrorNotice, Loading } from "./ui";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function lastDelivery(w: Webhook): string {
  if (!w.enabled) {
    return w.consecutive_failures > 0
      ? `Switched off after ${w.consecutive_failures} failed deliveries in a row. Fix the receiver, then switch it on.`
      : "Switched off.";
  }
  if (!w.last_attempt_at) return "No message sent yet.";
  return `Last attempt ${formatDate(w.last_attempt_at)}: ${w.last_status ?? "unknown"}`;
}

function SecretBox({
  secret,
  onClose,
}: {
  secret: string;
  onClose: () => void;
}) {
  const [note, setNote] = useState<string | null>(null);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret);
      setNote("Secret copied.");
    } catch {
      setNote("Copying was blocked. Select the secret and copy it yourself.");
    }
  };
  return (
    <div className="notice notice-info form-stack" role="status">
      <p>
        <strong>Signing secret.</strong> Copy it now. It is shown only once. Use
        it to check that a message really came from SecureScope.
      </p>
      <code className="break-all">{secret}</code>
      <div className="actions">
        <button className="btn-ghost" type="button" onClick={() => void copy()}>
          Copy secret
        </button>
        <button className="btn-ghost" type="button" onClick={onClose}>
          I have saved it
        </button>
      </div>
      {note && <p className="muted small">{note}</p>}
    </div>
  );
}

function Row({
  hook,
  manage,
  onChange,
  onRemoved,
  onSecret,
}: {
  hook: Webhook;
  manage: boolean;
  onChange: (next: Webhook) => void;
  onRemoved: () => void;
  onSecret: (secret: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      await work();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="card form-stack">
      <h3 className="break-all">{hook.address}</h3>
      <p className="muted small">{lastDelivery(hook)}</p>
      {manage && (
        <div className="actions">
          <button
            className="btn-ghost"
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const r = await api.testWebhook(hook.id);
                setResult(
                  r.ok
                    ? `Test message delivered. ${r.status}`
                    : `Test message failed. ${r.status}`,
                );
                onChange(
                  (await api.listWebhooks()).items.find(
                    (i) => i.id === hook.id,
                  ) ?? hook,
                );
              })
            }
          >
            Send test message
          </button>
          <button
            className="btn-ghost"
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                onChange(await api.setWebhookEnabled(hook.id, !hook.enabled));
              })
            }
          >
            {hook.enabled ? "Switch off" : "Switch on"}
          </button>
          <button
            className="btn-ghost"
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const renewed = await api.renewWebhookSecret(hook.id);
                onSecret(renewed.signing_secret);
              })
            }
          >
            Renew secret
          </button>
          {confirming ? (
            <>
              <button
                className="btn-danger"
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api.deleteWebhook(hook.id);
                    onRemoved();
                  })
                }
              >
                Confirm removal of {hook.address}
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
      {result && (
        <p className="muted small" role="status">
          {result}
        </p>
      )}
      {error && <ErrorNotice message={error} />}
    </li>
  );
}

export default function WebhookAlerts({ manage }: { manage: boolean }) {
  const [data, setData] = useState<WebhookList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listWebhooks()
      .then((list) => {
        if (!cancelled) setData(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const add = async () => {
    if (!data) return;
    setBusy(true);
    setFormError(null);
    try {
      const created = await api.createWebhook(url.trim());
      const { signing_secret, ...hook } = created;
      setData({ ...data, items: [...data.items, hook] });
      setSecret(signing_secret);
      setUrl("");
    } catch (err) {
      setFormError(message(err));
    } finally {
      setBusy(false);
    }
  };

  const usable = data?.available === true && data.configured;
  return (
    <section className="stack" aria-labelledby="h-webhooks">
      <h2 id="h-webhooks">Webhook alerts</h2>
      <p className="muted">
        Send the same alerts as the email to your own server, so they can reach
        a chat tool, a ticket system or a script. SecureScope sends a signed
        JSON message over HTTPS when a scheduled scan finds something new or the
        score drops by 5 points or more. No evidence or page content is
        included.
      </p>
      {error && <ErrorNotice message={error} />}
      {!data && !error && <Loading label="Loading webhooks…" />}
      {data && !data.available && (
        <div className="notice notice-info">
          Webhook alerts are part of the Professional and Agency plans, which
          are not on sale yet. Your plan does not include webhook alerts.
        </div>
      )}
      {data && data.available && !data.configured && (
        <div className="notice notice-info">
          Webhook alerts are not switched on for this server yet.
        </div>
      )}
      {secret && <SecretBox secret={secret} onClose={() => setSecret(null)} />}
      {data && usable && data.items.length === 0 && (
        <p className="muted">No webhook address yet.</p>
      )}
      {data && usable && data.items.length > 0 && (
        <ul className="plain-list stack">
          {data.items.map((hook) => (
            <Row
              key={hook.id}
              hook={hook}
              manage={manage}
              onChange={(next) =>
                setData({
                  ...data,
                  items: data.items.map((i) => (i.id === next.id ? next : i)),
                })
              }
              onRemoved={() =>
                setData({
                  ...data,
                  items: data.items.filter((i) => i.id !== hook.id),
                })
              }
              onSecret={setSecret}
            />
          ))}
        </ul>
      )}
      {data && usable && manage && data.items.length < data.limit && (
        <form
          className="card form-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void add();
          }}
        >
          <label htmlFor="webhook-url">Webhook address</label>
          <input
            id="webhook-url"
            className="input"
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder="https://example.com/securescope-alerts"
            value={url}
            maxLength={2048}
            onChange={(e) => setUrl(e.target.value)}
            aria-describedby="webhook-help"
          />
          <p id="webhook-help" className="muted small">
            Must start with https:// and point to a public server. Up to{" "}
            {data.limit} addresses. The address is stored but only its host name
            is shown again.
          </p>
          {formError && <ErrorNotice message={formError} />}
          <div className="actions">
            <button
              className="btn"
              type="submit"
              disabled={busy || url.trim().length < 8}
            >
              Add webhook address
            </button>
          </div>
        </form>
      )}
      {data && usable && (
        <details className="card">
          <summary>How to check a message</summary>
          <p className="muted small">
            Each request has the header{" "}
            <code>
              X-SecureScope-Signature: t=&lt;seconds&gt;,v1=&lt;hex&gt;
            </code>
            . Compute HMAC-SHA256 with your signing secret over{" "}
            <code>&lt;t&gt;.&lt;raw request body&gt;</code>, compare it with{" "}
            <code>v1</code> in constant time, and reject messages whose{" "}
            <code>t</code> is more than a few minutes old. The event name is in
            the body and in <code>X-SecureScope-Event</code>. Answer with any
            2xx status; redirects are not followed.
          </p>
        </details>
      )}
    </section>
  );
}
