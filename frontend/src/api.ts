import type {
  AgencyDashboard,
  ActivationFunnel,
  AnalyticsSummary,
  Client,
  CreatedShare,
  ShareLink,
  SharedReportInfo,
  PlatformHealth,
  AuditList,
  FindingRecheck,
  FindingStatus,
  Invitation,
  InvitationPreview,
  Member,
  Overview,
  Organization,
  OrganizationDetail,
  ReportFormat,
  ReportLink,
  ScanComparison,
  Schedule,
  ScheduleFrequency,
  ScheduleList,
  ApiTokenCreated,
  ApiTokenList,
  Badge,
  BadgeList,
  Webhook,
  WebhookCreated,
  WebhookDelivery,
  WebhookList,
  WebhookTestResult,
  Role,
  ScanDetail,
  ScanList,
  Target,
  User,
  VerificationMethod,
  PlanInfo,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const BASE = "/api/v1";

let activeOrganizationId: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setActiveOrganization(id: string | null): void {
  activeOrganizationId = id;
}
export type OAuthProvider = "google" | "github";

/** Which outside sign-in methods the server offers. Anything unexpected means none. */
export async function fetchAuthProviders(): Promise<OAuthProvider[]> {
  const body = await request<{ providers?: unknown }>("/auth/providers");
  return Array.isArray(body.providers)
    ? body.providers.filter(
        (p): p is OAuthProvider => p === "google" || p === "github",
      )
    : [];
}

/** A plain link, not a fetch: the browser leaves for the provider and comes back signed in. */
export const oauthStartUrl = (provider: OAuthProvider): string =>
  `${BASE}/auth/oauth/${provider}/start`;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function readCookie(name: string): string {
  const match = document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  if (method !== "GET" && method !== "HEAD")
    headers["X-CSRF-Token"] = readCookie("ss_csrf");
  if (activeOrganizationId) headers["X-Organization-Id"] = activeOrganizationId;
  // Callers may add plain header pairs (for example Idempotency-Key); the ones above cannot be replaced.
  for (const [name, value] of Object.entries(
    (init.headers ?? {}) as Record<string, string>,
  ))
    if (!(name in headers)) headers[name] = value;

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      method,
      headers,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(
      "Could not reach the SecureScope service. Is the backend running?",
      0,
    );
  }
  if (!response.ok) {
    // A 401 on /auth/login is a wrong password, not an expired session.
    if (response.status === 401 && !path.startsWith("/auth/login"))
      onUnauthorized?.();
    throw new ApiError(await describeError(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function describeError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        const first: unknown = detail[0];
        if (first && typeof first === "object" && "msg" in first) {
          return String((first as { msg: unknown }).msg).replace(
            /^Value error, /,
            "",
          );
        }
        return "The request was not valid. Check the fields and try again.";
      }
    }
  } catch {
    /* fall through */
  }
  return `The request failed (HTTP ${response.status}).`;
}

// --- auth ---------------------------------------------------------------------------------------

export const register = (
  email: string,
  password: string,
  organizationName?: string,
) =>
  request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      ...(organizationName ? { organization_name: organizationName } : {}),
    }),
  });
export const login = (email: string, password: string) =>
  request<User>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
export const logout = () => request<void>("/auth/logout", { method: "POST" });
export const fetchMe = () => request<User>("/auth/me");
export const forgotPassword = (email: string) =>
  request<{ detail: string }>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
export const resetPassword = (token: string, password: string) =>
  request<{ detail: string }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
export const resendVerification = () =>
  request<{ detail: string }>("/auth/resend-verification", { method: "POST" });
export const verifyEmail = (token: string) =>
  request<{ detail: string }>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });

// --- account ------------------------------------------------------------------------------------

export const changePassword = (
  current_password: string,
  new_password: string,
) =>
  request<void>("/account/password", {
    method: "PATCH",
    body: JSON.stringify({ current_password, new_password }),
  });
