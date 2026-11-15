import { useEffect, useState } from "react";
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
  accent: string;
}

const SLIDES: Slide[] = [
  {
    icon: Compass,
    titleKey: "tut1Title",
    bodyKey: "tut1Body",
    bullets: ["tut1Bullet1", "tut1Bullet2", "tut1Bullet3"],
    accent: "from-emerald-500 to-teal-600",
  },
  {
    icon: MapPin,
    titleKey: "tut2Title",
    bodyKey: "tut2Body",
    bullets: ["tut2Bullet1", "tut2Bullet2", "tut2Bullet3"],
    accent: "from-sky-500 to-blue-600",
  },
  {
    icon: Sparkles,
    titleKey: "tut3Title",
    bodyKey: "tut3Body",
    bullets: ["tut3Bullet1", "tut3Bullet2", "tut3Bullet3"],
    accent: "from-amber-500 to-orange-600",
  },
  {
    icon: SlidersHorizontal,
    titleKey: "tut4Title",
    bodyKey: "tut4Body",
    bullets: ["tut4Bullet1", "tut4Bullet2", "tut4Bullet3"],
    accent: "from-violet-500 to-purple-600",
  },
  {
    icon: Sprout,
    titleKey: "tut5Title",
    bodyKey: "tut5Body",
    bullets: ["tut5Bullet1", "tut5Bullet2", "tut5Bullet3"],
    accent: "from-emerald-500 to-green-700",
  },
];

interface TutorialProps {
  open: boolean;
  lang: Lang;
  onClose: () => void;
}

export function Tutorial({ open, lang, onClose }: TutorialProps) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") {
        setIndex((current) => Math.min(current + 1, SLIDES.length - 1));
      }
      if (event.key === "ArrowLeft") {
        setIndex((current) => Math.max(current - 1, 0));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const slide = SLIDES[index];
  const Icon = slide.icon;
  const isLast = index === SLIDES.length - 1;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tutorial-title"
    >
      <div className="relative w-full max-w-2xl overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="h-1.5 w-full bg-slate-100">
          <div
            className="h-full rounded-r-full bg-gradient-to-r from-emerald-500 to-teal-600 transition-all duration-300"
            style={{ width: `${((index + 1) / SLIDES.length) * 100}%` }}
          />
        </div>

        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-5 inline-flex h-9 w-9 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          aria-label={t(lang, "close")}
        >
          <X className="h-5 w-5" />
        </button>

        <div className="px-6 pb-6 pt-7 sm:px-9 sm:pb-8">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
            <GraduationCap className="h-4 w-4 text-emerald-600" />
            {t(lang, "tutorialTitle")}
          </div>

          <div className="mt-5 flex items-start gap-4">
            <span
              className={`inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${slide.accent} text-white shadow-lg shadow-slate-900/15`}
            >
              <Icon className="h-7 w-7" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-medium text-slate-400">
                {tFormat(lang, "tutorialStep", {
                  n: index + 1,
                  total: SLIDES.length,
                })}
              </p>
              <h2
                id="tutorial-title"
                className="mt-1 text-2xl font-semibold tracking-tight text-slate-900"
              >
                {t(lang, slide.titleKey)}
              </h2>
            </div>
          </div>

          <p className="mt-4 text-sm leading-relaxed text-slate-600">
            {t(lang, slide.bodyKey)}
          </p>

          <ul className="mt-4 space-y-2">
            {slide.bullets.map((key) => (
              <li key={key} className="flex items-start gap-2 text-sm text-slate-700">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                {t(lang, key)}
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-wrap items-center gap-1.5">
            {SLIDES.map((item, dotIndex) => (
              <button
                key={item.titleKey}
                type="button"
                onClick={() => setIndex(dotIndex)}
                aria-label={`${dotIndex + 1} / ${SLIDES.length}`}
                className={`h-1.5 rounded-full transition-all ${
                  dotIndex === index
                    ? "w-7 bg-emerald-600"
                    : "w-2.5 bg-slate-200 hover:bg-slate-300"
                }`}
              />
            ))}
          </div>

          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full px-4 py-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            >
              {t(lang, "skipTutorial")}
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIndex((current) => Math.max(current - 1, 0))}
                disabled={index === 0}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
                {t(lang, "back")}
              </button>

              <button
                type="button"
                autoFocus
                onClick={() => {
                  if (isLast) {
                    onClose();
                    return;
                  }
                  setIndex((current) => Math.min(current + 1, SLIDES.length - 1));
                }}
                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
              >
                {isLast ? t(lang, "startPlanning") : t(lang, "next")}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
