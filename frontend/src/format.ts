import type { Severity } from "./types";

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
