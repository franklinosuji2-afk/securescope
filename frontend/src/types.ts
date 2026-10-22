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
  checks_skipped?: { name: string; reason: string }[];
  tls?: {
    protocol: string | null;
    cipher: string | null;
    not_before: string | null;
    not_after: string | null;
    days_remaining: number | null;
    issuer: string | null;
    subject: string | null;
    verified: boolean;
  } | null;
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

/** A short-lived link to one PDF report. It only works for the person who asked for it. */
export interface ReportLink {
  report_id: string;
  url: string;
  expires_at: string;
  size_bytes: number;
  created_at: string;
}

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
  /** True only for the operator account that may open the Analytics page. */
  is_admin?: boolean;
  organizations: Organization[];
}

export interface Member {
  user_id: string;
  email: string;
  role: Role;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  invited_by_email: string | null;
  created_at: string;
  expires_at: string;
}

export interface InvitationPreview {
  organization_name: string;
  email: string;
  role: Role;
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
  /** Capped (the most recently scanned few), so a host missing here may still have been scanned. */
  sites: SitePosture[];
  fix_first: TopFinding | null;
  other_open: number;
  /** Every host with a completed scan on record. Absent from older servers: then it is unknown. */
  scanned_hosts?: string[];
}

export interface AnalyticsDay {
  date: string;
  views: number;
  visitors: number;
}
export interface AnalyticsPeriod {
  views: number;
  visitors: number;
  series: AnalyticsDay[];
}
export interface AnalyticsCount {
  name: string;
  count: number;
}
export interface AnalyticsPageCount extends AnalyticsCount {
  visitors: number;
}
export interface AnalyticsSummary {
  range_days: number;
  timezone: string;
  tracking_enabled: boolean;
  last_event_at: string | null;
  current: AnalyticsPeriod;
  previous: AnalyticsPeriod;
  today: { views: number; visitors: number };
  yesterday: { views: number; visitors: number };
  top_pages: AnalyticsPageCount[];
  landing_pages: AnalyticsCount[];
  sources: AnalyticsCount[];
  devices: AnalyticsCount[];
}

export interface PlatformHealth {
  version: string;
  started_at: string;
  uptime_seconds: number;
  database: { ok: boolean; latency_ms: number | null };
  requests: {
    window_seconds: number;
    requests: number;
    server_errors: number;
    client_errors: number;
    error_rate: number | null;
    p50_ms: number | null;
    p95_ms: number | null;
    p99_ms: number | null;
    routes: {
      route: string;
      requests: number;
      errors: number;
      p95_ms: number | null;
    }[];
    truncated: boolean;
  };
  scans: {
    window_hours: number;
    completed: number;
    failed: number;
    cancelled: number;
    in_progress: number;
    avg_seconds: number | null;
    max_concurrent: number;
    running_here: number;
  };
  mail: {
    provider: string;
    delivering: boolean;
    sent: number;
    failed: number;
    last_success_at: string | null;
    last_failure_at: string | null;
    last_failure_status: number | null;
  };
  configuration: {
    trusted_proxy: boolean;
    admin_email: boolean;
    analytics_enabled: boolean;
    metrics_endpoint: boolean;
    cookie_secure: boolean;
    verification_valid_days: number;
    retention_days: number;
  };
}

export interface PlanInfo {
  plan_id: string;
  name: string;
  price_eur_month: number;
  limits: {
    websites: number | null;
    scans_per_month: number | null;
    history_days: number;
    can_invite: boolean;
  };
  usage: {
    websites: number;
    scans_this_period: number;
    period_start: string;
    period_end: string;
  };
}
