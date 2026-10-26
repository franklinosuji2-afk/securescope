import { useState, type FormEvent } from "react";
import { ApiError, setFindingStatus } from "../api";
import { useAuth } from "../auth";
import {
  confidenceLabel,
  formatDate,
  statusExplanation,
  statusLabel,
} from "../format";
import { buildAssistantPrompt } from "../assistantPrompt";
import { guidanceFor } from "../guidance";
import { buildHash } from "../router";
import type { Finding, FindingStatus, ScanDetail } from "../types";
import { ANALYST_STATUSES, canTriageFindings } from "../types";
import RecheckPanel from "./RecheckPanel";
import { FindingStatusTag, SeverityBadge } from "./ui";

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card detail-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

function AssistantPrompt({ text }: { text: string }) {
  const [note, setNote] = useState("");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setNote("Copied.");
    } catch {
      setNote("Copying was blocked. Select the text and copy it yourself.");
    }
  };
  return (
    <details className="assistant-prompt">
      <summary>Prompt for an AI coding assistant</summary>
      <p className="muted small">
        Built from this finding and the fix guidance above. It contains no file
        paths or secrets. Read it before you paste it anywhere.
      </p>
      <textarea
        className="input"
        readOnly
        rows={12}
        value={text}
        aria-label="Prompt for an AI coding assistant"
      />
      <div className="row">
        <button type="button" className="btn-ghost" onClick={copy}>
          Copy prompt
        </button>
        {note && (
          <span role="status" className="muted small">
            {note}
          </span>
        )}
      </div>
    </details>
  );
}

function StatusPanel({
  finding,
  onChanged,
}: {
  finding: Finding;
  onChanged: () => void;
}) {
  const { organization } = useAuth();
  const allowed = organization ? canTriageFindings(organization.role) : false;
  const [status, setStatus] = useState<FindingStatus>(
    finding.status === "resolved" ? "open" : finding.status,
  );
  const [note, setNote] = useState(finding.status_note ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{
    kind: "ok" | "error";
    text: string;
  } | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!finding.fingerprint) return;
    setSaving(true);
    setMessage(null);
    try {
      await setFindingStatus(finding.fingerprint, status, note);
      setMessage({ kind: "ok", text: "Status saved." });
      onChanged();
    } catch (err) {
      setMessage({
        kind: "error",
        text:
          err instanceof ApiError
            ? err.message
            : "The status could not be saved.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section id="d-status" title="Status">
      <p>
        <FindingStatusTag status={finding.status} />{" "}
        <span className="muted">{statusExplanation(finding.status)}</span>
      </p>
      {finding.status_note && (
        <p className="small">
          <strong>Note:</strong> {finding.status_note}
        </p>
      )}
      {finding.first_seen_at && (
        <p className="muted small">
          First seen {formatDate(finding.first_seen_at)} · last seen{" "}
          {formatDate(finding.last_seen_at)}
        </p>
      )}
      {allowed && finding.fingerprint ? (
        <form className="status-form" onSubmit={(e) => void submit(e)}>
          <label className="toolbar-field">
            <span className="field-label">Change status</span>
            <select
              className="input"
              value={status}
              onChange={(e) => setStatus(e.target.value as FindingStatus)}
            >
              {ANALYST_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="toolbar-field">
            <span className="field-label">Note (optional)</span>
            <input
              className="input"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="row">
            <button className="btn" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save status"}
            </button>
            <span
              role="status"
              className={
                message?.kind === "error" ? "form-error" : "muted small"
              }
            >
              {message?.text}
            </span>
          </div>
          <p className="muted small">
            “No longer detected” cannot be set by hand. SecureScope sets it when
            a later scan of this host no longer reports the finding. It does not
            prove the fix is correct.
          </p>
        </form>
      ) : (
        <p className="muted small">
          Your role can read statuses but not change them.
        </p>
      )}
    </Section>
  );
}

export default function FindingDetail({
  scan,
  finding,
  onChanged = () => undefined,
}: {
  scan: ScanDetail;
  finding: Finding;
  onChanged?: () => void;
}) {
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
          <FindingStatusTag status={finding.status} />
          <span className="muted small">
            {finding.category} · <code>{finding.id}</code> ·{" "}
            {confidenceLabel(finding.confidence)}
          </span>
        </div>
        <h1>{finding.title}</h1>
        <p className="muted">
          Reported in the scan of <strong>{scan.host}</strong> on{" "}
          {formatDate(scan.created_at)}.
        </p>
      </header>

      <StatusPanel finding={finding} onChanged={onChanged} />
      <RecheckPanel scan={scan} finding={finding} />

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
        {finding.evidence ? (
          <pre className="evidence">{finding.evidence}</pre>
        ) : (
          <p className="muted">No evidence was recorded.</p>
        )}
        <p className="small">
          <strong>How this was detected:</strong>{" "}
          {finding.confidence === "high"
            ? "Direct observation. "
            : "Heuristic match, not confirmed. "}
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
        {guidance.fixes.map((fix) => (
          <div key={fix.label}>
            <h3>{fix.label}</h3>
            <pre className="evidence">{fix.code}</pre>
          </div>
        ))}
        {guidance.fixes.length > 0 && (
          <p className="muted small">
            Adapt these examples to your framework or hosting platform before
            using them.
          </p>
        )}
        <AssistantPrompt text={buildAssistantPrompt(finding, guidance)} />
      </Section>

      <Section id="d-verify" title="How to verify">
        <ol>
          {guidance.verify.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <p className="muted small">
          SecureScope does not mark a finding as fixed. It is treated as
          resolved only when a later scan of the same target no longer reports
          it.
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
