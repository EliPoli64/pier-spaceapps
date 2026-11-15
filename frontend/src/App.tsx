import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  CloudRain,
  Copy,
  MapPin,
  RefreshCw,
  RotateCcw,
  Sprout,
  ThermometerSun,
  X,
} from "lucide-react";
import { ControlsPanel } from "./components/ControlsPanel";
import { Hero } from "./components/Hero";
import { MapPicker } from "./components/MapPicker";
import { Results } from "./components/Results";
import { Tutorial } from "./components/Tutorial";
import { api } from "./lib/api";
import { formatFriendlyError } from "./lib/errors";
import type { FriendlyError } from "./lib/errors";
import type { Lang } from "./lib/i18n";
import { t } from "./lib/i18n";
import type {
  Demo,
  PlanResponse,
  ResultMeta,
  Scenario,
  Weights,
} from "./lib/types";
import {
  formatDate,
  prefersReducedMotion,
  roundCoord,
  tomorrowISO,
} from "./lib/format";

const BASE_SCENARIOS: Scenario[] = [
  {
    id: "flood",
    labelKey: "scenarioFlood",
    demo_name: "flood",
    lat: 41.8,
    lon: -93.6,
    current_date: "2025-05-15",
  },
  {
    id: "drought",
    labelKey: "scenarioDrought",
    demo_name: "drought",
    lat: 9.0,
    lon: 41.0,
    current_date: "2025-01-30",
  },
  {
    id: "normal",
    labelKey: "scenarioNormal",
    demo_name: "normal",
    lat: 41.8,
    lon: -93.6,
    current_date: "2025-07-07",
  },
  {
    id: "late_flood",
    labelKey: "scenarioLateFlood",
    demo_name: "late_flood",
    lat: 41.8,
    lon: -93.6,
    current_date: "2025-08-28",
  },
  {
    id: "auto",
    labelKey: "scenarioAuto",
    demo_name: null,
    lat: 41.8,
    lon: -93.6,
    current_date: "2025-05-15",
  },
];

const FALLBACK_DEMOS: Demo[] = [
  {
    name: "flood_demo",
    label: "Flood demo",
    lat: 41.8,
    lon: -93.6,
    event_type: "flood",
    current_date: "2025-05-15",
    demo_name: "flood",
  },
  {
    name: "drought_demo",
    label: "Drought demo",
    lat: 9.0,
    lon: 41.0,
    event_type: "drought",
    current_date: "2025-01-30",
    demo_name: "drought",
  },
  {
    name: "normal_demo",
    label: "Normal season",
    lat: 41.8,
    lon: -93.6,
    event_type: "none",
    current_date: "2025-07-07",
    demo_name: "normal",
  },
  {
    name: "late_flood_demo",
    label: "Late flood",
    lat: 41.8,
    lon: -93.6,
    event_type: "flood",
    current_date: "2025-08-28",
    demo_name: "late_flood",
  },
];

function readLang(): Lang {
  try {
    const stored = localStorage.getItem("pier-lang");
    if (stored === "en" || stored === "es") return stored;
  } catch {
    // Storage can be unavailable in private browsing; fall through.
  }
  if (typeof navigator !== "undefined" && navigator.language.startsWith("es")) {
    return "es";
  }
  return "en";
}

