import { useState, type CSSProperties } from "react";
import sample from "../sample/sampleReport.json";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "../home.css";

/**
 * The first screen. SecureScope reads what a site sends back and says what is missing, so the hero shows exactly
 * that: an excerpt of a response with the gaps marked. All of it is an illustration and says so.
 */

type Verdict = "ok" | "weak" | "missing";
interface Line {
  id: string;
  text: string;
  verdict?: Verdict;
  label?: string;
  severity?: "Medium" | "Low" | "High";
  title?: string;
  evidence?: string;
  fix?: string;
}

const WEBSITE: Line[] = [
  { id: "w1", text: "HTTP/2 200" },
  { id: "w2", text: "content-type: text/html; charset=utf-8" },
  {
    id: "w3",
    text: "strict-transport-security: max-age=86400",
    verdict: "weak",
    label: "Short lifetime",
    severity: "Low",
    title: "Strict-Transport-Security max-age is short",
    evidence: "max-age=86400 is one day. Browsers forget the rule after that.",
    fix: "strict-transport-security: max-age=31536000",
  },
  {
    id: "w4",
    text: "set-cookie: session=…; Secure",
    verdict: "weak",
    label: "No HttpOnly",
    severity: "Low",
    title: "Cookies set without the HttpOnly attribute",
    evidence: "The session cookie can be read by scripts running on the page.",
    fix: "set-cookie: session=…; Secure; HttpOnly; SameSite=Lax",
  },
  {
    id: "w5",
    text: "x-content-type-options: nosniff",
    verdict: "ok",
    label: "Present",
  },
  {
    id: "w6",
    text: "referrer-policy: strict-origin-when-cross-origin",
    verdict: "ok",
    label: "Present",
  },
  {
    id: "w7",
    text: "content-security-policy:",
    verdict: "missing",
    label: "Missing",
    severity: "Medium",
    title: "Content-Security-Policy header is missing",
    evidence:
      "The response has no content-security-policy header, so the browser applies no limits on where scripts may load from.",
    fix: "content-security-policy-report-only: default-src 'self'",
  },
];

const APP: Line[] = [
  { id: "a1", text: '"dependencies": {' },
  {
    id: "a2",
    text: '  "example-library": "1.2.0",',
    verdict: "weak",
    label: "Known issue",
    severity: "High",
    title: "Known vulnerability (illustrative)",
    evidence:
      "Illustrative only. The exact version 1.2.0 would be compared with a vulnerability source.",
    fix: "Update to a fixed version when the source names one.",
  },
  {
    id: "a3",
    text: '  "another-package": "^2.0.0"',
    verdict: "missing",
    label: "Not checked",
    title: "Not checked: the version is a range",
    evidence:
      "^2.0.0 allows many versions, so no single version can be assessed.",
    fix: "Pin an exact version, or scan the lockfile instead.",
  },
  { id: "a4", text: "}" },
];

function Sheet() {
  const [tab, setTab] = useState<"site" | "app">("site");
  const lines = tab === "site" ? WEBSITE : APP;
  const first = lines.find((l) => l.verdict === "missing") ?? lines[0];
  const [pick, setPick] = useState<Record<string, string>>({
    site: "w7",
    app: "a3",
  });
  const selectedId = pick[tab] ?? first?.id;
  const selected = lines.find((l) => l.id === selectedId) ?? first;
  if (!selected) return null;
  return (
    <figure className="hx-sheet">
      <div className="hx-tabs" role="tablist" aria-label="Example input">
        <button
          type="button"
          role="tab"
          id="hx-tab-site"
          aria-selected={tab === "site"}
          aria-controls="hx-panel"
          tabIndex={tab === "site" ? 0 : -1}
          onClick={() => setTab("site")}
        >
          example.com
        </button>
        <button
          type="button"
          role="tab"
          id="hx-tab-app"
          aria-selected={tab === "app"}
          aria-controls="hx-panel"
          tabIndex={tab === "app" ? 0 : -1}
          onClick={() => setTab("app")}
        >
          package.json
        </button>
        <span className="hx-tabs-note">
          {tab === "site" ? "Response headers, excerpt" : "In development"}
        </span>
      </div>
      <div
        id="hx-panel"
        role="tabpanel"
        aria-labelledby={`hx-tab-${tab}`}
        className="hx-code"
        key={tab}
      >
        {lines.map((l, i) =>
          l.verdict ? (
            <button
              key={l.id}
              type="button"
              className={`hx-line hx-${l.verdict}`}
              aria-pressed={l.id === selected.id}
              style={{ "--i": i } as CSSProperties}
              onClick={() => setPick({ ...pick, [tab]: l.id })}
            >
              <span className="hx-no" aria-hidden="true">
                {i + 1}
              </span>
              <code>{l.text}</code>
              <span className="hx-verdict">
                <span aria-hidden="true" className="hx-mark" /> {l.label}
              </span>
            </button>
          ) : (
            <div
              key={l.id}
              className="hx-line hx-plain"
              style={{ "--i": i } as CSSProperties}
            >
              <span className="hx-no" aria-hidden="true">
                {i + 1}
              </span>
              <code>{l.text}</code>
            </div>
          ),
        )}
      </div>
      <figcaption className="hx-detail" aria-live="polite">
        <p className="hx-detail-title">
          {selected.severity && (
            <span className={`hx-sev hx-sev-${selected.severity}`}>
              {selected.severity}
            </span>
          )}
          {selected.title}
        </p>
        <p>{selected.evidence}</p>
        <pre>{selected.fix}</pre>
        <p className="hx-fine">
          {tab === "site"
            ? `Illustrative example, not a real scan. The full sample report scores this site ${sample.score} out of 100, grade ${sample.grade}.`
            : "Illustrative example. App Scanning is not open to the public, and an incomplete run is never shown as clean."}
        </p>
      </figcaption>
    </figure>
  );
}

