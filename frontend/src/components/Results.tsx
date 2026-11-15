import { useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ClipboardCopy,
  CloudRain,
  Info,
  Leaf,
  RotateCcw,
  ShieldCheck,
  Sprout,
  ThermometerSun,
  TrendingUp,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { PlanResponse } from "../lib/types";
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

interface ResultsProps {
  result: PlanResponse;
  lang: Lang;
  stale: boolean;
  date: string;
  lat: number;
  lon: number;
  demoMode: boolean;
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
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <span className={`inline-flex h-7 w-7 items-center justify-center rounded-lg ${tone}`}>
          <Icon className="h-3.5 w-3.5" />
        </span>
        {label}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
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
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-10 text-center">
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-white text-slate-400 shadow-sm">
        <Icon className="h-5 w-5" />
      </span>
      <p className="mt-3 max-w-md text-sm text-slate-500">{text}</p>
    </div>
  );
}

function CropRow({
  crop,
  lang,
}: {
  crop: PlanResponse["crops"][number];
  lang: Lang;
}) {
  const deadlineTone =
    crop.days_until_deadline <= 0
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : crop.days_until_deadline <= 7
        ? "bg-amber-50 text-amber-800 ring-amber-200"
        : "bg-emerald-50 text-emerald-700 ring-emerald-200";

  return (
    <tr className="border-t border-slate-100 transition hover:bg-slate-50/70">
      <td className="whitespace-nowrap px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
            <Sprout className="h-3.5 w-3.5" />
          </span>
          <span className="font-medium text-slate-900">{crop.crop}</span>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-slate-600">
        {formatDate(crop.plant_by_date, lang)}
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${deadlineTone}`}>
          {crop.days_until_deadline}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-slate-600">
        {formatNumber(crop.gdd_requirement, lang, 0)}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-slate-600">
        {formatNumber(crop.margin_pct, lang, 1)}%
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <span className="font-medium text-slate-800">
          {formatPercent(crop.rescue_confidence)}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-slate-600">
        {formatNumber(crop.composite_score, lang, 2)}
      </td>
    </tr>
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
}: ResultsProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const [copied, setCopied] = useState(false);

  const copyPlan = async () => {
    try {
      await navigator.clipboard.writeText(result.plan_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  const tabCount: Record<Tab, number | null> = {
    overview: null,
    crops: result.crops.length,
    excluded: result.exclusiones.length,
    rotation: null,
  };

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

  return (
    <section className="space-y-4">
      {stale ? (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{t(lang, "staleWarning")}</p>
        </div>
      ) : null}

      {result.no_action_needed ? (
        <div className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{t(lang, "noActionNeeded")}</p>
        </div>
      ) : null}

      {result.fallback ? (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{t(lang, "fallbackNote")}</p>
        </div>
      ) : null}

      {result.alertas.length > 0 ? (
        <div className="space-y-2">
          {result.alertas.map((alert, index) => (
            <div
              key={`${alert.codigo}-${index}`}
              className={`flex items-start gap-3 rounded-2xl border p-3.5 text-sm ${alertTone(alert.nivel)}`}
            >
              {alert.nivel === "info" ? (
                <Info className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-white/60 px-1.5 py-0.5 font-mono text-[0.65rem] font-semibold uppercase tracking-wide">
                    {alert.codigo}
                  </span>
                  <span>{alert.mensaje}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${eventTone(result.event_type)}`}
              >
                {result.event_type === "flood" ? (
                  <CloudRain className="h-3.5 w-3.5" />
                ) : result.event_type === "drought" ? (
                  <ThermometerSun className="h-3.5 w-3.5" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                {eventLabel(result.event_type, lang)}
              </span>
              <span className="text-xs font-medium text-slate-400">
                {t(lang, "planForLabel")} {formatDate(date, lang)} ·{" "}
                {lat.toFixed(3)}, {lon.toFixed(3)}
              </span>
            </div>
            <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">
              {t(lang, "recoveryPlan")}
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[0.68rem] font-semibold text-slate-600">
              {sourceLabel(result.fuente_datos, lang)}
            </span>
            <span
              className={`rounded-full px-2.5 py-1 text-[0.68rem] font-semibold ring-1 ${
                demoMode
                  ? "bg-amber-50 text-amber-800 ring-amber-200"
                  : "bg-emerald-50 text-emerald-700 ring-emerald-200"
              }`}
            >
              {demoMode ? t(lang, "demoBadge") : t(lang, "liveBadge")}
            </span>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric
            label={t(lang, "metricEvent")}
            value={eventLabel(result.event_type, lang)}
            hint={result.event_severity ? `${t(lang, "severity")}: ${result.event_severity}` : undefined}
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
            tone="bg-sky-50 text-sky-700"
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
            tone="bg-amber-50 text-amber-700"
          />
          <Metric
            label={t(lang, "metricCrops")}
            value={result.crops.length}
            hint={t(lang, "tabCrops")}
            icon={Sprout}
            tone="bg-emerald-50 text-emerald-700"
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div
          className="flex gap-1 overflow-x-auto border-b border-slate-200 px-3 pt-3"
          role="tablist"
          aria-label={t(lang, "recoveryPlan")}
        >
          {TABS.map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            const count = tabCount[item.id];
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(item.id)}
                className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-t-xl px-3.5 py-2.5 text-xs font-semibold transition ${
                  active
                    ? "bg-slate-900 text-white"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {t(lang, item.key)}
                {count != null ? (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[0.62rem] ${
                      active
                        ? "bg-white/15 text-white"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {count}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        <div className="p-5">
          {tab === "overview" ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
              <div className="min-w-0">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {t(lang, "recoveryPlan")}
                  </h3>
                  <button
                    type="button"
                    onClick={copyPlan}
                    className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-emerald-600" />
                    ) : (
                      <ClipboardCopy className="h-3.5 w-3.5" />
                    )}
                    {copied ? t(lang, "copied") : t(lang, "copy")}
                  </button>
                </div>
                <pre className="pier-scroll mt-3 max-h-[460px] overflow-auto whitespace-pre-wrap rounded-2xl border border-slate-200 bg-slate-950 p-4 font-mono text-[0.74rem] leading-relaxed text-slate-100">
                  {result.plan_text}
                </pre>
              </div>

              <div className="space-y-3">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    {t(lang, "dataSource")}
                  </h3>
                  <dl className="mt-3 space-y-2.5 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">{t(lang, "dataSource")}</dt>
                      <dd className="text-right font-medium text-slate-800">
                        {sourceLabel(result.fuente_datos, lang)}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">{t(lang, "lastUpdate")}</dt>
                      <dd className="text-right font-medium text-slate-800">
                        {updatedLabel}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">{t(lang, "severity")}</dt>
                      <dd className="text-right font-medium capitalize text-slate-800">
                        {result.event_severity || "—"}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">{t(lang, "gddAccumulated")}</dt>
                      <dd className="text-right font-medium text-slate-800">
                        {formatNumber(result.gdd_accumulated, lang, 0)}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">{t(lang, "frostDate")}</dt>
                      <dd className="text-right font-medium text-slate-800">
                        {formatDate(result.frost_date, lang)}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">{t(lang, "demoName")}</dt>
                      <dd className="text-right font-medium text-slate-800">
                        {result.demo_name || "—"}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
                    <Leaf className="h-4 w-4" />
                    {t(lang, "rescueConfidence")}
                  </div>
                  <p className="mt-1 text-2xl font-semibold text-emerald-900">
                    {formatPercent(result.rescue_confidence)}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-emerald-800">
                    {t(lang, "metricCrops")}: {result.crops.length}
                  </p>
                </div>
              </div>
            </div>
          ) : null}

          {tab === "crops" ? (
            result.crops.length === 0 ? (
              <EmptyState icon={Sprout} text={t(lang, "noCrops")} />
            ) : (
              <div className="pier-scroll overflow-x-auto">
                <table className="min-w-[760px] w-full text-left text-sm">
                  <thead>
                    <tr className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-slate-400">
                      <th className="px-4 py-2">{t(lang, "crop")}</th>
                      <th className="px-4 py-2">{t(lang, "plantBy")}</th>
                      <th className="px-4 py-2">{t(lang, "daysLeft")}</th>
                      <th className="px-4 py-2">{t(lang, "gddRequirement")}</th>
                      <th className="px-4 py-2">{t(lang, "margin")}</th>
                      <th className="px-4 py-2">{t(lang, "confidence")}</th>
                      <th className="px-4 py-2">{t(lang, "score")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.crops.map((crop) => (
                      <CropRow key={crop.crop} crop={crop} lang={lang} />
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : null}

          {tab === "excluded" ? (
            result.exclusiones.length === 0 ? (
              <EmptyState icon={CheckCircle2} text={t(lang, "noExclusions")} />
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {result.exclusiones.map((exclusion, index) => (
                  <div
                    key={`${exclusion.crop}-${exclusion.motivo}-${index}`}
                    className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
                          <XCircle className="h-4 w-4" />
                        </span>
                        <h3 className="text-sm font-semibold text-slate-900">
                          {exclusion.crop}
                        </h3>
                      </div>
                      <span className="rounded-full bg-white px-2 py-0.5 text-[0.65rem] font-semibold text-slate-500 ring-1 ring-slate-200">
                        {reasonLabel(exclusion.motivo, lang)}
                      </span>
                    </div>
                    <p className="mt-2.5 text-xs leading-relaxed text-slate-600">
                      {exclusion.explicacion}
                    </p>
                  </div>
                ))}
              </div>
            )
          ) : null}

          {tab === "rotation" ? (
            result.rotacion || result.ahorro ? (
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="space-y-3">
                  {result.rotacion ? (
                    <>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <RotateCcw className="h-4 w-4 text-emerald-600" />
                          {t(lang, "rotationSequence")}
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {result.rotacion.rotation_sequence.map((item, index) => (
                            <span key={`${item}-${index}`} className="flex items-center gap-2">
                              <span className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                                {item}
                              </span>
                              {index < result.rotacion!.rotation_sequence.length - 1 ? (
                                <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                              ) : null}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div className="rounded-2xl border border-slate-200 bg-white p-3">
                          <p className="text-[0.65rem] font-medium uppercase tracking-wide text-slate-400">
                            {t(lang, "soilHealth")}
                          </p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">
                            {formatNumber(result.rotacion.soil_health_score, lang, 1)}
                            <span className="text-xs font-normal text-slate-400">/100</span>
                          </p>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-white p-3">
                          <p className="text-[0.65rem] font-medium uppercase tracking-wide text-slate-400">
                            {t(lang, "nitrogen")}
                          </p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">
                            {formatNumber(result.rotacion.n_fixation_total_kg_ha, lang, 0)}
                            <span className="text-xs font-normal text-slate-400"> kg/ha</span>
                          </p>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-white p-3">
                          <p className="text-[0.65rem] font-medium uppercase tracking-wide text-slate-400">
                            {t(lang, "residue")}
                          </p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">
                            {formatNumber(result.rotacion.residue_cover_avg_pct, lang, 0)}
                            <span className="text-xs font-normal text-slate-400">%</span>
                          </p>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <Info className="h-4 w-4 text-sky-600" />
                          {t(lang, "rationale")}
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-slate-600">
                          {result.rotacion.rationale}
                        </p>
                      </div>
                    </>
                  ) : null}
                </div>

                <div className="space-y-3">
                  {result.ahorro ? (
                    <>
                      <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
                          <TrendingUp className="h-4 w-4" />
                          {t(lang, "savings")}
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-[0.65rem] font-medium uppercase tracking-wide text-emerald-700">
                              {t(lang, "revenue")}
                            </p>
                            <p className="mt-1 text-xl font-semibold text-emerald-950">
                              {formatCurrency(
                                result.ahorro.estimated_revenue_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                          <div>
                            <p className="text-[0.65rem] font-medium uppercase tracking-wide text-emerald-700">
                              {t(lang, "savingsPerHa")}
                            </p>
                            <p className="mt-1 text-xl font-semibold text-emerald-950">
                              {formatCurrency(
                                result.ahorro.estimated_savings_usd_per_ha,
                                result.ahorro.currency,
                                lang,
                              )}
                            </p>
                          </div>
                        </div>
                        <div className="mt-3 space-y-1.5 text-xs text-emerald-900">
                          <div className="flex items-center justify-between gap-3">
                            <span>{t(lang, "crop")}</span>
                            <span className="font-semibold">{result.ahorro.crop}</span>
                          </div>
                          <div className="flex items-center justify-between gap-3">
                            <span>{t(lang, "yieldLabel")}</span>
                            <span className="font-semibold">
                              {formatNumber(
                                result.ahorro.expected_yield_tons_per_ha,
                                lang,
                                1,
                              )}{" "}
                              t/ha
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-3">
                            <span>{t(lang, "price")}</span>
                            <span className="font-semibold">
                              {formatCurrency(
                                result.ahorro.price_per_unit,
                                result.ahorro.currency,
                                lang,
                              )}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <Info className="h-4 w-4 text-slate-500" />
                          {t(lang, "note")}
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-slate-600">
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
