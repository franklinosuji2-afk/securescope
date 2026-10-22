import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { ErrorNotice } from "../components/ui";
import { forgetInvite, rememberInvite } from "../pendingInvite";
import { buildHash, parseOAuthError, type OAuthErrorCode } from "../router";
import type { InvitationPreview, Role } from "../types";
import { LegalLinks } from "./Legal";
import ProviderIcon from "../components/ProviderIcon";

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <h1>{title}</h1>
        {children}
        <LegalLinks />
      </div>
    </div>
  );
}

function message(err: unknown): string {
  return err instanceof ApiError
    ? err.message
    : "Something went wrong. Please try again.";
}

const OAUTH_MESSAGES: Record<OAuthErrorCode, string> = {
  failed:
    "Signing in with that provider did not work. Please try again, or use your email and password.",
  cancelled: "Sign-in was cancelled. Nothing was changed.",
  email_unverified:
    "That account has no verified email address, so we cannot sign you in with it. Confirm the address with the provider, or use your email and password.",
  disabled: "This account is disabled.",
  unavailable: "That sign-in method is not available right now.",
};

const PROVIDER_LABEL: Record<api.OAuthProvider, string> = {
  google: "Google",
  github: "GitHub",
};

/** "Continue with Google / GitHub". Shown only for providers the server has configured. */
function SocialSignIn({ verb }: { verb: string }) {
  const [providers, setProviders] = useState<api.OAuthProvider[]>([]);
  useEffect(() => {
    let cancelled = false;
    api
      .fetchAuthProviders()
      .then((list) => {
        if (!cancelled) setProviders(list);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  if (providers.length === 0) return null;
  return (
    <div className="social">
      {providers.map((p) => (
        <a key={p} className="btn-ghost social-btn" href={api.oauthStartUrl(p)}>
          <ProviderIcon provider={p} />
          <span>
            {verb} with {PROVIDER_LABEL[p]}
          </span>
        </a>
      ))}
      <p className="muted small">
        No account yet? Signing in creates one. We keep only your verified email
        address and the provider's account ID.
      </p>
      <div className="social-or" aria-hidden="true">
        <span>or use email</span>
      </div>
    </div>
  );
}

function Field(props: {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  hint?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="field-label" htmlFor={props.id}>
        {props.label}
      </label>
      <input
        id={props.id}
        className="input"
        style={{ width: "100%", marginTop: 6 }}
        type={props.type ?? "text"}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        autoComplete={props.autoComplete}
        required={props.required ?? true}
        aria-describedby={props.hint ? `${props.id}-hint` : undefined}
      />
      {props.hint && (
        <p
          id={`${props.id}-hint`}
          className="muted small"
          style={{ marginTop: 4 }}
        >
          {props.hint}
        </p>
      )}
    </div>
  );
}

export function LoginPage({ onDone }: { onDone: () => void }) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(() => {
    const code = parseOAuthError(window.location.hash);
    return code ? OAUTH_MESSAGES[code] : null;
  });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // Show the reason once; reloading the page should not show it again.
    if (parseOAuthError(window.location.hash))
      window.history.replaceState(null, "", buildHash("login", null));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      onDone();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Sign in">
      {error && <ErrorNotice message={error} />}
      <SocialSignIn verb="Continue" />
      <form className="scan-form" onSubmit={submit}>
        <Field
          id="email"
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="username"
        />
        <Field
          id="password"
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />

        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="small">
          <a href={buildHash("forgot-password", null)}>Forgot your password?</a>{" "}
          · <a href={buildHash("register", null)}>Create an account</a>
        </p>
      </form>
    </Shell>
  );
}

export function RegisterPage({ onDone }: { onDone: () => void }) {
  const { signUp } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signUp(email.trim(), password, org.trim() || undefined);
      onDone();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Create your account">
      <SocialSignIn verb="Sign up" />
      <form className="scan-form" onSubmit={submit}>
        <Field
          id="email"
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="username"
        />
        <Field
          id="password"
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint="At least 12 characters. A passphrase works well."
        />
        <Field
          id="org"
          label="Workspace name (optional)"
          value={org}
          onChange={setOrg}
          required={false}
        />
        {error && <ErrorNotice message={error} />}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
        <p className="muted small">
          By creating an account you agree to the{" "}
          <a href="#/terms">Terms of use</a> and have read the{" "}
          <a href="#/privacy">Privacy notice</a>.
        </p>
        <p className="small">
          Already registered? <a href={buildHash("login", null)}>Sign in</a>
        </p>
      </form>
    </Shell>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setDone((await api.forgotPassword(email.trim())).detail);
    } catch (err) {
      setError(message(err));
    }
  }

  return (
    <Shell title="Reset your password">
      <form className="scan-form" onSubmit={submit}>
        <Field
          id="email"
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="username"
        />
        {error && <ErrorNotice message={error} />}
        {done && (
          <div className="notice notice-info" role="status">
            {done}
          </div>
        )}
        <button className="btn" type="submit">
          Send reset link
        </button>
        <p className="muted small">
          If an account exists for this email, we will send a reset link. It can
          take a minute, and it may land in your spam folder.
        </p>
        <a className="small" href={buildHash("login", null)}>
          Back to sign in
        </a>
      </form>
    </Shell>
  );
}

