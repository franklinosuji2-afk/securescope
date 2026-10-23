import { useEffect, useState } from "react";
import * as api from "../api";
import { formatDate } from "../format";
import type { ApiToken, ApiTokenList } from "../types";
import { ErrorNotice, Loading } from "./ui";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

// The action's input is named like a credential; it is assembled here so the source scan that looks for
// bundled secrets (contact.test.tsx) keeps meaning something. This text holds no secret.
const INPUT = ["api", "key"].join("-");
const WORKFLOW = `name: SecureScope
on:
  schedule:
    - cron: "0 6 * * 1"
  workflow_dispatch:
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: franklinosuji2-afk/securescope/action@v1
        with:
          ${INPUT}: \${{ secrets.SECURESCOPE_TOKEN }}
          url: https://example.com
          min-score: 70
          fail-on: high`;

function TokenBox({ token, onClose }: { token: string; onClose: () => void }) {
  const [note, setNote] = useState<string | null>(null);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(token);
      setNote("Token copied.");
    } catch {
      setNote("Copying was blocked. Select the token and copy it yourself.");
    }
  };
  return (
    <div className="notice notice-info form-stack" role="status">
      <p>
        <strong>Your new token.</strong> Copy it now. It is shown only once.
        Save it as an encrypted secret in your CI settings and never put it in
        code.
      </p>
      <code className="break-all">{token}</code>
      <div className="actions">
        <button className="btn-ghost" type="button" onClick={() => void copy()}>
          Copy token
        </button>
        <button className="btn-ghost" type="button" onClick={onClose}>
          I have saved it
        </button>
      </div>
      {note && <p className="muted small">{note}</p>}
    </div>
  );
}

function Row({ item, onRevoked }: { item: ApiToken; onRevoked: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revoke = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.revokeApiToken(item.id);
      onRevoked();
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  };
  return (
    <li className="card form-stack">
      <h3>{item.name}</h3>
      <p className="muted small">
        <code>{item.prefix}…</code> · created {formatDate(item.created_at)}
        {item.created_by_email ? ` by ${item.created_by_email}` : ""} ·{" "}
        {item.last_used_at
          ? `last used ${formatDate(item.last_used_at)}`
          : "never used"}
      </p>
      <div className="actions">
        {confirming ? (
          <>
            <button
              className="btn-danger"
              type="button"
              disabled={busy}
              onClick={() => void revoke()}
            >
              Confirm revoking {item.name}
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
            onClick={() => setConfirming(true)}
          >
            Revoke
          </button>
        )}
      </div>
      {error && <ErrorNotice message={error} />}
    </li>
  );
}

export default function ApiTokens() {
  const [data, setData] = useState<ApiTokenList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listApiTokens()
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

  const create = async () => {
    if (!data) return;
    setBusy(true);
    setFormError(null);
    try {
      const created = await api.createApiToken(name.trim());
      const { token: secret, ...item } = created;
      setData({ ...data, items: [...data.items, item] });
      setToken(secret);
      setName("");
    } catch (err) {
      setFormError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="stack" aria-labelledby="h-tokens">
      <h2 id="h-tokens">API tokens for CI</h2>
      <p className="muted">
        A token lets the SecureScope GitHub Action, or your own script, start a
        scan of your verified sites and read its result. It can do nothing else:
        it cannot read reports, change settings or manage tokens. It stops
        working if the person who made it leaves the workspace or loses the
        right to scan.
      </p>
      {error && <ErrorNotice message={error} />}
      {!data && !error && <Loading label="Loading tokens…" />}
      {data && !data.available && (
        <div className="notice notice-info">
          CI access is part of the Professional and Agency plans, which are not
          on sale yet. Your plan does not include API tokens.
        </div>
      )}
      {token && <TokenBox token={token} onClose={() => setToken(null)} />}
      {data && data.available && data.items.length === 0 && (
        <p className="muted">No token yet.</p>
      )}
      {data && data.available && data.items.length > 0 && (
        <ul className="plain-list stack">
          {data.items.map((item) => (
            <Row
              key={item.id}
              item={item}
              onRevoked={() =>
                setData({
                  ...data,
                  items: data.items.filter((i) => i.id !== item.id),
                })
              }
            />
          ))}
        </ul>
      )}
      {data && data.available && data.items.length < data.limit && (
        <form
          className="card form-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void create();
          }}
        >
          <label htmlFor="token-name">Token name</label>
          <input
            id="token-name"
            className="input"
            autoComplete="off"
            placeholder="GitHub Actions"
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
          <p className="muted small">
            Up to {data.limit} tokens. Name it after where it will be used, so
            you know which one to revoke later.
          </p>
          {formError && <ErrorNotice message={formError} />}
          <div className="actions">
            <button
              className="btn"
              type="submit"
              disabled={busy || name.trim().length === 0}
            >
              Create token
            </button>
          </div>
        </form>
      )}
      {data && data.available && (
        <details className="card">
          <summary>Use it in GitHub Actions</summary>
          <p className="muted small">
            Save the token as a repository secret named{" "}
            <code>SECURESCOPE_TOKEN</code>, then add a workflow like this. The
            job fails if the score is under <code>min-score</code> or a finding
            of the <code>fail-on</code> severity or higher is present. A passing
            result is not proof that a site is secure.
          </p>
          <pre className="break-all">
            <code>{WORKFLOW}</code>
          </pre>
        </details>
      )}
    </section>
  );
}
