import { formatDate } from "../format";
import { guidanceFor } from "../guidance";
import { buildHash } from "../router";
import type { Finding, ScanDetail } from "../types";
import { SeverityBadge } from "./ui";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="card detail-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export default function FindingDetail({ scan, finding }: { scan: ScanDetail; finding: Finding }) {
  const guidance = guidanceFor(finding.id);
  const meta = scan.metadata;
  return (
    <article className="stack">
      <a className="back-link" href={buildHash("findings", scan.id)}>
        ← All findings
      </a>
      <header className="detail-head">
        <div className="row">
          <SeverityBadge severity={finding.severity} />
          <span className="muted small">
            {finding.category} · <code>{finding.id}</code>
          </span>
        </div>
        <h1>{finding.title}</h1>
        <p className="muted">
          Reported in the scan of <strong>{scan.host}</strong> on {formatDate(scan.created_at)}. Not yet re-checked by a
          later scan.
        </p>
      </header>

      <Section id="d-target" title="Affected target">
        <dl className="meta">
          <dt>Host</dt>
          <dd>{scan.host}</dd>
          <dt>Scanned URL</dt>
          <dd>{scan.target_url}</dd>
          {meta?.final_url && (
            <>
              <dt>Final URL</dt>
              <dd>{meta.final_url}</dd>
            </>
          )}
          {meta?.status_code != null && (
            <>
              <dt>HTTP status</dt>
              <dd>{meta.status_code}</dd>
            </>
          )}
          <dt>Scan</dt>
          <dd>
            <a href={buildHash("overview", scan.id)}>Open scan summary</a>
          </dd>
        </dl>
      </Section>

      <Section id="d-evidence" title="Evidence">
        {finding.evidence ? <pre className="evidence">{finding.evidence}</pre> : <p className="muted">No evidence was recorded.</p>}
        <p className="small">
          <strong>How this was detected:</strong>{" "}
          {guidance.detection === "observed" ? "Direct observation. " : "Heuristic match, not confirmed. "}
          {guidance.detectionNote}
        </p>
      </Section>

      <Section id="d-impact" title="What it means">
        <p>{finding.description}</p>
        <p>
          <strong>Why it matters:</strong> {guidance.impact}
        </p>
      </Section>

      <Section id="d-fix" title="Recommended fix">
        <p>{finding.remediation}</p>
        {guidance.fixExample && (
          <>
            <h3>{guidance.fixExample.label}</h3>
            <pre className="evidence">{guidance.fixExample.code}</pre>
            <p className="muted small">Adapt this example to your framework or hosting platform before using it.</p>
          </>
        )}
      </Section>

      <Section id="d-verify" title="How to verify">
        <p>{guidance.verify}</p>
        <p className="muted small">
          SecureScope does not mark a finding as fixed. It is treated as resolved only when a later scan of the same target
          no longer reports it.
        </p>
      </Section>

      <Section id="d-limits" title="Limits of this finding">
        <p>{guidance.limitations}</p>
        {guidance.references.length > 0 && (
          <>
            <h3>References</h3>
            <ul className="refs">
              {guidance.references.map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noopener noreferrer">
                    {r.label}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>
    </article>
  );
}