export function ResetPasswordPage({ token }: { token: string | null }) {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.resetPassword(token ?? "", password);
      setDone(true);
    } catch (err) {
      setError(message(err));
    }
  }

  if (!token) {
    return (
      <Shell title="Reset your password">
        <ErrorNotice message="This reset link is missing its token. Request a new one." />
      </Shell>
    );
  }
  return (
    <Shell title="Choose a new password">
      {done ? (
        <div className="notice notice-info" role="status">
          Password updated. <a href={buildHash("login", null)}>Sign in</a>
        </div>
      ) : (
        <form className="scan-form" onSubmit={submit}>
          <Field
            id="password"
            label="New password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            hint="At least 12 characters."
          />
          {error && <ErrorNotice message={error} />}
          <button className="btn" type="submit">
            Update password
          </button>
        </form>
      )}
    </Shell>
  );
}

export function VerifyEmailPage({ token }: { token: string | null }) {
  const { reload } = useAuth();
  const [state, setState] = useState<"idle" | "ok" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    try {
      await api.verifyEmail(token ?? "");
      setState("ok");
      void reload();
    } catch (err) {
      setError(message(err));
      setState("error");
    }
  }

  return (
    <Shell title="Confirm your email">
      {!token && <ErrorNotice message="This link is missing its token." />}
      {token && state === "idle" && (
        <button className="btn" type="button" onClick={() => void confirm()}>
          Confirm email address
        </button>
      )}
      {state === "ok" && (
        <div className="notice notice-info" role="status">
          Email confirmed. <a href={buildHash("overview", null)}>Continue</a>
        </div>
      )}
      {state === "error" && error && <ErrorNotice message={error} />}
    </Shell>
  );
}

const ROLE_TEXT: Record<Role, string> = {
  OWNER: "an owner",
  ADMIN: "an administrator",
  SECURITY_ANALYST: "a security analyst",
  MEMBER: "a member who can read results and start scans",
  VIEWER: "a viewer with read-only access",
};

