import type { Lang } from "./i18n";
import { t } from "./i18n";
import type { EventType } from "./types";

export function tomorrowISO(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
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
    return "bg-sky-50 text-sky-800 ring-sky-200";
  }
  if (eventType === "drought") {
    return "bg-amber-50 text-amber-800 ring-amber-200";
  }
  return "bg-emerald-50 text-emerald-800 ring-emerald-200";
}

export function eventDot(eventType: EventType | string): string {
  if (eventType === "flood") return "#0284c7";
  if (eventType === "drought") return "#b45309";
  return "#15803d";
}

export function alertTone(nivel: string): string {
  if (nivel === "critical") {
    return "border-rose-200 bg-rose-50 text-rose-900";
  }
  if (nivel === "warning") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-sky-200 bg-sky-50 text-sky-900";
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