export interface AccountInfo {
  email: string;
  email_verified: boolean;
  status: string;
  created_at: string;
  has_password: boolean;
}
export interface DeviceSession {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
}
export type FeedbackCategory =
  "general" | "ease_of_use" | "reports" | "accuracy" | "pricing" | "other";
export interface Feedback {
  rating: number;
  category: FeedbackCategory | null;
  message: string | null;
  created_at: string;
  updated_at: string;
}
export interface FeedbackEntry extends Feedback {
  plan: string | null;
}
export interface FeedbackSummary {
  count: number;
  average: number | null;
  by_rating: Record<string, number>;
  by_plan?: Record<string, { count: number; average: number }>;
  latest: FeedbackEntry[];
}
export const getFeedback = () => request<Feedback | null>("/feedback");
export const saveFeedback = (input: {
  rating: number;
  category: FeedbackCategory | null;
  message: string | null;
}) =>
  request<Feedback>("/feedback", {
    method: "PUT",
    body: JSON.stringify(input),
  });
export const withdrawFeedback = () =>
  request<void>("/feedback", { method: "DELETE" });
export const getFeedbackSummary = () =>
  request<FeedbackSummary>("/feedback/summary");
export const getAccount = () => request<AccountInfo>("/account");
export const listSessions = () => request<DeviceSession[]>("/account/sessions");
export const revokeSession = (id: string) =>
  request<void>(`/account/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
export const revokeOtherSessions = () =>
  request<void>("/account/sessions/revoke-others", { method: "POST" });
/** Where the browser downloads the person's own data file from (a plain GET, sent with the session cookie). */
export const ACCOUNT_EXPORT_URL = `${BASE}/account/export`;

/** Deletes the signed-in person's account for good. `confirm` must be the word DELETE. */
export const deleteAccount = (password: string, confirm: string) =>
  request<void>("/account", {
    method: "DELETE",
    body: JSON.stringify({ password, confirm }),
  });

// --- organizations ------------------------------------------------------------------------------

export const createOrganization = (name: string) =>
  request<Organization>("/organizations", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
export const getOrganization = (id: string) =>
  request<OrganizationDetail>(`/organizations/${encodeURIComponent(id)}`);
export const addMember = (orgId: string, email: string, role: Role) =>
  request<Member>(`/organizations/${encodeURIComponent(orgId)}/members`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
export const updateMember = (orgId: string, userId: string, role: Role) =>
  request<Member>(
    `/organizations/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ role }),
    },
  );
export const removeMember = (orgId: string, userId: string) =>
  request<void>(
    `/organizations/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "DELETE",
    },
  );

export async function getPlan(orgId: string): Promise<PlanInfo | null> {
  const plan = await request<PlanInfo>(
    `/organizations/${encodeURIComponent(orgId)}/plan`,
  );
  // Anything that is not a complete plan is treated as "unknown"; the server enforces limits regardless.
  return plan && plan.limits && plan.usage ? plan : null;
}
export const listInvitations = (orgId: string) =>
  request<Invitation[]>(
    `/organizations/${encodeURIComponent(orgId)}/invitations`,
  );
export const createInvitation = (orgId: string, email: string, role: Role) =>
  request<Invitation>(
    `/organizations/${encodeURIComponent(orgId)}/invitations`,
    { method: "POST", body: JSON.stringify({ email, role }) },
  );
export const revokeInvitation = (orgId: string, invitationId: string) =>
  request<void>(
    `/organizations/${encodeURIComponent(orgId)}/invitations/${encodeURIComponent(invitationId)}`,
    { method: "DELETE" },
  );
export const previewInvitation = (token: string) =>
  request<InvitationPreview>(
    `/invitations/preview?token=${encodeURIComponent(token)}`,
  );
export const acceptInvitation = (token: string) =>
  request<{ organization_id: string }>("/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ token }),
  });

// --- scans --------------------------------------------------------------------------------------

/** `idempotencyKey` makes a repeated request (double click, retry after a lost answer) return the same scan. */
export function createScan(
  url: string,
  authorizationConfirmed: boolean,
  idempotencyKey?: string,
): Promise<ScanDetail> {
  return request<ScanDetail>("/scans", {
    method: "POST",
    body: JSON.stringify({
      url,
      authorization_confirmed: authorizationConfirmed,
    }),
    ...(idempotencyKey
      ? { headers: { "Idempotency-Key": idempotencyKey } }
      : {}),
  });
}

export function getScan(id: string): Promise<ScanDetail> {
  return request<ScanDetail>(`/scans/${encodeURIComponent(id)}`);
}

export function listScans(limit = 25, offset = 0): Promise<ScanList> {
  return request<ScanList>(`/scans?limit=${limit}&offset=${offset}`);
}

export const cancelScan = (id: string) =>
  request<ScanDetail>(`/scans/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
  });
