import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth";
import { useTheme } from "./theme";
import { Loading } from "./components/ui";
import type { Page } from "./router";
import { LEGAL_PAGES, PUBLIC_PAGES, buildHash, useRoute } from "./router";
import {
  AcceptInvitePage,
  ConfirmEmailPage,
  ForgotPasswordPage,
  LoginPage,
  RegisterPage,
  ResetPasswordPage,
  VerifyEmailPage,
} from "./pages/AuthPages";
import LegalPage, { LegalLinks } from "./pages/Legal";
import Targets from "./pages/Targets";
import Team from "./pages/Team";
import Findings from "./pages/Findings";
import Analytics from "./pages/Analytics";
import Health from "./pages/Health";
import Audit from "./pages/Audit";
import History from "./pages/History";
import NotFound from "./pages/NotFound";
import Account from "./pages/Account";
import Overview from "./pages/Overview";
import { forgetInvite, pendingInvite } from "./pendingInvite";
import { canReadAudit } from "./types";
import { trackPageView, trackedPageName } from "./tracking";

const NAV: { page: Page; label: string }[] = [
  { page: "overview", label: "Overview" },
  { page: "targets", label: "Targets" },
  { page: "findings", label: "Findings" },
  { page: "history", label: "Scan History" },
  { page: "team", label: "Team" },
  { page: "account", label: "Account" },
  { page: "audit", label: "Audit log" },
  { page: "analytics", label: "Analytics" },
  { page: "health", label: "Platform Health" },
];

export default function App() {
  const [route, navigate] = useRoute();
  const { user, loading, organization, setOrganizationId, signOut } = useAuth();
  const { theme, toggle } = useTheme();
  // The navigation is a Menu button at every width. It is open only for the page it was opened on, so choosing
  // any page closes it without an effect; Escape closes it and returns focus to the button.
  const routeKey = `${route.page}|${route.scanId ?? ""}`;
  const [openFor, setOpenFor] = useState<string | null>(null);
  const menuOpen = openFor === routeKey;
  const setMenuOpen = (open: boolean) => setOpenFor(open ? routeKey : null);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpenFor(null);
      menuButton.current?.focus();
    };
    const onPointer = (event: PointerEvent) => {
      // A press outside the bar and its panel closes the menu.
      if (!(event.target as Element | null)?.closest(".rail")) setOpenFor(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [menuOpen]);

  // A signed-in person has no use for the sign-in or registration forms: send them to the app.
  const signedInOnAuthForm =
    !!user && (route.page === "login" || route.page === "register");
  useEffect(() => {
    if (signedInOnAuthForm) window.location.hash = buildHash("overview", null);
  }, [signedInOnAuthForm]);

  // An invitation opened while signed out is picked up again once the person is signed in, even after a trip
  // to Google or GitHub.
  useEffect(() => {
    if (!user || route.page === "accept-invite") return;
    const token = pendingInvite();
    if (!token) return;
    // Used once: the invitation page takes the token from the address from here on.
    forgetInvite();
    window.location.hash = `#/accept-invite?token=${token}`;
  }, [user, route.page]);

  // Count visits to the public pages only. Nobody who is signed in is counted, and nothing is sent until
  // we know whether someone is signed in.
  const lastTracked = useRef<string | null>(null);
  useEffect(() => {
    if (loading) return;
    if (user) {
      lastTracked.current = null;
      return;
    }
    const name = trackedPageName(route.page);
    if (!name || lastTracked.current === name) return;
    lastTracked.current = name;
    trackPageView(name);
  }, [loading, user, route.page]);

  if (LEGAL_PAGES.includes(route.page)) {
    return (
      <main id="main">
        <LegalPage page={route.page} />
      </main>
    );
  }

  if (signedInOnAuthForm) return null;

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
          <a
            className="btn"
            style={{ textAlign: "center", textDecoration: "none" }}
            href={buildHash("login", null)}
          >
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
        ) : route.page === "accept-invite" ? (
          <AcceptInvitePage token={route.token} />
        ) : (
          <LoginPage onDone={done} />
        )}
      </main>
    );
  }

  if (!user.email_verified) {
    // The server refuses the dashboard's requests too; this explains it instead of showing errors.
    return (
      <main id="main">
        <ConfirmEmailPage />
      </main>
    );
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`rail${menuOpen ? " rail-open" : ""}`}>
        <div className="rail-top">
          <div className="brand">
            <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
              <path
                d="M16 3 5 7v8c0 7 4.6 11.7 11 14 6.4-2.3 11-7 11-14V7L16 3Z"
                fill="none"
                strokeWidth="2.2"
                style={{ stroke: "var(--accent-soft)" }}
              />
              <path
                d="m11 16 4 4 6-8"
                fill="none"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ stroke: "var(--ok)" }}
              />
            </svg>
            SecureScope
          </div>
          <button
            ref={menuButton}
            type="button"
            className="btn-ghost menu-btn"
            aria-expanded={menuOpen}
            aria-controls="rail-menu"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? "Close menu" : "Menu"}
          </button>
        </div>
        <div className="rail-menu" id="rail-menu">
          <nav className="nav" aria-label="Primary">
            {NAV.filter((n) =>
              n.page === "analytics" || n.page === "health"
                ? user.is_admin === true
                : n.page !== "audit" ||
                  (organization ? canReadAudit(organization.role) : false),
            ).map((n) => (
              <a
                key={n.page}
                href={buildHash(
                  n.page,
                  n.page === "history" ? null : route.scanId,
                )}
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
                onChange={(e) => {
                  setOrganizationId(e.target.value);
                  // A scan in the address belongs to the organization being left.
                  if (route.scanId) navigate(route.page);
                }}
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
            <button
              className="btn-ghost"
              type="button"
              onClick={toggle}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? "Light theme" : "Dark theme"}
            </button>
            <button
              className="btn-ghost"
              type="button"
              onClick={() => void signOut().then(() => navigate("login"))}
            >
              Sign out
            </button>
          </div>
          <p className="rail-note">
            Heuristic, passive checks only. Not a penetration test.
          </p>
          <LegalLinks />
        </div>
      </aside>
      {/* Keyed by organization: switching remounts every page, so nothing loaded for the previous
          organization stays on screen and its unfinished requests are ignored. */}
      <main
        className="main"
        id="main"
        tabIndex={-1}
        key={organization?.id ?? "none"}
      >
        {route.page === "overview" && (
          <Overview
            route={route}
            onStarted={(id) => navigate("overview", id)}
          />
        )}
        {route.page === "not-found" && <NotFound />}
        {route.page === "targets" && <Targets />}
        {route.page === "findings" && <Findings route={route} />}
        {route.page === "history" && (
          <History onOpen={(id) => navigate("findings", id)} />
        )}
        {route.page === "team" && <Team />}
        {route.page === "account" && <Account />}
        {route.page === "audit" && <Audit />}
        {route.page === "analytics" && user.is_admin === true && <Analytics />}
        {route.page === "health" && user.is_admin === true && <Health />}
      </main>
    </div>
  );
}
