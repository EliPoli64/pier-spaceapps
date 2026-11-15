import { useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Award,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardCopy,
  CloudRain,
  Info,
  Leaf,
  MessageSquare,
  Printer,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sprout,
  ThermometerSun,
  TrendingUp,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Lang } from "../lib/i18n";
import { t, tFormat } from "../lib/i18n";
import type { Crop, PlanResponse } from "../lib/types";
import {
  alertTone,
  eventLabel,
  eventTone,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  reasonLabel,
  sourceLabel,
} from "../lib/format";

type Tab = "overview" | "crops" | "excluded" | "rotation";
type SortKey = "score" | "deadline" | "margin" | "confidence";

interface ResultsProps {
  result: PlanResponse;
  lang: Lang;
  stale: boolean;
  date: string;
  lat: number;
  lon: number;
  demoMode: boolean;
  onRefresh: () => void;
  loading: boolean;
}

function Metric({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  tone: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
        <span
          className={`inline-flex h-7 w-7 items-center justify-center rounded-lg ${tone}`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        {label}
      </div>
      <p className="mt-2 text-xl font-bold tracking-tight tabular-nums text-slate-900 sm:text-2xl">
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-xs font-medium text-slate-600">{hint}</p>
      ) : null}
    </div>
  );
}

function EmptyState({
  icon: Icon,
  text,
}: {
  icon: LucideIcon;
  text: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <p className="mt-3 max-w-md text-sm font-medium text-slate-600">{text}</p>
    </div>
  );
}

function deadlineBadge(days: number, lang: Lang) {
  if (days <= 0) {
    return {
      tone: "bg-rose-50 text-rose-800 ring-rose-200",
      label: t(lang, "pastDueBadge"),
    };
  }
  if (days <= 7) {
    return {
      tone: "bg-amber-50 text-amber-800 ring-amber-200",
      label: `${days}d · ${t(lang, "urgentBadge")}`,
    };
  }
  return {
    tone: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    label: `${days}d · ${t(lang, "onTrackBadge")}`,
  };
}

function CropRow({
  crop,
  rank,
  lang,
}: {
  crop: Crop;
  rank: number;
  lang: Lang;
}) {
  const badge = deadlineBadge(crop.days_until_deadline, lang);
  const confPct = Math.round((crop.rescue_confidence ?? 0) * 100);

  return (
    <tr
      className={`border-t border-slate-100 transition hover:bg-slate-50/80 ${
        rank === 1 ? "bg-emerald-50/35" : ""
      }`}
    >
      <td className="whitespace-nowrap px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span
            className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
              rank === 1
                ? "bg-emerald-700 text-white"
                : "bg-emerald-50 text-emerald-800"
            }`}
          >
            {rank}
          </span>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-slate-900">{crop.crop}</span>
              {rank === 1 ? (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-900">
                  {t(lang, "topPickBadge")}
                </span>
              ) : null}
            </div>
            {crop.role ? (
              <p className="text-[0.7rem] text-slate-600">{crop.role}</p>
            ) : null}
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3.5 tabular-nums text-slate-700">
        {formatDate(crop.plant_by_date, lang)}
      </td>
      <td className="whitespace-nowrap px-4 py-3.5">
        <span
          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ring-1 ${badge.tone}`}
        >
          {badge.label}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3.5 tabular-nums text-slate-700">
        {formatNumber(crop.gdd_requirement, lang, 0)}
      </td>
      <td className="whitespace-nowrap px-4 py-3.5 tabular-nums text-slate-700">
        {formatNumber(crop.margin_pct, lang, 1)}%
      </td>
      <td className="whitespace-nowrap px-4 py-3.5">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-emerald-700"
              style={{ width: `${Math.min(100, Math.max(0, confPct))}%` }}
            />
          </div>
          <span className="font-semibold tabular-nums text-slate-800">
            {formatPercent(crop.rescue_confidence)}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3.5 font-semibold tabular-nums text-slate-900">
        {formatNumber(crop.composite_score, lang, 2)}
      </td>
    </tr>
  );
}

