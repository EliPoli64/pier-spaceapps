import type { RefObject } from "react";
import { GraduationCap, Satellite } from "lucide-react";
import { LANGS, t } from "../lib/i18n";
import type { Lang } from "../lib/i18n";

interface HeroProps {
  lang: Lang;
  onLanguageChange: (lang: Lang) => void;
  onOpenTutorial: () => void;
  tutorialTriggerRef?: RefObject<HTMLButtonElement | null>;
}

export function Hero({
  lang,
  onLanguageChange,
  onOpenTutorial,
  tutorialTriggerRef,
}: HeroProps) {
  return (
    <header className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-[#0b1f3a] via-[#10334f] to-[#14532d] px-4 py-3 text-white shadow-lg shadow-slate-900/15 sm:px-6 sm:py-3.5">
      <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-emerald-300/15 blur-3xl" />

      <div className="relative flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3 sm:gap-4 min-w-0">
          <img
            src="/pier-logo.svg"
            alt="PiER"
            className="h-12 w-auto shrink-0 sm:h-14"
          />

          <div className="min-w-0 border-l border-white/15 pl-3 sm:pl-4">
            <h1 className="sr-only">{t(lang, "appName")}</h1>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-white sm:text-base">
                {t(lang, "appSubtitle")}
              </p>
              <span className="hidden md:inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 text-[0.68rem] font-medium text-emerald-100">
                <Satellite className="h-3 w-3" aria-hidden="true" />
                {t(lang, "chipPower")}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-200 sm:text-[0.8rem]">
              {t(lang, "heroTagline")}
            </p>
          </div>
        </div>

        <div className="pier-no-print flex shrink-0 flex-wrap items-center gap-2">
          <div
            className="inline-flex rounded-full border border-white/20 bg-white/10 p-0.5"
            role="group"
            aria-label={t(lang, "language")}
          >
            {LANGS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onLanguageChange(option.value)}
                aria-pressed={lang === option.value}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 ${
                  lang === option.value
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-100 hover:bg-white/15"
                }`}
              >
                {option.value.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            ref={tutorialTriggerRef}
            type="button"
            onClick={onOpenTutorial}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/10 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
          >
            <GraduationCap className="h-4 w-4" aria-hidden="true" />
            {t(lang, "howItWorks")}
          </button>
        </div>
      </div>
    </header>
  );
}
