import BrandMark from "./BrandMark";
import type { ReactNode } from "react";
import { buildHash } from "../router";
import ThemeToggle from "./ThemeToggle";
import "../landing.css";
import "../sample.css";

const register = buildHash("register", null);
const login = buildHash("login", null);

/** Header, main area and footer shared by the public pages that are not the home page. */
export default function PublicShell({
  current,
  children,
}: {
  current:
    | "sample-report"
    | "agency-features"
    | "checks"
    | "pricing"
    | "help"
    | "early-access"
    | null;
  children: ReactNode;
}) {
  return (
    <div className="landing-page sample-page">
      <a className="skip-link" href="#public-main">
        Skip to content
      </a>
      <header className="landing-bar">
        <div className="landing-bar-inner">
          <a className="landing-brand sample-brand" href="#/">
            <BrandMark size={26} shield="var(--accent-soft)" />
            <span className="landing-wordmark">SecureScope</span>
          </a>
          <nav className="sample-links" aria-label="Site">
            <a
              href="#/checks"
              aria-current={current === "checks" ? "page" : undefined}
            >
              What we check
            </a>
            <a
              href="#/pricing"
              aria-current={current === "pricing" ? "page" : undefined}
            >
              Pricing
            </a>
            <a
              href="#/sample-report"
              aria-current={current === "sample-report" ? "page" : undefined}
            >
              Sample report
            </a>
            <a
              href="#/help"
              aria-current={current === "help" ? "page" : undefined}
            >
              Help
            </a>
          </nav>
          <div className="landing-actions">
            <ThemeToggle />
            <a className="btn-ghost" href={login}>
              Sign in
            </a>
            <a className="btn" href={register}>
              Get started
            </a>
          </div>
        </div>
      </header>

      <div className="landing">
        <main id="public-main">{children}</main>
        <footer className="landing-foot sample-foot">
          <div className="landing-foot-brand">
            <strong>SecureScope</strong>
            <p className="muted small">
              Passive website security checks for sites you own. Operated from
              Berlin, Germany.
            </p>
          </div>
          <nav aria-label="Product" className="landing-foot-col">
            <h2>Product</h2>
            <a href="#/checks">What we check</a>
            <a href="#/sample-report">Sample report</a>
            <a href="#/agency-features">For agencies</a>
            <a href="#/pricing">Pricing</a>
            <a href="#/early-access">App Scanning (Early Access)</a>
          </nav>
          <nav aria-label="Account" className="landing-foot-col">
            <h2>Account</h2>
            <a href={login}>Sign in</a>
            <a href={register}>Create free account</a>
          </nav>
          <nav aria-label="Help and legal" className="landing-foot-col">
            <h2>Help and legal</h2>
            <a href="#/help">Help</a>
            <a href="/.well-known/security.txt">Report a security issue</a>
            <a href="#/impressum">Impressum</a>
            <a href="#/privacy">Privacy</a>
            <a href="#/terms">Terms</a>
          </nav>
        </footer>
      </div>
    </div>
  );
}
