import { useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { useAuth } from "../auth";
import { ErrorNotice } from "../components/ui";
import { formatDate } from "../format";
import type { PlanInfo } from "../types";
import { canManageMembers } from "../types";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function limitText(used: number, limit: number | null): string {
  return limit === null ? `${used} (no limit)` : `${used} of ${limit}`;
}

function PlanCard() {
  const { organization } = useAuth();
  const orgId = organization?.id ?? null;
  const [plan, setPlan] = useState<PlanInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const allowed = organization ? canManageMembers(organization.role) : false;

  useEffect(() => {
    if (!orgId || !allowed) return;
    let live = true;
    api
      .getPlan(orgId)
      .then((next) => {
        if (live) setPlan(next);
      })
      .catch((err: unknown) => {
        if (live) setError(message(err));
      });
    return () => {
      live = false;
    };
  }, [orgId, allowed]);

  if (!organization || !allowed) return null;
  return (
    <section className="card" aria-labelledby="account-plan">
      <h2 id="account-plan">Your plan</h2>
      {error && <ErrorNotice message={error} />}
      {plan && (
        <>
          <p>
            <strong>{plan.name}</strong>
            {plan.price_eur_month > 0
              ? ` · €${plan.price_eur_month} per month`
              : plan.plan_id === "free"
                ? " · €0"
                : ""}
          </p>
          <p className="muted small">Workspace: {organization.name}</p>
          <dl className="plan-facts">
            <dt>Websites</dt>
            <dd>{limitText(plan.usage.websites, plan.limits.websites)}</dd>
            <dt>Scans this month</dt>
            <dd>
              {limitText(
                plan.usage.scans_this_period,
                plan.limits.scans_per_month,
              )}
              {" · renews "}
              {formatDate(plan.usage.period_end)}
            </dd>
            <dt>Scan history kept</dt>
            <dd>{plan.limits.history_days} days</dd>
            <dt>Invite your team and clients</dt>
            <dd>{plan.limits.can_invite ? "Included" : "Agency plan"}</dd>
          </dl>
          <p className="muted small">
            If you reach a limit, everything you already have stays. You just
            can’t add more until the month renews or the plan changes.
          </p>
        </>
      )}
    </section>
  );
}

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setDone(true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="account-password">
      <h2 id="account-password">Change password</h2>
      <p className="muted small">
        You stay signed in on this device. Every other device is signed out.
      </p>
      <form className="scan-form" onSubmit={submit}>
        <div>
          <label className="field-label" htmlFor="current-password">
            Current password
          </label>
          <input
            id="current-password"
            className="input"
            style={{ width: "100%", marginTop: 6 }}
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <div>
          <label className="field-label" htmlFor="new-password">
            New password
          </label>
          <input
            id="new-password"
            className="input"
            style={{ width: "100%", marginTop: 6 }}
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            required
            aria-describedby="new-password-hint"
          />
          <p
            id="new-password-hint"
            className="muted small"
            style={{ marginTop: 4 }}
          >
            At least 12 characters.
          </p>
        </div>
        {error && <ErrorNotice message={error} />}
        {done && (
          <div className="notice notice-info" role="status">
            Your password was changed.
          </div>
        )}
        <button className="btn" type="submit" disabled={busy}>
          Change password
        </button>
      </form>
    </section>
  );
}

function DeleteAccount() {
  const { signOut } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(password, confirm);
      // The server ended the session; this clears what the page still holds and returns to sign-in.
      await signOut().catch(() => undefined);
      window.location.hash = "#/login";
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="account-delete">
      <h2 id="account-delete">Delete account</h2>
      <p className="small">
        This permanently deletes your account and everything only you have in
        it: your sites, scans, findings and reports. A workspace that other
        people still use is kept, and you simply leave it. This cannot be
        undone.
      </p>
      <form className="scan-form" onSubmit={submit}>
        <div>
          <label className="field-label" htmlFor="delete-password">
            Your password
          </label>
          <input
            id="delete-password"
            className="input"
            style={{ width: "100%", marginTop: 6 }}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            aria-describedby="delete-password-hint"
          />
          <p
            id="delete-password-hint"
            className="muted small"
            style={{ marginTop: 4 }}
          >
            Leave this empty if you sign in only with Google or GitHub.
          </p>
        </div>
        <div>
          <label className="field-label" htmlFor="delete-confirm">
            Type DELETE to confirm
          </label>
          <input
            id="delete-confirm"
            className="input"
            style={{ width: "100%", marginTop: 6 }}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="off"
            required
          />
        </div>
        {error && <ErrorNotice message={error} />}
        <button
          className="btn btn-danger"
          type="submit"
          disabled={busy || confirm !== "DELETE"}
        >
          Delete my account
        </button>
      </form>
    </section>
  );
}

export default function Account() {
  const { user } = useAuth();
  return (
    <div className="stack">
      <header className="page-head">
        <h1>Account</h1>
        <p>
          Signed in as <strong>{user?.email}</strong>. Manage your password and
          your account here.
        </p>
      </header>
      <PlanCard />
      <ChangePassword />
      <DeleteAccount />
    </div>
  );
}
