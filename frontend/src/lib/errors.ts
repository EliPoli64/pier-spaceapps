import { ApiError } from "./api";
import type { Lang } from "./i18n";
import { t } from "./i18n";

export interface FriendlyError {
  title: string;
  description: string;
  items?: string[];
  suggestDemo?: boolean;
}

function fieldLabel(field: string, lang: Lang): string {
  const key = field.toLowerCase();
  if (key.includes("lat")) return t(lang, "latitude");
  if (key.includes("lon")) return t(lang, "longitude");
  if (key.includes("date")) return t(lang, "currentDate");
  if (key.includes("rendimiento") || key.includes("yield")) {
    return t(lang, "expectedYield");
  }
  if (key.includes("peso") || key.includes("weight")) {
    return t(lang, "priorities");
  }
  return field;
}

export function formatFriendlyError(
  err: unknown,
  lang: Lang,
  demoMode: boolean,
): FriendlyError {
  if (err instanceof ApiError) {
    if (err.isTimeout) {
      return {
        title: t(lang, "errorTimeoutTitle"),
        description: t(lang, "errorTimeoutBody"),
        suggestDemo: !demoMode,
      };
    }

    if (err.status === 0) {
      return {
        title: t(lang, "errorOfflineTitle"),
        description: t(lang, "networkError"),
        suggestDemo: !demoMode,
      };
    }

    if (err.status === 401 || err.status === 403) {
      return {
        title: t(lang, "errorAuthTitle"),
        description: t(lang, "errorAuthBody"),
        suggestDemo: !demoMode,
      };
    }

    if (err.status === 422 && err.issues && err.issues.length > 0) {
      return {
        title: t(lang, "errorInputTitle"),
        description: t(lang, "errorInputBody"),
        items: err.issues.map((issue) =>
          issue.field
            ? `${fieldLabel(issue.field, lang)}: ${issue.message}`
            : issue.message,
        ),
      };
    }

    if (err.status === 429) {
      return {
        title: t(lang, "errorRateLimitTitle"),
        description: t(lang, "errorRateLimitBody"),
        suggestDemo: !demoMode,
      };
    }

    if (err.status >= 500) {
      return {
        title: t(lang, "errorServerTitle"),
        description: t(lang, "errorServerBody"),
        suggestDemo: !demoMode,
      };
    }

    return {
      title: t(lang, "requestFailed"),
      description: err.message || t(lang, "errorGenericBody"),
      suggestDemo: !demoMode,
    };
  }

  return {
    title: t(lang, "requestFailed"),
    description:
      err instanceof Error && err.message
        ? err.message
        : t(lang, "errorGenericBody"),
    suggestDemo: !demoMode,
  };
}
