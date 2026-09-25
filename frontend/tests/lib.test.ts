import { colorizeToRGBA, PRECIP_STOPS, rampColor } from "@/lib/colors";
import { decodeField, sampleField } from "@/lib/field";
import { fitView, geometryToPath, haversineKm, panBy, project, unproject, zoomAt } from "@/lib/geo";
import { formatIn, formatIst, formatUser, formatUtc, isKnownTimeZone, leadLabel, shortDayHour, zoneLabel } from "@/lib/time";
import { bearingToCompass, clamp, fmt, fmtInt, pct } from "@/lib/utils";
import type { FieldPayload } from "@/types/api";

const T = "2000-09-01T00:00:00Z";

describe("time: explicit zones, never silent conversion", () => {
  it("labels UTC and IST and converts correctly (IST = UTC+05:30)", () => {
    expect(formatUtc(T)).toBe("2000-09-01 00:00 UTC");
    expect(formatIst(T)).toBe("2000-09-01 05:30 IST");
    expect(formatIst("2000-09-01T20:00:00Z")).toBe("2000-09-02 01:30 IST"); // date rolls over
  });
  it("labels arbitrary zones and rejects invalid input", () => {
    expect(formatUser(T, "America/New_York")).toMatch(/2000-08-31 20:00 (EDT|GMT-4)/);
    expect(zoneLabel("UTC")).toBe("UTC");
    expect(() => formatUtc("not-a-date")).toThrow(RangeError);
    expect(isKnownTimeZone("Asia/Kolkata")).toBe(true);
    expect(isKnownTimeZone("Mars/Olympus")).toBe(false);
    expect(formatIn(T, "UTC", "Z")).toBe("2000-09-01 00:00 Z");
  });
  it("formats leads and day/hour stamps", () => {
    expect(leadLabel(0)).toBe("T+00");
    expect(leadLabel(48)).toBe("T+48");
    expect(shortDayHour("2000-09-02T12:00:00Z")).toBe("02/12Z");
  });
});

describe("geo", () => {
  it("haversine matches a known distance", () => {
    expect(haversineKm(19.076, 72.8777, 28.7041, 77.1025)).toBeGreaterThan(1100);
    expect(haversineKm(19.076, 72.8777, 28.7041, 77.1025)).toBeLessThan(1200);
    expect(haversineKm(10, 20, 10, 20)).toBe(0);
  });
  const size = { w: 800, h: 500 };
  const view = { lon: 86, lat: 18, zoom: 40 };
  it("project/unproject round-trips", () => {
    const [x, y] = project(view, size, 87.3, 20.1);
    const [lon, lat] = unproject(view, size, x, y);
    expect(lon).toBeCloseTo(87.3, 9);
    expect(lat).toBeCloseTo(20.1, 9);
    expect(project(view, size, 86, 18)).toEqual([400, 250]);
  });
  it("zoomAt keeps the point under the cursor fixed", () => {
    const [lon0, lat0] = unproject(view, size, 600, 120);
    const z = zoomAt(view, size, 600, 120, 1.7);
    const [lon1, lat1] = unproject(z, size, 600, 120);
    expect(lon1).toBeCloseTo(lon0, 9);
    expect(lat1).toBeCloseTo(lat0, 9);
    expect(z.zoom).toBeCloseTo(68, 9);
    expect(zoomAt(view, size, 0, 0, 1e6).zoom).toBe(400); // clamped
  });
  it("panBy moves the centre opposite to the drag and fitView contains the bounds", () => {
    expect(panBy(view, 40, 0).lon).toBeLessThan(view.lon);
    expect(panBy(view, 0, 40).lat).toBeGreaterThan(view.lat);
    const b: [number, number, number, number] = [80, 12, 92, 24];
    const v = fitView(b, size);
    const [x0, y1] = project(v, size, b[0], b[1]);
    const [x1, y0] = project(v, size, b[2], b[3]);
    expect(x0).toBeGreaterThanOrEqual(0); expect(x1).toBeLessThanOrEqual(size.w);
    expect(y0).toBeGreaterThanOrEqual(0); expect(y1).toBeLessThanOrEqual(size.h);
  });
  it("converts GeoJSON geometry to SVG paths", () => {
    expect(geometryToPath({ type: "LineString", coordinates: [[0, 0], [1, 2]] })).toBe("M0.0000 0.0000L1.0000 2.0000");
    expect(geometryToPath({ type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] })).toMatch(/^M.*Z$/);
    expect(geometryToPath({ type: "Point", coordinates: [1, 2] })).toBe("");
  });
});

