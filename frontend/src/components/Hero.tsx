import type { RefObject } from "react";
import { GraduationCap, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { LANGS, t } from "../lib/i18n";
import type { Lang } from "../lib/i18n";

interface HeroProps {
  lang: Lang;
  onLanguageChange: (lang: Lang) => void;
  onOpenTutorial: () => void;
  tutorialTriggerRef?: RefObject<HTMLButtonElement | null>;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function Hero({
  lang,
  onLanguageChange,
  onOpenTutorial,
  tutorialTriggerRef,
  sidebarOpen,
  onToggleSidebar,
}: HeroProps) {
  return (
    <header className="pier-no-print z-30 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-900/15 bg-gradient-to-r from-[#0b1f3a] via-[#10334f] to-[#14532d] px-3 text-white sm:px-4">
      <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-expanded={sidebarOpen}
          aria-label={sidebarOpen ? t(lang, "hideSidebar") : t(lang, "showSidebar")}
          title={sidebarOpen ? t(lang, "hideSidebar") : t(lang, "showSidebar")}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-100 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
        >
          {sidebarOpen ? (
            <PanelLeftClose className="h-4.5 w-4.5" aria-hidden="true" />
          ) : (
            <PanelLeftOpen className="h-4.5 w-4.5" aria-hidden="true" />
          )}
        </button>

        <img
          src="/pier-logo.svg"
          alt="PiER"
          className="h-8 w-auto shrink-0 sm:h-9"
        />

        <h1 className="sr-only">{t(lang, "appName")}</h1>
        <span className="hidden truncate border-l border-white/20 pl-3 text-xs font-medium text-emerald-100/90 md:inline">
          {t(lang, "appSubtitle")}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-2">
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
              className={`rounded-full px-2.5 py-1 text-[0.7rem] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 ${
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
          className="inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
        >
          <GraduationCap className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">{t(lang, "howItWorks")}</span>
        </button>
      </div>
    </header>
  );
}
