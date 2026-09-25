import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Tooltip from "@radix-ui/react-tooltip";

import { MapView } from "@/features/map/MapView";
import { TimelineBar } from "@/features/timeline/TimelineBar";
import { decodeField, type DecodedField } from "@/lib/field";
import { useTimeline } from "@/stores/timeline";
import { useUi } from "@/stores/ui";
import type { FieldPayload, TrajectoryData } from "@/types/api";

function makeField(nx: number, ny: number, fill: (r: number, c: number) => number, bounds: [number, number, number, number], km: number): DecodedField {
  const v = new Float32Array(nx * ny);
  for (let r = 0; r < ny; r++) for (let c = 0; c < nx; c++) v[r * nx + c] = fill(r, c);
  const b64 = btoa(String.fromCharCode(...new Uint8Array(v.buffer)));
  const p: FieldPayload = { product: "forecast", variable: "tp", method: null, units: "mm/6h", lead_hours: 0, valid_time: "2000-09-01T00:00:00Z", timezone: "UTC", bounds, shape: [ny, nx], row_order: "south_to_north", resolution_km: { north_south: km, east_west: km }, data_kind: "SYNTHETIC_DEMO", label: "x", min: 0, max: 100, encoding: "float32-le-base64", values_b64: b64 };
  return decodeField(p);
}
const DOMAIN: [number, number, number, number] = [80, 12, 92, 24];
const coarse = makeField(12, 12, () => 40, DOMAIN, 111);
const fine = makeField(24, 24, () => 90, DOMAIN, 55.5);
const traj: TrajectoryData = {
  type: "FeatureCollection", meta: { event_id: "e", data_kind: "SYNTHETIC_DEMO", timezone: "UTC", initialization_time: "2000-09-01T00:00:00Z" },
  features: [
    { type: "Feature", properties: { kind: "tracked" }, geometry: { type: "LineString", coordinates: [[88, 15], [87, 20]] } },
    { type: "Feature", properties: { kind: "tracked_point", lead_hours: 0, max_intensity: 70, speed_kmh: 10 }, geometry: { type: "Point", coordinates: [88, 15] } },
    { type: "Feature", properties: { kind: "tracked_point", lead_hours: 6, max_intensity: 90, speed_kmh: 12 }, geometry: { type: "Point", coordinates: [87.5, 17] } },
  ],
};

beforeEach(() => {
  useUi.setState({ compare: "split", tool: "pan", single: "fine" });
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
});

const renderMap = (): ReturnType<typeof render> => render(<Tooltip.Provider><div style={{ width: 900, height: 560 }}><MapView lead={0} domain={DOMAIN} coarse={coarse} fine={fine} trajectory={traj} /></div></Tooltip.Provider>);

