import BrandMark from "../components/BrandMark";
import ThemeToggle from "../components/ThemeToggle";
import PlanComparison from "../components/PlanComparison";
import { useEffect, useRef, useState } from "react";
import sample from "../sample/sampleReport.json";
import { buildHash } from "../router";
import "../landing.css";

const ICONS: Record<string, string> = {
  lock: "M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5m-18 4 9 5 9-5",
  cookie:
    "M12 3a9 9 0 1 0 9 9 4 4 0 0 1-4-4 4 4 0 0 1-5-5Zm-3 9h.01M13 16h.01M9 16h.01M14 12h.01",
  cert: "M5 4h14v11H5zM9 20l3-3 3 3v-5H9zM8 8h8M8 11h5",
  file: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  proof: "m5 12 4 4L19 6M4 20h16",
  cycle:
    "M4 12a8 8 0 0 1 14-5l2 2M20 4v5h-5M20 12a8 8 0 0 1-14 5l-2-2m0 5v-5h5",
  doc: "M6 3h9l4 4v14H6zM9 12h7M9 16h7M9 8h3",
  users:
    "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-6 9a6 6 0 0 1 12 0M17 11a3 3 0 1 0 0-6M21 20a6 6 0 0 0-4-5.6",
  log: "M5 4h14v16H5zM9 9h6M9 13h6M9 17h3",
  folder: "M3 6h6l2 2h10v11H3zM3 6v13",
  scan: "M4 8V4h4M20 8V4h-4M4 16v4h4m12-4v4h-4M8 12h8",
  review: "M5 4h14v16H5zM8 9h8M8 13h5m2 4 2 2 3-3",
  fix: "m14 6 4 4-9 9H5v-4zM12 8l4 4",
};

function Icon({ name }: { name: string }) {
  return (
    <span className="landing-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        width="22"
        height="22"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={ICONS[name] ?? ICONS.lock} />
      </svg>
    </span>
  );
}

function scrollTo(id: string) {
  const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: calm ? "auto" : "smooth" });
}

const PROBLEMS = [
  {
    icon: "eye",
    title: "Easy to overlook",
    text: "A missing header, a cookie anyone’s script can read, a forgotten .env file. None of it looks broken, so nobody notices until someone else does.",
  },
  {
    icon: "file",
    title: "Hard to read",
    text: "Big scanners can bury the two real problems under pages of jargon. You close the tab and promise yourself you’ll come back.",
  },
  {
    icon: "users",
    title: "Hard to prove",
    text: "A client asks whether their site is secure. “I think so” is not an answer, and you have nothing to hand them.",
  },
];

const NUMBERS = [
  { value: "0", label: "attack payloads sent. Ever." },
  { value: "9", label: "areas checked on every scan" },
  { value: "4", label: "steps from sign-up to your first scan" },
  { value: "3", label: "free scans every month" },
];

const BENEFITS = [
  {
    icon: "proof",
    title: "Catch the quick wins",
    text: "Most findings are a one-line setting. You fix them in minutes, not sprints.",
  },
  {
    icon: "chart",
    title: "Know what to fix first",
    text: "Findings are ranked by severity, and your Overview points at the one to do next.",
  },
  {
    icon: "doc",
    title: "Show your work",
    text: "Hand a client a clear PDF that says what was checked, what passed and what changed since last time.",
  },
  {
    icon: "lock",
    title: "Stay on the safe side",
    text: "Only sites you have proven you own can be scanned, and the scan only reads what any visitor could.",
  },
];

