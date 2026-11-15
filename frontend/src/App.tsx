import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  Check,
  CloudRain,
  Copy,
  FileText,
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
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
  const [resultsOpen, setResultsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<FriendlyError | null>(null);
  const [copiedCoords, setCopiedCoords] = useState(false);
  const [modeNotice, setModeNotice] = useState(false);

  const tutorialTriggerRef = useRef<HTMLButtonElement>(null);

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
      setResultsOpen(true);
      return;
    }
    if (!pDate) {
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, "invalidDate"),
      });
      setResultsOpen(true);
      return;
    }
    if (!(yieldT > 0)) {
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, "invalidYield"),
      });
      setResultsOpen(true);
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
      setResultsOpen(true);
      return;
    }

    const chosen = scenarios.find((item) => item.id === pScenario);
    setLoading(true);
    setError(null);
    setResultsOpen(true);
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setSidebarOpen(false);
    }

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

  const showOverlay = loading || error != null || (result != null && resultsOpen);

  return (
    <div className="flex min-h-screen flex-col bg-slate-100 text-slate-900 lg:h-screen lg:overflow-hidden">
      <Hero
        lang={lang}
        onLanguageChange={setLang}
        onOpenTutorial={() => setTutorialOpen(true)}
        tutorialTriggerRef={tutorialTriggerRef}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
      />

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Flush Google-Maps-style Left Side Panel */}
        {sidebarOpen ? (
          <div className="w-full shrink-0 lg:h-full lg:w-[390px] xl:w-[410px]">
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
          </div>
        ) : null}

        {/* Immersive Edge-to-Edge Map Canvas */}
        <main className="relative min-h-[460px] flex-1 overflow-hidden lg:h-full">
          <MapPicker
            lat={lat}
            lon={lon}
            eventType={result?.event_type ?? "none"}
            confidence={result?.event_confidence ?? 0}
            lang={lang}
            onPick={switchToLive}
          />

          {/* Floating Google-Maps-style Category & Status Pills */}
          <div className="pier-no-print pointer-events-none absolute left-3 right-3 top-3 z-[450] flex flex-wrap items-center justify-between gap-2">
            <div className="pointer-events-auto flex flex-wrap items-center gap-2">
              {result && !resultsOpen ? (
                <button
                  type="button"
                  onClick={() => setResultsOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-full bg-emerald-700 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(lang, "viewPlan")}
                </button>
              ) : null}

              <button
                type="button"
                onClick={() => quickStartDemo("flood")}
                className="inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3.5 py-1.5 text-xs font-semibold text-slate-800 shadow-md ring-1 ring-slate-900/10 backdrop-blur transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                <CloudRain
                  className="h-3.5 w-3.5 text-sky-700"
                  aria-hidden="true"
                />
                {t(lang, "quickPillFlood")}
              </button>

              <button
                type="button"
                onClick={() => quickStartDemo("drought")}
                className="inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3.5 py-1.5 text-xs font-semibold text-slate-800 shadow-md ring-1 ring-slate-900/10 backdrop-blur transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                <ThermometerSun
                  className="h-3.5 w-3.5 text-amber-700"
                  aria-hidden="true"
                />
                {t(lang, "quickPillDrought")}
              </button>

              <button
                type="button"
                onClick={() => quickStartDemo("late_flood")}
                className="inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3.5 py-1.5 text-xs font-semibold text-slate-800 shadow-md ring-1 ring-slate-900/10 backdrop-blur transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                <CloudRain
                  className="h-3.5 w-3.5 text-emerald-700"
                  aria-hidden="true"
                />
                {t(lang, "quickPillLateFlood")}
              </button>
            </div>

            <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-full bg-white/95 px-3 py-1 text-xs shadow-md ring-1 ring-slate-900/10 backdrop-blur">
              <span className="font-mono font-semibold tabular-nums text-slate-900">
                {lat.toFixed(4)}, {lon.toFixed(4)}
              </span>
              <button
                type="button"
                onClick={copyCoords}
                aria-label={t(lang, "copy")}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[0.68rem] font-semibold text-slate-700 transition hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
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
              <span className="hidden sm:inline text-slate-400">·</span>
              <span className="hidden sm:inline-flex items-center gap-1 font-medium tabular-nums text-slate-700">
                <CalendarDays
                  className="h-3 w-3 text-slate-500"
                  aria-hidden="true"
                />
                {formatDate(date, lang)}
              </span>
            </div>
          </div>

          {modeNotice ? (
            <div
              role="status"
              className="pier-no-print absolute left-3 top-16 z-[450] flex flex-wrap items-center gap-2 rounded-full bg-emerald-950/90 px-3.5 py-1.5 text-xs font-medium text-white shadow-lg backdrop-blur"
            >
              <span>{t(lang, "switchedToLiveNotice")}</span>
              <button
                type="button"
                onClick={() => handleDemoModeChange(true)}
                className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-[0.7rem] font-semibold text-emerald-950 transition hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              >
                <RotateCcw className="h-3 w-3" aria-hidden="true" />
                {t(lang, "revertToDemo")}
              </button>
              <button
                type="button"
                onClick={() => setModeNotice(false)}
                aria-label={t(lang, "dismiss")}
                className="inline-flex h-5 w-5 items-center justify-center rounded-full text-emerald-200 hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          ) : null}

          {/* Immersive Results / Loading / Error Overlay Sheet */}
          {showOverlay ? (
            <div className="pier-scroll absolute inset-0 z-[500] flex flex-col overflow-y-auto bg-[var(--color-pier-surface)]/97 backdrop-blur-sm">
              <div className="pier-no-print sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white/95 px-4 py-2.5 backdrop-blur sm:px-6">
                <button
                  type="button"
                  onClick={() => {
                    setResultsOpen(false);
                    setError(null);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-800 shadow-xs transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                >
                  <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(lang, "backToMap")}
                </button>

                <div className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="font-mono font-semibold tabular-nums text-slate-800">
                    {lat.toFixed(4)}, {lon.toFixed(4)}
                  </span>
                  <span>·</span>
                  <span className="tabular-nums">{formatDate(date, lang)}</span>
                </div>
              </div>

              <div className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-4 sm:p-6">
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
                        <p className="mt-0.5 text-rose-900">
                          {error.description}
                        </p>
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
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
                  >
                    <div className="flex items-center gap-3">
                      <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                        <Sprout
                          className="h-6 w-6 animate-pulse"
                          aria-hidden="true"
                        />
                      </span>
                      <div>
                        <h2 className="text-base font-bold text-slate-900">
                          {t(lang, "loadingTitle")}
                        </h2>
                        <p className="text-xs text-slate-600">
                          {t(lang, "loadingSubtitle")}
                        </p>
                      </div>
                    </div>
                    <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
                ) : null}

                <footer className="pt-2 text-center text-xs leading-relaxed text-slate-600">
                  {t(lang, "footerDisclaimer")}
                </footer>
              </div>
            </div>
          ) : null}
        </main>
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
