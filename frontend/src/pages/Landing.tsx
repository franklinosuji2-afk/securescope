import BrandMark from "../components/BrandMark";
import ThemeToggle from "../components/ThemeToggle";
import { useEffect, useRef, useState } from "react";
import { buildHash } from "../router";
import type { Page } from "../router";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "../landing.css";
import "../home.css";

/**
 * The public home page. It answers four questions and offers one action: what SecureScope does, which
 * two products there are and what state each is in, who it is for, and how to start. Everything that
 * used to sit here (the checks, pricing, questions, App Scanning detail) lives on its own page, with
 * the same wording.
 */

// Old links such as #/?section=pricing still land somewhere useful.
const LEGACY_SECTIONS: Record<string, Page> = {
  problem: "checks",
  checks: "checks",
  how: "checks",
  pricing: "pricing",
  products: "early-access",
  "app-scanning": "early-access",
};

const CAPABILITIES = [
  {
    key: "website",
    name: "Website Scanning",
    status: "Available now",
    live: true,
    text: "Checks your live site for missing or weak security settings: HTTPS, browser security rules, cookies and email-domain protections. Every problem comes with a plain-language fix.",
    foot: "Free plan: 3 scans every month.",
    link: "#/checks",
    linkLabel: "See what we check",
    base: "M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0M3 12h18",
    accent:
      "M12 3c2.4 2.5 3.7 5.5 3.7 9S14.4 18.5 12 21c-2.4-2.5-3.7-5.5-3.7-9S9.6 5.5 12 3Z",
  },
  {
    key: "app",
    name: "App Scanning",
    status: "Early Access",
    live: false,
    text: "For the code and libraries behind your product. Early Access means availability is limited and some parts are still being built, so it is not open to everyone yet.",
    foot: "Its page lists what works today and what is still planned.",
    link: "#/early-access",
    linkLabel: "Read about Early Access",
    base: "M8 8l-4 4 4 4M16 8l4 4-4 4",
    accent: "M13.5 6.5l-3 11",
  },
];

const AUDIENCE = [
  {
    title: "Developers",
    text: "Check what you ship before your users, or attackers, find the gaps.",
  },
  {
    title: "Freelancers",
    text: "Hand clients a clear report without needing to be a security specialist.",
  },
  {
    title: "Agencies",
    text: "Keep client sites in one place and download a report for each.",
    link: "#/agency-features",
    linkLabel: "For agencies",
  },
];

const START = [
  {
    title: "Add your site",
    text: "Enter the address of the website you want to check.",
  },
  {
    title: "Confirm it is yours",
    text: "Add a short line at your domain host, so we know you own the site.",
  },
  {
    title: "Read your results",
    text: "Run the scan and get a list of problems, most important first, with how to fix each one.",
  },
];