/** Opens an invitation from an email. Works signed out (sign in or create an account first) and signed in. */
export function AcceptInvitePage({ token }: { token: string | null }) {
  const { user, loading, reload, setOrganizationId, signOut } = useAuth();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [joined, setJoined] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resent, setResent] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .previewInvitation(token)
      .then((p) => !cancelled && setPreview(p))
      .catch((err: unknown) => !cancelled && setProblem(message(err)));
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Signed out: keep the link for after sign-in, which may take a trip to Google or GitHub.
  const signedOut = !loading && !user;
  useEffect(() => {
    if (token && signedOut && preview) rememberInvite(token);
  }, [token, signedOut, preview]);

  async function accept() {
    if (!token) return;
    setBusy(true);
    setProblem(null);
    try {
      const result = await api.acceptInvitation(token);
      forgetInvite();
      await reload();
      setOrganizationId(result.organization_id);
      setJoined(result.organization_id);
    } catch (err) {
      setProblem(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    try {
      await api.resendVerification();
      setResent(
        "Sent. Open the link in that email, then come back to this page.",
      );
    } catch (err) {
      setResent(message(err));
    } finally {
      setBusy(false);
    }
  }

  const mismatch =
    !!user &&
    !!preview &&
    user.email.toLowerCase() !== preview.email.toLowerCase();
  const unconfirmed = !!user && !mismatch && !user.email_verified;

  return (
    <Shell title="Join a workspace">
      {!token && (
        <ErrorNotice message="This link is missing its invitation code." />
      )}
      {problem && !joined && <ErrorNotice message={problem} />}
      {token && !preview && !problem && <p className="muted">Loading…</p>}
      {preview && !joined && (
        <>
          <p>
            You are invited to join <strong>{preview.organization_name}</strong>{" "}
            as {ROLE_TEXT[preview.role]}.
          </p>
          <p className="muted small">
            This invitation is for <strong>{preview.email}</strong>. It only
            works with that email address.
          </p>
          {signedOut && (
            <>
              <p className="small">
                Sign in or create an account with {preview.email} to accept.
              </p>
              <p>
                <a className="btn" href={buildHash("login", null)}>
                  Sign in
                </a>{" "}
                <a className="btn-ghost" href={buildHash("register", null)}>
                  Create an account
                </a>
              </p>
            </>
          )}
          {user && mismatch && (
            <div className="notice notice-warn" role="alert">
              You are signed in as {user.email}, but this invitation is for{" "}
              {preview.email}.{" "}
              <button
                type="button"
                className="btn-link"
                onClick={() => void signOut()}
              >
                Sign out
              </button>{" "}
              and use the invited address.
            </div>
          )}
          {unconfirmed && (
            <div className="notice notice-info" role="status">
              Your email address is not confirmed yet. We send a link to{" "}
              {user.email}; open it, then return here.{" "}
              <button
                type="button"
                className="btn-link"
                disabled={busy}
                onClick={() => void resend()}
              >
                Send confirmation email
              </button>
              {resent && <div className="muted">{resent}</div>}
            </div>
          )}
          {user && !mismatch && (
            <button
              className="btn"
              type="button"
              disabled={busy}
              onClick={() => void accept()}
            >
              Accept and join
            </button>
          )}
        </>
      )}
      {joined && preview && (
        <div className="notice notice-info" role="status">
          You joined {preview.organization_name}.{" "}
          <a href={buildHash("overview", null)}>Open the workspace</a>
        </div>
      )}
    </Shell>
  );
}

/** Shown instead of the dashboard while the signed-in address is not confirmed. The server enforces this too;
 * this page only explains it and offers the way forward. */
export function ConfirmEmailPage() {
  const { user, reload, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function resend() {
    setBusy(true);
    try {
      await api.resendVerification();
      setNote(
        "Sent. Open the link in that email, then press the button below.",
      );
    } catch (err) {
      setNote(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Confirm your email address">
      <p>
        We sent a confirmation link to <strong>{user?.email}</strong>. Open it
        to start using SecureScope. Check your spam folder if you cannot find
        it.
      </p>
      <p>
        <button
          type="button"
          className="btn-ghost"
          disabled={busy}
          onClick={() => void resend()}
        >
          Send the email again
        </button>
      </p>
      {note && (
        <div className="notice notice-info" role="status">
          {note}
        </div>
      )}
      <p>
        <button type="button" className="btn" onClick={() => void reload()}>
          I have confirmed my email
        </button>{" "}
        <button
          type="button"
          className="btn-link"
          onClick={() => void signOut()}
        >
          Sign out
        </button>
      </p>
    </Shell>
  );
}
