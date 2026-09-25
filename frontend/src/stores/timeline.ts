import { create } from "zustand";

interface TimelineState {
  leads: number[];
  index: number;
  playing: boolean;
  speed: 1 | 2 | 4;
  setLeads: (leads: number[]) => void;
  setLead: (lead: number) => void;
  step: (delta: number) => void;
  toggle: () => void;
  pause: () => void;
  setSpeed: (s: 1 | 2 | 4) => void;
  first: () => void;
  last: () => void;
}

/** Single source of truth for forecast time: the map, panels, alerts and statistics all subscribe to it. */
export const useTimeline = create<TimelineState>((set, get) => ({
  leads: [],
  index: 0,
  playing: false,
  speed: 1,
  setLeads: (leads) => set((s) => (s.leads.join() === leads.join() ? s : { leads, index: Math.min(s.index, Math.max(0, leads.length - 1)) })),
  setLead: (lead) => {
    const i = get().leads.indexOf(lead);
    if (i >= 0) set({ index: i });
  },
  step: (delta) => {
    const { leads, index } = get();
    if (!leads.length) return;
    set({ index: Math.min(leads.length - 1, Math.max(0, index + delta)) });
  },
  toggle: () => {
    const { playing, index, leads } = get();
    if (!leads.length) return;
    // Pressing play at the end restarts from the beginning.
    set({ playing: !playing, index: !playing && index >= leads.length - 1 ? 0 : index });
  },
  pause: () => set({ playing: false }),
  setSpeed: (speed) => set({ speed }),
  first: () => set({ index: 0 }),
  last: () => set((s) => ({ index: Math.max(0, s.leads.length - 1) })),
}));

export const currentLead = (s: Pick<TimelineState, "leads" | "index">): number | undefined => s.leads[s.index];