export default function Landing() {
  const register = buildHash("register", null);
  const login = buildHash("login", null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const wanted = new URLSearchParams(
      window.location.hash.split("?")[1] ?? "",
    ).get("section");
    const page = wanted ? LEGACY_SECTIONS[wanted] : undefined;
    if (page) window.location.hash = buildHash(page, null);
  }, []);
  // Escape closes the menu and returns focus to its button; a press outside closes it too.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      menuButton.current?.focus();
    };
    const onPointer = (event: PointerEvent) => {
      if (!(event.target as Element | null)?.closest(".landing-bar"))
        setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [menuOpen]);
  return (
    <div className="landing-page">
      <a className="skip-link" href="#landing-main">
        Skip to content
      </a>
      <header className="landing-bar">
        <div className="landing-bar-inner">
          <div className="landing-brand">
            <BrandMark size={26} shield="var(--accent-soft)" />
            <span className="landing-wordmark">SecureScope</span>
          </div>
          <nav
            id="landing-menu"
            className={`landing-links${menuOpen ? " open" : ""}`}
            aria-label="Site"
          >
            <a href="#/checks">What we check</a>
            <a href="#/pricing">Pricing</a>
            <a href="#/sample-report">Sample report</a>
            <a href="#/help">Help</a>
            <a className="landing-menu-signin" href={login}>
              Sign in
            </a>
            <div className="landing-menu-theme">
              <ThemeToggle />
              <span className="muted small">Light or dark theme</span>
            </div>
          </nav>
          <div className="landing-actions">
            <ThemeToggle />
            <button
              ref={menuButton}
              type="button"
              className="btn-ghost landing-menu-btn"
              aria-expanded={menuOpen}
              aria-controls="landing-menu"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              {menuOpen ? "Close menu" : "Menu"}
            </button>
            <a className="btn-ghost landing-signin" href={login}>
              Sign in
            </a>
            <a className="btn" href={register}>
              Get started
            </a>
          </div>
        </div>
      </header>

      <div className="landing">
        <main id="landing-main">
          <section className="hb-hero" aria-labelledby="hb-title">
            <p className="hb-eyebrow">Website security, in plain language</p>
            <h1 id="hb-title" className="hb-title">
              Find the security gaps on your website, and know how to fix them.
            </h1>
            <p className="hb-lead">
              SecureScope checks what your site tells every visitor&apos;s
              browser, then explains each problem in plain language with the fix
              beside it. No security background needed.
            </p>
            <div className="hb-actions">
              <a className="btn hb-cta" href={register}>
                Scan your website
              </a>
              <a className="hb-quiet" href="#/sample-report">
                View a sample report
              </a>
            </div>
            <p className="hb-assure">
              Passive checks only. Ownership verified first. Free plan, no card.
            </p>
          </section>

          <section
            id="products"
            className="hb-section"
            aria-labelledby="hb-scan-title"
          >
            <p className="hb-label">What you can scan</p>
            <h2 id="hb-scan-title" className="hb-h2">
              Two products, with clear status.
            </h2>
            <div className="hb-cards">
              {CAPABILITIES.map((c) => (
                <article key={c.key} className="hb-card hb-cap">
                  <div className="hb-cap-top">
                    <span className="hb-tile" aria-hidden="true">
                      <svg
                        viewBox="0 0 24 24"
                        width="32"
                        height="32"
                        fill="none"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path className="hb-ico-base" d={c.base} />
                        <path className="hb-ico-accent" d={c.accent} />
                      </svg>
                    </span>
                    <span
                      className={`hb-badge ${c.live ? "hb-badge-live" : "hb-badge-early"}`}
                    >
                      {c.status}
                    </span>
                  </div>
                  <h3>{c.name}</h3>
                  <p className="muted">{c.text}</p>
                  <p className="muted small">{c.foot}</p>
                  <a className="hb-link" href={c.link}>
                    {c.linkLabel}
                  </a>
                </article>
              ))}
            </div>
          </section>

          <section className="hb-section" aria-labelledby="hb-who-title">
            <p className="hb-label">Who it is for</p>
            <h2 id="hb-who-title" className="hb-h2">
              Built for people who ship, not security teams.
            </h2>
            <div className="hb-cards hb-cards-3">
              {AUDIENCE.map((w) => (
                <article key={w.title} className="hb-card">
                  <h3>{w.title}</h3>
                  <p className="muted">{w.text}</p>
                  {w.link && (
                    <a className="hb-link" href={w.link}>
                      {w.linkLabel}
                    </a>
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="hb-section" aria-labelledby="hb-start-title">
            <p className="hb-label">How to start</p>
            <h2 id="hb-start-title" className="hb-h2">
              Three steps, a few minutes.
            </h2>
            <ol className="hb-steps">
              {START.map((s, i) => (
                <li key={s.title}>
                  <span className="hb-step-no" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3>{s.title}</h3>
                  <p className="muted">{s.text}</p>
                </li>
              ))}
            </ol>
            <div className="hb-actions">
              <a className="btn hb-cta" href={register}>
                Scan your website
              </a>
              <a className="hb-quiet" href="#/sample-report">
                View a sample report
              </a>
            </div>
          </section>
        </main>

        <footer className="landing-foot">
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
