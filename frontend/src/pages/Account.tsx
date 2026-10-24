import { useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { useAuth } from "../auth";
import { ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import type { PlanInfo } from "../types";
import { canManageMembers } from "../types";

function message(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function limitText(used: number, limit: number | null): string {
  return limit === null ? `${used} (no limit)` : `${used} of ${limit}`;
}

function AccountDetails() {
  const [info, setInfo] = useState<api.AccountInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .getAccount()
      .then((next) => {
        if (live && next && typeof next.email === "string") setInfo(next);
      })
      .catch((err: unknown) => {
        if (live) setError(message(err));
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <section className="card" aria-labelledby="account-details">
      <h2 id="account-details">Your account</h2>
      {error && <ErrorNotice message={error} />}
      {!info && !error && <Loading label="Loading your account…" />}
      {info && (
        <dl className="plan-facts">
          <dt>Email</dt>
          <dd>
            {info.email}
            {info.email_verified ? " · verified" : " · not verified yet"}
          </dd>
          <dt>Status</dt>
          <dd>{info.status === "active" ? "Active" : info.status}</dd>
          <dt>Member since</dt>
          <dd>{formatDate(info.created_at)}</dd>
          <dt>Sign-in</dt>
          <dd>
            {info.has_password
              ? "Password"
              : "Google or GitHub (no password set)"}
          </dd>
        </dl>
      )}
    </section>
  );
}

function Devices() {
  const [sessions, setSessions] = useState<api.DeviceSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [version, setVersion] = useState(0);

  useEffect(() => {
    let live = true;
    api
      .listSessions()
      .then((next) => {
        if (live) setSessions(Array.isArray(next) ? next : []);
      })
      .catch((err: unknown) => {
        if (live) setError(message(err));
      });
    return () => {
      live = false;
    };
  }, [version]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setVersion((v) => v + 1);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  const others = sessions?.filter((s) => !s.current) ?? [];
  return (
    <section className="card" aria-labelledby="account-devices">
      <h2 id="account-devices">Signed-in devices</h2>
      <p className="muted small">
        Each browser you are signed in on appears here. If you do not recognise
        one, sign it out and change your password.
      </p>
      {error && <ErrorNotice message={error} />}
      {!sessions && !error && <Loading label="Loading devices…" />}
      {sessions && (
        <ul className="plain-list">
          {sessions.map((s) => (
            <li key={s.id} className="row" style={{ gap: 12 }}>
              <span>
                {s.current ? <strong>This device</strong> : "Another device"}
                {" · signed in "}
                {formatDate(s.created_at)}
                {" · expires "}
                {formatDate(s.expires_at)}
              </span>
              {!s.current && (
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={busy}
                  onClick={() => void run(() => api.revokeSession(s.id))}
                  aria-label={`Sign out the device signed in ${formatDate(s.created_at)}`}
                >
                  Sign out
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <button
          className="btn btn-ghost"
          type="button"
          disabled={busy}
          onClick={() => void run(() => api.revokeOtherSessions())}
        >
          Sign out all other devices
        </button>
      )}
    </section>
  );
}

const CATEGORIES: { value: api.FeedbackCategory; label: string }[] = [
  { value: "general", label: "General" },
  { value: "ease_of_use", label: "Ease of use" },
  { value: "reports", label: "Reports" },
  { value: "accuracy", label: "Accuracy of findings" },
  { value: "pricing", label: "Plans and pricing" },
  { value: "other", label: "Something else" },
];
const MESSAGE_LIMIT = 2000;

function FeedbackCard() {
  const [saved, setSaved] = useState<api.Feedback | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [rating, setRating] = useState(0);
  const [category, setCategory] = useState<string>("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .getFeedback()
      .then((next) => {
        if (!live) return;
        if (next && typeof next.rating === "number") {
          setSaved(next);
          setRating(next.rating);
          setCategory(next.category ?? "");
          setText(next.message ?? "");
        }
        setLoaded(true);
      })
      .catch((err: unknown) => {
        if (live) {
          setError(message(err));
          setLoaded(true);
        }
      });
    return () => {
      live = false;
    };
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (rating < 1) {
      setError("Choose a rating from 1 to 5 stars first.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const next = await api.saveFeedback({
        rating,
        category: (category || null) as api.FeedbackCategory | null,
        message: text.trim() || null,
      });
      setSaved(next);
      setNotice("Thank you. Your feedback was saved.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.withdrawFeedback();
      setSaved(null);
      setRating(0);
      setCategory("");
      setText("");
      setNotice("Your feedback was withdrawn and deleted.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="account-feedback">
      <h2 id="account-feedback">Your feedback</h2>
      <p className="muted small">
        Tell us how SecureScope is working for you. It is private: only the
        operator reads it, it is never published, and you can change or withdraw
        it at any time. You never need to give feedback to use or leave
        SecureScope.
      </p>
      {!loaded && <Loading label="Loading…" />}
      {loaded && (
        <form className="scan-form" onSubmit={submit}>
          <fieldset className="rating">
            <legend className="field-label">Rating</legend>
            <div className="row" role="radiogroup" aria-label="Rating">
              {[1, 2, 3, 4, 5].map((n) => (
                <label key={n} className="rating-star">
                  <input
                    type="radio"
                    name="rating"
                    value={n}
                    checked={rating === n}
                    onChange={() => setRating(n)}
                  />
                  <span aria-hidden="true">{n <= rating ? "★" : "☆"}</span>
                  <span className="visually-hidden">
                    {n} {n === 1 ? "star" : "stars"}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <label className="field-label" htmlFor="feedback-category">
              Topic (optional)
            </label>
            <select
              id="feedback-category"
              className="input"
              style={{ width: "100%", marginTop: 6 }}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">No topic</option>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="feedback-text">
              Your comments (optional)
            </label>
            <textarea
              id="feedback-text"
              className="input"
              style={{ width: "100%", marginTop: 6 }}
              rows={4}
              maxLength={MESSAGE_LIMIT}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <p className="muted small">
              {text.length} of {MESSAGE_LIMIT} characters
            </p>
          </div>
          {error && <ErrorNotice message={error} />}
          {notice && (
            <p role="status" className="muted small">
              {notice}
            </p>
          )}
          <div className="row">
            <button className="btn" type="submit" disabled={busy}>
              {saved ? "Update feedback" : "Send feedback"}
            </button>
            {saved && (
              <button
                className="btn btn-ghost"
                type="button"
                disabled={busy}
                onClick={() => void withdraw()}
              >
                Withdraw my feedback
              </button>
            )}
          </div>
          {saved && (
            <p className="muted small">
              Last saved {formatDate(saved.updated_at)}.
            </p>
          )}
        </form>
      )}
    </section>
  );
}

function YourData() {
  return (
    <section className="card" aria-labelledby="account-data">
      <h2 id="account-data">Your data</h2>
      <p className="muted small">
        Download the personal data we hold about you: your account details,
        sign-in methods, the workspaces you belong to and the actions recorded
        under your name. Websites, scan results and reports belong to the
        workspace and are exported from its pages. Each download is recorded in
        the audit log.
      </p>
      <a
        className="btn btn-ghost"
        href={api.ACCOUNT_EXPORT_URL}
        download="securescope-account-data.json"
      >
        Download my data (JSON)
      </a>
    </section>
  );
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
      <AccountDetails />
      <PlanCard />
      <ChangePassword />
      <Devices />
      <YourData />
      <FeedbackCard />
      <DeleteAccount />
    </div>
  );
}
