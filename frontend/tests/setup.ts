import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

// jsdom lacks these browser APIs.
class RO {
  constructor(private cb: ResizeObserverCallback) {}
  observe(el: Element): void {
    this.cb([{ target: el, contentRect: { width: 900, height: 560, top: 0, left: 0, bottom: 560, right: 900, x: 0, y: 0, toJSON: () => ({}) } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  unobserve(): void {}
  disconnect(): void {}
}
vi.stubGlobal("ResizeObserver", RO);
if (!window.matchMedia) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false }));
}
HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as unknown as HTMLCanvasElement["getContext"];
Element.prototype.scrollIntoView = vi.fn();

// jsdom has no PointerEvent; a MouseEvent subclass lets Testing Library carry clientX/clientY/button through.
if (typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
    }
  }
  vi.stubGlobal("PointerEvent", PointerEventPolyfill);
}
