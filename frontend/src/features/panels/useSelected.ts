import { useEffect } from "react";

import { useEvents } from "@/hooks/queries";
import { useUi } from "@/stores/ui";
import type { EventSummary } from "@/types/api";

/** The selected event (defaults to the first available). */
export function useSelectedEvent(): { event: EventSummary | undefined; events: EventSummary[] } {
  const q = useEvents();
  const selected = useUi((s) => s.selectedEventId);
  const select = useUi((s) => s.selectEvent);
  const events = q.data ?? [];
  const event = events.find((e) => e.id === selected) ?? events[0];
  useEffect(() => { if (event && event.id !== selected) select(event.id); }, [event, selected, select]);
  return { event, events };
}
