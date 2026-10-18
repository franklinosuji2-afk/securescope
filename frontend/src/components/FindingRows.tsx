import { buildHash } from "../router";
import type { Finding } from "../types";
import { SeverityBadge } from "./ui";

export default function FindingRows({ scanId, findings }: { scanId: string; findings: Finding[] }) {
  return (
    <ul className="finding-list">
      {findings.map((finding) => (
        <li key={finding.id} className="finding-row">
          <a className="finding-link" href={buildHash("findings", scanId, finding.id)}>
            <SeverityBadge severity={finding.severity} />
            <span className="finding-main">
              <span className="finding-title">{finding.title}</span>
              <span className="muted small">
                {finding.category} · <code>{finding.id}</code>
              </span>
            </span>
            <span className="chev" aria-hidden="true">
              ▸
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
