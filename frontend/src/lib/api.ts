import type { Demo, PlanRequest, PlanResponse } from "./types";

const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api"
).replace(/\/$/, "");

const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? "";

export interface ValidationIssue {
  field: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  issues?: ValidationIssue[];
  isTimeout?: boolean;

  constructor(
    message: string,
    status: number,
    options?: {
      code?: string;
      issues?: ValidationIssue[];
      isTimeout?: boolean;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options?.code;
    this.issues = options?.issues;
    this.isTimeout = options?.isTimeout;
  }
}

function parseBody(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function looksLikeHtml(value: string): boolean {
  const trimmed = value.trim().toLowerCase();
  return trimmed.startsWith("<!doctype") || trimmed.startsWith("<html");
}

function extractValidationIssues(detail: unknown): ValidationIssue[] | undefined {
  if (!Array.isArray(detail)) return undefined;
  const issues: ValidationIssue[] = [];
  for (const item of detail) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const loc = Array.isArray(record.loc)
      ? record.loc
          .filter((part) => part !== "body")
          .map((part) => String(part))
          .join(".")
      : "";
    const msg =
      typeof record.msg === "string"
        ? record.msg.replace(/^Value error,\s*/i, "")
        : "";
    if (msg) issues.push({ field: loc, message: msg });
  }
  return issues.length > 0 ? issues : undefined;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 30000,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (API_KEY) headers.set("X-API-Key", API_KEY);

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    window.clearTimeout(timeoutId);
    const isTimeout = err instanceof DOMException && err.name === "AbortError";
    throw new ApiError(
      isTimeout ? "Request timed out." : "Network error.",
      0,
      { isTimeout },
    );
  }
  window.clearTimeout(timeoutId);

  const data = parseBody(await response.text());

  if (!response.ok) {
    const record =
      data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const detail = record.detail ?? record.error ?? data;
    const issues = extractValidationIssues(detail);

    let message = response.statusText || "Request failed";
    if (issues && issues.length > 0) {
      message = issues.map((i) => i.message).join(" ");
    } else if (typeof detail === "string" && detail.trim()) {
      message = looksLikeHtml(detail)
        ? `Server returned ${response.status}`
        : detail.trim();
    }

    throw new ApiError(message, response.status, {
      code: typeof record.error === "string" ? record.error : undefined,
      issues,
    });
  }

  return data as T;
}

export const api = {
  health: () =>
    request<{ status: string; version: string; demo_mode_default: boolean }>(
      "/health",
    ),
  demos: () => request<{ count: number; demos: Demo[] }>("/demos"),
  generatePlan: (body: PlanRequest) =>
    request<PlanResponse>(
      "/generate_plan",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
      120000,
    ),
};
