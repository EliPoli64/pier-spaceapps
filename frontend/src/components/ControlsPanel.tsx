import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ClipboardEvent } from "react";
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  Droplets,
  Leaf,
  Loader2,
  LocateFixed,
  MapPin,
  Play,
  RefreshCw,
  Satellite,
  Scale,
  Search,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Lang } from "../lib/i18n";
import { t, tFormat } from "../lib/i18n";
import type { Scenario, Weights } from "../lib/types";
import {
  MIN_NASA_DATE,
  clamp,
  formatDate,
  isoWithOffset,
  roundCoord,
  validatePlanningDate,
} from "../lib/format";
import { searchPlaces } from "../lib/places";
import type { PlaceResult } from "../lib/places";

interface ControlsPanelProps {
  lang: Lang;
  demoMode: boolean;
  onDemoModeChange: (value: boolean) => void;
  scenarios: Scenario[];
  scenario: string;
  onScenarioChange: (value: string) => void;
  lat: number;
  lon: number;
  date: string;
  onLatChange: (value: number) => void;
  onLonChange: (value: number) => void;
  onCoordsChange: (lat: number, lon: number) => void;
  onDateChange: (value: string) => void;
  weights: Weights;
  onWeightChange: (key: keyof Weights, value: number) => void;
  onApplyWeights: (weights: Weights) => void;
  yieldT: number;
  onYieldChange: (value: number) => void;
  onPreset: (lat: number, lon: number) => void;
  onGenerate: () => void;
  loading: boolean;
  stale: boolean;
  hasResult: boolean;
}

