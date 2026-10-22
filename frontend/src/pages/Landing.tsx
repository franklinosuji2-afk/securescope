import { LegalLinks } from "./Legal";
import { buildHash } from "../router";
import "../landing.css";

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

const CHECKS = [
  {
    title: "HTTPS and redirects",
    text: "Is the site served over HTTPS, and does plain HTTP send visitors there?",
  },
  {
    title: "Security headers",
    text: "HSTS, Content-Security-Policy, X-Content-Type-Options, Referrer-Policy and Permissions-Policy: present, and not set so weakly they do nothing.",
  },
  {
    title: "Cookies",
    text: "Session cookies without Secure, HttpOnly or SameSite are flagged, with the cookie named.",
  },
  {
    title: "TLS certificate",
    text: "Valid for the host name, trusted, and not about to expire.",
  },
  {
    title: "Exposed files",
    text: "A readable .env file, public .git metadata, directory listings, and a missing security.txt contact.",
  },
  {
    title: "Information leaks",
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
    text: "One grade per site, with a severity breakdown and a history so you can see whether things are getting better.",
  },
  {
    title: "Evidence on every finding",
    text: "The URL, status and headers that were actually seen, and whether a result was observed or a heuristic.",
  },
  {
    title: "Findings with a lifecycle",
    text: "Mark a finding as accepted risk or false positive with a note. It only counts as resolved when a later scan no longer sees it.",
  },
  {
    title: "Reports you can hand over",
    text: "Download a PDF, or export HTML, Markdown or JSON. Reports say what was checked, what passed and where the scan stops.",
  },
  {
    title: "Built for clients",
    text: "On the Agency plan, invite clients as read-only viewers so they see results without being able to change anything.",
  },
  {
    title: "An audit trail",
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
  return (
    <div className="landing">
      <a className="skip-link" href="#landing-main">
        Skip to content
      </a>
      <header className="landing-bar">
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
          SecureScope
        </div>
        <nav className="landing-links" aria-label="Sections">
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
        <div className="landing-actions">
          <a className="btn-ghost landing-signin" href={login}>
            Sign in
          </a>
          <a className="btn" href={register}>
            Create free account
          </a>
        </div>
      </header>

      <main id="landing-main">
        <section className="landing-hero">
          <div>
            <p className="landing-eyebrow">Website security checks</p>
            <h1>
              Find the gaps in your website’s security before anyone else does.
            </h1>
            <p className="landing-lead">
              SecureScope checks the security basics of a site you own: HTTPS,
              headers, cookies, certificates and exposed files. You get a score,
              the evidence, and plain instructions for fixing each problem.
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
            <p className="landing-note muted small">
              Free plan: 1 website and 3 scans a month. No card needed.
            </p>
          </div>
          <div
            className="landing-sample card"
            role="img"
            aria-label="Example report: grade B with one high, two medium and one low finding"
          >
            <p className="landing-sample-tag">Example report</p>
            <div className="landing-sample-head">
              <span className="landing-grade">B</span>
              <div>
                <strong>example.com</strong>
                <br />
                <span className="muted small">4 findings, 9 checks passed</span>
              </div>
            </div>
            <ul className="landing-sample-list">
              <li>
                <span className="sev sev-high">High</span>{" "}
                Content-Security-Policy header is missing
              </li>
              <li>
                <span className="sev sev-medium">Medium</span> Cookies set
                without the HttpOnly attribute
              </li>
              <li>
                <span className="sev sev-medium">Medium</span>{" "}
                Strict-Transport-Security max-age is short
              </li>
              <li>
                <span className="sev sev-low">Low</span> No security.txt contact
                file
              </li>
            </ul>
          </div>
        </section>

        <section
          id="checks"
          className="landing-section"
          aria-labelledby="h-checks"
        >
          <h2 id="h-checks">What SecureScope checks</h2>
          <p className="landing-sub muted">
            Passive checks that are visible from outside. Nothing is attacked or
            changed.
          </p>
          <div className="landing-grid">
            {CHECKS.map((c) => (
              <article key={c.title} className="card">
                <h3>{c.title}</h3>
                <p className="muted">{c.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="how" className="landing-section" aria-labelledby="h-how">
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
          <h2 id="h-features">What you get</h2>
          <div className="landing-grid">
            {FEATURES.map((f) => (
              <article key={f.title} className="card">
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
          <h2 id="h-pricing">Pricing</h2>
          <p className="landing-sub muted">
            Start free. The paid plans are not on sale yet; they will be
            announced here.
          </p>
          <div className="landing-grid landing-plans">
            <article className="card">
              <h3>Free</h3>
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
            <article className="card">
              <h3>Professional</h3>
              <p className="landing-price">
                €19 <span className="muted small">/ month</span>
              </p>
              <ul>
                <li>5 websites</li>
                <li>30 scans per month</li>
                <li>Scan history kept 90 days</li>
                <li>PDF and data exports</li>
              </ul>
              <p className="muted small">Coming soon</p>
            </article>
            <article className="card">
              <h3>Agency</h3>
              <p className="landing-price">
                €49 <span className="muted small">/ month</span>
              </p>
              <ul>
                <li>20 websites</li>
                <li>150 scans per month</li>
                <li>Scan history kept 365 days</li>
                <li>Invite team members and clients</li>
              </ul>
              <p className="muted small">Coming soon</p>
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
        <span className="muted small">
          SecureScope, operated from Berlin, Germany.
        </span>
        <LegalLinks />
      </footer>
    </div>
  );
}
