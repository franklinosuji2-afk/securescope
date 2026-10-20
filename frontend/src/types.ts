export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type ScanStatus =
  "queued" | "running" | "completed" | "failed" | "cancelled";

export const SEVERITIES: readonly Severity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];

export type Confidence = "high" | "medium" | "low";
/** `resolved` is only ever set by the scanner, when a later completed scan no longer reports the finding. */
export type FindingStatus =
  "open" | "accepted_risk" | "false_positive" | "resolved";
export const FINDING_STATUSES: readonly FindingStatus[] = [
  "open",
  "accepted_risk",
  "false_positive",
  "resolved",
];
export const ANALYST_STATUSES: readonly FindingStatus[] = [
  "open",
  "accepted_risk",
  "false_positive",
];

export interface Finding {
  id: string;
  title: string;
  severity: Severity;
  category: string;
  description: string;
  evidence: string | null;
  remediation: string;
  confidence: Confidence;
  fingerprint: string | null;
  status: FindingStatus;
  status_note: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
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

export type ReportFormat = "json" | "md" | "html" | "pdf";

export type Role = "OWNER" | "ADMIN" | "SECURITY_ANALYST" | "MEMBER" | "VIEWER";
export const ROLES: readonly Role[] = [
  "OWNER",
  "ADMIN",
  "SECURITY_ANALYST",
  "MEMBER",
  "VIEWER",
];

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

export type VerificationMethod = "dns_txt" | "http_file";
export type TargetStatus = "pending" | "verified" | "expired" | "reverify";

export interface Target {
  id: string;
  hostname: string;
  status: TargetStatus;
  challenge_token: string;
  challenge_expires_at: string;
  verified_at: string | null;
  verification_expires_at?: string | null;
  verification_method: VerificationMethod | null;
  last_check_at: string | null;
  last_check_error: string | null;
  created_at: string;
  dns_record_name: string;
  dns_record_value: string;
  http_file_url: string;
  http_file_content: string;
}

export function canManageTargets(role: Role): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "SECURITY_ANALYST";
}

export function canReadAudit(role: Role): boolean {
  return role === "OWNER" || role === "ADMIN";
}

export function isActive(status: ScanStatus): boolean {
  return status === "queued" || status === "running";
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  event_type: string;
  actor_user_id: string | null;
  actor_email: string | null;
  resource_type: string | null;
  resource_id: string | null;
  request_id: string | null;
}

export interface AuditList {
  items: AuditEntry[];
  total: number;
  event_types: string[];
}

export function canTriageFindings(role: Role): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "SECURITY_ANALYST";
}

export interface ScorePoint {
  scan_id: string;
  score: number;
  scanned_at: string;
}

export interface TopFinding {
  host: string;
  scan_id: string;
  finding_id: string;
  title: string;
  severity: Severity;
  confidence: Confidence;
  remediation: string;
}

export interface SitePosture {
  host: string;
  latest_scan_id: string;
  score: number | null;
  grade: string | null;
  scanned_at: string;
  previous_score: number | null;
  score_change: number | null;
  open_counts: Partial<Record<Severity, number>>;
  open_total: number;
  top_finding: TopFinding | null;
  history: ScorePoint[];
}

export interface Overview {
  sites: SitePosture[];
  fix_first: TopFinding | null;
  other_open: number;
}
