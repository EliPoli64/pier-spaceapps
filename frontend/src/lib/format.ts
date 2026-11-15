import type { Lang } from "./i18n";
import { t } from "./i18n";
import type { EventType } from "./types";

export const MIN_NASA_DATE = "1981-01-01";

export function isoWithOffset(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export type DateValidationError = "empty" | "future" | "too_early";

export function validatePlanningDate(
  iso: string,
  enforceAvailableWindow: boolean,
): DateValidationError | null {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "empty";
  const parsed = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return "empty";
  if (!enforceAvailableWindow) return null;
  if (iso > isoWithOffset(0)) return "future";
  if (iso < MIN_NASA_DATE) return "too_early";
  return null;
}

export function formatDate(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(lang === "es" ? "es" : "en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatNumber(
  value: number | null | undefined,
  lang: Lang,
  digits = 0,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(lang === "es" ? "es" : "en", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

export function formatCurrency(
  value: number | null | undefined,
  currency: string | null | undefined,
  lang: Lang,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  try {
    return new Intl.NumberFormat(lang === "es" ? "es" : "en", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toFixed(0)} ${currency || "USD"}`;
  }
}

export function roundCoord(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function eventLabel(eventType: EventType | string, lang: Lang): string {
  if (eventType === "flood") return t(lang, "eventFlood");
  if (eventType === "drought") return t(lang, "eventDrought");
  return t(lang, "eventNone");
}

export function sourceLabel(source: string | null | undefined, lang: Lang): string {
  if (!source) return t(lang, "sourceUnknown");
  const normalized = source.toLowerCase();
  if (normalized.includes("imerg") || normalized.includes("power+")) {
    return t(lang, "sourcePowerImerg");
  }
  if (normalized.includes("power") || normalized.includes("nasa")) {
    return t(lang, "sourcePower");
  }
  if (
    normalized.includes("sint") ||
    normalized.includes("synth") ||
    normalized.includes("cache")
  ) {
    return t(lang, "sourceSynthetic");
  }
  return source;
}

export function reasonLabel(motivo: string | null | undefined, lang: Lang): string {
  const normalized = (motivo || "").toLowerCase();
  if (normalized.includes("gdd") || normalized.includes("window")) {
    return t(lang, "reasonGddWindow");
  }
  if (normalized.includes("waterlog") || normalized.includes("flood")) {
    return t(lang, "reasonWaterlogging");
  }
  if (normalized.includes("drought") || normalized.includes("water")) {
    return t(lang, "reasonDrought");
  }
  if (normalized.includes("event") || normalized.includes("match")) {
    return t(lang, "reasonEventMatch");
  }
  return t(lang, "reasonUnknown");
}

export function eventTone(eventType: EventType | string): string {
  if (eventType === "flood") {
    return "bg-sky-50 text-sky-900 ring-sky-200";
  }
  if (eventType === "drought") {
    return "bg-stone-100 text-stone-800 ring-stone-300";
  }
  return "bg-emerald-50 text-emerald-900 ring-emerald-200";
}

export function eventDot(eventType: EventType | string): string {
  if (eventType === "flood") return "#0284c7";
  if (eventType === "drought") return "#78716c";
  return "#15803d";
}

export function alertTone(nivel: string): string {
  if (nivel === "critical") {
    return "border-slate-200 border-l-4 border-l-[#0b1f3a] bg-slate-50 text-slate-900";
  }
  if (nivel === "warning") {
    return "border-slate-200 border-l-4 border-l-teal-700 bg-slate-50/75 text-slate-800";
  }
  return "border-sky-200 border-l-4 border-l-sky-700 bg-sky-50/45 text-slate-800";
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
