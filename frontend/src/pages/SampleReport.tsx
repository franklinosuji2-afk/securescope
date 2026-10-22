import { useEffect } from "react";
import sample from "../sample/sampleReport.json";
import { buildHash } from "../router";
import "../landing.css";
import "../sample.css";

type Severity = "critical" | "high" | "medium" | "low" | "info";

interface SampleFinding {
  id: string;
  title: string;
  severity: string;
  category: string;
  description: string;
  evidence: string;
  remediation: string;
}

const SEVERITIES: readonly { key: Severity; label: string }[] = [
  { key: "critical", label: "Critical" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
  { key: "info", label: "Informational" },
];

// Where each sample finding was observed, and how the site owner confirms a fix. The finding text itself
// (title, evidence, impact, fix) comes from the scanner's own output in sampleReport.json.
const DETAIL: Record<string, { url: string; verify: string[] }> = {
  "SS-HDR-CSP-001": {
    url: "https://example.com/",
    verify: [
      "Run curl -sI https://example.com/ and look for a Content-Security-Policy line.",
      "Open the site with the browser developer tools console open and check for blocked-resource messages. In report-only mode nothing is blocked yet, so fix what is reported before enforcing.",
      "Run a new scan. The finding should move to “no longer detected”.",
    ],
  },
  "SS-COOKIE-HTTPONLY-001": {
    url: "https://example.com/",
    verify: [
      "Run curl -sI https://example.com/ and check that the Set-Cookie line for the session cookie includes HttpOnly.",
      "In the browser developer tools, open Application, then Cookies, and confirm the HttpOnly column is ticked.",
      "Run a new scan to confirm the finding is no longer detected.",
    ],
  },
  "SS-HDR-HSTS-002": {
    url: "https://example.com/",
    verify: [
      "Run curl -sI https://example.com/ and read the Strict-Transport-Security line.",
      "Check that max-age is at least 15552000 (180 days). Raise it in steps if you are cautious.",
      "Run a new scan to confirm.",
    ],
  },
  "SS-DISC-SEC-001": {
    url: "https://example.com/.well-known/security.txt",
    verify: [
      "Open https://example.com/.well-known/security.txt in a browser. It should return the file, not an error page.",
      "Check that it has a Contact line and an Expires date in the future.",
      "Run a new scan to confirm.",
    ],
  },
};

const CHECKS_PERFORMED = [
  "HTTPS is used and HTTP redirects to it",
  "TLS certificate validity and time left",
  "Strict-Transport-Security",
  "Content-Security-Policy",
  "X-Content-Type-Options, Referrer-Policy and Permissions-Policy",
  "Cookie attributes: Secure, HttpOnly and SameSite",
  "Server and X-Powered-By version disclosure",
  "Directory listing in the page",
  "A readable .env file or public .git metadata",
  "A security.txt contact file",
];

const CONTENTS = [
  ["summary", "Executive summary"],
  ["score", "How the score works"],
  ["findings", "Findings"],
  ["passed", "Checks that passed"],
  ["performed", "Checks performed"],
  ["scope", "Scope and limitations"],
  ["next", "Next steps"],
] as const;

const register = buildHash("register", null);
const login = buildHash("login", null);

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

export default function SampleReport() {
  useEffect(() => {
    document.title = "Sample security report – SecureScope";
    return () => {
      document.title = "SecureScope";
    };
  }, []);

  const findings = sample.findings as SampleFinding[];
  const counts = Object.fromEntries(
    SEVERITIES.map(({ key }) => [
      key,
      findings.filter((f) => f.severity === key).length,
    ]),
  ) as Record<Severity, number>;
  const penalties = sample.penalties as Record<Severity, number>;
  const total = findings.length;

  return (
    <div className="landing-page sample-page">
      <a className="skip-link" href="#sample-main">
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
            <a href="#/sample-report" aria-current="page">
              Sample report
            </a>
            <a href="#/?section=pricing">Pricing</a>
          </nav>
          <div className="landing-actions">
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
        <main id="sample-main">
          <div className="sample-notice" role="note">
            <strong>Sample report.</strong> This is a demonstration. It is not a
            scan of a real website. <code>example.com</code> is a domain
            reserved for documentation, and the findings were produced by
            SecureScope’s own checks against a described test site.
          </div>

          <section className="sample-title" aria-labelledby="h-sample">
            <p className="landing-eyebrow">Website security report</p>
            <h1 id="h-sample">Sample security report</h1>
            <dl className="sample-meta">
              <div>
                <dt>Site</dt>
                <dd>{sample.domain}</dd>
              </div>
              <div>
                <dt>Report reference</dt>
                <dd>SAMPLE-0001</dd>
              </div>
              <div>
                <dt>Illustrative date</dt>
                <dd>15 October 2026</dd>
              </div>
              <div>
                <dt>Scan type</dt>
                <dd>Passive, read-only</dd>
              </div>
            </dl>
          </section>

          <div className="sample-layout">
            <nav className="sample-toc card" aria-label="Report contents">
              <h2>Contents</h2>
              <ol>
                {CONTENTS.map(([id, label]) => (
                  <li key={id}>
                    <a href={`#${id}`} onClick={(e) => jump(e, id)}>
                      {label}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>

            <div className="sample-body">
              <section id="summary" aria-labelledby="h-summary">
                <h2 id="h-summary">Executive summary</h2>
                <div className="sample-score card">
                  <div
                    className="sample-grade"
                    role="img"
                    aria-label={`Score ${sample.score} out of 100, grade ${sample.grade}`}
                  >
                    <strong>{sample.score}</strong>
                    <span>Grade {sample.grade}</span>
                  </div>
                  <ul
                    className="sample-counts"
                    aria-label="Findings by severity"
                  >
                    {SEVERITIES.map(({ key, label }) => (
                      <li key={key}>
                        <span className={`sev sev-${key}`}>{label}</span>
                        <strong>{counts[key]}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
                <p>
                  SecureScope ran {sample.checks_run} checks on this site and
                  found {plural(total, "issue", "issues")}.{" "}
                  {sample.checks_passed.length} checks found nothing to report.
                  None of the findings is critical or high. The most important
                  one is the missing Content-Security-Policy, which is the
                  quickest way to limit the damage if a script ever gets
                  injected into a page.
                </p>
                <p>
                  The two low findings are small settings that are quick to
                  change. The informational finding is a good-practice item: it
                  does not reduce the score.
                </p>
              </section>

              <section id="score" aria-labelledby="h-score">
                <h2 id="h-score">How the score works</h2>
                <p>
                  Every site starts at 100. Each finding takes points off
                  according to its severity, and the grade follows from the
                  result. The score is a way to compare scans over time. It is
                  not a measurement of how secure a site is.
                </p>
                <div className="sample-two">
                  <table className="sample-table">
                    <caption>Points taken off per finding</caption>
                    <thead>
                      <tr>
                        <th scope="col">Severity</th>
                        <th scope="col">Points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {SEVERITIES.map(({ key, label }) => (
                        <tr key={key}>
                          <th scope="row">{label}</th>
                          <td>{penalties[key]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <table className="sample-table">
                    <caption>Grade bands</caption>
                    <thead>
                      <tr>
                        <th scope="col">Score</th>
                        <th scope="col">Grade</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sample.grade_bands.map((b) => (
                        <tr key={b.grade}>
                          <th scope="row">{b.min} or more</th>
                          <td>{b.grade}</td>
                        </tr>
                      ))}
                      <tr>
                        <th scope="row">Below 50</th>
                        <td>F</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p className="muted">
                  This report: 100 − 10 (medium) − 4 − 4 (two low) − 0
                  (informational) = {sample.score}, grade {sample.grade}.
                </p>
              </section>

              <section id="findings" aria-labelledby="h-findings">
                <h2 id="h-findings">Findings</h2>
                {SEVERITIES.filter(({ key }) => counts[key] > 0).map(
                  ({ key, label }) => (
                    <div key={key} className="sample-group">
                      <h3>
                        <span className={`sev sev-${key}`}>{label}</span>{" "}
                        <span className="muted">
                          {plural(counts[key], "finding", "findings")}
                        </span>
                      </h3>
                      {findings
                        .filter((f) => f.severity === key)
                        .map((f) => {
                          const d = DETAIL[f.id];
                          return (
                            <article
                              key={f.id}
                              className="card sample-finding"
                              aria-labelledby={`t-${f.id}`}
                            >
                              <h4 id={`t-${f.id}`}>{f.title}</h4>
                              <p className="muted small">
                                {f.id} · {f.category}
                              </p>
                              <dl>
                                {d && (
                                  <>
                                    <dt>Affected URL</dt>
                                    <dd>
                                      <code>{d.url}</code>
                                    </dd>
                                  </>
                                )}
                                <dt>Evidence</dt>
                                <dd>{f.evidence}</dd>
                                <dt>Why it matters</dt>
                                <dd>{f.description}</dd>
                                <dt>How to fix it</dt>
                                <dd>{f.remediation}</dd>
                                {d && (
                                  <>
                                    <dt>How to verify the fix</dt>
                                    <dd>
                                      <ol>
                                        {d.verify.map((v) => (
                                          <li key={v}>{v}</li>
                                        ))}
                                      </ol>
                                    </dd>
                                  </>
                                )}
                              </dl>
                            </article>
                          );
                        })}
                    </div>
                  ),
                )}
              </section>

              <section id="passed" aria-labelledby="h-passed">
                <h2 id="h-passed">Checks that passed</h2>
                <p className="muted">
                  These checks ran and found nothing to report on this site.
                </p>
                <ul className="sample-ticks">
                  {sample.checks_passed.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </section>

              <section id="performed" aria-labelledby="h-performed">
                <h2 id="h-performed">Checks performed</h2>
                <p>
                  SecureScope looks at what any visitor can already see. It
                  sends a handful of ordinary requests and reads the answers:
                </p>
                <ul className="sample-list">
                  {CHECKS_PERFORMED.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </section>

              <section id="scope" aria-labelledby="h-scope">
                <h2 id="h-scope">Scope and limitations</h2>
                <ul className="sample-list">
                  <li>
                    The scan is passive and read-only. It does not log in, guess
                    passwords, submit forms or try to exploit anything.
                  </li>
                  <li>
                    It only scans sites whose ownership you have verified, and
                    it stays on that site.
                  </li>
                  <li>
                    It reads the home page and three fixed paths. It does not
                    crawl the whole site or test your application’s logic.
                  </li>
                  <li>
                    A clean report does not mean a site is secure. It means
                    these specific checks found nothing at that moment.
                  </li>
                  <li>
                    Some findings are indicators, not proof. Each finding states
                    how confident the check is, and you can mark a finding as an
                    accepted risk or a false positive.
                  </li>
                  <li>
                    This is not a penetration test or a compliance
                    certification.
                  </li>
                </ul>
              </section>

              <section
                id="next"
                aria-labelledby="h-next"
                className="sample-cta card"
              >
                <h2 id="h-next">Run this on your own site</h2>
                <p className="muted">
                  Create a free account, verify your site and get a report like
                  this one for it.
                </p>
                <div className="landing-cta">
                  <a className="btn" href={register}>
                    Create free account
                  </a>
                  <a className="btn-ghost" href="#/?section=pricing">
                    See pricing
                  </a>
                  <a className="btn-ghost" href="#/?section=how">
                    See how it works
                  </a>
                </div>
              </section>
            </div>
          </div>
        </main>

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

// The app routes with the URL hash, so a plain #id link would be read as a page. Scroll instead.
function jump(e: React.MouseEvent, id: string) {
  e.preventDefault();
  const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const el = document.getElementById(id);
  el?.scrollIntoView({ behavior: calm ? "auto" : "smooth" });
  el?.setAttribute("tabindex", "-1");
  el?.focus({ preventScroll: true });
}
