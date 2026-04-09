export interface UiStyleSettings {
  version?: number;
  backgroundPreset: "ocean" | "sunset" | "forest" | "slate";
  windowRadius: number;
  shellOpacity: number;
  fontScale: number;
}

export const DEFAULT_UI_STYLE_SETTINGS: UiStyleSettings = {
  version: 2,
  backgroundPreset: "ocean",
  windowRadius: 10,
  shellOpacity: 0.9,
  fontScale: 1,
};

const STORAGE_KEY = "class-assistant-ui-style";

const BACKGROUND_GRADIENTS: Record<UiStyleSettings["backgroundPreset"], string> = {
  ocean: "radial-gradient(circle at top left, rgba(14,165,233,0.32), transparent 38%), radial-gradient(circle at top right, rgba(34,197,94,0.18), transparent 42%), linear-gradient(135deg, rgba(3,12,28,0.98), rgba(7,31,52,0.94))",
  sunset: "radial-gradient(circle at top left, rgba(251,146,60,0.34), transparent 35%), radial-gradient(circle at bottom right, rgba(244,63,94,0.3), transparent 42%), linear-gradient(135deg, rgba(31,12,18,0.98), rgba(56,24,22,0.94))",
  forest: "radial-gradient(circle at top left, rgba(74,222,128,0.32), transparent 36%), radial-gradient(circle at bottom right, rgba(20,184,166,0.28), transparent 40%), linear-gradient(135deg, rgba(6,22,16,0.98), rgba(13,46,31,0.94))",
  slate: "radial-gradient(circle at top left, rgba(148,163,184,0.18), transparent 34%), radial-gradient(circle at bottom right, rgba(99,102,241,0.18), transparent 40%), linear-gradient(135deg, rgba(15,23,42,0.98), rgba(30,41,59,0.94))",
};

const THEME_VARS: Record<UiStyleSettings["backgroundPreset"], Record<string, string>> = {
  ocean: {
    "--theme-shell-border": "rgba(56, 189, 248, 0.28)",
    "--theme-panel-bg": "rgba(4, 18, 36, 0.6)",
    "--theme-panel-border": "rgba(56, 189, 248, 0.18)",
    "--theme-primary-bg": "linear-gradient(135deg, rgba(8, 80, 120, 0.78), rgba(4, 124, 142, 0.78))",
    "--theme-primary-border": "rgba(34, 211, 238, 0.32)",
    "--theme-primary-text": "#e0f7ff",
    "--theme-secondary-bg": "rgba(12, 28, 52, 0.86)",
    "--theme-secondary-border": "rgba(125, 211, 252, 0.18)",
    "--theme-secondary-text": "rgba(240, 249, 255, 0.92)",
    "--theme-feature-bg": "rgba(8, 31, 60, 0.84)",
    "--theme-feature-border": "rgba(59, 130, 246, 0.32)",
    "--theme-feature-text": "#dbeafe",
    "--theme-muted-text": "rgba(191, 219, 254, 0.72)",
  },
  sunset: {
    "--theme-shell-border": "rgba(251, 146, 60, 0.3)",
    "--theme-panel-bg": "rgba(46, 17, 18, 0.62)",
    "--theme-panel-border": "rgba(251, 146, 60, 0.18)",
    "--theme-primary-bg": "linear-gradient(135deg, rgba(180, 83, 9, 0.82), rgba(225, 29, 72, 0.72))",
    "--theme-primary-border": "rgba(253, 186, 116, 0.28)",
    "--theme-primary-text": "#fff7ed",
    "--theme-secondary-bg": "rgba(65, 24, 28, 0.88)",
    "--theme-secondary-border": "rgba(251, 146, 60, 0.2)",
    "--theme-secondary-text": "rgba(255, 237, 213, 0.92)",
    "--theme-feature-bg": "rgba(86, 31, 38, 0.84)",
    "--theme-feature-border": "rgba(251, 113, 133, 0.28)",
    "--theme-feature-text": "#ffe4e6",
    "--theme-muted-text": "rgba(254, 215, 170, 0.76)",
  },
  forest: {
    "--theme-shell-border": "rgba(74, 222, 128, 0.28)",
    "--theme-panel-bg": "rgba(8, 28, 18, 0.64)",
    "--theme-panel-border": "rgba(74, 222, 128, 0.16)",
    "--theme-primary-bg": "linear-gradient(135deg, rgba(21, 128, 61, 0.84), rgba(13, 148, 136, 0.72))",
    "--theme-primary-border": "rgba(110, 231, 183, 0.28)",
    "--theme-primary-text": "#ecfdf5",
    "--theme-secondary-bg": "rgba(15, 40, 27, 0.88)",
    "--theme-secondary-border": "rgba(74, 222, 128, 0.18)",
    "--theme-secondary-text": "rgba(220, 252, 231, 0.92)",
    "--theme-feature-bg": "rgba(17, 54, 35, 0.84)",
    "--theme-feature-border": "rgba(45, 212, 191, 0.28)",
    "--theme-feature-text": "#d1fae5",
    "--theme-muted-text": "rgba(187, 247, 208, 0.72)",
  },
  slate: {
    "--theme-shell-border": "rgba(148, 163, 184, 0.22)",
    "--theme-panel-bg": "rgba(15, 23, 42, 0.66)",
    "--theme-panel-border": "rgba(148, 163, 184, 0.14)",
    "--theme-primary-bg": "linear-gradient(135deg, rgba(51, 65, 85, 0.86), rgba(79, 70, 229, 0.66))",
    "--theme-primary-border": "rgba(165, 180, 252, 0.26)",
    "--theme-primary-text": "#eef2ff",
    "--theme-secondary-bg": "rgba(30, 41, 59, 0.86)",
    "--theme-secondary-border": "rgba(148, 163, 184, 0.14)",
    "--theme-secondary-text": "rgba(226, 232, 240, 0.92)",
    "--theme-feature-bg": "rgba(30, 41, 59, 0.82)",
    "--theme-feature-border": "rgba(129, 140, 248, 0.24)",
    "--theme-feature-text": "#e2e8f0",
    "--theme-muted-text": "rgba(203, 213, 225, 0.72)",
  },
};

