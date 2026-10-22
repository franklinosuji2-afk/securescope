import type { Confidence, FindingStatus, Severity } from "./types";

export function formatDate(iso: string | null): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "–";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function severityLabel(severity: Severity): string {
  return severity.charAt(0).toUpperCase() + severity.slice(1);
}

export function gradeClass(grade: string | null): string {
  if (grade === "D") return "grade grade-poor";
  if (grade === "F") return "grade grade-bad";
  return "grade";
}

export function statusLabel(status: FindingStatus): string {
  return {
    open: "Open",
    accepted_risk: "Accepted risk",
    false_positive: "False positive",
    resolved: "No longer detected",
  }[status];
}

export function statusExplanation(status: FindingStatus): string {
  return {
    open: "Reported and still open. It becomes “No longer detected” when a later completed scan of this host no longer reports it.",
    accepted_risk:
      "Your team decided to accept this risk. Later scans do not change that decision.",
    false_positive:
      "Your team marked this as a false positive. Later scans do not change that decision.",
    resolved:
      "A later scan of this host no longer reported it. That suggests the fix worked but does not prove it. It returns to Open if it appears again.",
  }[status];
}

export function confidenceLabel(confidence: Confidence): string {
  return {
    high: "High confidence",
    medium: "Medium confidence",
    low: "Low confidence",
  }[confidence];
}

const AUDIT_LABELS: Record<string, string> = {
  "user.registered": "Account created",
  "auth.email_verified": "Email confirmed",
  "auth.login.success": "Signed in",
  "auth.login.failed": "Failed sign-in",
  "auth.session.refreshed": "Session renewed",
  "auth.password_reset.requested": "Password reset requested",
  "auth.password_reset.completed": "Password reset completed",
  "auth.logout": "Signed out",
  "org.created": "Organization created",
  "org.member.added": "Member added",
  "org.member.role_changed": "Member role changed",
  "org.member.removed": "Member removed",
  "org.invitation.created": "Invitation sent",
  "org.invitation.accepted": "Invitation accepted",
  "org.invitation.revoked": "Invitation revoked",
  "target.created": "Site added",
  "target.verified": "Site ownership verified",
  "target.verification_failed": "Site verification failed",
  "target.reverified": "Site ownership re-verified",
  "target.challenge_regenerated": "Verification challenge renewed",
  "target.deleted": "Site removed",
  "scan.created": "Scan started",
  "scan.cancelled": "Scan cancelled",
  "scan.retried": "Scan run again",
  "report.exported": "Report exported",
  "finding.status_changed": "Finding status changed",
};

/** A readable name for an audit event type. Unknown types show their raw name rather than hiding it. */
export function auditLabel(eventType: string): string {
  return AUDIT_LABELS[eventType] ?? eventType;
}