function NumberField({
  id,
  label,
  value,
  onChange,
  onPastePair,
  min,
  max,
  step,
  digits = 2,
  suffix,
  invalidMessage,
}: {
  id: string;
  label?: string;
  value: number;
  onChange: (value: number) => void;
  onPastePair?: (lat: number, lon: number) => void;
  min: number;
  max: number;
  step?: number;
  digits?: number;
  suffix?: string;
  invalidMessage: string;
}) {
  const [text, setText] = useState(() => value.toFixed(digits));
  const [lastValue, setLastValue] = useState(value);
  const [focused, setFocused] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (value !== lastValue) {
    setLastValue(value);
    if (!focused) {
      setText(value.toFixed(digits));
      setErrorMsg(null);
    }
  }

  const validateText = (raw: string): string | null => {
    const parsed = Number.parseFloat(raw);
    if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
      return invalidMessage;
    }
    return null;
  };

  const commit = () => {
    const parsed = Number.parseFloat(text);
    if (Number.isFinite(parsed)) {
      const clamped = clamp(parsed, min, max);
      onChange(clamped);
      setText(clamped.toFixed(digits));
      setErrorMsg(null);
    } else {
      setText(value.toFixed(digits));
      setErrorMsg(null);
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    if (!onPastePair) return;
    const raw = event.clipboardData.getData("text").trim();
    const match = raw.match(
      /^(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)$/,
    );
    if (!match) return;
    const pLat = Number.parseFloat(match[1]);
    const pLon = Number.parseFloat(match[2]);
    if (
      Number.isFinite(pLat) &&
      Number.isFinite(pLon) &&
      pLat >= -90 &&
      pLat <= 90 &&
      pLon >= -180 &&
      pLon <= 180
    ) {
      event.preventDefault();
      onPastePair(roundCoord(pLat), roundCoord(pLon));
      setErrorMsg(null);
    }
  };

  const errorId = `${id}-error`;

  return (
    <div>
      {label ? (
        <label
          htmlFor={id}
          className="block text-xs font-semibold text-slate-700"
        >
          {label}
        </label>
      ) : null}
      <div className={`relative ${label ? "mt-1" : ""}`}>
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={text}
          aria-invalid={errorMsg != null}
          aria-describedby={errorMsg ? errorId : undefined}
          onFocus={() => setFocused(true)}
          onPaste={handlePaste}
          onChange={(event) => {
            const nextText = event.target.value;
            setText(nextText);
            setErrorMsg(validateText(nextText));
          }}
          onBlur={() => {
            setFocused(false);
            commit();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
          className={`w-full rounded-xl border bg-white px-3 py-2 text-sm font-medium tabular-nums text-slate-900 shadow-sm outline-none transition ${
            suffix ? "pr-12" : ""
          } ${
            errorMsg
              ? "border-rose-400 focus:border-rose-500 focus:ring-4 focus:ring-rose-500/15"
              : "border-slate-300 focus:border-emerald-700 focus:ring-4 focus:ring-emerald-700/15"
          }`}
        />
        {suffix ? (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-slate-600">
            {suffix}
          </span>
        ) : null}
      </div>
      {errorMsg ? (
        <p id={errorId} className="mt-1 text-[0.72rem] font-medium text-rose-700">
          {errorMsg}
        </p>
      ) : null}
    </div>
  );
}

function Slider({
  id,
  label,
  value,
  sharePct,
  onChange,
  shareTemplate,
}: {
  id: string;
  label: string;
  value: number;
  sharePct: number;
  onChange: (value: number) => void;
  shareTemplate: string;
}) {
  const percent = Math.round(value * 100);
  return (
    <div>
      <div className="flex items-center justify-between gap-2 text-xs">
        <label htmlFor={id} className="font-semibold text-slate-800">
          {label}
        </label>
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[0.7rem] font-semibold tabular-nums text-emerald-800 ring-1 ring-emerald-200">
          {shareTemplate.replace("{pct}", String(sharePct))}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1.5 w-full"
        style={{ "--fill": `${percent}%` } as CSSProperties}
      />
    </div>
  );
}

const PRESETS = [
  { key: "presetIowa" as const, lat: 41.8, lon: -93.6 },
  { key: "presetHorn" as const, lat: 9.0, lon: 41.0 },
  { key: "presetCape" as const, lat: -33.9, lon: 18.4 },
];

const SCENARIO_SHORT_KEY: Record<string, Parameters<typeof t>[1]> = {
  auto: "scenarioAutoShort",
  flood: "scenarioFloodShort",
  drought: "scenarioDroughtShort",
  normal: "scenarioNormalShort",
  late_flood: "scenarioLateFloodShort",
};

const WEIGHT_PRESETS: {
  key: Parameters<typeof t>[1];
  descKey: Parameters<typeof t>[1];
  icon: LucideIcon;
  weights: Weights;
}[] = [
  {
    key: "presetBalanced",
    descKey: "presetBalancedDesc",
    icon: Scale,
    weights: {
      soil_protection: 0.4,
      salvage_revenue: 0.3,
      water_conservation: 0.3,
    },
  },
  {
    key: "presetSoil",
    descKey: "presetSoilDesc",
    icon: Leaf,
    weights: {
      soil_protection: 0.7,
      salvage_revenue: 0.15,
      water_conservation: 0.15,
    },
  },
  {
    key: "presetRevenue",
    descKey: "presetRevenueDesc",
    icon: TrendingUp,
    weights: {
      soil_protection: 0.2,
      salvage_revenue: 0.65,
      water_conservation: 0.15,
    },
  },
  {
    key: "presetWater",
    descKey: "presetWaterDesc",
    icon: Droplets,
    weights: {
      soil_protection: 0.2,
      salvage_revenue: 0.15,
      water_conservation: 0.65,
    },
  },
];

const YIELD_CHIPS = [1.5, 2.5, 4.0];

const SLIDE_STEPS = [
  { index: 0, labelKey: "slideStep1" as const },
  { index: 1, labelKey: "slideStep2" as const },
  { index: 2, labelKey: "slideStep3" as const },
];

export function ControlsPanel({
  lang,
  demoMode,
  onDemoModeChange,
  scenarios,
  scenario,
  onScenarioChange,
  lat,
  lon,
  date,
  onLatChange,
  onLonChange,
  onCoordsChange,
  onDateChange,
  weights,
  onWeightChange,
  onApplyWeights,
  yieldT,
  onYieldChange,
  onPreset,
  onGenerate,
  loading,
  stale,
  hasResult,
}: ControlsPanelProps) {
  const [slide, setSlide] = useState(0);
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [placeQuery, setPlaceQuery] = useState("");
  const [placeResults, setPlaceResults] = useState<PlaceResult[]>([]);
  const [searchingPlaces, setSearchingPlaces] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [showSliders, setShowSliders] = useState(false);

  const searchBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = placeQuery.trim();
    if (trimmed.length < 2) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearchingPlaces(true);
      searchPlaces(trimmed, controller.signal)
        .then((items) => {
          setPlaceResults(items);
          setSearchOpen(true);
        })
        .finally(() => setSearchingPlaces(false));
    }, 280);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [placeQuery]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        searchBoxRef.current &&
        !searchBoxRef.current.contains(event.target as Node)
      ) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const totalWeight =
    weights.soil_protection +
    weights.salvage_revenue +
    weights.water_conservation;
  const zeroWeights = totalWeight <= 0;
  const dateError = validatePlanningDate(date, !demoMode);
  const invalidDate = dateError !== null;
  const dateErrorMessage =
    dateError === "future"
      ? t(lang, "dateFutureBlocked")
      : dateError === "too_early"
        ? t(lang, "dateTooEarly")
        : dateError === "empty"
          ? t(lang, "invalidDate")
          : null;
  const canSubmit = !loading && !zeroWeights && !invalidDate;

  const shareOf = (w: number) =>
    totalWeight > 0 ? Math.round((w / totalWeight) * 100) : 0;

  const handleUseMyLocation = () => {
    setGeoError(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoError(t(lang, "geolocationUnsupported"));
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        onPreset(
          roundCoord(position.coords.latitude),
          roundCoord(position.coords.longitude),
        );
      },
      () => {
        setLocating(false);
        setGeoError(t(lang, "geolocationDenied"));
      },
      { enableHighAccuracy: false, timeout: 8000 },
    );
  };

  const generateLabel = loading
    ? t(lang, "generating")
    : hasResult && stale
      ? t(lang, "regenerate")
      : t(lang, "generate");

  const isWeightPresetActive = (preset: Weights) =>
    Math.abs(preset.soil_protection - weights.soil_protection) < 0.01 &&
    Math.abs(preset.salvage_revenue - weights.salvage_revenue) < 0.01 &&
    Math.abs(preset.water_conservation - weights.water_conservation) < 0.01;

  const activeGoalLabel = (() => {
    const found = WEIGHT_PRESETS.find((p) => isWeightPresetActive(p.weights));
    return found ? t(lang, found.key) : t(lang, "fineTuneWeights");
  })();

  const twoWeeksAgo = isoWithOffset(-14);
  const lastWeek = isoWithOffset(-7);
  const today = isoWithOffset(0);

  return (
    <aside className="pier-no-print flex h-full flex-col border-b border-slate-200 bg-white lg:border-b-0 lg:border-r">
      {/* Top Progress Bar */}
      <div className="h-1.5 w-full bg-slate-100">
        <div
          className="h-full bg-emerald-700 transition-all duration-300"
          style={{ width: `${((slide + 1) / SLIDE_STEPS.length) * 100}%` }}
        />
      </div>

      {/* Top Action & Stepper Header */}
      <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-2.5 sm:px-5">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[0.7rem] font-semibold ring-1 ${
              demoMode
                ? "bg-slate-100 text-slate-800 ring-slate-200"
                : "bg-emerald-50 text-emerald-800 ring-emerald-200"
            }`}
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${
                demoMode ? "bg-slate-600" : "bg-emerald-700"
              }`}
            />
            {demoMode ? t(lang, "demoBadge") : t(lang, "liveBadge")}
          </span>

          <button
            type="button"
            onClick={onGenerate}
            disabled={!canSubmit}
            aria-busy={loading}
            className="inline-flex items-center gap-1.5 rounded-full bg-emerald-700 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm shadow-emerald-900/15 transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-1 disabled:opacity-55"
          >
            {loading ? (
              <Loader2
                className="h-3.5 w-3.5 animate-spin"
                aria-hidden="true"
              />
            ) : hasResult && stale ? (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <Play className="h-3 w-3 fill-current" aria-hidden="true" />
            )}
            {loading
              ? t(lang, "generating")
              : hasResult && stale
                ? t(lang, "regenerate")
                : t(lang, "quickRunNow")}
          </button>
        </div>

        <div
          className="mt-2.5 flex items-center gap-1.5"
          role="tablist"
          aria-label={t(lang, "controlsTitle")}
        >
          {SLIDE_STEPS.map((step) => {
            const isCurrent = slide === step.index;
            const isPast = slide > step.index;
            return (
              <button
                key={step.index}
                type="button"
                role="tab"
                aria-selected={isCurrent}
                aria-current={isCurrent ? "step" : undefined}
                onClick={() => setSlide(step.index)}
                className={`inline-flex flex-1 items-center justify-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                  isCurrent
                    ? "bg-[#123b5c] text-white shadow-xs"
                    : isPast
                      ? "bg-emerald-100 text-emerald-900 hover:bg-emerald-200"
                      : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100"
                }`}
              >
                <span
                  className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[0.65rem] font-bold ${
                    isCurrent
                      ? "bg-white/20 text-white"
                      : isPast
                        ? "bg-emerald-700 text-white"
                        : "bg-slate-200 text-slate-700"
                  }`}
                >
                  {isPast ? (
                    <Check className="h-2.5 w-2.5" aria-hidden="true" />
                  ) : (
                    step.index + 1
                  )}
                </span>
                <span>{t(lang, step.labelKey)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Slide Content */}
      <div className="pier-scroll flex-1 overflow-y-auto p-4 sm:p-5">
        {slide === 0 ? (
          <div className="space-y-4">
            <div>
              <p className="text-[0.68rem] font-bold uppercase tracking-[0.12em] text-emerald-800">
                {tFormat(lang, "tutorialStep", { n: 1, total: 3 })}
              </p>
              <h2 className="mt-0.5 text-lg font-bold tracking-tight text-slate-900">
                {t(lang, "slide1Title")}
              </h2>
              <p className="mt-0.5 text-xs text-slate-600">
                {t(lang, "slide1Subtitle")}
              </p>
            </div>

            <div
              className="grid grid-cols-2 rounded-xl bg-slate-100 p-1"
              role="group"
              aria-label={t(lang, "dataSourceMode")}
            >
              <button
                type="button"
                onClick={() => onDemoModeChange(false)}
                aria-pressed={!demoMode}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                  !demoMode
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Satellite
                  className="h-3.5 w-3.5 text-emerald-700"
                  aria-hidden="true"
                />
                {t(lang, "liveMode")}
              </button>
              <button
                type="button"
                onClick={() => onDemoModeChange(true)}
                aria-pressed={demoMode}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                  demoMode
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Sparkles
                  className="h-3.5 w-3.5 text-amber-700"
                  aria-hidden="true"
                />
                {t(lang, "demoMode")}
              </button>
            </div>

            {demoMode ? (
              <div
                className="space-y-1.5"
                role="radiogroup"
                aria-label={t(lang, "scenario")}
              >
                {scenarios.map((item) => {
                  const active = scenario === item.id;
                  const shortKey = SCENARIO_SHORT_KEY[item.id];
                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      onClick={() => onScenarioChange(item.id)}
                      className={`flex w-full items-start justify-between gap-2 rounded-xl border px-3.5 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                        active
                          ? "border-emerald-600 bg-emerald-50/75 text-slate-900 shadow-xs"
                          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="text-xs font-bold">
                          {t(lang, item.labelKey as Parameters<typeof t>[1])}
                        </p>
                        {shortKey ? (
                          <p className="mt-0.5 text-[0.72rem] text-slate-600">
                            {t(lang, shortKey)}
                          </p>
                        ) : null}
                      </div>
                      {active ? (
                        <Check
                          className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700"
                          aria-hidden="true"
                        />
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-3.5">
                {/* Place Search */}
                <div ref={searchBoxRef} className="relative">
                  <label
                    htmlFor="place-search"
                    className="block text-xs font-semibold text-slate-700"
                  >
                    {t(lang, "searchPlaceLabel")}
                  </label>
                  <div className="relative mt-1">
                    <Search
                      className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                      aria-hidden="true"
                    />
                    <input
                      id="place-search"
                      type="search"
                      value={placeQuery}
                      placeholder={t(lang, "searchPlacePlaceholder")}
                      onFocus={() => {
                        if (placeResults.length > 0) setSearchOpen(true);
                      }}
                      onChange={(e) => {
                        const next = e.target.value;
                        setPlaceQuery(next);
                        if (next.trim().length < 2) {
                          setPlaceResults([]);
                          setSearchingPlaces(false);
                          setSearchOpen(false);
                        }
                      }}
                      className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-8 pr-8 text-xs font-medium text-slate-900 shadow-sm outline-none transition placeholder:text-slate-500 focus:border-emerald-700 focus:ring-4 focus:ring-emerald-700/15"
                    />
                    {searchingPlaces ? (
                      <Loader2
                        className="absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-emerald-700"
                        aria-hidden="true"
                      />
                    ) : null}
                  </div>

                  {searchOpen && placeQuery.trim().length >= 2 ? (
                    <div className="absolute left-0 right-0 z-30 mt-1 max-h-52 overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
                      {placeResults.length === 0 && !searchingPlaces ? (
                        <p className="px-3 py-2 text-xs text-slate-600">
                          {t(lang, "noPlacesFound")}
                        </p>
                      ) : (
                        placeResults.map((place, idx) => (
                          <button
                            key={`${place.label}-${idx}`}
                            type="button"
                            onClick={() => {
                              onPreset(
                                roundCoord(place.lat),
                                roundCoord(place.lon),
                              );
                              setPlaceQuery(place.label);
                              setSearchOpen(false);
                            }}
                            className="flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
                          >
                            <MapPin
                              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-700"
                              aria-hidden="true"
                            />
                            <span className="min-w-0">
                              <span className="block font-semibold text-slate-900">
                                {place.label}
                              </span>
                              {place.region ? (
                                <span className="block text-[0.68rem] text-slate-600">
                                  {place.region}
                                </span>
                              ) : null}
                            </span>
                          </button>
                        ))
                      )}
                    </div>
                  ) : null}
                </div>

                <div>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-slate-700">
                      {t(lang, "quickLocations")}
                    </p>
                    <button
                      type="button"
                      onClick={handleUseMyLocation}
                      disabled={locating}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2.5 py-1 text-[0.7rem] font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-60"
                    >
                      {locating ? (
                        <Loader2
                          className="h-3 w-3 animate-spin"
                          aria-hidden="true"
                        />
                      ) : (
                        <LocateFixed
                          className="h-3 w-3 text-emerald-700"
                          aria-hidden="true"
                        />
                      )}
                      {locating
                        ? t(lang, "locating")
                        : t(lang, "useMyLocation")}
                    </button>
                  </div>
                  {geoError ? (
                    <p className="mt-1.5 rounded-lg bg-rose-50 px-2.5 py-1.5 text-[0.72rem] font-medium text-rose-800">
                      {geoError}
                    </p>
                  ) : null}
                  <div className="mt-1.5 grid grid-cols-3 gap-2">
                    {PRESETS.map((preset) => {
                      const isSelected =
                        Math.abs(lat - preset.lat) < 0.05 &&
                        Math.abs(lon - preset.lon) < 0.05;
                      return (
                        <button
                          key={preset.key}
                          type="button"
                          onClick={() => onPreset(preset.lat, preset.lon)}
                          className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-[0.7rem] font-semibold leading-tight transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                            isSelected
                              ? "border-emerald-600 bg-emerald-50 text-emerald-900"
                              : "border-slate-200 bg-white text-slate-700 hover:border-emerald-400 hover:bg-emerald-50/50"
                          }`}
                        >
                          <MapPin
                            className="h-3.5 w-3.5 text-emerald-700"
                            aria-hidden="true"
                          />
                          {t(lang, preset.key)}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <div className="grid grid-cols-2 gap-3">
                    <NumberField
                      id="latitude"
                      label={t(lang, "latitude")}
                      value={lat}
                      onChange={onLatChange}
                      onPastePair={onCoordsChange}
                      min={-90}
                      max={90}
                      step={0.0001}
                      digits={4}
                      invalidMessage={t(lang, "invalidLatitude")}
                    />
                    <NumberField
                      id="longitude"
                      label={t(lang, "longitude")}
                      value={lon}
                      onChange={onLonChange}
                      min={-180}
                      max={180}
                      step={0.0001}
                      digits={4}
                      invalidMessage={t(lang, "invalidLongitude")}
                    />
                  </div>
                  <p className="mt-1 text-[0.68rem] text-slate-600">
                    {t(lang, "coordsPasteHint")}
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {slide === 1 ? (
          <div className="space-y-4">
            <div>
              <p className="text-[0.68rem] font-bold uppercase tracking-[0.12em] text-emerald-800">
                {tFormat(lang, "tutorialStep", { n: 2, total: 3 })}
              </p>
              <h2 className="mt-0.5 text-lg font-bold tracking-tight text-slate-900">
                {t(lang, "slide2Title")}
              </h2>
              <p className="mt-0.5 text-xs text-slate-600">
                {t(lang, "slide2Subtitle")}
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3.5 text-xs">
              <p className="font-semibold text-slate-600">
                {t(lang, "selectedLocation")}
              </p>
              <p className="mt-0.5 font-mono text-sm font-bold tabular-nums text-slate-900">
                {lat.toFixed(4)}, {lon.toFixed(4)}
              </p>
            </div>

            {demoMode ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50/75 p-4 text-xs text-amber-950 space-y-3">
                <div className="flex items-start gap-2.5">
                  <CalendarDays
                    className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="font-bold">
                      {formatDate(date, lang)}
                    </p>
                    <p className="mt-1 leading-relaxed text-amber-900">
                      {tFormat(lang, "demoDateLockedNote", {
                        date: formatDate(date, lang),
                      })}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onDemoModeChange(false)}
                  className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 ring-1 ring-amber-300 transition hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-700"
                >
                  <Satellite className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(lang, "switchToCustomDate")}
                </button>
              </div>
            ) : null}

            <div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label
                  htmlFor="current-date"
                  className="block text-xs font-semibold text-slate-700"
                >
                  {t(lang, "currentDate")}
                </label>
                {!demoMode ? (
                  <div className="flex items-center gap-1">
                    {[
                      { label: t(lang, "dateTwoWeeksAgo"), value: twoWeeksAgo },
                      { label: t(lang, "dateLastWeek"), value: lastWeek },
                      { label: t(lang, "dateToday"), value: today },
                    ].map((chip) => (
                      <button
                        key={chip.label}
                        type="button"
                        onClick={() => onDateChange(chip.value)}
                        className={`rounded-full px-2.5 py-1 text-[0.7rem] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                          date === chip.value
                            ? "bg-emerald-700 text-white"
                            : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                        }`}
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="relative mt-1.5">
                <CalendarDays
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                  aria-hidden="true"
                />
                <input
                  id="current-date"
                  type="date"
                  value={date}
                  min={demoMode ? undefined : MIN_NASA_DATE}
                  max={today}
                  aria-invalid={invalidDate}
                  onChange={(event) => onDateChange(event.target.value)}
                  className={`w-full rounded-xl border bg-white py-2.5 pl-9 pr-3 text-sm font-medium tabular-nums text-slate-900 shadow-sm outline-none transition ${
                    invalidDate
                      ? "border-rose-400 focus:border-rose-500 focus:ring-4 focus:ring-rose-500/15"
                      : "border-slate-300 focus:border-emerald-700 focus:ring-4 focus:ring-emerald-700/15"
                  }`}
                />
              </div>
              {dateErrorMessage ? (
                <p
                  role="alert"
                  className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-rose-50 px-2.5 py-1.5 text-[0.72rem] font-medium text-rose-800"
                >
                  <AlertCircle
                    className="mt-0.5 h-3.5 w-3.5 shrink-0"
                    aria-hidden="true"
                  />
                  <span>{dateErrorMessage}</span>
                </p>
              ) : null}
              <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                {demoMode ? t(lang, "dateHintDemo") : t(lang, "dateHintLive")}
              </p>
            </div>
          </div>
        ) : null}

        {slide === 2 ? (
          <div className="space-y-4">
            <div>
              <p className="text-[0.68rem] font-bold uppercase tracking-[0.12em] text-emerald-800">
                {tFormat(lang, "tutorialStep", { n: 3, total: 3 })}
              </p>
              <h2 className="mt-0.5 text-lg font-bold tracking-tight text-slate-900">
                {t(lang, "slide3Title")}
              </h2>
              <p className="mt-0.5 text-xs text-slate-600">
                {t(lang, "slide3Subtitle")}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {WEIGHT_PRESETS.map((preset) => {
                const active = isWeightPresetActive(preset.weights);
                const Icon = preset.icon;
                return (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => onApplyWeights(preset.weights)}
                    aria-pressed={active}
                    className={`flex items-start gap-2.5 rounded-xl border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                      active
                        ? "border-emerald-700 bg-emerald-50/80 text-slate-900 shadow-xs"
                        : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <span
                      className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                        active
                          ? "bg-emerald-700 text-white"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-bold">{t(lang, preset.key)}</p>
                      <p className="mt-0.5 text-[0.68rem] leading-snug text-slate-600">
                        {t(lang, preset.descKey)}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>

            <div>
              <button
                type="button"
                onClick={() => setShowSliders((v) => !v)}
                aria-expanded={showSliders}
                className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
              >
                <span>{t(lang, "fineTuneWeights")}</span>
                <span className="inline-flex items-center gap-1.5 text-[0.7rem] tabular-nums text-slate-600">
                  {shareOf(weights.soil_protection)}/
                  {shareOf(weights.salvage_revenue)}/
                  {shareOf(weights.water_conservation)}
                  {showSliders ? (
                    <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                </span>
              </button>

              {showSliders ? (
                <div className="mt-2.5 space-y-3 rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                  <Slider
                    id="soil-protection"
                    label={t(lang, "soilProtection")}
                    value={weights.soil_protection}
                    sharePct={shareOf(weights.soil_protection)}
                    shareTemplate={t(lang, "shareLabel")}
                    onChange={(value) =>
                      onWeightChange("soil_protection", value)
                    }
                  />
                  <Slider
                    id="salvage-revenue"
                    label={t(lang, "salvageRevenue")}
                    value={weights.salvage_revenue}
                    sharePct={shareOf(weights.salvage_revenue)}
                    shareTemplate={t(lang, "shareLabel")}
                    onChange={(value) =>
                      onWeightChange("salvage_revenue", value)
                    }
                  />
                  <Slider
                    id="water-conservation"
                    label={t(lang, "waterConservation")}
                    value={weights.water_conservation}
                    sharePct={shareOf(weights.water_conservation)}
                    shareTemplate={t(lang, "shareLabel")}
                    onChange={(value) =>
                      onWeightChange("water_conservation", value)
                    }
                  />
                </div>
              ) : null}
            </div>

            {zeroWeights ? (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-800"
              >
                <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{t(lang, "weightsZeroError")}</span>
              </div>
            ) : null}

            <div className="border-t border-slate-100 pt-3">
              <div className="flex items-center justify-between gap-2">
                <label
                  htmlFor="expected-yield"
                  className="text-xs font-semibold text-slate-700"
                >
                  {t(lang, "expectedYield")}
                </label>
                <div className="flex items-center gap-1">
                  {YIELD_CHIPS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => onYieldChange(val)}
                      className={`rounded-full px-2 py-0.5 text-[0.68rem] font-semibold tabular-nums transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${
                        Math.abs(yieldT - val) < 0.05
                          ? "bg-emerald-700 text-white"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {val.toFixed(1)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-1.5">
                <NumberField
                  id="expected-yield"
                  value={yieldT}
                  onChange={onYieldChange}
                  min={0.1}
                  max={50}
                  step={0.1}
                  digits={1}
                  suffix="t/ha"
                  invalidMessage={t(lang, "invalidYield")}
                />
              </div>
              <p className="mt-1 text-[0.7rem] text-slate-600">
                {t(lang, "yieldHint")}
              </p>
            </div>

            {/* Compact Review Strip */}
            <dl className="grid grid-cols-2 gap-2 rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 text-[0.72rem]">
              <div>
                <dt className="text-slate-600">{t(lang, "summaryLocation")}</dt>
                <dd className="font-mono font-semibold tabular-nums text-slate-900">
                  {lat.toFixed(2)}, {lon.toFixed(2)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-600">{t(lang, "summaryDate")}</dt>
                <dd className="font-semibold tabular-nums text-slate-900">
                  {formatDate(date, lang)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-600">{t(lang, "summaryGoal")}</dt>
                <dd className="font-semibold text-slate-900">
                  {activeGoalLabel}
                </dd>
              </div>
              <div>
                <dt className="text-slate-600">{t(lang, "summaryYield")}</dt>
                <dd className="font-semibold tabular-nums text-slate-900">
                  {yieldT.toFixed(1)} t/ha
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
      </div>

      {/* Bottom Slideshow Navigation Bar */}
      <div className="border-t border-slate-200 bg-slate-50/80 px-4 py-3 sm:px-5">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => setSlide((s) => Math.max(0, s - 1))}
            disabled={slide === 0}
            className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            {t(lang, "back")}
          </button>

          <div className="flex items-center gap-1.5" aria-hidden="true">
            {SLIDE_STEPS.map((s) => (
              <span
                key={s.index}
                className={`h-1.5 rounded-full transition-all ${
                  slide === s.index
                    ? "w-6 bg-emerald-700"
                    : "w-1.5 bg-slate-300"
                }`}
              />
            ))}
          </div>

          {slide < SLIDE_STEPS.length - 1 ? (
            <button
              type="button"
              onClick={() =>
                setSlide((s) => Math.min(SLIDE_STEPS.length - 1, s + 1))
              }
              className="inline-flex items-center gap-1 rounded-full bg-emerald-700 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
            >
              {t(lang, "next")}
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onGenerate}
              disabled={!canSubmit}
              aria-busy={loading}
              className="inline-flex items-center gap-1.5 rounded-full bg-emerald-700 px-5 py-2 text-xs font-semibold text-white shadow-md shadow-emerald-900/15 transition hover:bg-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-1 disabled:opacity-60"
            >
              {loading ? (
                <Loader2
                  className="h-3.5 w-3.5 animate-spin"
                  aria-hidden="true"
                />
              ) : hasResult && stale ? (
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
              )}
              {generateLabel}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
