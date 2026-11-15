import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  CloudRain,
  Copy,
  FileText,
  Loader2,
  Map as MapIcon,
  RefreshCw,
  RotateCcw,
  SlidersHorizontal,
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
import { t, tFormat } from "./lib/i18n";
import type {
  Demo,
  PlanResponse,
  ResultMeta,
  Scenario,
  Weights,
} from "./lib/types";
import {
  formatDate,
  isoWithOffset,
  roundCoord,
  validatePlanningDate,
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
  const [mobileView, setMobileView] = useState<"setup" | "map">("setup");
  const [demos, setDemos] = useState<Demo[]>(FALLBACK_DEMOS);
  const [demoMode, setDemoMode] = useState(false);
  const [scenario, setScenario] = useState("flood");
  const [lat, setLat] = useState(41.8);
  const [lon, setLon] = useState(-93.6);
  const [date, setDate] = useState(() => isoWithOffset(-7));
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
  const [loadingSeconds, setLoadingSeconds] = useState(0);
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
    if (!loading) {
      setLoadingSeconds(0);
      return;
    }
    setLoadingSeconds(0);
    const id = window.setInterval(() => {
      setLoadingSeconds((s) => s + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [loading]);

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
      setDate(isoWithOffset(-7));
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
      setDate(isoWithOffset(-7));
    }
  };

  const handleLatChange = (value: number) => {
    setLat(value);
    if (demoMode) {
      setDemoMode(false);
      setDate(isoWithOffset(-7));
      setModeNotice(true);
    }
  };

  const handleLonChange = (value: number) => {
    setLon(value);
    if (demoMode) {
      setDemoMode(false);
      setDate(isoWithOffset(-7));
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
      setDate(isoWithOffset(-7));
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
    const dateError = validatePlanningDate(pDate, !pDemo);
    if (dateError) {
      const descriptionKey =
        dateError === "future"
          ? "dateFutureBlocked"
          : dateError === "too_early"
            ? "dateTooEarly"
            : "invalidDate";
      setError({
        title: t(lang, "errorInputTitle"),
        description: t(lang, descriptionKey),
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
    <div className="flex h-dvh flex-col overflow-hidden bg-slate-100 text-slate-900 print:h-auto print:overflow-visible">
      <Hero
        lang={lang}
        onLanguageChange={setLang}
        onOpenTutorial={() => setTutorialOpen(true)}
        tutorialTriggerRef={tutorialTriggerRef}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
      />

      {/* Mobile View Switcher (Field setup / Field map / View plan) */}
      <div className="pier-no-print flex shrink-0 items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2 lg:hidden">
        <div
          className="grid flex-1 grid-cols-2 gap-1 rounded-xl bg-slate-100 p-0.5"
          role="group"
          aria-label={t(lang, "controlsTitle")}
        >
          <button
            type="button"
            onClick={() => setMobileView("setup")}
            aria-pressed={mobileView === "setup"}
            className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
              mobileView === "setup"
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <SlidersHorizontal
              className={`h-3.5 w-3.5 ${mobileView === "setup" ? "text-emerald-700" : "text-slate-500"}`}
              aria-hidden="true"
            />
            <span className="truncate">{t(lang, "controlsTitle")}</span>
          </button>
          <button
            type="button"
            onClick={() => setMobileView("map")}
            aria-pressed={mobileView === "map"}
            className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
              mobileView === "map"
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <MapIcon
              className={`h-3.5 w-3.5 ${mobileView === "map" ? "text-emerald-700" : "text-slate-500"}`}
              aria-hidden="true"
            />
            <span className="truncate">{t(lang, "mapTitle")}</span>
          </button>
        </div>

        {result && !resultsOpen ? (
          <button
            type="button"
            onClick={() => setResultsOpen(true)}
            className="inline-flex shrink-0 items-center gap-1 rounded-xl bg-emerald-700 px-3 py-2 text-xs font-semibold text-white shadow-xs transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
          >
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t(lang, "mobilePlanTab")}</span>
          </button>
        ) : null}
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Flush Left Side Panel (Desktop sidebar / Mobile Setup view) */}
        <div
          className={`${
            mobileView === "setup" ? "flex min-h-0 flex-1 flex-col" : "hidden"
          } ${
            sidebarOpen
              ? "lg:block lg:h-full lg:w-[390px] lg:flex-none xl:w-[410px]"
              : "lg:hidden"
          } w-full shrink-0`}
        >
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
            onOpenMap={() => setMobileView("map")}
            loading={loading}
            stale={stale}
            hasResult={result != null}
          />
        </div>

        {/* Immersive Edge-to-Edge Map Canvas */}
        <main
          className={`relative min-h-0 flex-1 overflow-hidden lg:h-full ${
            mobileView === "map" || showOverlay ? "block" : "hidden lg:block"
          }`}
        >
          <MapPicker
            lat={lat}
            lon={lon}
            eventType={result?.event_type ?? "none"}
            confidence={result?.event_confidence ?? 0}
            lang={lang}
            onPick={switchToLive}
          />

          {/* Floating Map Quick Demos & Desktop Coordinates */}
          <div className="pier-no-print pointer-events-none absolute left-3 right-3 top-3 z-[450] flex items-center justify-between gap-2">
            <div className="pointer-events-auto pier-no-scrollbar flex max-w-full flex-nowrap items-center gap-2 overflow-x-auto pb-0.5 sm:flex-wrap sm:overflow-visible sm:pb-0">
              {result && !resultsOpen ? (
                <button
                  type="button"
                  onClick={() => setResultsOpen(true)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-700 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(lang, "viewPlan")}
                </button>
              ) : null}

              <button
                type="button"
                onClick={() => quickStartDemo("flood")}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-md ring-1 ring-slate-900/10 backdrop-blur transition hover:bg-white active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 sm:px-3.5"
              >
                <CloudRain
                  className="h-3.5 w-3.5 stroke-[1.75] text-sky-700"
                  aria-hidden="true"
                />
                {t(lang, "quickPillFlood")}
              </button>

              <button
                type="button"
                onClick={() => quickStartDemo("drought")}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-md ring-1 ring-slate-900/10 backdrop-blur transition hover:bg-white active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 sm:px-3.5"
              >
                <ThermometerSun
                  className="h-3.5 w-3.5 stroke-[1.75] text-amber-700"
                  aria-hidden="true"
                />
                {t(lang, "quickPillDrought")}
              </button>

              <button
                type="button"
                onClick={() => quickStartDemo("late_flood")}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-md ring-1 ring-slate-900/10 backdrop-blur transition hover:bg-white active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 sm:px-3.5"
              >
                <CloudRain
                  className="h-3.5 w-3.5 stroke-[1.75] text-emerald-700"
                  aria-hidden="true"
                />
                {t(lang, "quickPillLateFlood")}
              </button>
            </div>

            <div className="pointer-events-auto hidden shrink-0 items-center gap-1.5 rounded-full bg-white/95 px-3 py-1 text-xs shadow-md ring-1 ring-slate-900/10 backdrop-blur lg:flex">
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
              <span className="text-slate-400">·</span>
              <span className="inline-flex items-center gap-1 font-medium tabular-nums text-slate-700">
                <CalendarDays
                  className="h-3 w-3 text-slate-500"
                  aria-hidden="true"
                />
                {formatDate(date, lang)}
              </span>
            </div>
          </div>

          {/* Mobile Bottom Pin Coordinates + Use Field CTA */}
          <div className="pier-no-print pointer-events-none absolute bottom-12 left-3 right-14 z-[450] flex items-center lg:hidden">
            <div className="pointer-events-auto flex w-full max-w-sm items-center justify-between gap-2 rounded-2xl bg-white/95 px-3 py-2 text-xs shadow-lg ring-1 ring-slate-900/10 backdrop-blur">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="truncate font-mono font-semibold tabular-nums text-slate-900">
                  {lat.toFixed(4)}, {lon.toFixed(4)}
                </span>
                <button
                  type="button"
                  onClick={copyCoords}
                  aria-label={t(lang, "copy")}
                  className="inline-flex shrink-0 items-center justify-center rounded-full bg-slate-100 p-1 text-slate-700 transition hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                >
                  {copiedCoords ? (
                    <Check
                      className="h-3 w-3 text-emerald-700"
                      aria-hidden="true"
                    />
                  ) : (
                    <Copy className="h-3 w-3" aria-hidden="true" />
                  )}
                </button>
              </div>
              <button
                type="button"
                onClick={() => setMobileView("setup")}
                className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-700 px-3 py-1.5 text-[11px] font-semibold text-white shadow-xs transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                {t(lang, "useThisPin")}
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          </div>

          {modeNotice ? (
            <div
              role="status"
              className="pier-slide-in pier-no-print absolute left-3 right-3 top-14 z-[450] flex flex-wrap items-center gap-2 rounded-2xl bg-emerald-950/90 px-3.5 py-2 text-xs font-medium text-white shadow-lg backdrop-blur sm:right-auto sm:top-16 sm:rounded-full sm:py-1.5"
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
                className="ml-auto inline-flex h-5 w-5 items-center justify-center rounded-full text-emerald-200 hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white sm:ml-0"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          ) : null}

          {/* Immersive Results / Loading / Error Overlay Sheet */}
          {showOverlay ? (
            <div className="pier-sheet-in pier-scroll fixed inset-x-0 bottom-0 top-14 z-[500] flex flex-col overflow-y-auto bg-[var(--color-pier-surface)]/97 backdrop-blur-sm print:static print:inset-auto print:overflow-visible lg:absolute lg:inset-0">
              <div className="pier-no-print sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-slate-200 bg-white/95 px-3 py-2.5 backdrop-blur sm:px-6">
                <div className="flex items-center gap-1.5 sm:gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setResultsOpen(false);
                      setError(null);
                      setMobileView("map");
                    }}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-xs transition hover:bg-slate-100 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                  >
                    <ArrowLeft className="h-3.5 w-3.5 stroke-[1.75]" aria-hidden="true" />
                    {t(lang, "backToMap")}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setResultsOpen(false);
                      setError(null);
                      setMobileView("setup");
                    }}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 lg:hidden"
                  >
                    <SlidersHorizontal
                      className="h-3.5 w-3.5 stroke-[1.75] text-emerald-700"
                      aria-hidden="true"
                    />
                    {t(lang, "editInputs")}
                  </button>
                </div>

                <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-slate-600 sm:gap-2 sm:text-xs">
                  <span className="truncate font-mono font-semibold tabular-nums text-slate-800">
                    {lat.toFixed(2)}, {lon.toFixed(2)}
                  </span>
                  <span className="hidden sm:inline" aria-hidden="true">
                    ·
                  </span>
                  <span className="hidden tabular-nums sm:inline">
                    {formatDate(date, lang)}
                  </span>
                </div>
              </div>

              <div className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-3 sm:p-6">
                {error ? (
                  <div
                    role="alert"
                    className="pier-slide-in flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-950 sm:flex-row sm:items-start sm:justify-between"
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
                    className="pier-slide-in overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-xs"
                  >
                    <div className="relative h-[3px] w-full overflow-hidden bg-slate-100">
                      <div className="pier-progress-bar h-full w-1/2 rounded-full bg-gradient-to-r from-[#0b1f3a] via-[#123b5c] to-[#15803d]" />
                    </div>

                    <div className="px-4 pb-5 pt-4 sm:px-7 sm:pb-6 sm:pt-5">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="flex items-start gap-3.5">
                          <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/90">
                            <Loader2
                              className="h-5.5 w-5.5 animate-spin stroke-[2.2]"
                              aria-hidden="true"
                            />
                          </span>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-800 ring-1 ring-emerald-200/80">
                                <Loader2
                                  className="h-3 w-3 animate-spin stroke-[2.25]"
                                  aria-hidden="true"
                                />
                                {t(lang, "loadingBadge")}
                              </span>
                              <span className="text-xs font-medium tabular-nums text-slate-500">
                                {tFormat(lang, "loadingElapsed", { seconds: loadingSeconds })}
                              </span>
                            </div>
                            <h2 className="mt-1.5 text-base font-semibold tracking-tight text-slate-900 sm:text-lg">
                              {t(lang, "loadingTitle")}
                            </h2>
                            <p className="mt-0.5 text-xs text-slate-600">
                              {loadingSeconds >= 15
                                ? t(lang, "loadingStillWorking")
                                : t(lang, "loadingSubtitle")}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 flex items-center gap-2.5 rounded-xl border border-slate-200/90 bg-slate-50/90 px-3.5 py-2.5 text-xs leading-relaxed text-slate-700">
                        <Loader2
                          className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-700"
                          aria-hidden="true"
                        />
                        <span>{t(lang, "loadingEta")}</span>
                      </div>

                      <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 border-t border-slate-200/80 pt-4 sm:mt-6 sm:gap-x-6 sm:pt-5 lg:grid-cols-4 lg:gap-x-0 lg:divide-x lg:divide-slate-200/80">
                        {[0, 1, 2, 3].map((item) => (
                          <div
                            key={item}
                            className="space-y-2 py-0.5 lg:px-5 first:lg:pl-0 last:lg:pr-0"
                          >
                            <div className="pier-shimmer h-3 w-20 rounded-full" />
                            <div className="pier-shimmer h-6 w-24 rounded-lg" />
                            <div className="pier-shimmer h-2.5 w-16 rounded-full" />
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="border-t border-slate-200/80 px-4 py-5 sm:px-7 sm:py-7">
                      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
                        <div className="space-y-3">
                          <div className="pier-shimmer h-3 w-24 rounded-full" />
                          <div className="pier-shimmer h-7 w-2/3 rounded-lg" />
                          <div className="pier-shimmer h-3 w-full max-w-md rounded-full" />
                          <div className="pier-shimmer h-3 w-4/5 max-w-sm rounded-full" />
                        </div>
                        <div className="space-y-3 border-t border-slate-200/80 pt-5 xl:border-l xl:border-t-0 xl:pl-7 xl:pt-0">
                          <div className="pier-shimmer h-3 w-28 rounded-full" />
                          <div className="pier-shimmer h-4 w-full rounded-full" />
                          <div className="pier-shimmer h-4 w-5/6 rounded-full" />
                          <div className="pier-shimmer h-4 w-2/3 rounded-full" />
                        </div>
                      </div>
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
