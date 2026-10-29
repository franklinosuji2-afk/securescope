import PublicShell from "../components/PublicShell";
import FinalCta from "../components/FinalCta";
import { Sheet } from "../components/HomeHero";
import { Icon } from "../components/LandingIcon";
import {
  BENEFITS,
  CHECKS,
  CHECK_PLAIN,
  FEATURES,
  NUMBERS,
  PROBLEMS,
  STEPS,
} from "../publicContent";
import { buildHash } from "../router";

/** What the scan looks at, how it works and why. Everything here used to be on the home page. */
export default function Checks() {
  const register = buildHash("register", null);
  return (
    <PublicShell current="checks">
      <section className="sample-title agency-hero" aria-labelledby="h-checks">
        <p className="landing-eyebrow">What we check</p>
        <h1 id="h-checks">What SecureScope checks</h1>
        <p className="landing-lead">
          Passive checks that are visible from outside. Nothing is attacked or
          changed. Each check below starts with the plain question it answers.
        </p>
        <div className="landing-cta">
          <a className="btn" href={register}>
            Scan your website
          </a>
          <a className="btn-ghost" href="#/sample-report">
            View sample report
          </a>
        </div>
      </section>

      <div className="landing-body">
        <section className="landing-section" aria-labelledby="h-checks-list">
          <h2 id="h-checks-list">The nine areas</h2>
          <div className="landing-grid">
            {CHECKS.map((c) => (
              <article key={c.title} className="card landing-card">
                <Icon name={c.icon} />
                <h3>{c.title}</h3>
                <p>{CHECK_PLAIN[c.title]}</p>
                <p className="muted">{c.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" aria-labelledby="h-example">
          <h2 id="h-example">What a finding looks like</h2>
          <Sheet />
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
          id="problem"
          className="landing-section"
          aria-labelledby="h-problem"
        >
          <p className="landing-eyebrow">Why SecureScope</p>
          <h2 id="h-problem">
            Website security fails in boring ways. That is exactly why it gets
            missed.
          </h2>
          <p className="landing-sub muted">
            The headline-grabbing attacks are rare. The everyday gaps are not: a
            setting nobody switched on, a file nobody meant to publish, a
            certificate that quietly runs out. They sit there for months because
            checking for them has always been either expensive or exhausting.
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
            any visitor would, checks the basics that attackers look for first,
            and explains every result in plain language, with the evidence
            beside it. No agents to install, no dashboards to learn, nothing
            that touches your site.
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
            These describe how SecureScope works. They are not usage statistics
            or customer results.
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
              passed, and how the score is worked out. It describes example.com,
              a domain reserved for documentation, so it is clearly a
              demonstration and not a real customer or scan.
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

        <FinalCta />
      </div>
    </PublicShell>
  );
}
