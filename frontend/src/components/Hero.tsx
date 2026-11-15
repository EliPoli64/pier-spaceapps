import type { ReactNode } from "react";
import { GraduationCap, Satellite, Sprout, WifiOff } from "lucide-react";
import { LANGS, t } from "../lib/i18n";
import type { Lang } from "../lib/i18n";

interface HeroProps {
  lang: Lang;
  onLanguageChange: (lang: Lang) => void;
  onOpenTutorial: () => void;
}

function Chip({
  icon,
  children,
}: {
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium text-emerald-50">
      {icon}
      {children}
    </span>
  );
}

export function Hero({ lang, onLanguageChange, onOpenTutorial }: HeroProps) {
  return (
    <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#0b1f3a] via-[#123b5c] to-[#1f6b4a] px-6 py-7 text-white shadow-2xl shadow-slate-900/20 sm:px-8 sm:py-9">
      <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-emerald-300/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-28 left-1/3 h-64 w-64 rounded-full bg-sky-300/10 blur-3xl" />

      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-emerald-200">
            {t(lang, "heroBadge")}
          </p>

          <div className="mt-2 flex items-center gap-3">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 ring-1 ring-white/20">
              <svg
                viewBox="0 0 24 24"
                className="h-6 w-6 text-emerald-200"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 3 20 6v5c0 5.4-3.4 9.4-8 11-4.6-1.6-8-5.6-8-11V6l8-3Z" />
                <path d="M9 13c2.8-1 5-3 6.2-5.5.8 3.4-.7 6.6-4 7.9" />
              </svg>
            </span>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                {t(lang, "appName")}
              </h1>
              <p className="text-sm font-medium text-slate-200">
                {t(lang, "appSubtitle")}
              </p>
            </div>
          </div>

          <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-200">
            {t(lang, "heroTagline")}
          </p>

          <div className="mt-5 flex flex-wrap gap-2">
            <Chip icon={<Satellite className="h-3.5 w-3.5" />}>
              {t(lang, "chipPower")}
            </Chip>
            <Chip icon={<Sprout className="h-3.5 w-3.5" />}>
              {t(lang, "chipCrops")}
            </Chip>
            <Chip icon={<WifiOff className="h-3.5 w-3.5" />}>
              {t(lang, "chipOffline")}
            </Chip>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div
            className="inline-flex rounded-full border border-white/20 bg-white/10 p-1"
            role="group"
            aria-label={t(lang, "language")}
          >
            {LANGS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onLanguageChange(option.value)}
                aria-pressed={lang === option.value}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                  lang === option.value
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-200 hover:bg-white/10 hover:text-white"
                }`}
              >
                {option.value.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={onOpenTutorial}
            className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs font-semibold text-white transition hover:bg-white/20"
          >
            <GraduationCap className="h-4 w-4" />
            {t(lang, "howItWorks")}
          </button>
        </div>
      </div>
    </header>
  );
}