describe("MapView", () => {
  it("is a labelled, focusable application region with a text summary of the state", () => {
    renderMap();
    const m = screen.getByRole("application");
    expect(m).toHaveAccessibleName(/Arrow keys pan/);
    expect(m).toHaveAttribute("tabindex", "0");
    expect(m).toHaveAccessibleDescription(/synthetic precipitation at T\+00/i);
  });
  it("labels both halves of the comparison with resolution and data kind", () => {
    renderMap();
    expect(screen.getByText(/Coarse forecast · 111\.0 km/)).toBeInTheDocument();
    expect(screen.getByText(/Baseline · 55\.5 km · interpolation, no ML/)).toBeInTheDocument();
    expect(screen.getAllByTestId("data-kind-badge").length).toBeGreaterThanOrEqual(2);
  });
  it("the wipe divider is an accessible slider that moves with the keyboard and stops following the event", async () => {
    renderMap();
    const s = screen.getByRole("slider", { name: /Comparison divider/ });
    const before = Number(s.getAttribute("aria-valuenow"));
    s.focus();
    await userEvent.keyboard("{ArrowRight}");
    const after = Number(s.getAttribute("aria-valuenow"));
    expect(after).toBe(before + 5);
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(Number(s.getAttribute("aria-valuenow"))).toBe(before - 5);
  });
  it("single mode drops the divider and shows the chosen source", () => {
    useUi.setState({ compare: "single", single: "coarse" });
    renderMap();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.getByText(/Coarse forecast · 111\.0 km/)).toBeInTheDocument();
    expect(screen.queryByTestId("raster-right")).toBeNull();
  });
  it("probe tool reads real field values at the clicked point", () => {
    useUi.setState({ tool: "probe" });
    renderMap();
    const m = screen.getByRole("application");
    expect(screen.getByText(/Click the map to read values/)).toBeInTheDocument();
    fireEvent.pointerDown(m, { button: 0, clientX: 450, clientY: 280, pointerId: 1 });
    fireEvent.pointerUp(m, { button: 0, clientX: 450, clientY: 280, pointerId: 1 });
    const r = screen.getByTestId("probe-readout");
    expect(r).toHaveTextContent("Coarse tp");
    expect(r).toHaveTextContent("40.0 mm/6h");
    expect(r).toHaveTextContent("90.0 mm/6h");
  });
  it("measure tool reports great-circle distance between two clicks", () => {
    useUi.setState({ tool: "measure" });
    renderMap();
    const m = screen.getByRole("application");
    for (const x of [300, 600]) { fireEvent.pointerDown(m, { button: 0, clientX: x, clientY: 280, pointerId: 1 }); fireEvent.pointerUp(m, { button: 0, clientX: x, clientY: 280, pointerId: 1 }); }
    expect(screen.getByTestId("measure-readout")).toHaveTextContent(/Distance: \d+\.\d km \(great-circle\)/);
  });
  it("dragging pans instead of triggering the tool action; pointer position updates the cursor readout", () => {
    useUi.setState({ tool: "probe" });
    renderMap();
    const m = screen.getByRole("application");
    fireEvent.pointerDown(m, { button: 0, clientX: 300, clientY: 200, pointerId: 1 });
    fireEvent.pointerMove(m, { clientX: 340, clientY: 220, pointerId: 1 });
    fireEvent.pointerUp(m, { button: 0, clientX: 340, clientY: 220, pointerId: 1 });
    expect(screen.queryByTestId("probe-readout")).toBeNull();
    expect(useUi.getState().cursor).not.toBeNull();
  });
  it("keyboard zoom and reset do not throw and keep the map usable", async () => {
    renderMap();
    const m = screen.getByRole("application");
    m.focus();
    await userEvent.keyboard("+-0{ArrowLeft}{ArrowUp}");
    expect(m).toBeInTheDocument();
  });
  it("draws the track, the current-lead marker and an event label", () => {
    renderMap();
    expect(screen.getByTestId("world-land-layer")).toBeInTheDocument();
    expect(screen.getByTestId("track-line")).toBeInTheDocument();
    expect(screen.getByText(/T\+00 · SYNTHETIC EVENT/)).toBeInTheDocument();
  });
});

describe("TimelineBar (forecast time machine)", () => {
  const times = ["2000-09-01T00:00:00Z", "2000-09-01T06:00:00Z", "2000-09-01T12:00:00Z"];
  beforeEach(() => useTimeline.setState({ leads: [0, 6, 12], index: 0, playing: false, speed: 1 }));
  const r = (): ReturnType<typeof render> => render(<Tooltip.Provider><TimelineBar validTimes={times} peakLead={6} extrapolationHours={[54, 60]} /></Tooltip.Provider>);

  it("shows UTC and IST valid times and marks the peak lead", () => {
    r();
    expect(screen.getByTestId("valid-time")).toHaveTextContent("T+00 · 2000-09-01 00:00 UTC · 2000-09-01 05:30 IST");
    expect(screen.getByRole("button", { name: /T\+06 \(peak intensity\)/ })).toBeInTheDocument();
    expect(screen.getByText(/extrapolation/)).toBeInTheDocument();
  });
  it("step, direct selection and slider all drive the same store", async () => {
    r();
    await userEvent.click(screen.getByRole("button", { name: "Step forward" }));
    expect(useTimeline.getState().index).toBe(1);
    await userEvent.click(screen.getByRole("button", { name: /T\+12/ }));
    expect(useTimeline.getState().index).toBe(2);
    expect(screen.getByRole("button", { name: "Step forward" })).toBeDisabled();
    fireEvent.change(screen.getByRole("slider", { name: "Forecast lead time" }), { target: { value: "0" } });
    expect(useTimeline.getState().index).toBe(0);
    expect(screen.getByRole("button", { name: "Step back" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /T\+00/ })).toHaveAttribute("aria-pressed", "true");
  });
  it("play advances frames on a timer and stops at the end", () => {
    vi.useFakeTimers();
    r();
    act(() => useTimeline.getState().toggle());
    expect(screen.getByRole("button", { name: "Pause forecast" })).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(1200); });
    expect(useTimeline.getState().index).toBe(1);
    act(() => { vi.advanceTimersByTime(5000); });
    expect(useTimeline.getState()).toMatchObject({ index: 2, playing: false });
    vi.useRealTimers();
  });
});
