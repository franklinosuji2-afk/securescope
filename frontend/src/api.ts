import type { ReportFormat, ScanDetail, ScanList } from "./types";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch {
    throw new ApiError("Could not reach the SecureScope service. Is the backend running?", 0);
  }
  if (!response.ok) {
    throw new ApiError(await describeError(response), response.status);
  }
  return (await response.json()) as T;
}

async function describeError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return "The request was not valid. Check the URL and try again.";
    }
  } catch {
    /* fall through */
  }
  return `The request failed (HTTP ${response.status}).`;
}

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
