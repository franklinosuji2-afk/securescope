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
  "scan-scope": {
    label: "Scan stayed on your verified site",
    why: "The scan never followed a redirect to a site you did not authorize.",
    prefixes: ["SS-SCOPE-"],
  },
};

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
    // Like the exported report: informational findings are notes and do not fail a check.
    const hits = matching.filter(
      (f) => f.severity !== "info" || f.id.startsWith("SS-DISC-SEC-"),
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
              {hits.length === 0 ? "✓ Passed" : "⚠ Needs attention"}
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
