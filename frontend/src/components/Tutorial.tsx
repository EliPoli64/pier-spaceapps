import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import {
  ArrowRight,
  ChevronLeft,
  Compass,
  GraduationCap,
  MapPin,
  SlidersHorizontal,
  Sparkles,
  Sprout,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { t, tFormat } from "../lib/i18n";
import type { Lang } from "../lib/i18n";

interface Slide {
  icon: LucideIcon;
  titleKey:
    | "tut1Title"
    | "tut2Title"
    | "tut3Title"
    | "tut4Title"
    | "tut5Title";
  bodyKey:
    | "tut1Body"
    | "tut2Body"
    | "tut3Body"
    | "tut4Body"
    | "tut5Body";
  bullets: Parameters<typeof t>[1][];
}

const SLIDES: Slide[] = [
  {
    icon: Compass,
    titleKey: "tut1Title",
    bodyKey: "tut1Body",
    bullets: ["tut1Bullet1", "tut1Bullet2", "tut1Bullet3"],
  },
  {
    icon: MapPin,
    titleKey: "tut2Title",
    bodyKey: "tut2Body",
    bullets: ["tut2Bullet1", "tut2Bullet2", "tut2Bullet3"],
  },
  {
    icon: Sparkles,
    titleKey: "tut3Title",
    bodyKey: "tut3Body",
    bullets: ["tut3Bullet1", "tut3Bullet2", "tut3Bullet3"],
  },
  {
    icon: SlidersHorizontal,
    titleKey: "tut4Title",
    bodyKey: "tut4Body",
    bullets: ["tut4Bullet1", "tut4Bullet2", "tut4Bullet3"],
  },
  {
    icon: Sprout,
    titleKey: "tut5Title",
    bodyKey: "tut5Body",
    bullets: ["tut5Bullet1", "tut5Bullet2", "tut5Bullet3"],
  },
];

interface TutorialProps {
  open: boolean;
  lang: Lang;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLButtonElement | null>;
}

export function Tutorial({
  open,
  lang,
  onClose,
  returnFocusRef,
}: TutorialProps) {
  const [index, setIndex] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleClose = () => {
      onClose();
      requestAnimationFrame(() => returnFocusRef?.current?.focus());
    };

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleClose();
        return;
      }
      if (event.key === "ArrowRight") {
        setIndex((current) => Math.min(current + 1, SLIDES.length - 1));
        return;
      }
      if (event.key === "ArrowLeft") {
        setIndex((current) => Math.max(current - 1, 0));
        return;
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, returnFocusRef]);

  if (!open) return null;

  const closeAndReturnFocus = () => {
    onClose();
    requestAnimationFrame(() => returnFocusRef?.current?.focus());
  };

  const slide = SLIDES[index];
  const Icon = slide.icon;
  const isLast = index === SLIDES.length - 1;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tutorial-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) closeAndReturnFocus();
      }}
    >
      <div
        ref={dialogRef}
        className="pier-modal-in pier-scroll relative max-h-[90dvh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl"
      >
        <div className="h-1 w-full bg-slate-100">
          <div
            className="h-full rounded-r-full bg-emerald-700 transition-all duration-300 ease-out"
            style={{ width: `${((index + 1) / SLIDES.length) * 100}%` }}
          />
        </div>

        <button
          type="button"
          onClick={closeAndReturnFocus}
          className="absolute right-4 top-5 inline-flex h-9 w-9 items-center justify-center rounded-full text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
          aria-label={t(lang, "close")}
        >
          <X className="h-4.5 w-4.5 stroke-[1.75]" aria-hidden="true" />
        </button>

        <div className="px-5 pb-5 pt-6 sm:px-9 sm:pb-8 sm:pt-7">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            <GraduationCap
              className="h-4 w-4 stroke-[1.75] text-emerald-700"
              aria-hidden="true"
            />
            {t(lang, "tutorialTitle")}
          </div>

          <div key={index} className="pier-slide-in">
            <div className="mt-5 flex items-start gap-3.5 sm:gap-4">
              <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-emerald-700 ring-1 ring-slate-200/80">
                <Icon className="h-5 w-5 stroke-[1.75]" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-500">
                  {tFormat(lang, "tutorialStep", {
                    n: index + 1,
                    total: SLIDES.length,
                  })}
                </p>
                <h2
                  id="tutorial-title"
                  className="mt-1 text-xl font-bold tracking-tight text-slate-900 sm:text-2xl"
                >
                  {t(lang, slide.titleKey)}
                </h2>
              </div>
            </div>

            <p className="mt-4 text-sm leading-relaxed text-slate-700">
              {t(lang, slide.bodyKey)}
            </p>

            <ul className="mt-4 space-y-2">
              {slide.bullets.map((key) => (
                <li
                  key={key}
                  className="flex items-start gap-2.5 text-sm text-slate-800"
                >
                  <span
                    aria-hidden="true"
                    className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-700"
                  />
                  {t(lang, key)}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            {SLIDES.map((item, dotIndex) => (
              <button
                key={item.titleKey}
                type="button"
                onClick={() => setIndex(dotIndex)}
                aria-label={tFormat(lang, "tutorialStep", {
                  n: dotIndex + 1,
                  total: SLIDES.length,
                })}
                aria-current={dotIndex === index ? "step" : undefined}
                className={`h-2 rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2 ${
                  dotIndex === index
                    ? "w-8 bg-emerald-700"
                    : "w-2.5 bg-slate-300 hover:bg-slate-400"
                }`}
              />
            ))}
          </div>

          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              onClick={closeAndReturnFocus}
              className="rounded-full px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
            >
              {t(lang, "skipTutorial")}
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIndex((current) => Math.max(current - 1, 0))}
                disabled={index === 0}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4 stroke-[1.75]" aria-hidden="true" />
                {t(lang, "back")}
              </button>

              <button
                type="button"
                autoFocus
                onClick={() => {
                  if (isLast) {
                    closeAndReturnFocus();
                    return;
                  }
                  setIndex((current) =>
                    Math.min(current + 1, SLIDES.length - 1),
                  );
                }}
                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-700 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-800 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2"
              >
                {isLast ? t(lang, "startPlanning") : t(lang, "next")}
                <ArrowRight className="h-4 w-4 stroke-[1.75]" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
