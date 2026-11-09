import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";
import { applyTheme, storedTheme, systemTheme, THEME_KEY } from "../theme";

function renderNavbar() {
  return render(
    <MemoryRouter>
      <Navbar />
    </MemoryRouter>,
  );
}

describe("Theme", () => {
  it("toggle switches to dark, persists the choice and updates its label", async () => {
    renderNavbar();
    await userEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));

    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
  });

  it("reads an existing preference applied before load", () => {
    applyTheme("dark");
    renderNavbar();
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
  });

  it("falls back to the operating system preference", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} });
    expect(storedTheme()).toBeNull();
    expect(systemTheme()).toBe("dark");
  });

  it("ignores invalid stored values", () => {
    localStorage.setItem(THEME_KEY, "purple");
    expect(storedTheme()).toBeNull();
  });
});
