import BrandMark from "./components/BrandMark";
import { useEffect, useRef, useState } from "react";
import { PageLoader, lazyPage } from "./lazyPage";
import { useAuth } from "./auth";
import { useTheme } from "./theme";
import { Loading } from "./components/ui";
import ThemeToggle, { CornerThemeToggle } from "./components/ThemeToggle";
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
const Targets = lazyPage(() => import("./pages/Targets"));
const Integrations = lazyPage(() => import("./pages/Integrations"));
const Team = lazyPage(() => import("./pages/Team"));
const Findings = lazyPage(() => import("./pages/Findings"));
const Analytics = lazyPage(() => import("./pages/Analytics"));
const Health = lazyPage(() => import("./pages/Health"));
const Audit = lazyPage(() => import("./pages/Audit"));
const History = lazyPage(() => import("./pages/History"));
import NotFound from "./pages/NotFound";
import ErrorBoundary from "./components/ErrorBoundary";
const Account = lazyPage(() => import("./pages/Account"));
import Overview from "./pages/Overview";
import Landing from "./pages/Landing";
const AgencyFeatures = lazyPage(() => import("./pages/AgencyFeatures"));
const Compare = lazyPage(() => import("./pages/Compare"));
const Clients = lazyPage(() => import("./pages/Clients"));
const SampleReport = lazyPage(() => import("./pages/SampleReport"));
const SharedReport = lazyPage(() => import("./pages/SharedReport"));
import { useAgencyAvailable } from "./agency";
import { useAppScanningAvailable } from "./appScanning";
const AppScanning = lazyPage(() => import("./pages/AppScanning"));
import { forgetInvite, pendingInvite } from "./pendingInvite";
import { canReadAudit, canReadClients } from "./types";
import { trackPageView, trackedPageName } from "./tracking";

const NAV: { page: Page; label: string }[] = [
  { page: "overview", label: "Overview" },
  { page: "targets", label: "Targets" },
  { page: "integrations", label: "Integrations" },
  { page: "clients", label: "Clients" },
  { page: "app-scanning", label: "App Scanning" },
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
  useTheme(); // applies the saved or system theme as soon as the app starts
  // The navigation is a Menu button at every width. It is open only for the page it was opened on, so choosing
  // any page closes it without an effect; Escape closes it and returns focus to the button.
  const routeKey = `${route.page}|${route.scanId ?? ""}`;
  const [openFor, setOpenFor] = useState<string | null>(null);
  const menuOpen = openFor === routeKey;
  const setMenuOpen = (open: boolean) => setOpenFor(open ? routeKey : null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const agency = useAgencyAvailable(
    organization?.id ?? null,
    !!user && !!organization && canReadClients(organization.role),
  );
  const appScanning = useAppScanningAvailable(
    organization?.id ?? null,
    !!user && user.email_verified && !!organization,
  );
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

  // Pages for signed-in work and the long public pages are loaded when first opened, so the home and
  // sign-in pages do not download them.
  if (route.page === "sample-report")
    return (
      <PageLoader>
        <SampleReport />
      </PageLoader>
    );
  if (route.page === "agency-features")
    return (
      <PageLoader>
        <AgencyFeatures />
      </PageLoader>
    );
  if (route.page === "shared")
    return (
      <PageLoader>
        <SharedReport token={route.token} />
      </PageLoader>
    );

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
        <CornerThemeToggle />
        <Loading label="Loading…" />
      </div>
    );
  }

  const isPublic = PUBLIC_PAGES.includes(route.page);
  // Visitors who are not signed in see the public home page instead of a bare sign-in prompt.
  if (!user && route.page === "overview") return <Landing />;
  if (!user && !isPublic) {
    return (
      <main className="auth-wrap" id="main">
        <CornerThemeToggle />
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
      </main>
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
            <BrandMark className="brand-mark" shield="var(--accent-soft)" />
            SecureScope
          </div>
          <div className="rail-top-actions">
            <ThemeToggle />
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
        </div>
        <div className="rail-menu" id="rail-menu">
          <nav className="nav" aria-label="Primary">
            {NAV.filter((n) =>
              n.page === "clients"
                ? agency === true
                : n.page === "app-scanning"
                  ? appScanning === true
                  : n.page === "analytics" || n.page === "health"
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
        <ErrorBoundary scope="page" key={route.page}>
          {route.page === "overview" && (
            <Overview
              route={route}
              onStarted={(id) => navigate("overview", id)}
            />
          )}
          {route.page === "not-found" && <NotFound />}
          <PageLoader>
            {route.page === "targets" && <Targets />}
            {route.page === "integrations" && <Integrations />}
            {route.page === "clients" && agency === true && <Clients />}
            {route.page === "app-scanning" && appScanning === true && (
              <AppScanning
                canCreate={
                  organization ? organization.role !== "VIEWER" : false
                }
              />
            )}
            {route.page === "findings" && <Findings route={route} />}
            {route.page === "history" && (
              <History onOpen={(id) => navigate("findings", id)} />
            )}
            {route.page === "compare" && <Compare route={route} />}
            {route.page === "team" && <Team />}
            {route.page === "account" && <Account />}
            {route.page === "audit" && <Audit />}
            {route.page === "analytics" && user.is_admin === true && (
              <Analytics />
            )}
            {route.page === "health" && user.is_admin === true && <Health />}
          </PageLoader>
        </ErrorBoundary>
      </main>
    </div>
  );
}