export const deleteScan = (id: string) =>
  request<void>(`/scans/${encodeURIComponent(id)}`, { method: "DELETE" });
export const recheckFinding = (scanId: string, findingId: string) =>
  request<FindingRecheck>(
    `/scans/${encodeURIComponent(scanId)}/findings/${encodeURIComponent(findingId)}/recheck`,
    { method: "POST" },
  );

export const retryScan = (id: string) =>
  request<ScanDetail>(`/scans/${encodeURIComponent(id)}/retry`, {
    method: "POST",
  });

export function listAuditEvents(
  limit = 25,
  offset = 0,
  eventType = "",
): Promise<AuditList> {
  const filter = eventType
    ? `&event_type=${encodeURIComponent(eventType)}`
    : "";
  return request<AuditList>(
    `/audit-events?limit=${limit}&offset=${offset}${filter}`,
  );
}

/**
 * Reports download through plain links, which cannot send the X-Organization-Id header, so the active
 * organization goes in the query. The server accepts it only from a member of that organization.
 */
export function reportUrl(
  id: string,
  format: ReportFormat,
  organizationId: string | null,
): string {
  const org = organizationId
    ? `&org=${encodeURIComponent(organizationId)}`
    : "";
  return `${BASE}/scans/${encodeURIComponent(id)}/report?format=${format}${org}`;
}

export const compareScans = (id: string, other: string) =>
  request<ScanComparison>(
    `/scans/${encodeURIComponent(id)}/compare?with=${encodeURIComponent(other)}`,
  );

/** Makes the PDF report for a finished scan (once; it is kept) and returns a link that expires. */
export const createPdfReport = (scanId: string) =>
  request<ReportLink>(`/scans/${encodeURIComponent(scanId)}/report/pdf`);

// --- targets ------------------------------------------------------------------------------------

export const listTargets = () =>
  request<{ items: Target[] }>("/targets").then((r) => r.items);
export const createTarget = (hostname: string) =>
  request<Target>("/targets", {
    method: "POST",
    body: JSON.stringify({ hostname }),
  });
export const deleteTarget = (id: string) =>
  request<void>(`/targets/${encodeURIComponent(id)}`, { method: "DELETE" });
export const regenerateChallenge = (id: string) =>
  request<Target>(`/targets/${encodeURIComponent(id)}/challenge`, {
    method: "POST",
  });
export const removeChallenge = (id: string) =>
  request<Target>(`/targets/${encodeURIComponent(id)}/challenge`, {
    method: "DELETE",
  });
export const verifyTarget = (id: string, method: VerificationMethod) =>
  request<Target>(`/targets/${encodeURIComponent(id)}/verify`, {
    method: "POST",
    body: JSON.stringify({ method }),
  });

