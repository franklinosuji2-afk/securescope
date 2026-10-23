import { buildHash } from "../router";
import type { ScanDetail } from "../types";

// Mirrors the checks the scanner runs (backend/app/scanner/checks.py, CHECK_LABELS).
const CHECKS: Record<
  string,
  { label: string; why: string; prefixes: string[] }
> = {
  https: {
    label: "HTTPS",
    why: "Traffic is encrypted, so visitors cannot be spied on or altered in transit.",
    prefixes: ["SS-TLS-"],
  },
  hsts: {
    label: "Strict-Transport-Security (HSTS)",
    why: "Tells browsers to always use HTTPS, which blocks downgrade attacks.",
    prefixes: ["SS-HDR-HSTS-"],
  },
  csp: {
    label: "Content-Security-Policy",
    why: "Limits where scripts can load from, which reduces the damage of injected code (XSS).",
    prefixes: ["SS-HDR-CSP-"],
  },
  "x-content-type-options": {
    label: "X-Content-Type-Options",
    why: "Stops browsers from guessing file types, a trick used to run disguised scripts.",
    prefixes: ["SS-HDR-XCTO-"],
  },
  "referrer-policy": {
    label: "Referrer-Policy",
    why: "Controls how much of your URLs is shared with other sites.",
    prefixes: ["SS-HDR-REF-"],
  },
  "permissions-policy": {
    label: "Permissions-Policy",
    why: "Switches off browser features such as camera or location that your site does not need.",
    prefixes: ["SS-HDR-PERM-"],
  },
  "disclosure-headers": {
    label: "Software version disclosure",
    why: "Server and X-Powered-By headers can reveal versions that attackers look up.",
    prefixes: ["SS-DISC-SRV-", "SS-DISC-XPB-"],
  },
  "cookie-attributes": {
    label: "Cookie security attributes",
    why: "Secure, HttpOnly and SameSite protect login cookies from theft and misuse.",
    prefixes: ["SS-COOKIE-"],
  },
  "directory-index": {
    label: "Directory listing",
    why: "An open file listing can expose files you never meant to publish.",
    prefixes: ["SS-DIR-"],
  },
  "tls-certificate": {
    label: "TLS certificate",
    why: "A valid, trusted, unexpired certificate for this host name. This is one connection, not a full TLS test.",
    prefixes: ["SS-TLS-CERT-"],
  },
  "exposed-files": {
    label: "No exposed .git directory or .env file",
    why: "Repository metadata or environment files on a web server can leak source code and secrets.",
    prefixes: ["SS-EXPOSE-"],
  },
  "security-txt": {
    label: "A security.txt contact file is published",
    why: "Tells researchers how to report a vulnerability to you.",
    prefixes: ["SS-DISC-SEC-"],
  },
  "mixed-content": {
    label: "The page loads nothing over plain HTTP",
    why: "Scripts, forms or styles fetched over HTTP on an HTTPS page can be changed by anyone on the network.",
    prefixes: ["SS-MIX-"],
  },
  sri: {
    label: "Scripts and styles from other sites carry integrity hashes",
    why: "An integrity hash makes the browser refuse a third-party file that was changed.",
    prefixes: ["SS-SRI-"],
  },
  cors: {
    label: "No risky cross-origin (CORS) headers",
    why: "Wildcard or null origins combined with credentials let other websites read private responses.",
    prefixes: ["SS-CORS-"],
  },
  "robots-sitemap": {
    label: "robots.txt and sitemap.xml do not point at sensitive paths",
    why: "These public files sometimes list admin, backup or staging paths that are better kept unannounced.",
    prefixes: ["SS-DISC-ROBOTS-", "SS-DISC-SITEMAP-"],
  },
  "email-spf": {
    label: "An SPF record limits who can send mail for the domain",
    why: "Without a strict SPF record, mail pretending to come from your domain is easier to send.",
    prefixes: ["SS-DNS-SPF-"],
  },
  "email-dmarc": {
    label: "A DMARC policy is published",
    why: "DMARC tells receiving mail servers what to do with mail that fails the domain's checks.",
    prefixes: ["SS-DNS-DMARC-"],
  },
  "dns-caa": {
    label: "A CAA record limits who can issue certificates",
    why: "It narrows which certificate authorities may issue certificates for your domain.",
    prefixes: ["SS-DNS-CAA-"],
  },
  dnssec: {
    label: "DNSSEC is enabled for the domain",
    why: "It lets resolvers detect forged DNS answers.",
    prefixes: ["SS-DNS-DNSSEC-"],
  },
  "scan-scope": {
    label: "Scan stayed on your verified site",
    why: "The scan never followed a redirect to a site you did not authorize.",
    prefixes: ["SS-SCOPE-"],
  },
};

