import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { colorizeToRGBA, type Stop } from "@/lib/colors";
import type { DecodedField } from "@/lib/field";
import { project, type Size, type View } from "@/lib/geo";

interface Props {
  field: DecodedField | undefined;
  stops: Stop[];
  view: View;
  size: Size;
  opacity?: number;
  className?: string;
  testId?: string;
  maxGridCells?: number;
}

function downsampleIfNeeded(values: Float32Array, nx: number, ny: number, maxCells: number): { values: Float32Array; nx: number; ny: number } {
  const total = nx * ny;
  if (total <= maxCells) return { values, nx, ny };
  const scale = Math.sqrt(maxCells / total);
  const newNx = Math.max(1, Math.floor(nx * scale));
  const newNy = Math.max(1, Math.floor(ny * scale));
  const out = new Float32Array(newNx * newNy);
  for (let r = 0; r < newNy; r++) {
    for (let c = 0; c < newNx; c++) {
      const srcR = Math.floor((r / newNy) * ny);
      const srcC = Math.floor((c / newNx) * nx);
      out[r * newNx + c] = values[srcR * nx + srcC] ?? NaN;
    }
  }
  return { values: out, nx: newNx, ny: newNy };
}

export function RasterCanvas({ field, stops, view, size, opacity = 1, className, testId, maxGridCells = 500000 }: Props): JSX.Element {
  const ref = useRef<HTMLCanvasElement>(null);
  const [loading, setLoading] = useState(false);

  const { offscreen, effectiveField } = useMemo(() => {
    if (!field) return { offscreen: null, effectiveField: null };
    setLoading(true);
    const { values, nx, ny } = downsampleIfNeeded(field.values, field.nx, field.ny, maxGridCells);
    const c = document.createElement("canvas");
    c.width = nx;
    c.height = ny;
    const ctx = c.getContext("2d");
    if (!ctx) { setLoading(false); return { offscreen: null, effectiveField: field }; }
    const img = ctx.createImageData(nx, ny);
    const rgba = colorizeToRGBA(values, nx, ny, stops);
    for (let i = 0; i < rgba.length; i += 4) {
      if (rgba[i] === 0 && rgba[i + 1] === 0 && rgba[i + 2] === 0 && rgba[i + 3] === 0) {
        continue;
      }
    }
    img.data.set(rgba);
    ctx.putImageData(img, 0, 0);
    setLoading(false);
    return { offscreen: c, effectiveField: { ...field, nx, ny, values } };
  }, [field, stops, maxGridCells]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);
    if (!offscreen || !effectiveField) return;
    const [w, s, e, n] = effectiveField.payload.bounds;
    const [x0, y0] = project(view, size, w, n);
    const [x1, y1] = project(view, size, e, s);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(offscreen, x0, y0, x1 - x0, y1 - y0);
  }, [offscreen, effectiveField, view, size]);

  return (
    <div className="relative h-full w-full">
      <canvas ref={ref} data-testid={testId} aria-hidden className={className ?? "absolute inset-0 h-full w-full"} style={{ opacity }} />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-surface-container-lowest/60" data-testid="raster-loading">
          <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden />
          <span className="sr-only">Loading raster data...</span>
        </div>
      )}
    </div>
  );
}
