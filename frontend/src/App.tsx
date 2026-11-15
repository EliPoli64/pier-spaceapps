import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  Check,
  Copy,
  Loader2,
  MapPin,
  Play,
  Sparkles,
  Sprout,
} from "lucide-react";
import { ControlsPanel } from "./components/ControlsPanel";
import { Hero } from "./components/Hero";
import { MapPicker } from "./components/MapPicker";
import { Results } from "./components/Results";
import { Tutorial } from "./components/Tutorial";
import { api } from "./lib/api";
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
  sourceLabel,
  tomorrowISO,
} from "./lib/format";

const BASE_SCENARIOS: Scenario[] = [
  {
    id: "auto",
    labelKey: "scenarioAuto",
    demo_name: null,
    lat: 41.8,
    lon: -93.6,
    current_date: "2025-05-15",
  },
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

function readTutorialSeen(): boolean {
  try {
    return localStorage.getItem("pier-tutorial-seen") === "1";
  } catch {
    return false;
  }
}

export default function App() {
  const [lang, setLang] = useState<Lang>(readLang);
  const [tutorialOpen, setTutorialOpen] = useState(() => !readTutorialSeen());
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
  const [error, setError] = useState<string | null>(null);
  const [copiedCoords, setCopiedCoords] = useState(false);

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
        // The fallback packets keep the demo UI usable if /demos is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const closeTutorial = () => {
    setTutorialOpen(false);
    try {
      localStorage.setItem("pier-tutorial-seen", "1");
    } catch {
      // Ignore storage failures.
    }
  };

  const goLiveAt = (nextLat: number, nextLon: number) => {
    const wasDemo = demoMode;
    setDemoMode(false);
    setLat(roundCoord(nextLat));
    setLon(roundCoord(nextLon));
    if (wasDemo) setDate(tomorrowISO());
  };

  const handleScenarioChange = (value: string) => {
    setScenario(value);
    const chosen = scenarios.find((item) => item.id === value);
    if (demoMode && chosen) {
      setLat(chosen.lat);
      setLon(chosen.lon);
      setDate(chosen.current_date);
    }
  };

  const handleDemoModeChange = (value: boolean) => {
    setDemoMode(value);
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
    }
  };

  const handleLonChange = (value: number) => {
    setLon(value);
    if (demoMode) {
      setDemoMode(false);
      setDate(tomorrowISO());
    }
  };

  const handleDateChange = (value: string) => {
    setDate(value);
    if (demoMode) setDemoMode(false);
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

  const handleGenerate = async () => {
    if (
      !Number.isFinite(lat) ||
      lat < -90 ||
      lat > 90 ||
      !Number.isFinite(lon) ||
      lon < -180 ||
      lon > 180
    ) {
      setError(t(lang, "invalidCoordinates"));
      return;
    }
    if (!date) {
      setError(t(lang, "invalidDate"));
      return;
    }
    if (!(yieldT > 0)) {
      setError(t(lang, "invalidYield"));
      return;
    }

    const chosen = scenarios.find((item) => item.id === scenario);
    setLoading(true);
    setError(null);

    try {
      const response = await api.generatePlan({
        lat,
        lon,
        current_date: date,
        demo_mode: demoMode,
        demo_name: demoMode ? chosen?.demo_name ?? null : null,
        pesos_agricultor: weights,
        rendimiento_t_ha: yieldT,
      });
      setResult(response);
      setResultMeta({
        lat,
        lon,
        date,
        demoMode,
        scenario,
        weights: { ...weights },
        yieldT,
      });
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : t(lang, "requestFailed"),
      );
    } finally {
      setLoading(false);
    }
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
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <Hero
          lang={lang}
          onLanguageChange={setLang}
          onOpenTutorial={() => setTutorialOpen(true)}
        />

        <div className="mt-5 grid gap-5 lg:grid-cols-[350px_minmax(0,1fr)]">
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
            onDateChange={handleDateChange}
            weights={weights}
            onWeightChange={handleWeightChange}
            yieldT={yieldT}
            onYieldChange={setYieldT}
            onPreset={goLiveAt}
            onGenerate={handleGenerate}
            loading={loading}
          />

          <main className="min-w-0 space-y-4">
            <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <MapPin className="h-4 w-4 text-emerald-600" />
                    {t(lang, "mapTitle")}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {t(lang, "mapHint")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.68rem] font-semibold ring-1 ${
                      demoMode
                        ? "bg-amber-50 text-amber-800 ring-amber-200"
                        : "bg-emerald-50 text-emerald-700 ring-emerald-200"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        demoMode ? "bg-amber-500" : "bg-emerald-500"
                      }`}
                    />
                    {demoMode ? t(lang, "demoBadge") : t(lang, "liveBadge")}
                  </span>
                  <button
                    type="button"
                    onClick={handleGenerate}
                    disabled={loading}
                    aria-label={t(lang, "generate")}
                    className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-3 py-1.5 text-[0.68rem] font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {loading ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Play className="h-3 w-3 fill-current" />
                    )}
                    <span className="hidden sm:inline">
                      {loading ? t(lang, "generating") : t(lang, "generate")}
                    </span>
                  </button>
                </div>
              </div>

              <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
                <MapPicker
                  lat={lat}
                  lon={lon}
                  eventType={result?.event_type ?? "none"}
                  confidence={result?.event_confidence ?? 0}
                  lang={lang}
                  onPick={goLiveAt}
                />

                <div className="flex h-full flex-col gap-3">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium text-slate-500">
                        {t(lang, "selectedLocation")}
                      </p>
                      <button
                        type="button"
                        onClick={copyCoords}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[0.65rem] font-semibold text-slate-600 transition hover:bg-slate-100"
                      >
                        {copiedCoords ? (
                          <Check className="h-3 w-3 text-emerald-600" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                        {copiedCoords ? t(lang, "copied") : t(lang, "copy")}
                      </button>
                    </div>
                    <p className="mt-1 font-mono text-lg font-semibold tracking-tight text-slate-900">
                      {lat.toFixed(4)}, {lon.toFixed(4)}
                    </p>

                    <div className="mt-3 grid grid-cols-2 gap-3 border-t border-slate-200 pt-3 text-xs">
                      <div>
                        <p className="flex items-center gap-1 text-slate-400">
                          <CalendarDays className="h-3 w-3" />
                          {t(lang, "dateLabel")}
                        </p>
                        <p className="mt-0.5 font-medium text-slate-800">
                          {formatDate(date, lang)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400">
                          {t(lang, "dataSource")}
                        </p>
                        <p className="mt-0.5 font-medium text-slate-800">
                          {result
                            ? sourceLabel(result.fuente_datos, lang)
                            : "—"}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div
                    className={`flex flex-col justify-between gap-3 rounded-2xl border p-4 text-xs leading-relaxed xl:flex-1 ${
                      demoMode
                        ? "border-amber-200 bg-amber-50 text-amber-900"
                        : "border-emerald-200 bg-emerald-50 text-emerald-900"
                    }`}
                  >
                    <p className="font-semibold">
                      {demoMode
                        ? t(lang, "demoLocationNote")
                        : t(lang, "liveModeHint")}
                    </p>
                    {demoMode ? (
                      <button
                        type="button"
                        onClick={() => {
                          setDemoMode(false);
                          setDate(tomorrowISO());
                        }}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 font-semibold text-amber-900 shadow-sm ring-1 ring-amber-200 transition hover:bg-amber-100"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        {t(lang, "useLiveData")}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            </section>

            {error ? (
              <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <p className="font-semibold">{t(lang, "requestFailed")}</p>
                  <p className="mt-0.5 text-rose-800">{error}</p>
                </div>
              </div>
            ) : null}

            {result ? (
              <Results
                key={result.request_id}
                result={result}
                lang={lang}
                stale={stale}
                date={resultMeta?.date ?? date}
                lat={resultMeta?.lat ?? lat}
                lon={resultMeta?.lon ?? lon}
                demoMode={resultMeta?.demoMode ?? demoMode}
              />
            ) : (
              <section className="rounded-3xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center shadow-sm">
                <span className="mx-auto inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
                  <Sprout className="h-7 w-7" />
                </span>
                <h2 className="mt-4 text-lg font-semibold tracking-tight text-slate-900">
                  {t(lang, "welcomeTitle")}
                </h2>
                <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-slate-500">
                  {t(lang, "welcomeBody")}
                </p>
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={loading}
                  className="mt-5 inline-flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 fill-current" />
                  )}
                  {loading ? t(lang, "generating") : t(lang, "generate")}
                </button>
              </section>
            )}
          </main>
        </div>

        <footer className="mt-8 border-t border-slate-200 pt-4 text-center text-[0.7rem] leading-relaxed text-slate-400">
          {t(lang, "footerDisclaimer")}
        </footer>
      </div>

      <Tutorial
        key={tutorialOpen ? "open" : "closed"}
        open={tutorialOpen}
        lang={lang}
        onClose={closeTutorial}
      />
    </div>
  );
}
