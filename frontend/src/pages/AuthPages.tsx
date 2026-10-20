import { useState, type FormEvent, type ReactNode } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { ErrorNotice } from "../components/ui";
import { buildHash } from "../router";
import { LegalLinks } from "./Legal";

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
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
        {error && <ErrorNotice message={error} />}
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
