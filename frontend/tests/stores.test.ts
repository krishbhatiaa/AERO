import { currentLead, useTimeline } from "@/stores/timeline";
import { useUi } from "@/stores/ui";

const reset = (): void => useTimeline.setState({ leads: [0, 6, 12, 18], index: 0, playing: false, speed: 1 });

describe("timeline store (single source of truth for forecast time)", () => {
  beforeEach(reset);
  it("steps within bounds and never goes out of range", () => {
    useTimeline.getState().step(-1);
    expect(useTimeline.getState().index).toBe(0);
    useTimeline.getState().step(10);
    expect(useTimeline.getState().index).toBe(3);
    expect(currentLead(useTimeline.getState())).toBe(18);
  });
  it("setLead selects by lead hours and ignores unknown leads", () => {
    useTimeline.getState().setLead(12);
    expect(useTimeline.getState().index).toBe(2);
    useTimeline.getState().setLead(999);
    expect(useTimeline.getState().index).toBe(2);
  });
  it("play at the end restarts from the first lead; play does nothing without data", () => {
    useTimeline.setState({ index: 3 });
    useTimeline.getState().toggle();
    expect(useTimeline.getState()).toMatchObject({ playing: true, index: 0 });
    useTimeline.getState().pause();
    expect(useTimeline.getState().playing).toBe(false);
    useTimeline.setState({ leads: [], index: 0 });
    useTimeline.getState().toggle();
    expect(useTimeline.getState().playing).toBe(false);
  });
  it("setLeads keeps the index valid when the lead list shrinks and is a no-op for identical lists", () => {
    useTimeline.setState({ index: 3 });
    useTimeline.getState().setLeads([0, 6]);
    expect(useTimeline.getState().index).toBe(1);
    const before = useTimeline.getState();
    useTimeline.getState().setLeads([0, 6]);
    expect(useTimeline.getState()).toBe(before);
  });
});

describe("ui store", () => {
  it("toggles layers independently and switches compare/tool/theme", () => {
    const a = useUi.getState().layers.wind;
    useUi.getState().toggleLayer("wind");
    expect(useUi.getState().layers.wind).toBe(!a);
    expect(useUi.getState().layers.precip).toBe(true);
    useUi.getState().setCompare("single");
    useUi.getState().setTool("measure");
    useUi.getState().setTheme("dark");
    expect(useUi.getState()).toMatchObject({ compare: "single", tool: "measure", theme: "dark" });
    expect(window.localStorage.getItem("ewai.theme")).toBe("dark");
    useUi.getState().setTheme("light");
  });
  it("survives unavailable storage (private mode)", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    expect(() => useUi.getState().setTimeZone("UTC")).not.toThrow();
    expect(useUi.getState().timeZone).toBe("UTC");
    spy.mockRestore();
    useUi.getState().setTimeZone("Asia/Kolkata");
  });
});
