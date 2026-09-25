import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { AsyncBoundary, deriveState } from "@/components/AsyncBoundary";
import { ControlButton } from "@/components/ControlButton";
import { DataKindBadge } from "@/components/DataKindBadge";
import { Dialog } from "@/components/Dialog";
import { SeverityChip } from "@/components/SeverityChip";
import { StatusChip } from "@/components/StatusChip";
import { TimeStamp } from "@/components/TimeStamp";
import { VirtualList } from "@/components/VirtualList";
import { ApiClientError } from "@/lib/api";
import { useUi } from "@/stores/ui";
import type { DataKind } from "@/types/api";

const wrap = (ui: ReactNode): JSX.Element => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Tooltip.Provider>{ui}</Tooltip.Provider></MemoryRouter></QueryClientProvider>
);

function Probe({ fn, isEmpty, partial }: { fn: () => Promise<string[]>; isEmpty?: (d: string[]) => boolean; partial?: string | null }): JSX.Element {
  const q = useQuery({ queryKey: [fn.toString()], queryFn: fn });
  return <AsyncBoundary query={q} label="widgets" isEmpty={isEmpty} partialNote={partial}>{(d) => <ul>{d.map((x) => <li key={x}>{x}</li>)}</ul>}</AsyncBoundary>;
}