// Keep in step with NOT_PASSED_AT_INFO in backend/app/scanner/checks.py.
const NOT_PASSED_AT_INFO = [
  "SS-DISC-SEC-",
  "SS-DISC-ROBOTS-",
  "SS-DISC-SITEMAP-",
  "SS-DNS-DMARC-",
  "SS-DNS-CAA-",
  "SS-DNS-DNSSEC-",
];

/** Every check that ran on this scan and whether it found something. */
export default function Checklist({ scan }: { scan: ScanDetail }) {
  const names = scan.metadata?.checks_run ?? [];
  const skipped = scan.metadata?.checks_skipped ?? [];
  const tls = scan.metadata?.tls;
  if (scan.status !== "completed" || names.length === 0) return null;
  const rows = names.map((name) => {
    const info = CHECKS[name] ?? { label: name, why: "", prefixes: [] };
    const matching = scan.findings.filter((f) =>
      info.prefixes.some((p) => f.id.startsWith(p)),
    );
    // Like the exported report: informational findings are notes and do not fail a check,
    // except for the checks whose informational finding still means "not done yet".
    const hits = matching.filter(
      (f) =>
        f.severity !== "info" ||
        NOT_PASSED_AT_INFO.some((p) => f.id.startsWith(p)),
    );
    const notes = matching.length - hits.length;
    return { name, info, hits, notes };
  });
  const passed = rows.filter((r) => r.hits.length === 0).length;
  return (
    <div className="card">
      <div className="card-title">
        <h2>What we checked</h2>
      </div>
      <p className="muted small">
        {passed} of {rows.length} checks passed. These checks are passive: they
        read the headers and page your site already sends, and change nothing.
      </p>
      <ul className="stack-sm" style={{ listStyle: "none", padding: 0 }}>
        {rows.map(({ name, info, hits, notes }) => (
          <li key={name}>
            <strong>
              {hits.length === 0 ? "✓ Passed" : "✕ Needs attention"}
            </strong>
            {" · "}
            {info.label}
            {hits.length > 0 && (
              <>
                {" "}
                <a href={buildHash("findings", scan.id)}>
                  ({hits.length} finding{hits.length === 1 ? "" : "s"})
                </a>
              </>
            )}
            {hits.length === 0 && notes > 0 && (
              <>
                {" "}
                <a href={buildHash("findings", scan.id)}>
                  ({notes} note{notes === 1 ? "" : "s"})
                </a>
              </>
            )}
            {info.why && <div className="muted small">{info.why}</div>}
          </li>
        ))}
      </ul>
      {skipped.length > 0 && (
        <div role="note">
          <strong>Not checked this time</strong>
          <ul className="stack-sm">
            {skipped.map((c) => (
              <li key={c.name}>
                {CHECKS[c.name]?.label ?? c.name}
                <div className="muted small">{c.reason}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {tls?.protocol && (
        <p className="muted small">
          TLS connection: {tls.protocol}
          {tls.days_remaining != null &&
            `, certificate valid for ${tls.days_remaining} more days`}
          {tls.issuer && `, issued by ${tls.issuer}`}.
        </p>
      )}
    </div>
  );
}