describe("colors and fields", () => {
  it("ramp thresholds: below 1 mm is transparent, 150+ is the darkest bin", () => {
    expect(rampColor(PRECIP_STOPS, 0.5)).toBeNull();
    expect(rampColor(PRECIP_STOPS, NaN)).toBeNull();
    expect(rampColor(PRECIP_STOPS, 1)).toEqual(PRECIP_STOPS[0]?.color);
    expect(rampColor(PRECIP_STOPS, 149.9)).toEqual(PRECIP_STOPS[5]?.color);
    expect(rampColor(PRECIP_STOPS, 500)).toEqual(PRECIP_STOPS[6]?.color);
  });
  it("colorize flips south-to-north rows so north is at the top", () => {
    const v = new Float32Array([0, 0, 200, 0]); // 2x2: row0 (south) = [0,0]; row1 (north) = [200,0]
    const px = colorizeToRGBA(v, 2, 2, PRECIP_STOPS);
    expect(px[3]).toBeGreaterThan(0); // canvas row 0 col 0 (north-west) is the 200 mm cell
    expect(px[(2 * 1 + 0) * 4 + 3]).toBe(0); // canvas row 1 col 0 is dry
  });
  const payload = (values: number[], shape: [number, number]): FieldPayload => {
    const b = new Uint8Array(new Float32Array(values).buffer);
    return { product: "forecast", variable: "tp", method: null, units: "mm/6h", lead_hours: 0, valid_time: "2000-09-01T00:00:00Z", timezone: "UTC", bounds: [80, 12, 82, 14], shape, row_order: "south_to_north", resolution_km: { north_south: 111, east_west: 108 }, data_kind: "SYNTHETIC_DEMO", label: "x", min: 0, max: 3, encoding: "float32-le-base64", values_b64: btoa(String.fromCharCode(...b)) };
  };
  it("decodes the API raster and samples by lon/lat", () => {
    const f = decodeField(payload([0, 1, 2, 3], [2, 2]));
    expect(Array.from(f.values)).toEqual([0, 1, 2, 3]);
    expect(sampleField(f, 80.5, 12.5)).toBe(0); // south-west
    expect(sampleField(f, 81.5, 12.5)).toBe(1);
    expect(sampleField(f, 80.5, 13.5)).toBe(2); // north-west
    expect(sampleField(f, 81.5, 13.5)).toBe(3);
    expect(sampleField(f, 79, 12.5)).toBeNull();
    expect(sampleField(f, 82, 12.5)).toBeNull(); // east edge is exclusive
  });
  it("rejects a payload whose byte length disagrees with its shape", () => {
    expect(() => decodeField(payload([0, 1, 2], [2, 2]))).toThrow(RangeError);
  });
});

describe("utils", () => {
  it("formats missing values as an em dash, never as 0", () => {
    expect(fmt(null)).toBe("—"); expect(fmt(undefined)).toBe("—"); expect(fmt(NaN)).toBe("—");
    expect(fmt(12.345, 1)).toBe("12.3"); expect(fmtInt(1234.6)).toBe("1,235"); expect(pct(0.874)).toBe("87%");
    expect(clamp(5, 0, 3)).toBe(3);
    expect(bearingToCompass(0)).toBe("N"); expect(bearingToCompass(350)).toBe("N"); expect(bearingToCompass(45)).toBe("NE"); expect(bearingToCompass(-90)).toBe("W");
  });
});

import { ANOMALY_STOPS } from "@/lib/colors";
import { labelContrast } from "@/features/map/Legend";

describe("legend swatch labels meet WCAG AA contrast (regression: dark text on dark red = 2.1:1)", () => {
  it.each([...PRECIP_STOPS, ...ANOMALY_STOPS].map((s) => [s.label, s.color] as const))("swatch %s", (_l, color) => {
    expect(labelContrast(color)).toBeGreaterThanOrEqual(4.5);
  });
});