function CropCardMobile({
  crop,
  rank,
  lang,
}: {
  crop: Crop;
  rank: number;
  lang: Lang;
}) {
  const badge = deadlineBadge(crop.days_until_deadline, lang);
  return (
    <article
      className={`rounded-2xl border p-4 ${
        rank === 1
          ? "border-emerald-300 bg-emerald-50/40"
          : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
              rank === 1
                ? "bg-emerald-700 text-white"
                : "bg-emerald-50 text-emerald-800"
            }`}
          >
            #{rank}
          </span>
          <div>
            <h3 className="text-sm font-bold text-slate-900">{crop.crop}</h3>
            {crop.role ? (
              <p className="text-xs text-slate-600">{crop.role}</p>
            ) : null}
          </div>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ring-1 ${badge.tone}`}
        >
          {badge.label}
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-slate-200/80 pt-3 text-xs">
        <div>
          <dt className="text-slate-600">{t(lang, "plantBy")}</dt>
          <dd className="font-semibold tabular-nums text-slate-900">
            {formatDate(crop.plant_by_date, lang)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-600">{t(lang, "score")}</dt>
          <dd className="font-semibold tabular-nums text-slate-900">
            {formatNumber(crop.composite_score, lang, 2)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-600">{t(lang, "gddRequirement")}</dt>
          <dd className="font-semibold tabular-nums text-slate-900">
            {formatNumber(crop.gdd_requirement, lang, 0)} (
            {formatNumber(crop.margin_pct, lang, 1)}%)
          </dd>
        </div>
        <div>
          <dt className="text-slate-600">{t(lang, "confidence")}</dt>
          <dd className="font-semibold tabular-nums text-slate-900">
            {formatPercent(crop.rescue_confidence)}
          </dd>
        </div>
      </dl>
    </article>
  );
}

const TABS: { id: Tab; key: Parameters<typeof t>[1]; icon: LucideIcon }[] = [
  { id: "overview", key: "tabOverview", icon: ClipboardCopy },
  { id: "crops", key: "tabCrops", icon: Sprout },
  { id: "excluded", key: "tabExcluded", icon: XCircle },
  { id: "rotation", key: "tabRotation", icon: RotateCcw },
];

export function Results({
  result,
  lang,
  stale,
  date,
  lat,
  lon,
  demoMode,
  onRefresh,
  loading,
}: ResultsProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const [copied, setCopied] = useState(false);
  const [smsCopied, setSmsCopied] = useState(false);
  const [rawExpanded, setRawExpanded] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>("score");
  const [reasonFilter, setReasonFilter] = useState<string>("all");
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    overview: null,
    crops: null,
    excluded: null,
    rotation: null,
  });

  const copyPlan = async () => {
    try {
      await navigator.clipboard.writeText(result.plan_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  const copySmsSummary = async () => {
    const top = result.crops[0];
    const eventStr = eventLabel(result.event_type, lang);
    const base = `PiER (${lat.toFixed(2)},${lon.toFixed(2)}): ${eventStr}. `;
    const action = top
      ? `${top.crop} -> ${top.plant_by_date} (${Math.round(result.gdd_remaining)} GDD)`
      : result.no_action_needed
        ? t(lang, "topPickNormal")
        : `${Math.round(result.gdd_remaining)} GDD`;
    const smsText = `${base}${action}`.slice(0, 160);
    try {
      await navigator.clipboard.writeText(smsText);
      setSmsCopied(true);
      window.setTimeout(() => setSmsCopied(false), 1800);
    } catch {
      setSmsCopied(false);
    }
  };

  const tabCount: Record<Tab, number | null> = {
    overview: null,
    crops: result.crops.length,
    excluded: result.exclusiones.length,
    rotation: null,
  };

  const topCrop = result.crops[0] ?? null;
  const runnersUp = result.crops.slice(1, 3);

  const sortedCrops = useMemo(() => {
    const copy = [...result.crops];
    copy.sort((a, b) => {
      if (sortBy === "deadline") {
        return a.days_until_deadline - b.days_until_deadline;
      }
      if (sortBy === "margin") {
        return b.margin_pct - a.margin_pct;
      }
      if (sortBy === "confidence") {
        return (b.rescue_confidence ?? 0) - (a.rescue_confidence ?? 0);
      }
      return b.composite_score - a.composite_score;
    });
    return copy;
  }, [result.crops, sortBy]);

  const exclusionReasons = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of result.exclusiones) {
      const label = reasonLabel(item.motivo, lang);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return Array.from(counts.entries());
  }, [result.exclusiones, lang]);

  const filteredExclusions = useMemo(() => {
    if (reasonFilter === "all") return result.exclusiones;
    return result.exclusiones.filter(
      (item) => reasonLabel(item.motivo, lang) === reasonFilter,
    );
  }, [result.exclusiones, reasonFilter, lang]);

  const updated = result.ultima_actualizacion
    ? new Date(result.ultima_actualizacion)
    : null;
  const updatedLabel =
    updated && !Number.isNaN(updated.getTime())
      ? updated.toLocaleString(lang === "es" ? "es" : "en", {
          dateStyle: "medium",
          timeStyle: "short",
        })
      : result.ultima_actualizacion || "—";

  const gddAcc = result.gdd_accumulated ?? 0;
  const gddTotal = gddAcc + result.gdd_remaining;
  const gddRemainingPct =
    gddTotal > 0 ? Math.round((result.gdd_remaining / gddTotal) * 100) : 100;

  const handleTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % TABS.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + TABS.length) % TABS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = TABS.length - 1;
    }
    if (nextIndex != null) {
      event.preventDefault();
      const nextTab = TABS[nextIndex].id;
      setTab(nextTab);
      tabRefs.current[nextTab]?.focus();
    }
  };

  return (
    <section className="space-y-4" aria-label={t(lang, "recoveryPlan")}>
      {stale ? (
        <div
          role="status"
          className="pier-no-print flex flex-col gap-2.5 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-start gap-2.5">
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
              aria-hidden="true"
            />
            <p className="font-medium">{t(lang, "staleWarning")}</p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-full bg-amber-800 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-amber-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-800 sm:self-auto"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            {t(lang, "refreshPlan")}
          </button>
        </div>
      ) : null}

      {result.fallback ? (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
            aria-hidden="true"
          />
          <p>{t(lang, "fallbackNote")}</p>
        </div>
      ) : null}

      {/* Top Decision Summary Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${eventTone(result.event_type)}`}
              >
                {result.event_type === "flood" ? (
                  <CloudRain className="h-3.5 w-3.5" aria-hidden="true" />
                ) : result.event_type === "drought" ? (
                  <ThermometerSun className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {eventLabel(result.event_type, lang)}
              </span>

              <span className="text-xs font-medium tabular-nums text-slate-600">
                {t(lang, "planForLabel")} {formatDate(date, lang)} ·{" "}
                {lat.toFixed(3)}, {lon.toFixed(3)}
              </span>

              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[0.7rem] font-semibold text-slate-700">
                {sourceLabel(result.fuente_datos, lang)}
              </span>

              <span
                className={`rounded-full px-2.5 py-0.5 text-[0.7rem] font-semibold ring-1 ${
                  demoMode
                    ? "bg-amber-50 text-amber-800 ring-amber-200"
                    : "bg-emerald-50 text-emerald-800 ring-emerald-200"
                }`}
              >
                {demoMode ? t(lang, "demoBadge") : t(lang, "liveBadge")}
              </span>
            </div>

            {/* Plain-language action headline */}
            <div className="mt-3">
              {result.no_action_needed ? (
                <h2 className="text-xl font-bold tracking-tight text-slate-900">
                  {t(lang, "topPickNormal")}
                </h2>
              ) : topCrop ? (
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
                    {tFormat(lang, "topPickHeadline", {
                      crop: topCrop.crop,
                      date: formatDate(topCrop.plant_by_date, lang),
                    })}
                  </h2>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${
                      topCrop.days_until_deadline <= 0
                        ? "bg-rose-50 text-rose-800 ring-rose-200"
                        : topCrop.days_until_deadline <= 7
                          ? "bg-amber-50 text-amber-800 ring-amber-200"
                          : "bg-emerald-50 text-emerald-800 ring-emerald-200"
                    }`}
                  >
                    {topCrop.days_until_deadline <= 0
                      ? t(lang, "pastDueBanner")
                      : tFormat(lang, "daysLeftBanner", {
                          days: topCrop.days_until_deadline,
                        })}
                  </span>
                </div>
              ) : (
                <h2 className="text-xl font-bold tracking-tight text-slate-900">
                  {tFormat(lang, "topPickNoCrops", {
                    gdd: formatNumber(result.gdd_remaining, lang, 0),
                  })}
                </h2>
              )}
            </div>
          </div>

          <div className="pier-no-print flex shrink-0 flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={copySmsSummary}
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 transition hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
            >
              {smsCopied ? (
                <Check
                  className="h-3.5 w-3.5 text-emerald-700"
                  aria-hidden="true"
                />
              ) : (
                <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {smsCopied ? t(lang, "smsCopied") : t(lang, "copySms")}
            </button>
            <button
              type="button"
              onClick={copyPlan}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
            >
              {copied ? (
                <Check
                  className="h-3.5 w-3.5 text-emerald-700"
                  aria-hidden="true"
                />
              ) : (
                <ClipboardCopy className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {copied ? t(lang, "copied") : t(lang, "copySummary")}
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
            >
              <Printer className="h-3.5 w-3.5" aria-hidden="true" />
              {t(lang, "printPlan")}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric
            label={t(lang, "metricEvent")}
            value={eventLabel(result.event_type, lang)}
            hint={
              result.event_severity
                ? `${t(lang, "severity")}: ${result.event_severity}`
                : undefined
            }
            icon={
              result.event_type === "flood"
                ? CloudRain
                : result.event_type === "drought"
                  ? ThermometerSun
                  : CheckCircle2
            }
            tone={eventTone(result.event_type)}
          />
          <Metric
            label={t(lang, "metricConfidence")}
            value={formatPercent(result.event_confidence)}
            hint={`${t(lang, "rescueConfidence")}: ${formatPercent(result.rescue_confidence)}`}
            icon={ShieldCheck}
            tone="bg-sky-50 text-sky-800"
          />
          <Metric
            label={t(lang, "metricGdd")}
            value={formatNumber(result.gdd_remaining, lang, 0)}
            hint={
              result.frost_date
                ? `${t(lang, "frostDate")}: ${formatDate(result.frost_date, lang)}`
                : undefined
            }
            icon={ThermometerSun}
            tone="bg-amber-50 text-amber-800"
          />
          <Metric
            label={t(lang, "metricCrops")}
            value={result.crops.length}
            hint={tFormat(lang, "excludedCountHint", {
              n: result.exclusiones.length,
            })}
            icon={Sprout}
            tone="bg-emerald-50 text-emerald-800"
          />
        </div>
      </div>

      {/* Tabbed Detail Workspace */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div
          className="pier-no-print flex gap-1 overflow-x-auto border-b border-slate-200 bg-slate-50/70 px-3 pt-2.5"
          role="tablist"
          aria-label={t(lang, "recoveryPlan")}
        >
          {TABS.map((item, idx) => {
            const Icon = item.icon;
            const active = tab === item.id;
            const count = tabCount[item.id];
            return (
              <button
                key={item.id}
                ref={(el) => {
                  tabRefs.current[item.id] = el;
                }}
                id={`tab-${item.id}`}
                type="button"
                role="tab"
                aria-selected={active}
                aria-controls={`panel-${item.id}`}
                tabIndex={active ? 0 : -1}
                onClick={() => setTab(item.id)}
                onKeyDown={(e) => handleTabKeyDown(e, idx)}
                className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-t-xl border border-b-0 px-3.5 py-2.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                  active
                    ? "border-slate-200 bg-white text-slate-900 shadow-xs"
                    : "border-transparent text-slate-600 hover:bg-white/70 hover:text-slate-900"
                }`}
              >
                <Icon
                  className={`h-3.5 w-3.5 ${active ? "text-emerald-700" : ""}`}
                  aria-hidden="true"
                />
                {t(lang, item.key)}
                {count != null ? (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[0.65rem] tabular-nums ${
                      active
                        ? "bg-emerald-100 text-emerald-900"
                        : "bg-slate-200 text-slate-700"
                    }`}
                  >
                    {count}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        <div
          id={`panel-${tab}`}
          role="tabpanel"
          aria-labelledby={`tab-${tab}`}
          className="p-5"
        >
          {tab === "overview" ? (
            <div className="space-y-5">
              {/* Alerts & Advisories */}
              {result.alertas.length > 0 ? (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-600">
                    {t(lang, "advisoriesTitle")}
                  </h3>
                  <div className="mt-2 space-y-2">
                    {result.alertas.map((alert, index) => (
                      <div
                        key={`${alert.codigo}-${index}`}
                        className={`flex items-start justify-between gap-3 rounded-xl border p-3.5 text-sm ${alertTone(alert.nivel)}`}
                      >
                        <div className="flex items-start gap-2.5">
                          {alert.nivel === "info" ? (
                            <Info
                              className="mt-0.5 h-4 w-4 shrink-0"
                              aria-hidden="true"
                            />
                          ) : (
                            <AlertTriangle
                              className="mt-0.5 h-4 w-4 shrink-0"
                              aria-hidden="true"
                            />
                          )}
                          <span className="font-medium leading-relaxed">
                            {alert.mensaje}
                          </span>
                        </div>
                        <span className="hidden shrink-0 rounded bg-white/70 px-1.5 py-0.5 font-mono text-[0.65rem] font-semibold uppercase tracking-wide text-slate-700 sm:inline-block">
                          {alert.codigo}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
                {/* Left column: Top Pick + Runners-up + Full Report */}
                <div className="space-y-4 min-w-0">
                  {topCrop ? (
                    <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white p-4 sm:p-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-700 px-3 py-1 text-xs font-semibold text-white">
                          <Award className="h-3.5 w-3.5" aria-hidden="true" />
                          {t(lang, "topPickBadge")}
                        </span>
                        <span className="text-xs font-semibold tabular-nums text-emerald-900">
                          {t(lang, "score")}:{" "}
                          {formatNumber(topCrop.composite_score, lang, 2)}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-3">
                        <div>
                          <h3 className="text-xl font-bold text-slate-900">
                            {topCrop.crop}
                          </h3>
                          {topCrop.role ? (
                            <p className="text-xs font-medium text-slate-600">
                              {topCrop.role}
                            </p>
                          ) : null}
                        </div>
                        {result.ahorro ? (
                          <div className="text-right">
                            <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-emerald-800">
                              {t(lang, "savingsPerHa")}
                            </p>
                            <p className="text-lg font-bold tabular-nums text-emerald-900">
                              {formatCurrency(
                                result.ahorro.estimated_savings_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                        ) : null}
                      </div>

                      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-emerald-200/70 pt-3 text-xs sm:grid-cols-4">
                        <div>
                          <dt className="text-slate-600">{t(lang, "plantBy")}</dt>
                          <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                            {formatDate(topCrop.plant_by_date, lang)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-600">
                            {t(lang, "gddRequirement")}
                          </dt>
                          <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                            {formatNumber(topCrop.gdd_requirement, lang, 0)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-600">{t(lang, "margin")}</dt>
                          <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                            {formatNumber(topCrop.margin_pct, lang, 1)}%
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-600">
                            {t(lang, "confidence")}
                          </dt>
                          <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                            {formatPercent(topCrop.rescue_confidence)}
                          </dd>
                        </div>
                      </dl>
                    </div>
                  ) : null}

                  {runnersUp.length > 0 ? (
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-600">
                          {t(lang, "runnersUpTitle")}
                        </h3>
                        {result.crops.length > 3 ? (
                          <button
                            type="button"
                            onClick={() => setTab("crops")}
                            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                          >
                            {t(lang, "tabCrops")} ({result.crops.length})
                            <ArrowRight className="h-3 w-3" aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                      <div className="mt-2 grid gap-2.5 sm:grid-cols-2">
                        {runnersUp.map((crop, idx) => {
                          const badge = deadlineBadge(
                            crop.days_until_deadline,
                            lang,
                          );
                          return (
                            <div
                              key={crop.crop}
                              className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-semibold text-slate-900">
                                  #{idx + 2} {crop.crop}
                                </span>
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[0.68rem] font-semibold tabular-nums ring-1 ${badge.tone}`}
                                >
                                  {badge.label}
                                </span>
                              </div>
                              <p className="mt-1.5 text-xs tabular-nums text-slate-600">
                                {t(lang, "plantBy")}:{" "}
                                <strong className="text-slate-800">
                                  {formatDate(crop.plant_by_date, lang)}
                                </strong>{" "}
                                · {t(lang, "confidence")}{" "}
                                {formatPercent(crop.rescue_confidence)}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  {/* Collapsible written report */}
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-slate-900">
                        {t(lang, "fullReportTitle")}
                      </h3>
                      <div className="pier-no-print flex items-center gap-2">
                        <button
                          type="button"
                          onClick={copyPlan}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                        >
                          {copied ? (
                            <Check
                              className="h-3 w-3 text-emerald-700"
                              aria-hidden="true"
                            />
                          ) : (
                            <ClipboardCopy
                              className="h-3 w-3"
                              aria-hidden="true"
                            />
                          )}
                          {copied ? t(lang, "copied") : t(lang, "copy")}
                        </button>
                        <button
                          type="button"
                          onClick={() => setRawExpanded((v) => !v)}
                          aria-expanded={rawExpanded}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                        >
                          {rawExpanded ? (
                            <>
                              {t(lang, "hideRawReport")}
                              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                            </>
                          ) : (
                            <>
                              {t(lang, "showRawReport")}
                              <ChevronDown
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              />
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                    {rawExpanded ? (
                      <pre className="pier-scroll pier-print-expand mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-white p-4 font-sans text-xs leading-relaxed text-slate-800">
                        {result.plan_text}
                      </pre>
                    ) : null}
                  </div>
                </div>

                {/* Right column: Weather & Window Summary */}
                <div className="space-y-3">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                    <h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-600">
                      {t(lang, "fieldSummaryTitle")}
                    </h3>

                    {gddTotal > 0 ? (
                      <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
                        <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                          <span>{t(lang, "metricGdd")}</span>
                          <span className="tabular-nums text-emerald-800">
                            {formatNumber(result.gdd_remaining, lang, 0)} (
                            {gddRemainingPct}%)
                          </span>
                        </div>
                        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-200">
                          <div
                            className="h-full rounded-full bg-emerald-700"
                            style={{ width: `${gddRemainingPct}%` }}
                          />
                        </div>
                        <div className="mt-1.5 flex justify-between text-[0.7rem] tabular-nums text-slate-600">
                          <span>
                            {t(lang, "gddAccumulated")}:{" "}
                            {formatNumber(gddAcc, lang, 0)}
                          </span>
                          <span>
                            {t(lang, "frostDate")}:{" "}
                            {formatDate(result.frost_date, lang)}
                          </span>
                        </div>
                      </div>
                    ) : null}

                    <dl className="mt-3 space-y-2.5 text-sm">
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-slate-600">
                          {t(lang, "dataSource")}
                        </dt>
                        <dd className="text-right font-semibold text-slate-900">
                          {sourceLabel(result.fuente_datos, lang)}
                        </dd>
                      </div>
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-slate-600">
                          {t(lang, "lastUpdate")}
                        </dt>
                        <dd className="text-right font-medium tabular-nums text-slate-800">
                          {updatedLabel}
                        </dd>
                      </div>
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-slate-600">
                          {t(lang, "severity")}
                        </dt>
                        <dd className="text-right font-medium capitalize text-slate-800">
                          {result.event_severity || "—"}
                        </dd>
                      </div>
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-slate-600">
                          {t(lang, "demoName")}
                        </dt>
                        <dd className="text-right font-medium text-slate-800">
                          {result.demo_name || "—"}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-emerald-950">
                      <Leaf
                        className="h-4 w-4 text-emerald-800"
                        aria-hidden="true"
                      />
                      {t(lang, "rescueConfidence")}
                    </div>
                    <p className="mt-1 text-2xl font-bold tabular-nums text-emerald-950">
                      {formatPercent(result.rescue_confidence)}
                    </p>
                    <p className="mt-1 text-xs font-medium text-emerald-900">
                      {t(lang, "metricCrops")}: {result.crops.length}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {tab === "crops" ? (
            result.crops.length === 0 ? (
              <EmptyState icon={Sprout} text={t(lang, "noCrops")} />
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-slate-600">
                    {result.crops.length} {t(lang, "metricCrops").toLowerCase()}
                  </p>
                  <div className="flex items-center gap-2">
                    <label
                      htmlFor="crop-sort"
                      className="text-xs font-semibold text-slate-700"
                    >
                      {t(lang, "sortBy")}:
                    </label>
                    <select
                      id="crop-sort"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as SortKey)}
                      className="rounded-xl border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                    >
                      <option value="score">{t(lang, "sortScore")}</option>
                      <option value="deadline">{t(lang, "sortDeadline")}</option>
                      <option value="margin">{t(lang, "sortMargin")}</option>
                      <option value="confidence">
                        {t(lang, "sortConfidence")}
                      </option>
                    </select>
                  </div>
                </div>

                {/* Mobile card list (no horizontal overflow) */}
                <div className="grid gap-3 md:hidden">
                  {sortedCrops.map((crop, index) => (
                    <CropCardMobile
                      key={crop.crop}
                      crop={crop}
                      rank={index + 1}
                      lang={lang}
                    />
                  ))}
                </div>

                {/* Desktop table */}
                <div className="pier-scroll hidden overflow-x-auto md:block">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-[0.7rem] font-semibold uppercase tracking-[0.06em] text-slate-600">
                        <th className="px-4 py-2.5">{t(lang, "crop")}</th>
                        <th className="px-4 py-2.5">{t(lang, "plantBy")}</th>
                        <th className="px-4 py-2.5">{t(lang, "daysLeft")}</th>
                        <th className="px-4 py-2.5">
                          {t(lang, "gddRequirement")}
                        </th>
                        <th className="px-4 py-2.5">{t(lang, "margin")}</th>
                        <th className="px-4 py-2.5">{t(lang, "confidence")}</th>
                        <th className="px-4 py-2.5">{t(lang, "score")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedCrops.map((crop, index) => (
                        <CropRow
                          key={crop.crop}
                          crop={crop}
                          rank={index + 1}
                          lang={lang}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          ) : null}

          {tab === "excluded" ? (
            result.exclusiones.length === 0 ? (
              <EmptyState icon={CheckCircle2} text={t(lang, "noExclusions")} />
            ) : (
              <div className="space-y-4">
                {exclusionReasons.length > 1 ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setReasonFilter("all")}
                      aria-pressed={reasonFilter === "all"}
                      className={`rounded-full border px-3 py-1 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                        reasonFilter === "all"
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {t(lang, "filterAll")} ({result.exclusiones.length})
                    </button>
                    {exclusionReasons.map(([label, count]) => (
                      <button
                        key={label}
                        type="button"
                        onClick={() => setReasonFilter(label)}
                        aria-pressed={reasonFilter === label}
                        className={`rounded-full border px-3 py-1 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                          reasonFilter === label
                            ? "border-slate-900 bg-slate-900 text-white"
                            : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        {label} ({count})
                      </button>
                    ))}
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-2">
                  {filteredExclusions.map((exclusion, index) => (
                    <div
                      key={`${exclusion.crop}-${exclusion.motivo}-${index}`}
                      className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-700">
                            <XCircle className="h-4 w-4" aria-hidden="true" />
                          </span>
                          <h3 className="text-sm font-bold text-slate-900">
                            {exclusion.crop}
                          </h3>
                        </div>
                        <span className="rounded-full bg-white px-2.5 py-0.5 text-[0.7rem] font-semibold text-slate-700 ring-1 ring-slate-200">
                          {reasonLabel(exclusion.motivo, lang)}
                        </span>
                      </div>
                      <p className="mt-2.5 text-xs leading-relaxed text-slate-700">
                        {exclusion.explicacion}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )
          ) : null}

          {tab === "rotation" ? (
            result.rotacion || result.ahorro ? (
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="space-y-3">
                  {result.rotacion ? (
                    <>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <RotateCcw
                            className="h-4 w-4 text-emerald-700"
                            aria-hidden="true"
                          />
                          {t(lang, "rotationSequence")}
                        </div>
                        <ol className="mt-3 flex flex-wrap items-center gap-2">
                          {result.rotacion.rotation_sequence.map(
                            (item, index) => (
                              <li
                                key={`${item}-${index}`}
                                className="flex items-center gap-2"
                              >
                                <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 ring-1 ring-slate-300">
                                  <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-emerald-700 text-[0.65rem] font-bold text-white">
                                    {index + 1}
                                  </span>
                                  {item}
                                </span>
                                {index <
                                result.rotacion!.rotation_sequence.length -
                                  1 ? (
                                  <ArrowRight
                                    className="h-3.5 w-3.5 text-slate-500"
                                    aria-hidden="true"
                                  />
                                ) : null}
                              </li>
                            ),
                          )}
                        </ol>
                      </div>

                      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                        <div className="rounded-2xl border border-slate-200 bg-white p-3.5">
                          <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-600">
                            {t(lang, "soilHealth")}
                          </p>
                          <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                            {formatNumber(
                              result.rotacion.soil_health_score,
                              lang,
                              1,
                            )}
                            <span className="text-xs font-medium text-slate-600">
                              /100
                            </span>
                          </p>
                          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                            <div
                              className="h-full rounded-full bg-emerald-700"
                              style={{
                                width: `${Math.min(100, Math.max(0, result.rotacion.soil_health_score))}%`,
                              }}
                            />
                          </div>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-white p-3.5">
                          <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-600">
                            {t(lang, "nitrogen")}
                          </p>
                          <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                            {formatNumber(
                              result.rotacion.n_fixation_total_kg_ha,
                              lang,
                              0,
                            )}
                            <span className="text-xs font-medium text-slate-600">
                              {" "}
                              kg/ha
                            </span>
                          </p>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-white p-3.5">
                          <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-600">
                            {t(lang, "residue")}
                          </p>
                          <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                            {formatNumber(
                              result.rotacion.residue_cover_avg_pct,
                              lang,
                              0,
                            )}
                            <span className="text-xs font-medium text-slate-600">
                              %
                            </span>
                          </p>
                          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                            <div
                              className="h-full rounded-full bg-sky-700"
                              style={{
                                width: `${Math.min(100, Math.max(0, result.rotacion.residue_cover_avg_pct))}%`,
                              }}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <Info
                            className="h-4 w-4 text-sky-700"
                            aria-hidden="true"
                          />
                          {t(lang, "rationale")}
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-slate-700">
                          {result.rotacion.rationale}
                        </p>
                      </div>
                    </>
                  ) : null}
                </div>

                <div className="space-y-3">
                  {result.ahorro ? (
                    <>
                      <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50/70 p-4 sm:p-5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-950">
                            <TrendingUp
                              className="h-4 w-4 text-emerald-800"
                              aria-hidden="true"
                            />
                            {t(lang, "savings")}
                          </div>
                          {result.ahorro.es_estimado ? (
                            <span className="rounded-full bg-white/80 px-2.5 py-0.5 text-[0.68rem] font-semibold text-emerald-900 ring-1 ring-emerald-200">
                              {t(lang, "estimatedBadge")}
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-emerald-900">
                              {t(lang, "revenue")}
                            </p>
                            <p className="mt-1 text-xl font-bold tabular-nums text-emerald-950">
                              {formatCurrency(
                                result.ahorro.estimated_revenue_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                          <div>
                            <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-emerald-900">
                              {t(lang, "savingsPerHa")}
                            </p>
                            <p className="mt-1 text-xl font-bold tabular-nums text-emerald-950">
                              {formatCurrency(
                                result.ahorro.estimated_savings_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                        </div>

                        <dl className="mt-4 space-y-1.5 border-t border-emerald-200/80 pt-3 text-xs text-emerald-950">
                          <div className="flex items-center justify-between gap-3">
                            <dt>{t(lang, "crop")}</dt>
                            <dd className="font-semibold">
                              {result.ahorro.crop}
                            </dd>
                          </div>
                          <div className="flex items-center justify-between gap-3">
                            <dt>{t(lang, "yieldLabel")}</dt>
                            <dd className="font-semibold tabular-nums">
                              {formatNumber(
                                result.ahorro.expected_yield_tons_per_ha,
                                lang,
                                1,
                              )}{" "}
                              t/ha
                            </dd>
                          </div>
                          <div className="flex items-center justify-between gap-3">
                            <dt>{t(lang, "price")}</dt>
                            <dd className="font-semibold tabular-nums">
                              {formatCurrency(
                                result.ahorro.price_per_unit,
                                result.ahorro.currency,
                                lang,
                              )}
                            </dd>
                          </div>
                        </dl>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <Info
                            className="h-4 w-4 text-slate-600"
                            aria-hidden="true"
                          />
                          {t(lang, "note")}
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-slate-700">
                          {result.ahorro.note}
                        </p>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
            ) : (
              <EmptyState icon={RotateCcw} text={t(lang, "noRotation")} />
            )
          ) : null}
        </div>
      </div>
    </section>
  );
}
