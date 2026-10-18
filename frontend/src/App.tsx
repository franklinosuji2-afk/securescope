import { useAuth } from "./auth";
import { Loading } from "./components/ui";
import type { Page } from "./router";
import { PUBLIC_PAGES, buildHash, useRoute } from "./router";
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from "./pages/AuthPages";
import Targets from "./pages/Targets";
import Team from "./pages/Team";
import Findings from "./pages/Findings";
import History from "./pages/History";
import Overview from "./pages/Overview";

const NAV: { page: Page; label: string }[] = [
  { page: "overview", label: "Overview" },
  { page: "targets", label: "Targets" },
  { page: "findings", label: "Findings" },
  { page: "history", label: "Scan History" },
  { page: "team", label: "Team" },
];

export default function App() {
  const [route, navigate] = useRoute();
  const { user, loading, organization, setOrganizationId, signOut } = useAuth();

  if (loading) {
    return (
      <div className="auth-wrap">
        <Loading label="Loading…" />
      </div>
    );
  }

  const isPublic = PUBLIC_PAGES.includes(route.page);
  if (!user && !isPublic) {
    return (
      <div className="auth-wrap">
        <div className="card auth-card">
          <h1>Sign in required</h1>
          <p className="muted">Please sign in to use SecureScope.</p>
          <a className="btn" style={{ textAlign: "center", textDecoration: "none" }} href={buildHash("login", null)}>
            Sign in
          </a>
        </div>
      </div>
    );
  }
  if (!user || isPublic) {
    // Verification and reset links work whether or not someone is signed in.
    const done = () => navigate("overview");
    return (
      <main id="main">
        {route.page === "register" ? (
          <RegisterPage onDone={done} />
        ) : route.page === "forgot-password" ? (
          <ForgotPasswordPage />
        ) : route.page === "reset-password" ? (
          <ResetPasswordPage token={route.token} />
        ) : route.page === "verify-email" ? (
          <VerifyEmailPage token={route.token} />
        ) : (
          <LoginPage onDone={done} />
        )}
      </main>
    );
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="rail">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3 5 7v8c0 7 4.6 11.7 11 14 6.4-2.3 11-7 11-14V7L16 3Z" fill="none" stroke="#6d4aff" strokeWidth="2.2" />
            <path d="m11 16 4 4 6-8" fill="none" stroke="#2dd4bf" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          SecureScope
        </div>
        <nav className="nav" aria-label="Primary">
          {NAV.map((n) => (
            <a
              key={n.page}
              href={buildHash(n.page, n.page === "history" ? null : route.scanId)}
              aria-current={route.page === n.page ? "page" : undefined}
            >
              {n.label}
            </a>
          ))}
        </nav>
        <div className="rail-user">
          {user.organizations.length > 1 ? (
            <select
              className="input"
              aria-label="Active organization"
              value={organization?.id ?? ""}
              onChange={(e) => setOrganizationId(e.target.value)}
            >
              {user.organizations.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="small">{organization?.name}</div>
          )}
          <div className="muted small" style={{ overflowWrap: "anywhere" }}>
            {user.email}
            {organization ? ` · ${organization.role}` : ""}
          </div>
          {!user.email_verified && <div className="small">Email not confirmed</div>}
          <button className="btn-ghost" type="button" onClick={() => void signOut().then(() => navigate("login"))}>
            Sign out
          </button>
        </div>
        <p className="rail-note">Heuristic, passive checks only. Not a penetration test.</p>
      </aside>
      <main className="main" id="main" tabIndex={-1}>
        {route.page === "overview" && <Overview route={route} onStarted={(id) => navigate("overview", id)} />}
        {route.page === "targets" && <Targets />}
        {route.page === "findings" && <Findings route={route} />}
        {route.page === "history" && <History onOpen={(id) => navigate("findings", id)} />}
        {route.page === "team" && <Team />}
      </main>
    </div>
  );
}