export function setFindingStatus(
  fingerprint: string,
  status: FindingStatus,
  note: string,
): Promise<void> {
  return request<void>(`/findings/${encodeURIComponent(fingerprint)}`, {
    method: "PATCH",
    body: JSON.stringify({ status, note: note.trim() || null }),
  });
}

export const getOverview = () => request<Overview>("/overview");

export const fetchAnalytics = (days: number, timezone: string) =>
  request<AnalyticsSummary>(
    `/analytics/summary?days=${days}&tz=${encodeURIComponent(timezone)}`,
  );

export const fetchActivation = (days: number) =>
  request<ActivationFunnel>(`/analytics/activation?days=${days}`);

export const fetchPlatformHealth = () =>
  request<PlatformHealth>("/platform/health");

// --- agency workspace ---------------------------------------------------------------------------

export interface ClientInput {
  name: string;
  contact_email: string | null;
  notes: string | null;
}

/** Whether this workspace's plan includes client workspaces. Anything unexpected counts as "no". */
export async function agencyAvailable(): Promise<boolean> {
  try {
    const result = await request<{ items?: unknown }>("/agency/clients");
    return Array.isArray(result?.items);
  } catch {
    return false;
  }
}
export const listClients = () =>
  request<{ items: Client[] }>("/agency/clients").then((r) => r.items);
export const createClient = (input: ClientInput) =>
  request<Client>("/agency/clients", {
    method: "POST",
    body: JSON.stringify(input),
  });
export const updateClient = (id: string, input: ClientInput) =>
  request<Client>(`/agency/clients/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
export const deleteClient = (id: string) =>
  request<void>(`/agency/clients/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
export const assignClient = (targetId: string, clientId: string | null) =>
  request<void>(`/agency/targets/${encodeURIComponent(targetId)}/client`, {
    method: "PUT",
    body: JSON.stringify({ client_id: clientId }),
  });
export const getDashboard = () => request<AgencyDashboard>("/agency/dashboard");
export const getBranding = () =>
  request<{ agency_name: string | null }>("/agency/branding");
export const setBranding = (agencyName: string | null) =>
  request<{ agency_name: string | null }>("/agency/branding", {
    method: "PUT",
    body: JSON.stringify({ agency_name: agencyName }),
  });
export const listShares = (scanId: string) =>
  request<{ items: ShareLink[] }>(
    `/agency/scans/${encodeURIComponent(scanId)}/shares`,
  ).then((r) => r.items);
export const createShare = (scanId: string, days: 7 | 30 | 90) =>
  request<CreatedShare>(`/agency/scans/${encodeURIComponent(scanId)}/shares`, {
    method: "POST",
    body: JSON.stringify({ days }),
  });
export const revokeShare = (scanId: string, shareId: string) =>
  request<void>(
    `/agency/scans/${encodeURIComponent(scanId)}/shares/${encodeURIComponent(shareId)}`,
    { method: "DELETE" },
  );
export const getSharedReport = (token: string) =>
  request<SharedReportInfo>(`/shared/${encodeURIComponent(token)}`);

// --- scheduled scans ----------------------------------------------------------------------------

export const listSchedules = () => request<ScheduleList>("/schedules");

export const setSchedule = (
  targetId: string,
  input: { frequency: ScheduleFrequency; notify: boolean },
) =>
  request<Schedule>(`/schedules/${encodeURIComponent(targetId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });

// --- webhook alerts -----------------------------------------------------------------------------

export const listWebhooks = () => request<WebhookList>("/webhooks");

export const createWebhook = (
  url: string,
  kind: "webhook" | "slack" = "webhook",
) =>
  request<WebhookCreated>("/webhooks", {
    method: "POST",
    body: JSON.stringify({ url, kind }),
  });

export const testWebhook = (id: string) =>
  request<WebhookTestResult>(`/webhooks/${encodeURIComponent(id)}/test`, {
    method: "POST",
  });

export const renewWebhookSecret = (id: string) =>
  request<WebhookCreated>(`/webhooks/${encodeURIComponent(id)}/rotate`, {
    method: "POST",
  });

export const setWebhookEnabled = (id: string, enabled: boolean) =>
  request<Webhook>(`/webhooks/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });

