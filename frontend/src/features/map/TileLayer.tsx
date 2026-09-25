import { useEffect, useMemo, useRef, useState } from "react";

import type { Size, View } from "@/lib/geo";

const TILE_SIZE = 256;

export interface TileSource {
  name: string;
  urlTemplate: string;
  attribution?: string;
  maxZoom?: number;
  minZoom?: number;
}

export const TILE_SOURCES: Record<string, TileSource> = {
  osm: {
    name: "OpenStreetMap",
    urlTemplate: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  },
  terrain: {
    name: "Stamen Terrain",
    urlTemplate: "https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png",
    attribution: "Stamen Design, CC BY 3.0",
    maxZoom: 18,
  },
  carto_light: {
    name: "CartoDB Positron",
    urlTemplate: "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png",
    attribution: "CartoDB, CC BY 3.0",
    maxZoom: 20,
  },
  carto_dark: {
    name: "CartoDB Dark Matter",
    urlTemplate: "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
    attribution: "CartoDB, CC BY 3.0",
    maxZoom: 20,
  },
};

interface Props {
  view: View;
  size: Size;
  source?: TileSource;
  opacity?: number;
  visible?: boolean;
}

function lonLatToTile(lon: number, lat: number, zoom: number): { x: number; y: number } {
  const n = 2 ** zoom;
  const x = ((lon + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const y = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  return { x, y };
}

function tileUrl(template: string, z: number, x: number, y: number): string {
  return template.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
}

export function TileLayer({ view, size, source = TILE_SOURCES.osm, opacity = 0.35, visible = true }: Props): JSX.Element | null {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState(false);
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());

  const zoom = Math.floor(Math.log2(view.zoom / 2));
  const clampedZoom = Math.max(source?.minZoom ?? 0, Math.min(source?.maxZoom ?? 19, zoom));

  const tiles = useMemo(() => {
    if (!visible || !source) return [];
    const center = lonLatToTile(view.lon, view.lat, clampedZoom);
    const n = 2 ** clampedZoom;
    const tilesX = Math.ceil(size.w / TILE_SIZE) + 2;
    const tilesY = Math.ceil(size.h / TILE_SIZE) + 2;
    const result: { url: string; x: number; y: number; z: number }[] = [];
    for (let dx = -Math.floor(tilesX / 2); dx <= Math.ceil(tilesX / 2); dx++) {
      for (let dy = -Math.floor(tilesY / 2); dy <= Math.ceil(tilesY / 2); dy++) {
        const tx = ((Math.floor(center.x) + dx) % n + n) % n;
        const ty = Math.floor(center.y) + dy;
        if (ty < 0 || ty >= n) continue;
        result.push({ url: tileUrl(source.urlTemplate, clampedZoom, tx, ty), x: tx, y: ty, z: clampedZoom });
      }
    }
    return result;
  }, [view.lon, view.lat, clampedZoom, size.w, size.h, source, visible]);

  useEffect(() => {
    if (!visible || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);
    ctx.globalAlpha = opacity;

    if (tiles.length === 0) return;

    setError(false);

    for (const tile of tiles) {
      const cached = imgCache.current.get(tile.url);
      if (cached) {
        drawTile(ctx, view, size, clampedZoom, tile, cached);
        continue;
      }
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        imgCache.current.set(tile.url, img);
        drawTile(ctx, view, size, clampedZoom, tile, img);
      };
      img.onerror = () => {
        setError(true);
      };
      img.src = tile.url;
    }
  }, [tiles, view, size, clampedZoom, opacity, visible]);

  if (!visible) return null;

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full"
      aria-hidden
      style={{ opacity: error ? 0.15 : 1 }}
      data-testid="tile-layer"
    />
  );
}

function drawTile(
  ctx: CanvasRenderingContext2D,
  view: View,
  size: Size,
  zoom: number,
  tile: { x: number; y: number; z: number },
  img: HTMLImageElement,
): void {
  const n = 2 ** zoom;
  const lonPerTile = 360 / n;
  const tileLon = tile.x * lonPerTile - 180;
  const latRad = Math.atan(Math.sinh(Math.PI * (1 - (2 * tile.y) / n)));
  const tileLat = (latRad * 180) / Math.PI;
  const latRad2 = Math.atan(Math.sinh(Math.PI * (1 - (2 * (tile.y + 1)) / n)));
  const tileLat2 = (latRad2 * 180) / Math.PI;

  const kx = view.zoom * Math.cos((18 * Math.PI) / 180);
  const x0 = size.w / 2 + (tileLon - view.lon) * kx;
  const y0 = size.h / 2 - (tileLat - view.lat) * view.zoom;
  const x1 = size.w / 2 + (tileLon + lonPerTile - view.lon) * kx;
  const y1 = size.h / 2 - (tileLat2 - view.lat) * view.zoom;

  ctx.drawImage(img, x0, y0, x1 - x0, y1 - y0);
}
