import type { Demo, PlanRequest, PlanResponse } from "./types";

const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api"
).replace(/\/$/, "");

const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (API_KEY) headers.set("X-API-Key", API_KEY);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      "Could not reach the PIER API. Check that the API service is running.",
      0,
    );
  }

  const data = parseBody(await response.text());

  if (!response.ok) {
    const record =
      data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const detail = record.detail ?? record.error ?? response.statusText;
    throw new ApiError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      response.status,
      typeof record.error === "string" ? record.error : undefined,
    );
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
    request<PlanResponse>("/generate_plan", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
