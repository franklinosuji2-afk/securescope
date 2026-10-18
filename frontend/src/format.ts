import type { Confidence, FindingStatus, Severity } from "./types";

export function formatDate(iso: string | null): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "–";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
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
    resolved: "Resolved",
  }[status];
}

export function statusExplanation(status: FindingStatus): string {
  return {
    open: "Reported and still open. It becomes Resolved when a later completed scan of this host no longer reports it.",
    accepted_risk: "Your team decided to accept this risk. Later scans do not change that decision.",
    false_positive: "Your team marked this as a false positive. Later scans do not change that decision.",
    resolved: "A later scan of this host no longer reported it. It returns to Open if it appears again.",
  }[status];
}

export function confidenceLabel(confidence: Confidence): string {
  return { high: "High confidence", medium: "Medium confidence", low: "Low confidence" }[confidence];
}
