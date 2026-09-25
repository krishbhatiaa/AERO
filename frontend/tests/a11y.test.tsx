import { render } from "@testing-library/react";
import axe from "axe-core";
import * as Tooltip from "@radix-ui/react-tooltip";

import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { ControlButton } from "@/components/ControlButton";
import { DataKindBadge } from "@/components/DataKindBadge";
import { Panel, KV } from "@/components/Panel";
import { SeverityChip } from "@/components/SeverityChip";
import { StatusChip } from "@/components/StatusChip";
import tokens from "@/styles/token-values.json";

async function violations(container: HTMLElement): Promise<string[]> {
  const r = await axe.run(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } }); // contrast is checked on tokens below and in the real browser
  return r.violations.map((v) => `${v.id}: ${v.help} :: ${v.nodes.map((n) => n.html.slice(0, 140)).join(" | ")}`);
}

describe("axe: no automated accessibility violations", () => {
  it("controls, chips and panels", async () => {
    const { container } = render(
      <Tooltip.Provider>
        <Panel title="Event monitor"><dl><KV k="Peak" v="222 mm/6h" /></dl></Panel>
        <ControlButton label="Play forecast" toggle active>PLAY</ControlButton>
        <ControlButton label="Step back" disabled disabledReason="At first lead" />
        <ControlButton label="Run" loading />
        <SeverityChip severity="SEVERE" /><DataKindBadge kind="SYNTHETIC_DEMO" /><StatusChip status="REQUIRES_GPU_TRAINING" />
      </Tooltip.Provider>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("charts (svg + table alternative)", async () => {
    const { container } = render(<><LineChart title="t" description="d" unit="u" xLabel="x" series={[{ name: "s", color: "red", points: [{ x: 0, y: 1 }, { x: 1, y: 2 }] }]} /><BarChart title="b" description="d" unit="u" bars={[{ label: "a", value: -1 }]} /></>);
    expect(await violations(container)).toEqual([]);
  });
});

// WCAG relative luminance / contrast ratio
function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * (c[0] ?? 0) + 0.7152 * (c[1] ?? 0) + 0.0722 * (c[2] ?? 0);
}
const ratio = (a: string, b: string): number => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return ((x ?? 0) + 0.05) / ((y ?? 0) + 0.05); };
const SEV = { light: { low: "#475569", moderate: "#a16207", severe: "#b91c1c" }, dark: { low: "#94a3b8", moderate: "#facc15", severe: "#f87171" } };

describe("WCAG 2.2 AA colour contrast of the design tokens (normal text >= 4.5:1)", () => {
  for (const theme of ["light", "dark"] as const) {
    const t = tokens[theme] as Record<string, string>;
    const pairs: [string, string][] = [
      ["on-surface", "surface"], ["on-surface", "surface-container-lowest"], ["on-surface", "surface-container-low"], ["on-surface-variant", "surface"],
      ["on-surface-variant", "surface-container-lowest"], ["on-surface-variant", "surface-container-low"], ["on-surface-variant", "surface-container"],
      ["primary", "surface"], ["primary", "surface-container-lowest"], ["primary", "surface-container-low"], ["on-primary", "primary"],
      ["error", "surface-container-lowest"], ["error", "surface"], ["tertiary", "surface-container-lowest"], ["secondary", "surface-container-lowest"],
      ["on-error-container", "error-container"], ["inverse-on-surface", "inverse-surface"],
    ];
    it.each(pairs)(`${theme}: %s on %s`, (fg, bg) => {
      expect(ratio(t[fg] as string, t[bg] as string)).toBeGreaterThanOrEqual(4.5);
    });
    it.each(Object.entries(SEV[theme]))(`${theme}: severity ${"%s"} text on the panel background`, (_k, hex) => {
      expect(ratio(hex, t["surface-container-lowest"] as string)).toBeGreaterThanOrEqual(4.5);
    });
  }
});