export default function App() {
  const [lang, setLang] = useState<Lang>(readLang);
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const [demos, setDemos] = useState<Demo[]>(FALLBACK_DEMOS);
  const [demoMode, setDemoMode] = useState(true);
  const [scenario, setScenario] = useState("flood");
  const [lat, setLat] = useState(41.8);
  const [lon, setLon] = useState(-93.6);
  const [date, setDate] = useState("2025-05-15");
  const [weights, setWeights] = useState<Weights>({
    soil_protection: 0.4,
    salvage_revenue: 0.3,
    water_conservation: 0.3,
  });
  const [yieldT, setYieldT] = useState(2.0);
  const [result, setResult] = useState<PlanResponse | null>(null);
  const [resultMeta, setResultMeta] = useState<ResultMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<FriendlyError | null>(null);
  const [copiedCoords, setCopiedCoords] = useState(false);
  const [modeNotice, setModeNotice] = useState(false);
  const [mapCollapsed, setMapCollapsed] = useState(false);

  const tutorialTriggerRef = useRef<HTMLButtonElement>(null);
  const resultsAnchorRef = useRef<HTMLDivElement>(null);

  const scenarios = useMemo(() => {
    const byName = new Map(demos.map((demo) => [demo.demo_name, demo]));
    return BASE_SCENARIOS.map((item) => {
      if (!item.demo_name) return item;
      const demo = byName.get(item.demo_name);
      return demo
        ? {
            ...item,
            lat: demo.lat,
            lon: demo.lon,
            current_date: demo.current_date,
          }
        : item;
    });
  }, [demos]);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = t(lang, "appTitle");
    try {
      localStorage.setItem("pier-lang", lang);
    } catch {
      // Ignore storage failures.
    }
  }, [lang]);

  useEffect(() => {
    let cancelled = false;
    api
      .demos()
      .then((data) => {
        if (!cancelled && Array.isArray(data.demos) && data.demos.length > 0) {
          setDemos(data.demos);
        }
      })
      .catch(() => {
        // Fallback packets keep the demo UI usable if /demos is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const switchToLive = (nextLat: number, nextLon: number) => {
    const wasDemo = demoMode;
    setDemoMode(false);
    setLat(roundCoord(nextLat));
    setLon(roundCoord(nextLon));
    if (wasDemo) {
      setDate(tomorrowISO());
      setModeNotice(true);
    }
  };

  const handleScenarioChange = (value: string) => {
    setScenario(value);
    setModeNotice(false);
    const chosen = scenarios.find((item) => item.id === value);
    if (demoMode && chosen) {
      setLat(chosen.lat);
      setLon(chosen.lon);
      setDate(chosen.current_date);
    }
  };

  const handleDemoModeChange = (value: boolean) => {
    setDemoMode(value);
    setModeNotice(false);
    if (value) {
      const chosen = scenarios.find((item) => item.id === scenario);
      if (chosen) {
        setLat(chosen.lat);
        setLon(chosen.lon);
        setDate(chosen.current_date);
      }
    } else {
      setDate(tomorrowISO());
    }
  };

  const handleLatChange = (value: number) => {
    setLat(value);
    if (demoMode) {
      setDemoMode(false);
      setDate(tomorrowISO());
      setModeNotice(true);
    }
  };

  const handleLonChange = (value: number) => {
    setLon(value);
    if (demoMode) {
      setDemoMode(false);
      setDate(tomorrowISO());
      setModeNotice(true);
    }
  };

  const handleDateChange = (value: string) => {
    setDate(value);
    if (demoMode) {
      setDemoMode(false);
      setModeNotice(true);
    }
  };

  const handleCoordsChange = (nextLat: number, nextLon: number) => {
    setLat(nextLat);
    setLon(nextLon);
    if (demoMode) {
      setDemoMode(false);
      setDate(tomorrowISO());
      setModeNotice(true);
    }
  };

  const handleWeightChange = (key: keyof Weights, value: number) => {
    setWeights((current) => ({ ...current, [key]: value }));
  };

  const copyCoords = async () => {
    try {
      await navigator.clipboard.writeText(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
      setCopiedCoords(true);
      window.setTimeout(() => setCopiedCoords(false), 1800);
    } catch {
      setCopiedCoords(false);
    }
  };

  const runPlan = async (params?: {
    lat: number;
    lon: number;
    date: string;
    demoMode: boolean;
    scenario: string;
  }) => {
    const pLat = params?.lat ?? lat;
    const pLon = params?.lon ?? lon;
    const pDate = params?.date ?? date;
    const pDemo = params?.demoMode ?? demoMode;
    const pScenario = params?.scenario ?? scenario;

    if (
      !Number.isFinite(pLat) ||
      pLat < -90 ||
      pLat > 90 ||
      !Number.isFinite(pLon) ||
      pLon < -180 ||
      pLon > 180
    ) {
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, "invalidCoordinates"),
      });
      return;
    }
    if (!pDate) {
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, "invalidDate"),
      });
      return;
    }
    if (!(yieldT > 0)) {
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, "invalidYield"),
      });
      return;
    }
    const weightTotal =
      weights.soil_protection +
      weights.salvage_revenue +
      weights.water_conservation;
    if (weightTotal <= 0) {
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, "weightsZeroError"),
      });
      return;
    }

    const chosen = scenarios.find((item) => item.id === pScenario);
    setLoading(true);
    setError(null);

    try {
      const response = await api.generatePlan({
        lat: pLat,
        lon: pLon,
        current_date: pDate,
        demo_mode: pDemo,
        demo_name: pDemo ? chosen?.demo_name ?? null : null,
        pesos_agricultor: weights,
        rendimiento_t_ha: yieldT,
      });
      setResult(response);
      setResultMeta({
        lat: pLat,
        lon: pLon,
        date: pDate,
        demoMode: pDemo,
        scenario: pScenario,
        weights: { ...weights },
        yieldT,
      });
      requestAnimationFrame(() => {
        resultsAnchorRef.current?.scrollIntoView({
          behavior: prefersReducedMotion() ? "auto" : "smooth",
          block: "nearest",
        });
      });
    } catch (err) {
      setError(formatFriendlyError(err, lang, pDemo));
    } finally {
      setLoading(false);
    }
  };

  const quickStartDemo = (scenarioId: string) => {
    const chosen = scenarios.find((item) => item.id === scenarioId);
    if (!chosen) return;
    setDemoMode(true);
    setModeNotice(false);
    setScenario(chosen.id);
    setLat(chosen.lat);
    setLon(chosen.lon);
    setDate(chosen.current_date);
    void runPlan({
      lat: chosen.lat,
      lon: chosen.lon,
      date: chosen.current_date,
      demoMode: true,
      scenario: chosen.id,
    });
  };

  const stale =
    resultMeta != null &&
    (Math.abs(resultMeta.lat - lat) > 1e-4 ||
      Math.abs(resultMeta.lon - lon) > 1e-4 ||
      resultMeta.date !== date ||
      resultMeta.demoMode !== demoMode ||
      resultMeta.scenario !== scenario ||
      resultMeta.weights.soil_protection !== weights.soil_protection ||
      resultMeta.weights.salvage_revenue !== weights.salvage_revenue ||
      resultMeta.weights.water_conservation !== weights.water_conservation ||
      resultMeta.yieldT !== yieldT);

  return (
    <div className="min-h-screen bg-[var(--color-pier-surface)] text-slate-900">
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 sm:py-5 lg:px-8">
        <Hero
          lang={lang}
          onLanguageChange={setLang}
          onOpenTutorial={() => setTutorialOpen(true)}
          tutorialTriggerRef={tutorialTriggerRef}
        />

        <div className="mt-5 grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <ControlsPanel
            lang={lang}
            demoMode={demoMode}
            onDemoModeChange={handleDemoModeChange}
            scenarios={scenarios}
            scenario={scenario}
            onScenarioChange={handleScenarioChange}
            lat={lat}
            lon={lon}
            date={date}
            onLatChange={handleLatChange}
            onLonChange={handleLonChange}
            onCoordsChange={handleCoordsChange}
            onDateChange={handleDateChange}
            weights={weights}
            onWeightChange={handleWeightChange}
            onApplyWeights={setWeights}
            yieldT={yieldT}
            onYieldChange={setYieldT}
            onPreset={switchToLive}
            onGenerate={() => void runPlan()}
            loading={loading}
            stale={stale}
            hasResult={result != null}
          />

          <main className="min-w-0 space-y-4">
            {modeNotice ? (
              <div
                role="status"
                className="pier-no-print flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-950"
              >
                <span>{t(lang, "switchedToLiveNotice")}</span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleDemoModeChange(true)}
                    className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-emerald-900 ring-1 ring-emerald-300 transition hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    <RotateCcw className="h-3 w-3" aria-hidden="true" />
                    {t(lang, "revertToDemo")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setModeNotice(false)}
                    aria-label={t(lang, "dismiss")}
                    className="inline-flex h-6 w-6 items-center justify-center rounded-full text-emerald-800 hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </div>
            ) : null}

            {/* Interactive Map Card */}
            <section className="pier-no-print rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <MapPin
                      className="h-4 w-4 text-emerald-700"
                      aria-hidden="true"
                    />
                    {t(lang, "mapTitle")}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-600">
                    {t(lang, "mapHint")}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs">
                    <span className="font-mono font-semibold tabular-nums text-slate-900">
                      {lat.toFixed(4)}, {lon.toFixed(4)}
                    </span>
                    <button
                      type="button"
                      onClick={copyCoords}
                      aria-label={t(lang, "copy")}
                      className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[0.68rem] font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                    >
                      {copiedCoords ? (
                        <Check
                          className="h-3 w-3 text-emerald-700"
                          aria-hidden="true"
                        />
                      ) : (
                        <Copy className="h-3 w-3" aria-hidden="true" />
                      )}
                      {copiedCoords ? t(lang, "copied") : t(lang, "copy")}
                    </button>
                  </div>

                  <span className="hidden sm:inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium tabular-nums text-slate-700">
                    <CalendarDays
                      className="h-3.5 w-3.5 text-slate-500"
                      aria-hidden="true"
                    />
                    {formatDate(date, lang)}
                  </span>

                  <button
                    type="button"
                    onClick={() => setMapCollapsed((v) => !v)}
                    aria-expanded={!mapCollapsed}
                    className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    {mapCollapsed ? (
                      <>
                        {t(lang, "mapExpand")}
                        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                      </>
                    ) : (
                      <>
                        {t(lang, "mapCollapse")}
                        <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                      </>
                    )}
                  </button>
                </div>
              </div>

              {!mapCollapsed ? (
                <div className="mt-3">
                  <MapPicker
                    lat={lat}
                    lon={lon}
                    eventType={result?.event_type ?? "none"}
                    confidence={result?.event_confidence ?? 0}
                    lang={lang}
                    onPick={switchToLive}
                    compact={result != null}
                  />
                </div>
              ) : null}
            </section>

            <div ref={resultsAnchorRef} />

            {error ? (
              <div
                role="alert"
                className="flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-950 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-rose-700"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="font-bold text-rose-950">{error.title}</p>
                    <p className="mt-0.5 text-rose-900">{error.description}</p>
                    {error.items && error.items.length > 0 ? (
                      <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-rose-900">
                        {error.items.map((item, idx) => (
                          <li key={idx}>{item}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {error.suggestDemo ? (
                    <button
                      type="button"
                      onClick={() => quickStartDemo("flood")}
                      className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-rose-900 transition hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-700"
                    >
                      {t(lang, "tryDemoInstead")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void runPlan()}
                    className="inline-flex items-center gap-1.5 rounded-full bg-rose-700 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-rose-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-700"
                  >
                    <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                    {t(lang, "retry")}
                  </button>
                </div>
              </div>
            ) : null}

            {loading ? (
              <section
                aria-busy="true"
                aria-live="polite"
                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                    <Sprout className="h-5 w-5 animate-pulse" aria-hidden="true" />
                  </span>
                  <div>
                    <h2 className="text-base font-semibold text-slate-900">
                      {t(lang, "loadingTitle")}
                    </h2>
                    <p className="text-xs text-slate-600">
                      {t(lang, "loadingSubtitle")}
                    </p>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {[0, 1, 2, 3].map((item) => (
                    <div
                      key={item}
                      className="h-24 animate-pulse rounded-2xl bg-slate-100"
                    />
                  ))}
                </div>
              </section>
            ) : result ? (
              <Results
                key={result.request_id}
                result={result}
                lang={lang}
                stale={stale}
                date={resultMeta?.date ?? date}
                lat={resultMeta?.lat ?? lat}
                lon={resultMeta?.lon ?? lon}
                demoMode={resultMeta?.demoMode ?? demoMode}
                onRefresh={() => void runPlan()}
                loading={loading}
              />
            ) : (
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                <div className="mx-auto max-w-2xl text-center">
                  <span className="mx-auto inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                    <Sprout className="h-6 w-6" aria-hidden="true" />
                  </span>
                  <h2 className="mt-3 text-xl font-bold tracking-tight text-slate-900">
                    {t(lang, "welcomeTitle")}
                  </h2>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
                    {t(lang, "welcomeBody")}
                  </p>
                </div>

                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                  <button
                    type="button"
                    onClick={() => quickStartDemo("flood")}
                    className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-slate-50/70 p-4 text-left transition hover:border-sky-300 hover:bg-sky-50/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    <div>
                      <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-sky-100 text-sky-800">
                        <CloudRain className="h-4 w-4" aria-hidden="true" />
                      </span>
                      <h3 className="mt-3 text-sm font-bold text-slate-900">
                        {t(lang, "quickTryFlood")}
                      </h3>
                      <p className="mt-1 text-xs leading-relaxed text-slate-600">
                        {t(lang, "quickTryFloodDesc")}
                      </p>
                    </div>
                    <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 group-hover:translate-x-0.5 transition-transform">
                      {t(lang, "generate")}
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => quickStartDemo("drought")}
                    className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-slate-50/70 p-4 text-left transition hover:border-amber-300 hover:bg-amber-50/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    <div>
                      <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 text-amber-800">
                        <ThermometerSun className="h-4 w-4" aria-hidden="true" />
                      </span>
                      <h3 className="mt-3 text-sm font-bold text-slate-900">
                        {t(lang, "quickTryDrought")}
                      </h3>
                      <p className="mt-1 text-xs leading-relaxed text-slate-600">
                        {t(lang, "quickTryDroughtDesc")}
                      </p>
                    </div>
                    <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 group-hover:translate-x-0.5 transition-transform">
                      {t(lang, "generate")}
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => quickStartDemo("late_flood")}
                    className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-slate-50/70 p-4 text-left transition hover:border-emerald-300 hover:bg-emerald-50/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    <div>
                      <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100 text-emerald-800">
                        <CloudRain className="h-4 w-4" aria-hidden="true" />
                      </span>
                      <h3 className="mt-3 text-sm font-bold text-slate-900">
                        {t(lang, "quickTryLateFlood")}
                      </h3>
                      <p className="mt-1 text-xs leading-relaxed text-slate-600">
                        {t(lang, "quickTryLateFloodDesc")}
                      </p>
                    </div>
                    <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 group-hover:translate-x-0.5 transition-transform">
                      {t(lang, "generate")}
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                  </button>
                </div>
              </section>
            )}
          </main>
        </div>

        <footer className="mt-8 border-t border-slate-200 pt-4 text-center text-xs leading-relaxed text-slate-600">
          {t(lang, "footerDisclaimer")}
        </footer>
      </div>

      <Tutorial
        key={tutorialOpen ? "open" : "closed"}
        open={tutorialOpen}
        lang={lang}
        onClose={() => setTutorialOpen(false)}
        returnFocusRef={tutorialTriggerRef}
      />
    </div>
  );
}
