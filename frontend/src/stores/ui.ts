import { create } from "zustand";

export type Theme = "light" | "dark";
export type Tool = "pan" | "probe" | "measure";
export type CompareMode = "split" | "single";
export type SingleSource = "coarse" | "fine" | "truth";
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
  timeZone: string;
  layers: Layers;
  compare: CompareMode;
  single: SingleSource;
  tool: Tool;
  cursor: { lat: number; lon: number } | null;
  selectedEventId: string | null;
  setTheme: (t: Theme) => void;
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
    /* storage may be unavailable (private mode); preferences are simply not persisted */
  }
}

const storedTheme = readStored("ewai.theme");
const storedTz = readStored("ewai.tz");

export const useUi = create<UiState>((set) => ({
  theme: storedTheme === "dark" ? "dark" : "light",
  timeZone: storedTz ?? "Asia/Kolkata",
  layers: { precip: true, anomaly: false, track: true, envelope: true, members: false, impact: true, wind: false, boundaries: true, graticule: true },
  compare: "split",
  single: "fine",
  tool: "pan",
  cursor: null,
  selectedEventId: null,
  setTheme: (theme) => {
    writeStored("ewai.theme", theme);
    set({ theme });
  },
  setTimeZone: (timeZone) => {
    writeStored("ewai.tz", timeZone);
    set({ timeZone });
  },
  toggleLayer: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
  setCompare: (compare) => set({ compare }),
  setSingle: (single) => set({ single }),
  setTool: (tool) => set({ tool }),
  setCursor: (cursor) => set({ cursor }),
  selectEvent: (selectedEventId) => set({ selectedEventId }),
}));