const CHECKS = [
  {
    title: "HTTPS and redirects",
    icon: "lock",
    text: "Is the site served over HTTPS, and does plain HTTP send visitors there?",
  },
  {
    title: "Security headers",
    icon: "layers",
    text: "HSTS, Content-Security-Policy, X-Content-Type-Options, Referrer-Policy and Permissions-Policy: present, and not set so weakly they do nothing.",
  },
  {
    title: "Cookies",
    icon: "cookie",
    text: "Session cookies without Secure, HttpOnly or SameSite are flagged, with the cookie named.",
  },
  {
    title: "TLS certificate",
    icon: "cert",
    text: "Valid for the host name, trusted, and not about to expire.",
  },
  {
    title: "Exposed files",
    icon: "file",
    text: "A readable .env file, public .git metadata, directory listings, and a missing security.txt contact.",
  },
  {
    title: "Information leaks",
    icon: "eye",
    text: "Server and X-Powered-By headers that announce software and version numbers to anyone who asks.",
  },
  {
    title: "Page content",
    icon: "doc",
    text: "Scripts and forms loaded over plain HTTP on an HTTPS page, and third-party scripts with no integrity check.",
  },
  {
    title: "Cross-origin access",
    icon: "users",
    text: "CORS headers that let any website read logged-in responses, or trust the “null” origin.",
  },
  {
    title: "Email and DNS",
    icon: "log",
    text: "SPF, DMARC, CAA and DNSSEC records on your main domain, so spoofed mail and mis-issued certificates are harder.",
  },
];

const STEPS = [
  {
    title: "Add your site",
    text: "Enter the host name you want checked.",
  },
  {
    title: "Prove it is yours",
    text: "Add a DNS TXT record or upload a small file. Only verified sites can be scanned.",
  },
  {
    title: "Run a scan",
    text: "A handful of ordinary page requests. No attack traffic, and it usually finishes within a minute.",
  },
  {
    title: "Review and fix",
    text: "Each finding shows the evidence and how to fix it. Scan again to see it marked resolved.",
  },
  {
    title: "Share a report",
    text: "Download a PDF, or export the data, to show what was checked and what changed.",
  },
];

const FEATURES = [
  {
    title: "A score you can follow",
    icon: "chart",
    text: "One grade per site, with a severity breakdown and a history so you can see whether things are getting better.",
  },
  {
    title: "Evidence on every finding",
    icon: "proof",
    text: "The URL, status and headers that were actually seen, and whether a result was observed or a heuristic.",
  },
  {
    title: "Findings with a lifecycle",
    icon: "cycle",
    text: "Mark a finding as accepted risk or false positive with a note. It only counts as resolved when a later scan no longer sees it.",
  },
  {
    title: "Reports you can hand over",
    icon: "doc",
    text: "Download a PDF, or export HTML, Markdown, JSON or CSV. Reports say what was checked, what passed and where the scan stops.",
  },
  {
    title: "Built for clients",
    icon: "users",
    text: "On the Agency plan, invite clients as read-only viewers so they see results without being able to change anything.",
  },
  {
    title: "An audit trail",
    icon: "log",
    text: "Owners and admins can see who did what in the workspace, with filters.",
  },
];

const APP_STEPS = [
  {
    icon: "folder",
    title: "Add your project",
    text: "Create a project for the application you want to assess.",
  },
  {
    icon: "scan",
    title: "Analyse supported manifests",
    text: "Upload package-lock.json, package.json or requirements.txt. The files are read, never run.",
  },
  {
    icon: "review",
    title: "Review findings and coverage",
    text: "See what was found, what was checked and what could not be.",
  },
  {
    icon: "fix",
    title: "Investigate and remediate",
    text: "Each finding names the package and, where the source provides it, a fixed version.",
  },
];

const APP_WORKS = [
  "Reading supported dependency manifests",
  "Listing the packages and exact versions they declare",
  "Recording a result as completed, incomplete or failed, never guessed",
];
const APP_PLANNED = [
  "Connecting the vulnerability database (a licence and privacy review comes first)",
  "Code analysis (SAST)",
  "Secret detection",
  "Downloadable App Scanning reports",
];

