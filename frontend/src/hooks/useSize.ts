import { useEffect, useRef, useState } from "react";

import type { Size } from "@/lib/geo";

/** Track an element's content box size with ResizeObserver. */
export function useSize<T extends HTMLElement>(): [React.RefObject<T>, Size, boolean] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState<Size>({ w: 800, h: 520 });
  const [measured, setMeasured] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r && r.width > 0 && r.height > 0) {
        setSize({ w: r.width, h: r.height });
        setMeasured(true);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size, measured];
}
