import { create } from "zustand";

export type Theme = "light" | "dark";
export type Tool = "pan" | "probe" | "measure";
export type CompareMode = "split" | "single";
export type SingleSource = "coarse" | "fine" | "truth";
export type TextSize = "sm" | "md" | "lg";
export type Basemap = "standard" | "satellite" | "terrain" | "dark" | "nautical";

export interface Layers {
  precip: boolean;
  anomaly: boolean;
  track: boolean;
  envelope: boolean;
  members: boolean;
  impact: boolean;
  wind: boolean;
  boundaries: boolean;
  graticule: boolean;
}

interface UiState {
  theme: Theme;
  basemap: Basemap;
  textSize: TextSize;
  reduceMotion: boolean;
  highContrast: boolean;
  timeZone: string;
  layers: Layers;
  compare: CompareMode;
  single: SingleSource;
  tool: Tool;
  cursor: { lat: number; lon: number } | null;
  selectedEventId: string | null;
  setTheme: (t: Theme) => void;
  setBasemap: (b: Basemap) => void;
  setTextSize: (s: TextSize) => void;
  setReduceMotion: (v: boolean) => void;
  setHighContrast: (v: boolean) => void;
  setTimeZone: (tz: string) => void;
  toggleLayer: (k: keyof Layers) => void;
  setCompare: (m: CompareMode) => void;
  setSingle: (s: SingleSource) => void;
  setTool: (t: Tool) => void;
  setCursor: (c: UiState["cursor"]) => void;
  selectEvent: (id: string | null) => void;
}

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage may be unavailable; preferences are simply not persisted */
  }
}

function applyTextSize(s: TextSize) {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-text-size", s);
  }
}

function applyHighContrast(v: boolean) {
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("high-contrast", v);
  }
}

// ── Bootstrap theme ───────────────────────────────────────────────────────
const storedTheme = readStored("ewai.theme");
const initialTheme: Theme = storedTheme === "dark" ? "dark" : "light";
if (typeof document !== "undefined") {
  document.documentElement.setAttribute("data-theme", initialTheme);
}

// ── Bootstrap text size ───────────────────────────────────────────────────
const storedTextSize = readStored("ewai.textSize");
const initialTextSize: TextSize =
  storedTextSize === "sm" || storedTextSize === "lg" ? storedTextSize : "md";
applyTextSize(initialTextSize);

// ── Bootstrap high contrast ───────────────────────────────────────────────
const storedHighContrast = readStored("ewai.highContrast");
const initialHighContrast = storedHighContrast === "1";
applyHighContrast(initialHighContrast);

// ── Bootstrap reduce motion ───────────────────────────────────────────────
const storedReduceMotion = readStored("ewai.reduceMotion");
const initialReduceMotion = storedReduceMotion === "1";

const storedTz = readStored("ewai.tz");

// ── Bootstrap basemap ─────────────────────────────────────────────────────
const storedBasemap = readStored("ewai.basemap") as Basemap | null;
const initialBasemap: Basemap =
  storedBasemap && ["standard", "satellite", "terrain", "dark", "nautical"].includes(storedBasemap)
    ? storedBasemap
    : "standard";

export const useUi = create<UiState>((set) => ({
  theme: initialTheme,
  basemap: initialBasemap,
  textSize: initialTextSize,
  reduceMotion: initialReduceMotion,
  highContrast: initialHighContrast,
  timeZone: storedTz ?? "Asia/Kolkata",
  layers: {
    precip: true,
    anomaly: false,
    track: true,
    envelope: true,
    members: false,
    impact: true,
    wind: false,
    boundaries: true,
    graticule: true,
  },
  compare: "split",
  single: "fine",
  tool: "pan",
  cursor: null,
  selectedEventId: null,

  setTheme: (theme) => {
    writeStored("ewai.theme", theme);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", theme);
    }
    set({ theme });
  },

  setBasemap: (basemap) => {
    writeStored("ewai.basemap", basemap);
    set({ basemap });
  },

  setTextSize: (textSize) => {
    writeStored("ewai.textSize", textSize);
    applyTextSize(textSize);
    set({ textSize });
  },

  setReduceMotion: (reduceMotion) => {
    writeStored("ewai.reduceMotion", reduceMotion ? "1" : "0");
    set({ reduceMotion });
  },

  setHighContrast: (highContrast) => {
    writeStored("ewai.highContrast", highContrast ? "1" : "0");
    applyHighContrast(highContrast);
    set({ highContrast });
  },

  setTimeZone: (timeZone) => {
    writeStored("ewai.tz", timeZone);
    set({ timeZone });
  },

  toggleLayer: (k) =>
    set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
  setCompare: (compare) => set({ compare }),
  setSingle:  (single)  => set({ single }),
  setTool:    (tool)    => set({ tool }),
  setCursor:  (cursor)  => set({ cursor }),
  selectEvent: (selectedEventId) => set({ selectedEventId }),
}));
