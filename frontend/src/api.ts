import type { Member, Organization, OrganizationDetail, ReportFormat, Role, ScanDetail, ScanList, Target, User, VerificationMethod } from "./types";

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
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function readCookie(name: string): string {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = readCookie("ss_csrf");
  if (activeOrganizationId) headers["X-Organization-Id"] = activeOrganizationId;

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError("Could not reach the SecureScope service. Is the backend running?", 0);
  }
  if (!response.ok) {
    // A 401 on /auth/login is a wrong password, not an expired session.
    if (response.status === 401 && !path.startsWith("/auth/login")) onUnauthorized?.();
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
          return String((first as { msg: unknown }).msg).replace(/^Value error, /, "");
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

export const register = (email: string, password: string, organizationName?: string) =>
  request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, ...(organizationName ? { organization_name: organizationName } : {}) }),
  });
export const login = (email: string, password: string) =>
  request<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => request<void>("/auth/logout", { method: "POST" });
export const fetchMe = () => request<User>("/auth/me");
export const forgotPassword = (email: string) =>
  request<{ detail: string }>("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
export const resetPassword = (token: string, password: string) =>
  request<{ detail: string }>("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) });
export const verifyEmail = (token: string) =>
  request<{ detail: string }>("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) });

// --- organizations ------------------------------------------------------------------------------

export const createOrganization = (name: string) =>
  request<Organization>("/organizations", { method: "POST", body: JSON.stringify({ name }) });
export const getOrganization = (id: string) => request<OrganizationDetail>(`/organizations/${encodeURIComponent(id)}`);
export const addMember = (orgId: string, email: string, role: Role) =>
  request<Member>(`/organizations/${encodeURIComponent(orgId)}/members`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
export const updateMember = (orgId: string, userId: string, role: Role) =>
  request<Member>(`/organizations/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
export const removeMember = (orgId: string, userId: string) =>
  request<void>(`/organizations/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });

// --- scans --------------------------------------------------------------------------------------

export function createScan(url: string, authorizationConfirmed: boolean): Promise<ScanDetail> {
  return request<ScanDetail>("/scans", {
    method: "POST",
    body: JSON.stringify({ url, authorization_confirmed: authorizationConfirmed }),
  });
}

export function getScan(id: string): Promise<ScanDetail> {
  return request<ScanDetail>(`/scans/${encodeURIComponent(id)}`);
}

export function listScans(limit = 25, offset = 0): Promise<ScanList> {
  return request<ScanList>(`/scans?limit=${limit}&offset=${offset}`);
}

export function reportUrl(id: string, format: ReportFormat): string {
  return `${BASE}/scans/${encodeURIComponent(id)}/report?format=${format}`;
}

// --- targets ------------------------------------------------------------------------------------

export const listTargets = () => request<{ items: Target[] }>("/targets").then((r) => r.items);
export const createTarget = (hostname: string) =>
  request<Target>("/targets", { method: "POST", body: JSON.stringify({ hostname }) });
export const deleteTarget = (id: string) => request<void>(`/targets/${encodeURIComponent(id)}`, { method: "DELETE" });
export const regenerateChallenge = (id: string) =>
  request<Target>(`/targets/${encodeURIComponent(id)}/challenge`, { method: "POST" });
export const verifyTarget = (id: string, method: VerificationMethod) =>
  request<Target>(`/targets/${encodeURIComponent(id)}/verify`, { method: "POST", body: JSON.stringify({ method }) });