// Illustrative only: not a real scan, not real customer data.
const APP_PREVIEW = [
  {
    pkg: "example-library 1.2.0",
    finding: "Known vulnerability (illustrative)",
    severity: "High",
    sev: "high",
    status: "Completed",
  },
  {
    pkg: "another-package ^2.0.0",
    finding: "Not checked: the version is a range, not an exact version",
    severity: "Not rated",
    sev: "info",
    status: "Skipped",
  },
  {
    pkg: "Whole run",
    finding: "Vulnerability source unavailable: no result is reported",
    severity: "Not rated",
    sev: "info",
    status: "Incomplete",
  },
];

const FAQ = [
  {
    q: "Who is SecureScope for?",
    a: "People who look after websites they own or are responsible for: freelancers, small teams and agencies that want a clear, repeatable check of the basics, with something to show a client. It does not replace a penetration test or a security team.",
  },
  {
    q: "Is it safe to run on my site?",
    a: "Yes. SecureScope only reads: a few normal page requests, requests for a few well-known paths such as /.env to see whether they are publicly readable, and one TLS connection. It sends no exploit payloads, no brute force and no port scans, and it never stores page contents.",
  },
  {
    q: "Can I scan a site that isn't mine?",
    a: "No. Every site has to be verified with a DNS record or a file first, so SecureScope is not a tool for testing other people's websites. Verification proves technical control of the domain; if it is not your own site you also need the owner's permission.",
  },
  {
    q: "What does scheduled monitoring do?",
    a: "On the Professional and Agency plans (not on sale yet) SecureScope scans a verified site daily or weekly and emails you only when something new appears or the score drops by 5 points or more, so a change that opens a gap does not go unnoticed for months.",
  },
  {
    q: "Is this a penetration test?",
    a: "No. It checks the basics that are visible from outside, such as headers, cookies, HTTPS and exposed files. A clean result does not mean a site is secure, and every report says what was not checked.",
  },
  {
    q: "What is App Scanning, and can I use it?",
    a: "App Scanning will check the dependency files of an application for known vulnerabilities. It is in development and not open to the public: the vulnerability database is not connected yet, so it cannot report vulnerabilities today. Website Scanning is the product available now.",
  },
  {
    q: "Where is my data?",
    a: "Scan results are kept for as long as your plan allows (30, 90 or 365 days) and then deleted. You can delete your account and its data yourself. See the privacy notice for details.",
  },
];