export const listWebhookDeliveries = (id: string) =>
  request<WebhookDelivery[]>(`/webhooks/${encodeURIComponent(id)}/deliveries`);

export const deleteWebhook = (id: string) =>
  request<void>(`/webhooks/${encodeURIComponent(id)}`, { method: "DELETE" });

// --- CI tokens and badges -----------------------------------------------------------------------

export const listApiTokens = () => request<ApiTokenList>("/api-tokens");

export const createApiToken = (name: string) =>
  request<ApiTokenCreated>("/api-tokens", {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const revokeApiToken = (id: string) =>
  request<void>(`/api-tokens/${encodeURIComponent(id)}`, { method: "DELETE" });

export const listBadges = () => request<BadgeList>("/badges");

export const setBadge = (targetId: string, enabled: boolean, renew = false) =>
  request<Badge>(`/badges/${encodeURIComponent(targetId)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled, renew }),
  });

// --- App Scanning (off unless the server enables it) ---------------------------------------------

export type AppResult =
  | "completed_findings"
  | "completed_no_findings"
  | "incomplete"
  | "scanner_error"
  | "interrupted"
  | "cancelled"
  | "queued"
  | "running";
export interface AppUsage {
  runs_used: number;
  runs_limit: number | null;
  projects_used: number;
  projects_limit: number | null;
  period_end: string;
}
export interface AppOverview {
  plan: string;
  usage: AppUsage;
  supported_files: string[];
  max_files: number;
  max_file_bytes: number;
  ci_tokens_available: boolean;
  limitations: string[];
}
export interface AppProject {
  id: string;
  name: string;
  source: string;
  created_at: string;
}
export interface AppFinding {
  rule_id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  description: string;
  remediation: string;
  package_name: string | null;
  package_version: string | null;
  fixed_versions: string[];
  references: string[];
  aliases: string[];
  path: string | null;
}
export interface AppScanSummary {
  id: string;
  project_id: string;
  origin: "ci" | "upload";
  ref: string | null;
  status: string;
  result: AppResult;
  result_text: string;
  created_at: string;
  finished_at: string | null;
  counts: Record<string, number>;
}
export interface AppScan extends AppScanSummary {
  inputs: { name: string; size: number; sha256: string }[];
  checks_run: unknown[];
  checks_skipped: { reason?: string; name?: string }[];
  scanners: { name?: string; version?: string; data_timestamp?: string }[];
  findings: AppFinding[];
  limitations: string[];
  replayed: boolean;
}

export async function appScanningAvailable(): Promise<boolean> {
  try {
    const o = await request<AppOverview>("/app/overview");
    // An answer that is not an overview (an error page, an empty body) is not "available".
    return typeof o?.plan === "string" && typeof o?.usage === "object";
  } catch {
    return false;
  }
}
export const getAppOverview = () => request<AppOverview>("/app/overview");
export const listAppProjects = () =>
  request<{ items: AppProject[] }>("/app/projects").then((r) => r.items);
export const createAppProject = (name: string) =>
  request<AppProject>("/app/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
export const listAppScans = (projectId?: string) =>
  request<{ items: AppScanSummary[] }>(
    projectId
      ? `/app/scans?project_id=${encodeURIComponent(projectId)}`
      : "/app/scans",
  ).then((r) => r.items);
export const getAppScan = (id: string) =>
  request<AppScan>(`/app/scans/${encodeURIComponent(id)}`);
export const createAppScan = (
  projectId: string,
  files: { name: string; content: string }[],
  idempotencyKey: string,
) =>
  request<AppScan>("/app/scans", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      kinds: ["dependency"],
      files,
    }),
    headers: { "Idempotency-Key": idempotencyKey },
  });
