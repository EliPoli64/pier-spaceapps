import { useState } from "react";
import type { CSSProperties } from "react";
import { CalendarDays, Loader2, MapPin, Play, SlidersHorizontal } from "lucide-react";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Scenario, Weights } from "../lib/types";
import { clamp } from "../lib/format";

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
  onDateChange: (value: string) => void;
  weights: Weights;
  onWeightChange: (key: keyof Weights, value: number) => void;
  yieldT: number;
  onYieldChange: (value: number) => void;
  onPreset: (lat: number, lon: number) => void;
  onGenerate: () => void;
  loading: boolean;
}

function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
        checked ? "bg-emerald-600" : "bg-slate-300"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step,
  digits = 2,
  suffix,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  digits?: number;
  suffix?: string;
}) {
  const [text, setText] = useState(() => value.toFixed(digits));
  const [lastValue, setLastValue] = useState(value);
  const [focused, setFocused] = useState(false);

  // Sync the local text when the parent changes the value from outside the
  // input (for example, a map click) without overwriting a focused edit.
  if (value !== lastValue) {
    setLastValue(value);
    if (!focused) setText(value.toFixed(digits));
  }

  const commit = () => {
    const parsed = Number.parseFloat(text);
    if (Number.isFinite(parsed)) {
      const next = clamp(parsed, min, max);
      onChange(next);
      setText(next.toFixed(digits));
    } else {
      setText(value.toFixed(digits));
    }
  };

  return (
    <div>
      <label
        htmlFor={id}
        className="block text-xs font-medium text-slate-500"
      >
        {label}
      </label>
      <div className="relative mt-1">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={text}
          onFocus={() => setFocused(true)}
          onChange={(event) => setText(event.target.value)}
          onBlur={() => {
            setFocused(false);
            commit();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 shadow-sm outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
        />
        {suffix ? (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
            {suffix}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function Slider({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const percent = Math.round(value * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <label htmlFor={id} className="font-medium text-slate-700">
          {label}
        </label>
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
          {percent}%
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
        className="mt-2 w-full cursor-pointer"
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
  onDateChange,
  weights,
  onWeightChange,
  yieldT,
  onYieldChange,
  onPreset,
  onGenerate,
  loading,
}: ControlsPanelProps) {
  const generateLabel = loading ? t(lang, "generating") : t(lang, "generate");

  return (
    <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-900">
            {t(lang, "controlsTitle")}
          </h2>
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

        <div className="mt-4 flex items-start justify-between gap-3 rounded-2xl bg-slate-50 p-3">
          <div>
            <p className="text-sm font-semibold text-slate-800">
              {t(lang, "demoMode")}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
              {t(lang, "demoModeHint")}
            </p>
          </div>
          <Switch
            checked={demoMode}
            onChange={onDemoModeChange}
            label={t(lang, "demoMode")}
          />
        </div>

        {demoMode ? (
          <div className="mt-4">
            <label
              htmlFor="scenario"
              className="block text-xs font-medium text-slate-500"
            >
              {t(lang, "scenario")}
            </label>
            <select
              id="scenario"
              value={scenario}
              onChange={(event) => onScenarioChange(event.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 shadow-sm outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
            >
              {scenarios.map((item) => (
                <option key={item.id} value={item.id}>
                  {t(lang, item.labelKey as Parameters<typeof t>[1])}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div className="mt-5">
          <p className="text-xs font-medium text-slate-500">
            {t(lang, "quickLocations")}
          </p>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => onPreset(preset.lat, preset.lon)}
                className="flex flex-col items-center gap-1 rounded-xl border border-slate-200 px-2 py-2.5 text-[0.68rem] font-medium leading-tight text-slate-600 transition hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-800"
              >
                <MapPin className="h-4 w-4" />
                {t(lang, preset.key)}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <NumberField
            id="latitude"
            label={t(lang, "latitude")}
            value={lat}
            onChange={onLatChange}
            min={-90}
            max={90}
            step={0.0001}
            digits={4}
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
          />
        </div>

        <div className="mt-3">
          <label
            htmlFor="current-date"
            className="block text-xs font-medium text-slate-500"
          >
            {t(lang, "currentDate")}
          </label>
          <div className="relative mt-1">
            <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="current-date"
              type="date"
              value={date}
              onChange={(event) => onDateChange(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
            />
          </div>
          <p className="mt-1.5 text-[0.7rem] leading-relaxed text-slate-500">
            {demoMode ? t(lang, "dateHintDemo") : t(lang, "dateHintLive")}
          </p>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-emerald-600" />
          <h2 className="text-sm font-semibold text-slate-900">
            {t(lang, "priorities")}
          </h2>
        </div>

        <div className="mt-4 space-y-4">
          <Slider
            id="soil-protection"
            label={t(lang, "soilProtection")}
            value={weights.soil_protection}
            onChange={(value) => onWeightChange("soil_protection", value)}
          />
          <Slider
            id="salvage-revenue"
            label={t(lang, "salvageRevenue")}
            value={weights.salvage_revenue}
            onChange={(value) => onWeightChange("salvage_revenue", value)}
          />
          <Slider
            id="water-conservation"
            label={t(lang, "waterConservation")}
            value={weights.water_conservation}
            onChange={(value) => onWeightChange("water_conservation", value)}
          />
        </div>

        <p className="mt-3 text-[0.7rem] leading-relaxed text-slate-500">
          {t(lang, "weightsHint")}
        </p>

        <div className="mt-4 border-t border-slate-100 pt-4">
          <NumberField
            id="expected-yield"
            label={t(lang, "expectedYield")}
            value={yieldT}
            onChange={onYieldChange}
            min={0.1}
            max={50}
            step={0.1}
            digits={1}
            suffix="t/ha"
          />
        </div>
      </section>

      <button
        type="button"
        onClick={onGenerate}
        disabled={loading}
        className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-5 py-3.5 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20 transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4 fill-current" />
        )}
        {generateLabel}
      </button>
    </aside>
  );
}
