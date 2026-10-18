export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type ScanStatus = "queued" | "running" | "completed" | "failed";

export const SEVERITIES: readonly Severity[] = ["critical", "high", "medium", "low", "info"];

export interface Finding {
  id: string;
  title: string;
  severity: Severity;
  category: string;
  description: string;
  evidence: string | null;
  remediation: string;
}

export interface TargetMetadata {
  requested_url: string;
  final_url: string | null;
  host: string;
  resolved_addresses: string[];
  status_code: number | null;
  content_type: string | null;
  redirect_chain: string[];
  off_origin_redirect: string | null;
  response_time_ms: number | null;
  requests_made: number;
  checks_run: string[];
}

export interface ScanSummary {
  id: string;
  target_url: string;
  host: string;
  status: ScanStatus;
  score: number | null;
  grade: string | null;
  created_at: string;
  finished_at: string | null;
  counts: Partial<Record<Severity, number>>;
}

export interface ScanDetail extends ScanSummary {
  error: string | null;
  metadata: TargetMetadata | null;
  findings: Finding[];
  score_note: string;
}

export interface ScanList {
  items: ScanSummary[];
  total: number;
}

export type ReportFormat = "json" | "md" | "html";

export type Role = "OWNER" | "ADMIN" | "SECURITY_ANALYST" | "MEMBER" | "VIEWER";
export const ROLES: readonly Role[] = ["OWNER", "ADMIN", "SECURITY_ANALYST", "MEMBER", "VIEWER"];

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  organizations: Organization[];
}

export interface Member {
  user_id: string;
  email: string;
  role: Role;
  joined_at: string;
}

export interface OrganizationDetail extends Organization {
  members: Member[];
}

/** Mirrors backend/app/security/permissions.py. The server enforces; this only shapes the UI. */
export function canScan(role: Role): boolean {
  return role !== "VIEWER";
}
export function canManageMembers(role: Role): boolean {
  return role === "OWNER" || role === "ADMIN";
}