export function readUiStyleSettings(): UiStyleSettings {
  if (typeof window === "undefined") {
    return DEFAULT_UI_STYLE_SETTINGS;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_UI_STYLE_SETTINGS;
    }

    const parsed = JSON.parse(raw) as Partial<UiStyleSettings>;
    const isLegacy = !parsed.version;
    return {
      version: DEFAULT_UI_STYLE_SETTINGS.version,
      backgroundPreset: parsed.backgroundPreset ?? DEFAULT_UI_STYLE_SETTINGS.backgroundPreset,
      windowRadius: isLegacy ? DEFAULT_UI_STYLE_SETTINGS.windowRadius : (parsed.windowRadius ?? DEFAULT_UI_STYLE_SETTINGS.windowRadius),
      shellOpacity: parsed.shellOpacity ?? DEFAULT_UI_STYLE_SETTINGS.shellOpacity,
      fontScale: parsed.fontScale ?? DEFAULT_UI_STYLE_SETTINGS.fontScale,
    };
  } catch {
    return DEFAULT_UI_STYLE_SETTINGS;
  }
}

export function saveUiStyleSettings(settings: UiStyleSettings) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function applyUiStyleSettings(settings: UiStyleSettings) {
  if (typeof document === "undefined") {
    return;
  }

  const root = document.documentElement;
  root.style.setProperty("--window-radius", `${settings.windowRadius}px`);
  root.style.setProperty("--app-shell-opacity", String(settings.shellOpacity));
  root.style.setProperty("--app-font-scale", String(settings.fontScale));
  root.style.setProperty("--app-bg-gradient", BACKGROUND_GRADIENTS[settings.backgroundPreset]);
  for (const [key, value] of Object.entries(THEME_VARS[settings.backgroundPreset])) {
    root.style.setProperty(key, value);
  }
}