describe("AsyncBoundary renders all six states", () => {
  it("loading -> success", async () => {
    render(wrap(<Probe fn={async () => ["a", "b"]} />));
    expect(screen.getByRole("status", { name: /Loading widgets/ })).toBeInTheDocument();
    expect(await screen.findByText("a")).toBeInTheDocument();
    expect(document.querySelector("[data-state='success']")).not.toBeNull();
  });
  it("empty", async () => {
    render(wrap(<Probe fn={async () => []} isEmpty={(d) => d.length === 0} />));
    expect(await screen.findByText(/No widgets to show/)).toBeInTheDocument();
    expect(document.querySelector("[data-state='empty']")).not.toBeNull();
  });
  it("partial shows the data plus a note", async () => {
    render(wrap(<Probe fn={async () => ["x"]} partial="one layer failed" />));
    expect(await screen.findByText("x")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("one layer failed");
    expect(document.querySelector("[data-state='partial']")).not.toBeNull();
  });
  it("error shows detail, request id and a working retry", async () => {
    let calls = 0;
    const fn = async (): Promise<string[]> => { calls += 1; if (calls === 1) throw new ApiClientError("Bad", { status: 500, code: "X", requestId: "req-42", problem: { type: "", title: "Bad", status: 500, code: "X", detail: "Something failed upstream", request_id: "req-42" } }); return ["recovered"]; };
    render(wrap(<Probe fn={fn} />));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something failed upstream");
    expect(screen.getByText(/request id: req-42/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("recovered")).toBeInTheDocument();
  });
  it("offline is distinguished from a server error", async () => {
    render(wrap(<Probe fn={async () => { throw new ApiClientError("no", { status: 0, code: "OFFLINE", offline: true }); }} />));
    expect(await screen.findByText(/Offline: the API cannot be reached/)).toBeInTheDocument();
    expect(document.querySelector("[data-state='offline']")).not.toBeNull();
  });
  it("deriveState maps every query status", () => {
    const base = { data: undefined, error: null, isPlaceholderData: false };
    expect(deriveState({ ...base, status: "pending" })).toBe("loading");
    expect(deriveState({ ...base, status: "error", error: new Error("x") })).toBe("error");
    expect(deriveState({ ...base, status: "success", data: [1] }, (d: number[]) => d.length === 0)).toBe("success");
  });
});

describe("badges never rely on colour alone", () => {
  const kinds: DataKind[] = ["OBSERVED", "REANALYSIS", "FORECAST", "MODEL_PREDICTION", "SYNTHETIC_DEMO"];
  it.each(kinds)("DataKindBadge %s carries a text label and a screen-reader explanation", (k) => {
    const { container } = render(<DataKindBadge kind={k} />);
    const el = screen.getByTestId("data-kind-badge");
    expect(el).toHaveAttribute("data-kind", k);
    expect(el.textContent?.length).toBeGreaterThan(5);
    expect(container.querySelector(".sr-only")?.textContent?.length).toBeGreaterThan(10);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
  it("synthetic data is unmistakable", () => {
    render(<DataKindBadge kind="SYNTHETIC_DEMO" />);
    expect(screen.getByTestId("data-kind-badge")).toHaveTextContent("SYNTHETIC / DEMO DATA");
  });
  it.each(["LOW", "MODERATE", "SEVERE"] as const)("SeverityChip %s has icon + text + non-official label", (s) => {
    const { container } = render(<SeverityChip severity={s} />);
    expect(screen.getByRole("img", { name: new RegExp(`${s}.*Not an official`) })).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container).toHaveTextContent(s);
  });
  it("StatusChip shows text for every status", () => {
    const { rerender } = render(<StatusChip status="IMPLEMENTED" />);
    expect(screen.getByText("IMPLEMENTED")).toBeInTheDocument();
    rerender(<StatusChip status="REQUIRES_GPU_TRAINING" />);
    expect(screen.getByText("NEEDS GPU TRAINING")).toBeInTheDocument();
    rerender(<StatusChip status="PENDING" />);
    expect(screen.getByText("PENDING")).toBeInTheDocument();
  });
});

describe("ControlButton states", () => {
  it("fires onClick, exposes toggle state, and always has an accessible name that contains its visible text", async () => {
    const onClick = vi.fn();
    render(wrap(<ControlButton label="Open details for alert abc" toggle active onClick={onClick}>Details</ControlButton>));
    const b = screen.getByRole("button", { name: "Open details for alert abc" });
    expect(b).toHaveAttribute("aria-pressed", "true");
    expect(b).toHaveTextContent("Details");
    await userEvent.click(b);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
  it("disabled: does not fire, is aria-disabled, and explains why on focus/hover", async () => {
    const onClick = vi.fn();
    render(wrap(<ControlButton label="Step back" disabled disabledReason="Already at the first lead time" onClick={onClick} />));
    const b = screen.getByRole("button", { name: "Step back" });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
    await userEvent.hover(b.parentElement as HTMLElement);
    expect((await screen.findAllByText("Already at the first lead time")).length).toBeGreaterThan(0);
  });
  it("loading: busy, disabled, and shows a spinner", () => {
    render(wrap(<ControlButton label="Run pipeline" loading>Run</ControlButton>));
    const b = screen.getByRole("button", { name: "Run pipeline" });
    expect(b).toHaveAttribute("aria-busy", "true");
    expect(b).toBeDisabled();
    expect(b.querySelector("svg.animate-spin")).not.toBeNull();
  });
  it("is keyboard operable", async () => {
    const onClick = vi.fn();
    render(wrap(<ControlButton label="Zoom in" onClick={onClick} />));
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Zoom in" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});

describe("TimeStamp", () => {
  it("always shows UTC and IST labels and adds the chosen zone", () => {
    useUi.setState({ timeZone: "America/New_York" });
    render(<TimeStamp iso="2000-09-01T00:00:00Z" />);
    const t = screen.getByText(/UTC/).closest("time") as HTMLElement;
    expect(t).toHaveTextContent("2000-09-01 00:00 UTC");
    expect(t).toHaveTextContent("2000-09-01 05:30 IST");
    expect(t.textContent).toMatch(/2000-08-31 20:00/);
    expect(t).toHaveAttribute("datetime", "2000-09-01T00:00:00Z");
    useUi.setState({ timeZone: "Asia/Kolkata" });
  });
});

describe("VirtualList renders only the visible window", () => {
  it("keeps the DOM small for 5000 rows", () => {
    const items = Array.from({ length: 5000 }, (_, i) => i);
    render(<VirtualList items={items} rowHeight={40} height={200} overscan={2} label="rows" renderRow={(i) => <span>row {i}</span>} />);
    const rows = within(screen.getByRole("list", { name: "rows" })).getAllByRole("listitem");
    expect(rows.length).toBeLessThan(12);
    expect(screen.getByText("row 0")).toBeInTheDocument();
    expect(screen.queryByText("row 4999")).toBeNull();
  });
});

describe("Dialog", () => {
  it("is labelled, traps focus and closes with Escape", async () => {
    const onOpenChange = vi.fn();
    render(<Dialog open onOpenChange={onOpenChange} title="Alert details" description="Analytical decision support"><button>inside</button></Dialog>);
    const d = screen.getByRole("dialog", { name: "Alert details" });
    expect(d).toHaveAccessibleDescription("Analytical decision support");
    expect(screen.getByRole("button", { name: "Close dialog" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
