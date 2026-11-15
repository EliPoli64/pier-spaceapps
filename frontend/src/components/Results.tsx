import { useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import {
  ArrowRight,
  Award,
  Check,
  CheckCircle2,
  ClipboardCopy,
  CloudRain,
  Compass,
  Info,
  Leaf,
  MessageSquare,
  MinusCircle,
  PlusCircle,
  Printer,
  RefreshCw,
  RotateCcw,
  Satellite,
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
  eventLabel,
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
  iconTone = "text-slate-500",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  iconTone?: string;
}) {
  return (
    <div className="py-1 sm:px-5 first:sm:pl-0 last:sm:pr-0">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        <Icon
          className={`h-4 w-4 shrink-0 stroke-[1.7] ${iconTone}`}
          aria-hidden="true"
        />
        <span>{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums text-slate-900">
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-xs text-slate-500">{hint}</p>
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
      tone: "bg-slate-800 text-white ring-slate-800",
      label: t(lang, "pastDueBadge"),
    };
  }
  if (days <= 7) {
    return {
      tone: "bg-sky-50 text-sky-900 ring-sky-200",
      label: `${days}d · ${t(lang, "urgentBadge")}`,
    };
  }
  return {
    tone: "bg-emerald-50 text-emerald-900 ring-emerald-200",
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
  { id: "overview", key: "tabOverview", icon: Compass },
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
  const [checksExpanded, setChecksExpanded] = useState(false);
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

  const isLiveDataFallback =
    !demoMode && result.fuente_datos.toLowerCase().includes("sint");

  const { fieldAlerts, technicalAlerts } = useMemo(() => {
    const field: typeof result.alertas = [];
    const technical: typeof result.alertas = [];
    const showingCoverCard = !topCrop && !result.no_action_needed;
    for (const alert of result.alertas) {
      if (showingCoverCard && alert.codigo === "SIN_CULTIVO_EN_VENTANA") {
        continue;
      }
      if (
        alert.codigo.startsWith("MONITOREO_") ||
        alert.codigo === "CALCULO_EN_API" ||
        alert.codigo === "PARAMETRO_PARCIAL" ||
        alert.codigo === "MODO_DEMO" ||
        alert.codigo === "DEMO_AUTODETECTADO"
      ) {
        technical.push(alert);
      } else {
        field.push(alert);
      }
    }
    return { fieldAlerts: field, technicalAlerts: technical };
  }, [result.alertas, result.no_action_needed, topCrop]);

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
          className="pier-no-print flex flex-col gap-2.5 rounded-2xl border border-slate-200 border-l-4 border-l-[#123b5c] bg-white px-4 py-3 text-sm text-slate-900 shadow-xs sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-start gap-2.5">
            <Info
              className="mt-0.5 h-4 w-4 shrink-0 text-[#123b5c]"
              aria-hidden="true"
            />
            <p className="font-medium">{t(lang, "staleWarning")}</p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-full bg-[#123b5c] px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-[#0b1f3a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#123b5c] sm:self-auto"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            {t(lang, "refreshPlan")}
          </button>
        </div>
      ) : null}

      {isLiveDataFallback ? (
        <div className="flex items-start gap-3 rounded-2xl border border-slate-200 border-l-4 border-l-sky-700 bg-white px-4 py-3 text-sm text-slate-700">
          <Info
            className="mt-0.5 h-4 w-4 shrink-0 text-sky-700"
            aria-hidden="true"
          />
          <p>{t(lang, "fallbackNote")}</p>
        </div>
      ) : null}

      {/* Unified Editorial Report Surface */}
      <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-xs">
        <div className="h-[3px] w-full bg-gradient-to-r from-[#0b1f3a] via-[#123b5c] to-[#15803d]" />

        {/* Summary Header + Key Spec Strip */}
        <div className="px-5 pb-6 pt-5 sm:px-7">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs">
                <span
                  className={`inline-flex items-center gap-1.5 font-semibold ${
                    result.event_type === "flood"
                      ? "text-[#123b5c]"
                      : result.event_type === "drought"
                        ? "text-stone-700"
                        : "text-emerald-700"
                  }`}
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

                <span className="text-slate-300" aria-hidden="true">
                  ·
                </span>

                <span className="tabular-nums text-slate-500">
                  {formatDate(date, lang)} · {lat.toFixed(3)}, {lon.toFixed(3)} ·{" "}
                  {demoMode
                    ? t(lang, "demoBadge")
                    : sourceLabel(result.fuente_datos, lang)}
                </span>
              </div>

              {/* Plain-language action headline */}
              <div className="mt-2">
                {result.no_action_needed ? (
                  <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
                    {t(lang, "topPickNormal")}
                  </h2>
                ) : topCrop ? (
                  <div className="flex flex-wrap items-baseline gap-2.5">
                    <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
                      {tFormat(lang, "topPickHeadline", {
                        crop: topCrop.crop,
                        date: formatDate(topCrop.plant_by_date, lang),
                      })}
                    </h2>
                    <span
                      className={`text-xs font-semibold ${
                        topCrop.days_until_deadline <= 0
                          ? "text-slate-900"
                          : topCrop.days_until_deadline <= 7
                            ? "text-[#123b5c]"
                            : "text-emerald-700"
                      }`}
                    >
                      ·{" "}
                      {topCrop.days_until_deadline <= 0
                        ? t(lang, "pastDueBanner")
                        : tFormat(lang, "daysLeftBanner", {
                            days: topCrop.days_until_deadline,
                          })}
                    </span>
                  </div>
                ) : (
                  <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
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
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 transition hover:border-emerald-700 hover:text-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                {smsCopied ? (
                  <Check
                    className="h-3.5 w-3.5 text-emerald-700"
                    aria-hidden="true"
                  />
                ) : (
                  <MessageSquare
                    className="h-3.5 w-3.5 text-emerald-700"
                    aria-hidden="true"
                  />
                )}
                {smsCopied ? t(lang, "smsCopied") : t(lang, "copySms")}
              </button>
              <button
                type="button"
                onClick={copyPlan}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
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
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                <Printer className="h-3.5 w-3.5" aria-hidden="true" />
                {t(lang, "printPlan")}
              </button>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-slate-200/80 pt-5 lg:grid-cols-4 lg:gap-x-0 lg:divide-x lg:divide-slate-200/80">
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
              iconTone={
                result.event_type === "flood"
                  ? "text-[#123b5c]"
                  : result.event_type === "drought"
                    ? "text-stone-600"
                    : "text-emerald-700"
              }
            />
            <Metric
              label={t(lang, "metricConfidence")}
              value={formatPercent(result.event_confidence)}
              hint={
                result.crops.length > 0
                  ? `${t(lang, "rescueConfidence")}: ${formatPercent(result.rescue_confidence)}`
                  : result.no_action_needed
                    ? t(lang, "normalStandingBadge")
                    : t(lang, "coverCropAdvisedHint")
              }
              icon={Satellite}
              iconTone="text-[#123b5c]"
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
              iconTone="text-teal-700"
            />
            <Metric
              label={t(lang, "metricCrops")}
              value={result.crops.length}
              hint={tFormat(lang, "excludedCountHint", {
                n: result.exclusiones.length,
              })}
              icon={Sprout}
              iconTone="text-emerald-700"
            />
          </div>
        </div>

        {/* Clean Underline Tab Navigation */}
        <div
          className="pier-no-print flex gap-6 overflow-x-auto border-t border-b border-slate-200/80 px-5 sm:px-7"
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
                className={`relative -mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 py-3 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                  active
                    ? "border-emerald-700 text-slate-900"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <Icon
                  className={`h-3.5 w-3.5 ${active ? "text-emerald-700" : "text-slate-400"}`}
                  aria-hidden="true"
                />
                <span>{t(lang, item.key)}</span>
                {count != null ? (
                  <span
                    className={`ml-0.5 text-[0.7rem] tabular-nums ${
                      active ? "text-emerald-700" : "text-slate-400"
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
          className="p-5 sm:p-7"
        >
          {tab === "overview" ? (
            <div key="tab-overview" className="pier-slide-in space-y-6">
              <div className="grid gap-8 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
                {/* Left column: Unboxed Editorial Guidance + Alternatives + Full Report */}
                <div className="min-w-0 space-y-6">
                  {topCrop ? (
                    <div>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                          <Award className="h-3.5 w-3.5" aria-hidden="true" />
                          {t(lang, "topPickBadge")}
                        </span>
                        <span className="text-xs font-medium tabular-nums text-slate-500">
                          {t(lang, "score")}:{" "}
                          <strong className="font-semibold text-slate-900">
                            {formatNumber(topCrop.composite_score, lang, 2)}
                          </strong>
                        </span>
                      </div>

                      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-4">
                        <div>
                          <h3 className="text-2xl font-semibold tracking-tight text-slate-900">
                            {topCrop.crop}
                          </h3>
                          {topCrop.role ? (
                            <p className="mt-0.5 text-sm text-slate-600">
                              {topCrop.role}
                            </p>
                          ) : null}
                        </div>
                        {result.ahorro ? (
                          <div className="sm:text-right">
                            <p className="text-xs font-medium text-slate-500">
                              {t(lang, "savingsPerHa")}
                            </p>
                            <p className="text-xl font-semibold tracking-tight tabular-nums text-emerald-800">
                              {formatCurrency(
                                result.ahorro.estimated_savings_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                        ) : null}
                      </div>

                      <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-200/80 pt-4 text-xs sm:grid-cols-4">
                        <div>
                          <dt className="text-slate-500">{t(lang, "plantBy")}</dt>
                          <dd className="mt-1 text-sm font-semibold tabular-nums text-slate-900">
                            {formatDate(topCrop.plant_by_date, lang)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">
                            {t(lang, "gddRequirement")}
                          </dt>
                          <dd className="mt-1 text-sm font-semibold tabular-nums text-slate-900">
                            {formatNumber(topCrop.gdd_requirement, lang, 0)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">{t(lang, "margin")}</dt>
                          <dd className="mt-1 text-sm font-semibold tabular-nums text-slate-900">
                            {formatNumber(topCrop.margin_pct, lang, 1)}%
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">
                            {t(lang, "confidence")}
                          </dt>
                          <dd className="mt-1 text-sm font-semibold tabular-nums text-slate-900">
                            {formatPercent(topCrop.rescue_confidence)}
                          </dd>
                        </div>
                      </dl>
                    </div>
                  ) : result.no_action_needed ? (
                    <div className="max-w-2xl">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {t(lang, "normalStandingBadge")}
                      </span>
                      <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                        {t(lang, "topPickNormal")}
                      </h3>
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">
                        {t(lang, "normalStandingBody")}
                      </p>
                    </div>
                  ) : (
                    <div className="max-w-2xl">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#123b5c]">
                        <Leaf className="h-3.5 w-3.5" aria-hidden="true" />
                        {t(lang, "coverCropBadge")}
                      </span>
                      <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                        {t(lang, "coverCropTitle")}
                      </h3>
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">
                        {result.gdd_remaining <= 0
                          ? tFormat(lang, "coverCropZeroGddBody", {
                              date: formatDate(result.frost_date, lang),
                            })
                          : tFormat(lang, "coverCropBody", {
                              gdd: formatNumber(result.gdd_remaining, lang, 0),
                              date: formatDate(result.frost_date, lang),
                            })}
                      </p>
                      <div className="pier-no-print mt-4 flex flex-wrap items-center gap-5">
                        {result.rotacion || result.ahorro ? (
                          <button
                            type="button"
                            onClick={() => setTab("rotation")}
                            className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 transition hover:text-emerald-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                          >
                            {t(lang, "viewRotationBtn")}
                            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        ) : null}
                        {result.exclusiones.length > 0 ? (
                          <button
                            type="button"
                            onClick={() => setTab("excluded")}
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                          >
                            {tFormat(lang, "viewExclusionsBtn", {
                              n: result.exclusiones.length,
                            })}
                            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                    </div>
                  )}

                  {runnersUp.length > 0 ? (
                    <div className="border-t border-slate-200/80 pt-5">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                          {t(lang, "runnersUpTitle")}
                        </h3>
                        {result.crops.length > 3 ? (
                          <button
                            type="button"
                            onClick={() => setTab("crops")}
                            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                          >
                            {t(lang, "tabCrops")} ({result.crops.length})
                            <ArrowRight className="h-3 w-3" aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                      <div className="mt-2 divide-y divide-slate-200/75 border-t border-b border-slate-200/80">
                        {runnersUp.map((crop, idx) => {
                          const badge = deadlineBadge(
                            crop.days_until_deadline,
                            lang,
                          );
                          return (
                            <div
                              key={crop.crop}
                              className="flex flex-wrap items-center justify-between gap-3 py-3"
                            >
                              <div className="flex items-baseline gap-2.5">
                                <span className="text-xs font-semibold tabular-nums text-slate-400">
                                  #{idx + 2}
                                </span>
                                <span className="text-sm font-semibold text-slate-900">
                                  {crop.crop}
                                </span>
                              </div>
                              <div className="flex flex-wrap items-center gap-4 text-xs tabular-nums">
                                <span className="text-slate-600">
                                  {t(lang, "plantBy")}{" "}
                                  <strong className="font-medium text-slate-900">
                                    {formatDate(crop.plant_by_date, lang)}
                                  </strong>
                                </span>
                                <span className="text-slate-500">
                                  {formatPercent(crop.rescue_confidence)}
                                </span>
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ring-1 ${badge.tone}`}
                                >
                                  {badge.label}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  {/* Quiet Apple Disclosure for Full Report */}
                  <div className="border-t border-slate-200/80 pt-4">
                    <div className="flex items-center justify-between gap-3">
                      <button
                        type="button"
                        onClick={() => setRawExpanded((v) => !v)}
                        aria-expanded={rawExpanded}
                        className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700 transition hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                      >
                        {rawExpanded ? (
                          <MinusCircle
                            className="h-4 w-4 text-slate-500"
                            aria-hidden="true"
                          />
                        ) : (
                          <PlusCircle
                            className="h-4 w-4 text-slate-500"
                            aria-hidden="true"
                          />
                        )}
                        <span>{t(lang, "fullReportTitle")}</span>
                      </button>

                      <button
                        type="button"
                        onClick={copyPlan}
                        className="pier-no-print inline-flex items-center gap-1 text-xs font-medium text-slate-500 transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                      >
                        {copied ? (
                          <Check
                            className="h-3.5 w-3.5 text-emerald-700"
                            aria-hidden="true"
                          />
                        ) : (
                          <ClipboardCopy
                            className="h-3.5 w-3.5"
                            aria-hidden="true"
                          />
                        )}
                        {copied ? t(lang, "copied") : t(lang, "copy")}
                      </button>
                    </div>
                    {rawExpanded ? (
                      <pre className="pier-scroll pier-print-expand mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 font-sans text-xs leading-relaxed text-slate-700">
                        {result.plan_text}
                      </pre>
                    ) : null}
                  </div>
                </div>

                {/* Right column: Weather Window & Specs with vertical hairline */}
                <div className="space-y-5 border-t border-slate-200/80 pt-6 xl:border-l xl:border-t-0 xl:pl-7 xl:pt-0">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                      {t(lang, "fieldSummaryTitle")}
                    </h3>

                    {gddTotal > 0 ? (
                      <div className="mt-4">
                        <div className="flex items-center justify-between text-xs font-medium text-slate-700">
                          <span>{t(lang, "metricGdd")}</span>
                          <span className="font-semibold tabular-nums text-slate-900">
                            {formatNumber(result.gdd_remaining, lang, 0)} (
                            {gddRemainingPct}%)
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80">
                          <div
                            className="h-full rounded-full bg-emerald-700"
                            style={{ width: `${gddRemainingPct}%` }}
                          />
                        </div>
                        <div className="mt-1.5 flex justify-between text-[0.7rem] tabular-nums text-slate-500">
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

                    <dl className="mt-4 divide-y divide-slate-200/75 text-sm">
                      <div className="flex items-center justify-between gap-3 py-2.5">
                        <dt className="text-slate-500">
                          {t(lang, "dataSource")}
                        </dt>
                        <dd className="text-right font-medium text-slate-900">
                          {sourceLabel(result.fuente_datos, lang)}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-3 py-2.5">
                        <dt className="text-slate-500">
                          {t(lang, "lastUpdate")}
                        </dt>
                        <dd className="text-right font-medium tabular-nums text-slate-900">
                          {updatedLabel}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-3 py-2.5">
                        <dt className="text-slate-500">
                          {t(lang, "severity")}
                        </dt>
                        <dd className="text-right font-medium capitalize text-slate-900">
                          {result.event_severity || "—"}
                        </dd>
                      </div>
                      {result.demo_name ? (
                        <div className="flex items-center justify-between gap-3 py-2.5">
                          <dt className="text-slate-500">
                            {t(lang, "demoName")}
                          </dt>
                          <dd className="text-right font-medium text-slate-900">
                            {result.demo_name}
                          </dd>
                        </div>
                      ) : null}
                      {result.crops.length > 0 ? (
                        <div className="flex items-center justify-between gap-3 py-2.5">
                          <dt className="text-slate-500">
                            {t(lang, "rescueConfidence")}
                          </dt>
                          <dd className="text-right font-semibold tabular-nums text-emerald-700">
                            {formatPercent(result.rescue_confidence)}
                          </dd>
                        </div>
                      ) : null}
                    </dl>
                  </div>

                  {result.crops.length === 0 && result.rotacion ? (
                    <div className="border-t border-slate-200/80 pt-4">
                      <div className="flex items-center justify-between gap-2 text-xs font-semibold text-slate-600">
                        <span className="inline-flex items-center gap-1.5">
                          <RotateCcw
                            className="h-3.5 w-3.5 text-emerald-700"
                            aria-hidden="true"
                          />
                          {t(lang, "rotationSequence")}
                        </span>
                        <span className="tabular-nums text-slate-900">
                          {formatNumber(
                            result.rotacion.soil_health_score,
                            lang,
                            0,
                          )}
                          /100
                        </span>
                      </div>
                      <p className="mt-2 text-sm font-medium leading-relaxed text-slate-900">
                        {result.rotacion.rotation_sequence.join(" -> ")}
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>

              {/* Quiet Field Notes & Collapsible Monitoring Checks */}
              {fieldAlerts.length > 0 || technicalAlerts.length > 0 ? (
                <div className="space-y-4 border-t border-slate-200/80 pt-5">
                  {fieldAlerts.length > 0 ? (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                        {t(lang, "advisoriesTitle")}
                      </h3>
                      <div className="mt-2.5 space-y-2">
                        {fieldAlerts.map((alert, index) => (
                          <div
                            key={`${alert.codigo}-${index}`}
                            className="flex items-start gap-2.5 border-l-2 border-slate-300 pl-3 text-sm text-slate-700"
                          >
                            <span className="leading-relaxed">
                              {alert.mensaje}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {technicalAlerts.length > 0 ? (
                    <div>
                      <button
                        type="button"
                        onClick={() => setChecksExpanded((v) => !v)}
                        aria-expanded={checksExpanded}
                        className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600 transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                      >
                        {checksExpanded ? (
                          <MinusCircle
                            className="h-4 w-4 text-slate-500"
                            aria-hidden="true"
                          />
                        ) : (
                          <PlusCircle
                            className="h-4 w-4 text-slate-500"
                            aria-hidden="true"
                          />
                        )}
                        <ShieldCheck
                          className="h-3.5 w-3.5 text-slate-500"
                          aria-hidden="true"
                        />
                        <span>
                          {tFormat(lang, "technicalChecksTitle", {
                            n: technicalAlerts.length,
                          })}
                        </span>
                      </button>

                      {checksExpanded ? (
                        <div className="mt-3 divide-y divide-slate-200/75 border-t border-slate-200/80">
                          {technicalAlerts.map((alert, index) => (
                            <div
                              key={`${alert.codigo}-${index}`}
                              className="flex items-start justify-between gap-4 py-2.5 text-xs text-slate-600"
                            >
                              <span className="leading-relaxed">
                                {alert.mensaje}
                              </span>
                              <span className="hidden shrink-0 font-mono text-[0.65rem] font-medium uppercase tracking-wide text-slate-400 sm:inline-block">
                                {alert.codigo}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {tab === "crops" ? (
            result.crops.length === 0 ? (
              <div key="tab-crops-empty" className="pier-slide-in">
                <EmptyState icon={Sprout} text={t(lang, "noCrops")} />
              </div>
            ) : (
              <div key="tab-crops" className="pier-slide-in space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-medium text-slate-500">
                    {result.crops.length} {t(lang, "metricCrops").toLowerCase()}
                  </p>
                  <div className="flex items-center gap-2">
                    <label
                      htmlFor="crop-sort"
                      className="text-xs font-medium text-slate-600"
                    >
                      {t(lang, "sortBy")}:
                    </label>
                    <select
                      id="crop-sort"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as SortKey)}
                      className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
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
                      <tr className="border-b border-slate-200 text-[0.7rem] font-semibold uppercase tracking-[0.06em] text-slate-500">
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
              <div key="tab-excluded-empty" className="pier-slide-in">
                <EmptyState icon={CheckCircle2} text={t(lang, "noExclusions")} />
              </div>
            ) : (
              <div key="tab-excluded" className="pier-slide-in space-y-4">
                {exclusionReasons.length > 1 ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setReasonFilter("all")}
                      aria-pressed={reasonFilter === "all"}
                      className={`rounded-full px-3 py-1 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                        reasonFilter === "all"
                          ? "bg-slate-900 text-white"
                          : "border border-slate-300 bg-white text-slate-600 hover:text-slate-900"
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
                        className={`rounded-full px-3 py-1 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                          reasonFilter === label
                            ? "bg-slate-900 text-white"
                            : "border border-slate-300 bg-white text-slate-600 hover:text-slate-900"
                        }`}
                      >
                        {label} ({count})
                      </button>
                    ))}
                  </div>
                ) : null}

                <div className="divide-y divide-slate-200/80 border-t border-slate-200/80">
                  {filteredExclusions.map((exclusion, index) => (
                    <div
                      key={`${exclusion.crop}-${exclusion.motivo}-${index}`}
                      className="flex flex-col gap-1.5 py-4 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <XCircle
                            className="h-4 w-4 shrink-0 text-slate-400"
                            aria-hidden="true"
                          />
                          <h3 className="text-sm font-semibold text-slate-900">
                            {exclusion.crop}
                          </h3>
                        </div>
                        <p className="mt-1 pl-6 text-xs leading-relaxed text-slate-600">
                          {exclusion.explicacion}
                        </p>
                      </div>
                      <span className="shrink-0 pl-6 text-xs font-medium text-slate-500 sm:pl-0">
                        {reasonLabel(exclusion.motivo, lang)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )
          ) : null}

          {tab === "rotation" ? (
            result.rotacion || result.ahorro ? (
              <div
                key="tab-rotation"
                className="pier-slide-in grid gap-8 xl:grid-cols-2"
              >
                <div className="space-y-6">
                  {result.rotacion ? (
                    <>
                      <div>
                        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                          <RotateCcw
                            className="h-3.5 w-3.5 text-emerald-700"
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
                                <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-900">
                                  <span className="text-[0.7rem] font-bold tabular-nums text-emerald-700">
                                    {index + 1}
                                  </span>
                                  {item}
                                </span>
                                {index <
                                result.rotacion!.rotation_sequence.length -
                                  1 ? (
                                  <ArrowRight
                                    className="h-3.5 w-3.5 text-slate-400"
                                    aria-hidden="true"
                                  />
                                ) : null}
                              </li>
                            ),
                          )}
                        </ol>
                      </div>

                      <div className="grid grid-cols-1 gap-5 border-t border-slate-200/80 pt-5 sm:grid-cols-3">
                        <div>
                          <p className="text-xs font-medium text-slate-500">
                            {t(lang, "soilHealth")}
                          </p>
                          <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-slate-900">
                            {formatNumber(
                              result.rotacion.soil_health_score,
                              lang,
                              1,
                            )}
                            <span className="text-xs font-normal text-slate-500">
                              /100
                            </span>
                          </p>
                          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80">
                            <div
                              className="h-full rounded-full bg-emerald-700"
                              style={{
                                width: `${Math.min(100, Math.max(0, result.rotacion.soil_health_score))}%`,
                              }}
                            />
                          </div>
                        </div>

                        <div>
                          <p className="text-xs font-medium text-slate-500">
                            {t(lang, "nitrogen")}
                          </p>
                          <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-slate-900">
                            {formatNumber(
                              result.rotacion.n_fixation_total_kg_ha,
                              lang,
                              0,
                            )}
                            <span className="text-xs font-normal text-slate-500">
                              {" "}
                              kg/ha
                            </span>
                          </p>
                        </div>

                        <div>
                          <p className="text-xs font-medium text-slate-500">
                            {t(lang, "residue")}
                          </p>
                          <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-slate-900">
                            {formatNumber(
                              result.rotacion.residue_cover_avg_pct,
                              lang,
                              0,
                            )}
                            <span className="text-xs font-normal text-slate-500">
                              %
                            </span>
                          </p>
                          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80">
                            <div
                              className="h-full rounded-full bg-[#123b5c]"
                              style={{
                                width: `${Math.min(100, Math.max(0, result.rotacion.residue_cover_avg_pct))}%`,
                              }}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="border-t border-slate-200/80 pt-4">
                        <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                          {t(lang, "rationale")}
                        </h4>
                        <p className="mt-2 text-sm leading-relaxed text-slate-600">
                          {result.rotacion.rationale}
                        </p>
                      </div>
                    </>
                  ) : null}
                </div>

                <div className="space-y-5 border-t border-slate-200/80 pt-6 xl:border-l xl:border-t-0 xl:pl-8 xl:pt-0">
                  {result.ahorro ? (
                    <>
                      <div>
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                            <TrendingUp
                              className="h-3.5 w-3.5 text-emerald-700"
                              aria-hidden="true"
                            />
                            {t(lang, "savings")}
                          </div>
                          {result.ahorro.es_estimado ? (
                            <span className="text-xs font-medium text-slate-500">
                              {t(lang, "estimatedBadge")}
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-4 grid grid-cols-2 gap-6">
                          <div>
                            <p className="text-xs font-medium text-slate-500">
                              {t(lang, "revenue")}
                            </p>
                            <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-slate-900">
                              {formatCurrency(
                                result.ahorro.estimated_revenue_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs font-medium text-slate-500">
                              {t(lang, "savingsPerHa")}
                            </p>
                            <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-emerald-700">
                              {formatCurrency(
                                result.ahorro.estimated_savings_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                        </div>

                        <dl className="mt-5 divide-y divide-slate-200/75 border-t border-slate-200/80 text-sm">
                          <div className="flex items-center justify-between gap-3 py-2.5">
                            <dt className="text-slate-500">{t(lang, "crop")}</dt>
                            <dd className="font-medium text-slate-900">
                              {result.ahorro.crop}
                            </dd>
                          </div>
                          <div className="flex items-center justify-between gap-3 py-2.5">
                            <dt className="text-slate-500">
                              {t(lang, "yieldLabel")}
                            </dt>
                            <dd className="font-medium tabular-nums text-slate-900">
                              {formatNumber(
                                result.ahorro.expected_yield_tons_per_ha,
                                lang,
                                1,
                              )}{" "}
                              t/ha
                            </dd>
                          </div>
                          <div className="flex items-center justify-between gap-3 py-2.5">
                            <dt className="text-slate-500">{t(lang, "price")}</dt>
                            <dd className="font-medium tabular-nums text-slate-900">
                              {formatCurrency(
                                result.ahorro.price_per_unit,
                                result.ahorro.currency,
                                lang,
                              )}
                            </dd>
                          </div>
                        </dl>
                      </div>

                      <div className="border-t border-slate-200/80 pt-4">
                        <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                          {t(lang, "note")}
                        </h4>
                        <p className="mt-2 text-xs leading-relaxed text-slate-600">
                          {result.ahorro.note}
                        </p>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
            ) : (
              <div key="tab-rotation-empty" className="pier-slide-in">
                <EmptyState icon={RotateCcw} text={t(lang, "noRotation")} />
              </div>
            )
          ) : null}
        </div>
      </div>
    </section>
  );
}
