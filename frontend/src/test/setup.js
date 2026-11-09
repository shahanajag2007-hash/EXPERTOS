import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom lacks these browser APIs.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}
Element.prototype.scrollIntoView = vi.fn();
window.scrollTo = vi.fn();

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  vi.restoreAllMocks();
});