export default function Landing() {
  const register = buildHash("register", null);
  const login = buildHash("login", null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  // Links from other pages (the sample report) arrive as #/?section=pricing.
  useEffect(() => {
    const wanted = new URLSearchParams(
      window.location.hash.split("?")[1] ?? "",
    ).get("section");
    if (
      wanted &&
      [
        "problem",
        "checks",
        "how",
        "pricing",
        "products",
        "app-scanning",
      ].includes(wanted)
    )
      requestAnimationFrame(() => scrollTo(wanted));
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
  const go = (id: string) => {
    setMenuOpen(false);
    scrollTo(id);
  };
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
            <button type="button" onClick={() => go("problem")}>
              Why SecureScope
            </button>
            <button type="button" onClick={() => go("checks")}>
              What we check
            </button>
            <button type="button" onClick={() => go("how")}>
              How it works
            </button>
            <a href="#/sample-report">Sample report</a>
            <a href="#/agency-features">For agencies</a>
            <button type="button" onClick={() => go("pricing")}>
              Pricing
            </button>
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
          <section className="landing-hero">
            <div>
              <p className="landing-eyebrow">
                Website &amp; application security
              </p>
              <h1>
                Know what puts your{" "}
                <span className="landing-grad">digital assets at risk.</span>
              </h1>
              <p className="landing-lead">
                Check the security basics of a website you own today: HTTPS,
                headers, cookies, certificates and exposed files. App Scanning,
                for known vulnerabilities in your application’s dependencies, is
                in development. Either way you get clear findings and plain
                instructions for fixing them.
              </p>
              <div className="landing-cta">
                <a className="btn" href={register}>
                  Scan your website
                </a>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => scrollTo("app-scanning")}
                >
                  Explore App Scanning
                </button>
                <a className="btn-ghost" href="#/sample-report">
                  View sample report
                </a>
              </div>
              <p className="landing-cta-note muted small">
                Clear findings. Actionable guidance. Security visibility without
                unnecessary complexity.
              </p>
              <ul className="landing-chips" aria-label="Highlights">
                <li>Passive checks only</li>
                <li>Ownership verified first</li>
                <li>Free plan, no card</li>
              </ul>
            </div>
            <figure className="landing-sample card">
              <figcaption className="landing-sample-tag">
                Sample report
                <span>Illustrative data, not a real scan</span>
              </figcaption>
              <div className="landing-sample-head">
                <span
                  className="landing-grade"
                  aria-label={`Grade ${sample.grade}`}
                >
                  {sample.grade}
                </span>
                <div>
                  <strong>example.com</strong>
                  <span className="muted small">
                    {sample.findings.length} findings ·{" "}
                    {sample.checks_passed.length} checks passed
                  </span>
                </div>
              </div>
              <div className="landing-bar-track" aria-hidden="true">
                <span style={{ width: `${sample.score}%` }} />
              </div>
              <p className="landing-sample-summary">
                <span className="sev sev-medium">1 Medium</span>
                <span className="sev sev-low">2 Low</span>
                <span className="sev sev-info">1 Info</span>
              </p>
              <ul className="landing-sample-list">
                <li>
                  <span className="sev sev-medium">Medium</span>
                  <span>Content-Security-Policy header is missing</span>
                </li>
                <li>
                  <span className="sev sev-low">Low</span>
                  <span>Cookies set without the HttpOnly attribute</span>
                </li>
                <li>
                  <span className="sev sev-low">Low</span>
                  <span>Strict-Transport-Security max-age is short</span>
                </li>
                <li>
                  <span className="sev sev-info">Info</span>
                  <span>No security.txt contact file</span>
                </li>
              </ul>
              <div className="landing-sample-app">
                <p className="landing-sample-app-title">
                  App Scanning
                  <span className="landing-status">In development</span>
                </p>
                <p className="muted small">
                  Illustrative: when the vulnerability source is unavailable the
                  run is reported as <strong>Incomplete</strong>, never as
                  clean.
                </p>
              </div>
              <div className="landing-sample-links">
                <a className="landing-sample-link" href="#/sample-report">
                  Open the full sample report <span aria-hidden="true">→</span>
                </a>
                <a
                  className="landing-sample-link"
                  href="/sample-report.pdf"
                  download="SecureScope-sample-report.pdf"
                >
                  Download the sample PDF <span aria-hidden="true">↓</span>
                </a>
              </div>
            </figure>
          </section>

          <section
            id="products"
            className="landing-section"
            aria-labelledby="h-products"
          >
            <p className="landing-eyebrow">Platform</p>
            <h2 id="h-products">Two products, one place to look</h2>
            <div className="landing-products">
              <article className="card landing-product">
                <p className="landing-status landing-status-live">Available</p>
                <h3>Website Scanning</h3>
                <p className="muted">
                  Assess the security configuration of a website you have
                  verified you own, and review each finding with the evidence
                  and a fix.
                </p>
                <ul className="landing-ticks">
                  <li>HTTPS, headers, cookies and TLS certificates</li>
                  <li>Exposed files and information leaks</li>
                  <li>Findings ranked by severity, with a PDF report</li>
                </ul>
                <a className="btn" href={register}>
                  Scan your website
                </a>
              </article>
              <article className="card landing-product">
                <p className="landing-status">In development</p>
                <h3>App Scanning</h3>
                <p className="muted">
                  Assess supported dependency manifests for known
                  vulnerabilities. Not open to the public yet.
                </p>
                <p className="landing-list-title">Built so far</p>
                <ul className="landing-ticks">
                  {APP_WORKS.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
                <p className="landing-list-title">Planned, not available</p>
                <ul className="landing-planned">
                  {APP_PLANNED.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => scrollTo("app-scanning")}
                >
                  Read about App Scanning
                </button>
              </article>
            </div>
          </section>

          <section
            id="problem"
            className="landing-section"
            aria-labelledby="h-problem"
          >
            <p className="landing-eyebrow">The problem</p>
            <h2 id="h-problem">
              Website security fails in boring ways. That is exactly why it gets
              missed.
            </h2>
            <p className="landing-sub muted">
              The headline-grabbing attacks are rare. The everyday gaps are not:
              a setting nobody switched on, a file nobody meant to publish, a
              certificate that quietly runs out. They sit there for months
              because checking for them has always been either expensive or
              exhausting.
            </p>
            <div className="landing-grid">
              {PROBLEMS.map((c) => (
                <article key={c.title} className="card landing-card">
                  <Icon name={c.icon} />
                  <h3>{c.title}</h3>
                  <p className="muted">{c.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="landing-solution" aria-labelledby="h-solution">
            <p className="landing-eyebrow">The answer</p>
            <h2 id="h-solution">
              One calm place to see what is wrong, why it matters and how to fix
              it.
            </h2>
            <p className="muted">
              SecureScope does the small things well. It reads your site the way
              any visitor would, checks the basics that attackers look for
              first, and explains every result in plain language, with the
              evidence beside it. No agents to install, no dashboards to learn,
              nothing that touches your site.
            </p>
            <dl className="landing-numbers">
              {NUMBERS.map((n) => (
                <div key={n.label}>
                  <dt>{n.value}</dt>
                  <dd>{n.label}</dd>
                </div>
              ))}
            </dl>
            <p className="landing-fineprint muted small">
              These describe how SecureScope works. They are not usage
              statistics or customer results.
            </p>
          </section>

          <section className="landing-section" aria-labelledby="h-benefits">
            <p className="landing-eyebrow">Benefits</p>
            <h2 id="h-benefits">Get the basics right, before they matter</h2>
            <div className="landing-grid landing-benefits">
              {BENEFITS.map((b) => (
                <article key={b.title} className="card landing-card">
                  <Icon name={b.icon} />
                  <h3>{b.title}</h3>
                  <p className="muted">{b.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section
            id="checks"
            className="landing-section"
            aria-labelledby="h-checks"
          >
            <p className="landing-eyebrow">Coverage</p>
            <h2 id="h-checks">What SecureScope checks</h2>
            <p className="landing-sub muted">
              Passive checks that are visible from outside. Nothing is attacked
              or changed.
            </p>
            <div className="landing-grid">
              {CHECKS.map((c) => (
                <article key={c.title} className="card landing-card">
                  <Icon name={c.icon} />
                  <h3>{c.title}</h3>
                  <p className="muted">{c.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section id="how" className="landing-section" aria-labelledby="h-how">
            <p className="landing-eyebrow">Getting started</p>
            <h2 id="h-how">How it works</h2>
            <ol className="landing-steps">
              {STEPS.map((s, i) => (
                <li key={s.title} className="card">
                  <span className="landing-step-no" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3>{s.title}</h3>
                  <p className="muted">{s.text}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="landing-section" aria-labelledby="h-features">
            <p className="landing-eyebrow">Features</p>
            <h2 id="h-features">What you get</h2>
            <div className="landing-grid">
              {FEATURES.map((f) => (
                <article key={f.title} className="card landing-card">
                  <Icon name={f.icon} />
                  <h3>{f.title}</h3>
                  <p className="muted">{f.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section
            id="app-scanning"
            className="landing-section"
            aria-labelledby="h-app-scanning"
          >
            <p className="landing-eyebrow">App Scanning · In development</p>
            <h2 id="h-app-scanning">
              Dependency security, explained before it is switched on
            </h2>
            <p className="landing-sub muted">
              App Scanning is not generally available and there is no waiting
              list yet. This is how it is designed to work, and what it will and
              will not tell you.
            </p>
            <ol className="landing-steps">
              {APP_STEPS.map((st, i) => (
                <li key={st.title} className="card">
                  <Icon name={st.icon} />
                  <span className="landing-step-no" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3>{st.title}</h3>
                  <p className="muted">{st.text}</p>
                </li>
              ))}
            </ol>
            <ul className="landing-honest">
              <li>
                Only supported files and exact package versions are assessed.
              </li>
              <li>
                Unsupported or unpinned dependencies may remain unchecked.
              </li>
              <li>
                If the vulnerability source is unavailable the result is
                incomplete or failed. It is never reported as clean.
              </li>
              <li>
                It is not a penetration test, and uploaded code is never
                executed.
              </li>
            </ul>

            <h3 className="landing-subhead" id="h-app-preview">
              What a result looks like
            </h3>
            <div className="landing-table-wrap">
              <table
                className="landing-table"
                aria-describedby="app-preview-note"
              >
                <caption className="visually-hidden">
                  Illustrative App Scanning results
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Package</th>
                    <th scope="col">Finding</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {APP_PREVIEW.map((r) => (
                    <tr key={r.pkg}>
                      <th scope="row" data-label="Package">
                        {r.pkg}
                      </th>
                      <td data-label="Finding">{r.finding}</td>
                      <td data-label="Severity">
                        <span className={`sev sev-${r.sev}`}>{r.severity}</span>
                      </td>
                      <td data-label="Status">
                        <strong>{r.status}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p id="app-preview-note" className="landing-fineprint muted small">
              Illustrative example with made-up package names. It is not a real
              scan and not customer data. Severity is shown only when the
              vulnerability source provides it.
            </p>

            <h3 className="landing-subhead" id="h-app-privacy">
              Privacy and trust
            </h3>
            <div className="landing-grid landing-trust">
              <article className="card landing-card">
                <h4>Website Scanning</h4>
                <p className="muted">
                  Reads what any visitor could read from a site you have
                  verified you own, and never stores page contents.
                </p>
              </article>
              <article className="card landing-card">
                <h4>App Scanning</h4>
                <p className="muted">
                  Uploaded files are read in memory. SecureScope keeps findings,
                  file names, package names and versions, and file digests, not
                  file contents.
                </p>
              </article>
              <article className="card landing-card">
                <h4>Not yet decided</h4>
                <p className="muted">
                  The vulnerability database is not connected. What would be
                  sent to it is reviewed first, and the privacy notice is
                  updated before App Scanning opens.
                </p>
              </article>
            </div>
            <p className="landing-fineprint muted small">
              See the <a href="#/privacy">privacy notice</a> and the{" "}
              <a href="#/terms">terms</a>.
            </p>
          </section>

          <section
            id="sample-pdf"
            className="landing-section landing-pdf"
            aria-labelledby="h-sample-pdf"
          >
            <div className="landing-pdf-text">
              <p className="landing-eyebrow">Sample report</p>
              <h2 id="h-sample-pdf">See exactly what you hand over</h2>
              <p className="landing-sub muted">
                This is the PDF SecureScope produces for a scan: the overall
                result, every finding with its evidence and fix, the checks that
                passed, and how the score is worked out. It describes
                example.com, a domain reserved for documentation, so it is
                clearly a demonstration and not a real customer or scan.
              </p>
              <div className="landing-cta">
                <a
                  className="btn"
                  href="/sample-report.pdf"
                  download="SecureScope-sample-report.pdf"
                >
                  Download the sample PDF
                </a>
                <a className="btn-ghost" href="#/sample-report">
                  Read it on the web
                </a>
              </div>
            </div>
            <a
              className="landing-pdf-cover"
              href="/sample-report.pdf"
              aria-label="Open the sample PDF report"
            >
              <img
                src="/sample-report-cover.webp"
                width="745"
                height="1053"
                loading="lazy"
                alt="First page of the sample website security report for example.com: the host, the score, an overall risk rating of Medium and a short summary"
              />
              <span className="landing-pdf-hint" aria-hidden="true">
                Open the PDF
              </span>
            </a>
          </section>

          <section
            id="pricing"
            className="landing-section"
            aria-labelledby="h-pricing"
          >
            <p className="landing-eyebrow">Plans</p>
            <h2 id="h-pricing">Pricing</h2>
            <p className="landing-sub muted">
              Start free. The paid plans are not on sale yet; they will be
              announced here.
            </p>
            <div className="landing-grid landing-plans">
              <article className="card landing-plan-live">
                <h3>
                  Free <span className="landing-badge">Available now</span>
                </h3>
                <p className="landing-price">€0</p>
                <ul>
                  <li>1 website</li>
                  <li>3 scans per month</li>
                  <li>Scan history kept 30 days</li>
                  <li>PDF and data exports</li>
                  <li>Optional public score badge</li>
                </ul>
                <div className="landing-plan-foot">
                  <a className="btn" href={register}>
                    Create free account
                  </a>
                  <p className="muted small landing-plan-note">
                    Available now.
                  </p>
                </div>
              </article>
              <article className="card landing-plan-soon">
                <h3>
                  Professional{" "}
                  <span className="landing-badge soon">Coming soon</span>
                </h3>
                <p className="landing-price">
                  €19 <span className="muted small">/ month</span>
                </p>
                <ul>
                  <li>5 websites</li>
                  <li>30 scans per month</li>
                  <li>Scan history kept 90 days</li>
                  <li>Scheduled scans with email and webhook alerts</li>
                  <li>GitHub Action and API tokens for CI</li>
                  <li>PDF and data exports</li>
                </ul>
                <div className="landing-plan-foot">
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => scrollTo("h-compare")}
                  >
                    Compare plans
                  </button>
                  <p className="muted small landing-plan-note">
                    Not on sale yet.
                  </p>
                </div>
              </article>
              <article className="card landing-plan-soon">
                <h3>
                  Agency <span className="landing-badge soon">Coming soon</span>
                </h3>
                <p className="landing-price">
                  €49 <span className="muted small">/ month</span>
                </p>
                <ul>
                  <li>20 websites</li>
                  <li>150 scans per month</li>
                  <li>Scan history kept 365 days</li>
                  <li>Scheduled scans with email and webhook alerts</li>
                  <li>GitHub Action and API tokens for CI</li>
                  <li>Invite team members and clients</li>
                  <li>Client dashboard, branded PDFs, share links</li>
                </ul>
                <div className="landing-plan-foot">
                  <a className="btn-ghost" href="#/agency-features">
                    Explore Agency features
                  </a>
                  <p className="muted small landing-plan-note">
                    Not on sale yet.
                  </p>
                </div>
              </article>
            </div>
            <PlanComparison />
            <p className="muted small">
              Prices are planned and may change before launch. If you reach a
              limit, nothing is deleted; you just can’t add more until the month
              renews.
            </p>
          </section>

          <section className="landing-section" aria-labelledby="h-faq">
            <h2 id="h-faq">Questions</h2>
            <div className="landing-faq">
              {FAQ.map((f) => (
                <details key={f.q} className="card">
                  <summary>{f.q}</summary>
                  <p className="muted">{f.a}</p>
                </details>
              ))}
            </div>
          </section>

          <section className="landing-final card">
            <h2>Check your first site in a few minutes</h2>
            <p className="muted">
              Create a free account, verify your site and run your first scan.
            </p>
            <a className="btn" href={register}>
              Create free account
            </a>
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
            <button type="button" onClick={() => scrollTo("checks")}>
              What we check
            </button>
            <button type="button" onClick={() => scrollTo("how")}>
              How it works
            </button>
            <a href="#/sample-report">Sample report</a>
            <a href="#/agency-features">For agencies</a>
            <button type="button" onClick={() => scrollTo("pricing")}>
              Pricing
            </button>
          </nav>
          <nav aria-label="Account" className="landing-foot-col">
            <h2>Account</h2>
            <a href={login}>Sign in</a>
            <a href={register}>Create free account</a>
          </nav>
          <nav aria-label="Help and legal" className="landing-foot-col">
            <h2>Help and legal</h2>
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
