import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BarChart } from "@/components/charts/BarChart";
import { LineChart, niceTicks } from "@/components/charts/LineChart";

describe("niceTicks", () => {
  it("always includes ticks at or beyond both data extremes (regression: axis stopped below the peak)", () => {
    for (const [lo, hi] of [[30, 222], [0, 1], [-74, -28], [0.31, 0.84], [5, 5.0001], [-3, 250]] as const) {
      const t = niceTicks(lo, hi);
      expect(t[0]).toBeLessThanOrEqual(lo);
      expect(t[t.length - 1]).toBeGreaterThanOrEqual(hi);
      expect(t.every((v, i) => i === 0 || v > (t[i - 1] ?? -Infinity))).toBe(true);
    }
  });
  it("handles degenerate and non-finite ranges", () => {
    expect(niceTicks(3, 3)).toEqual([2, 3, 4]);
    expect(niceTicks(NaN, 1)).toEqual([0, 1]);
  });
});

describe("charts are accessible", () => {
  const series = [{ name: "peak", color: "red", points: [{ x: 0, y: 70 }, { x: 6, y: 111 }, { x: 12, y: null }] }];
  it("LineChart exposes an accessible label, legend and a table alternative", async () => {
    render(<LineChart title="Intensity vs time" description="desc" unit="mm/6h" xLabel="lead" series={series} yDigits={0} />);
    expect(screen.getByRole("img", { name: /Intensity vs time/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /table/i }));
    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /peak \(mm\/6h\)/ })).toBeInTheDocument();
    expect(screen.getByText("111")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0); // missing value shown explicitly, not as 0
  });
  it("BarChart shows negative values and confidence intervals in its table", async () => {
    render(<BarChart title="Peak error" description="d" unit="mm" bars={[{ label: "nearest", value: -47.4, ci: [-60, -30] }, { label: "bicubic", value: -28.7 }]} />);
    await userEvent.click(screen.getByRole("button", { name: /table/i }));
    expect(screen.getByText("-47.4")).toBeInTheDocument();
    expect(screen.getByText("-60.0 to -30.0")).toBeInTheDocument();
  });
});
