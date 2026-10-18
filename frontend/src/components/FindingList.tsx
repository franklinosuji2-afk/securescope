import { useState } from "react";
import type { Finding } from "../types";
import { SeverityBadge } from "./ui";

function FindingItem({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const panelId = `finding-${finding.id}`;
  return (
    <li className="finding">
      <button className="finding-head" type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        <SeverityBadge severity={finding.severity} />
        <span className="finding-title">{finding.title}</span>
        <span className="chev" aria-hidden="true">
          ▸
        </span>
      </button>
      {open && (
        <div className="finding-body" id={panelId}>
          <div>
            <h4>ID</h4>
            <code>{finding.id}</code>
          </div>
          <div>
            <h4>What we saw</h4>
            <p>{finding.description}</p>
          </div>
          {finding.evidence && (
            <div>
              <h4>Evidence</h4>
              <div className="evidence">{finding.evidence}</div>
            </div>
          )}
          <div>
            <h4>Remediation</h4>
            <p>{finding.remediation}</p>
          </div>
        </div>
      )}
    </li>
  );
}

export default function FindingList({ findings }: { findings: Finding[] }) {
  return (
    <ul className="finding-list">
      {findings.map((f) => (
        <FindingItem key={f.id} finding={f} />
      ))}
    </ul>
  );
}
