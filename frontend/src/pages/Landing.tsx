import { useEffect, useRef, useState } from "react";
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
  { value: "6", label: "areas checked on every scan" },
  { value: "4", label: "steps from sign-up to first result" },
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
    title: "Fix and track",
    text: "Each finding shows the evidence and how to fix it. Scan again to see it marked resolved.",
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
    text: "Download a PDF, or export HTML, Markdown or JSON. Reports say what was checked, what passed and where the scan stops.",
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

const FAQ = [
  {
    q: "Is it safe to run on my site?",
    a: "Yes. SecureScope only reads: a few normal page requests and one TLS connection. It sends no exploit payloads, no brute force and no port scans, and it never stores page contents.",
  },
  {
    q: "Can I scan a site that isn't mine?",
    a: "No. Every site has to be verified with a DNS record or a file first, so SecureScope can't be pointed at someone else's website.",
  },
  {
    q: "Is this a penetration test?",
    a: "No. It checks the basics that are visible from outside, such as headers, cookies, HTTPS and exposed files. A clean result does not mean a site is secure, and every report says what was not checked.",
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
          </div>
          <nav
            id="landing-menu"
            className={`landing-links${menuOpen ? " open" : ""}`}
            aria-label="Site"
          >
            <button type="button" onClick={() => go("problem")}>
              Why
            </button>
            <button type="button" onClick={() => go("checks")}>
              What we check
            </button>
            <button type="button" onClick={() => go("how")}>
              How it works
            </button>
            <button type="button" onClick={() => go("pricing")}>
              Pricing
            </button>
            <a className="landing-menu-signin" href={login}>
              Sign in
            </a>
          </nav>
          <div className="landing-actions">
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
              <p className="landing-eyebrow">Website security checks</p>
              <h1>
                Find the gaps in your website’s security{" "}
                <span className="landing-grad">before anyone else does.</span>
              </h1>
              <p className="landing-lead">
                SecureScope checks the security basics of a site you own: HTTPS,
                headers, cookies, certificates and exposed files. You get a
                score, the evidence, and plain instructions for fixing each
                problem.
              </p>
              <div className="landing-cta">
                <a className="btn" href={register}>
                  Create free account
                </a>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => scrollTo("checks")}
                >
                  See what is checked
                </button>
              </div>
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
                <span className="landing-grade" aria-label="Grade B">
                  B
                </span>
                <div>
                  <strong>example.com</strong>
                  <span className="muted small">
                    4 findings · 9 checks passed
                  </span>
                </div>
              </div>
              <div className="landing-bar-track" aria-hidden="true">
                <span style={{ width: "82%" }} />
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
            </figure>
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
                </ul>
                <a className="btn" href={register}>
                  Create free account
                </a>
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
                  <li>PDF and data exports</li>
                </ul>
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
                  <li>Invite team members and clients</li>
                </ul>
              </article>
            </div>
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
            <button type="button" onClick={() => scrollTo("pricing")}>
              Pricing
            </button>
          </nav>
          <nav aria-label="Account" className="landing-foot-col">
            <h2>Account</h2>
            <a href={login}>Sign in</a>
            <a href={register}>Create free account</a>
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
