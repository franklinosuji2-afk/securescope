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
  current: "sample-report" | "agency-features" | null;
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
            <svg viewBox="0 0 32 32" aria-hidden="true" width="26" height="26">
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
            <span className="landing-wordmark">SecureScope</span>
          </a>
          <nav className="sample-links" aria-label="Site">
            <a href="#/?section=problem">Why SecureScope</a>
            <a href="#/?section=checks">What we check</a>
            <a
              href="#/sample-report"
              aria-current={current === "sample-report" ? "page" : undefined}
            >
              Sample report
            </a>
            <a
              href="#/agency-features"
              aria-current={current === "agency-features" ? "page" : undefined}
            >
              For agencies
            </a>
            <a href="#/?section=pricing">Pricing</a>
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
            <a href="#/?section=checks">What we check</a>
            <a href="#/?section=how">How it works</a>
            <a href="#/sample-report">Sample report</a>
            <a href="#/agency-features">For agencies</a>
            <a href="#/?section=pricing">Pricing</a>
          </nav>
          <nav aria-label="Legal" className="landing-foot-col">
            <h2>Legal</h2>
            <a href="#/impressum">Impressum</a>
            <a href="#/privacy">Privacy</a>
            <a href="#/terms">Terms</a>
          </nav>
        </footer>
      </div>
    </div>
  );
}