export function HomeHero({
  register,
  onApp,
}: {
  register: string;
  onApp: () => void;
}) {
  return (
    <section className="hx-hero" aria-labelledby="hx-title">
      <div className="hx-copy">
        <h1 id="hx-title" className="hx-title">
          Know what puts your digital assets at risk.
        </h1>
        <p className="hx-lead">
          SecureScope reads what your website sends to every visitor and tells
          you what is missing, with the evidence and the fix. App Scanning, for
          known vulnerabilities in your application’s dependencies, is in
          development.
        </p>
        <div className="hx-actions">
          <a className="btn" href={register}>
            Scan your website
          </a>
          <button type="button" className="btn-ghost" onClick={onApp}>
            Explore App Scanning
          </button>
          <a className="hx-quiet" href="#/sample-report">
            View sample report
          </a>
        </div>
        <p className="hx-assure">
          Passive checks only. Ownership verified first. Free plan, no card.
        </p>
      </div>
      <Sheet />
    </section>
  );
}

const SPEC = {
  site: [
    [
      "Checks",
      "HTTPS, headers, cookies and TLS certificates. Exposed files and information leaks.",
    ],
    [
      "You get",
      "Findings ranked by severity, each with evidence and a fix. A score history and a PDF report.",
    ],
    [
      "Limits",
      "Passive checks from outside only. Not a penetration test, and a clean result is not proof of security.",
    ],
  ],
  app: [
    [
      "Limits",
      "Only supported files and exact versions are assessed. An incomplete or failed run is never reported as clean.",
    ],
  ],
} as const;

export function HomeProducts({
  register,
  onApp,
  planned,
  works,
}: {
  register: string;
  onApp: () => void;
  planned: readonly string[];
  works: readonly string[];
}) {
  return (
    <section id="products" className="hx-products" aria-labelledby="h-products">
      <h2 id="h-products" className="hx-h2">
        Two products, one place to look
      </h2>
      <article className="hx-product">
        <header>
          <h3>Website Scanning</h3>
          <p className="hx-status hx-status-live">
            <span aria-hidden="true" className="hx-dot" /> Available
          </p>
          <p className="hx-blurb">
            Assess the security configuration of a website you have verified you
            own, and review each finding with the evidence and a fix.
          </p>
          <a className="btn" href={register}>
            Scan your website
          </a>
        </header>
        <dl>
          {SPEC.site.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </article>
      <article className="hx-product hx-product-soon">
        <header>
          <h3>App Scanning</h3>
          <p className="hx-status">
            <span aria-hidden="true" className="hx-dot" /> In development
          </p>
          <p className="hx-blurb">
            Assess supported dependency manifests for known vulnerabilities. Not
            open to the public yet.
          </p>
          <button type="button" className="btn-ghost" onClick={onApp}>
            Read about App Scanning
          </button>
        </header>
        <dl>
          <div>
            <dt>Built so far</dt>
            <dd>
              <ul>
                {works.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </dd>
          </div>
          {SPEC.app.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          <div>
            <dt>Planned, not available</dt>
            <dd>
              <ul>
                {planned.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </dd>
          </div>
        </dl>
      </article>
    </section>
  );
}
