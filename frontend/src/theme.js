import { useEffect, useState } from "react";

// Light/dark theme. The class on <html> is first set by the inline script in
// index.html (before React loads) so pages never flash the wrong theme.
// With no saved preference, the operating system's setting is followed.

export const THEME_KEY = "expertos.theme";

const media = () => window.matchMedia?.("(prefers-color-scheme: dark)");

export function storedTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function systemTheme() {
  return media()?.matches ? "dark" : "light";
}

export function currentTheme() {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function applyTheme(theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  window.dispatchEvent(new CustomEvent("expertos:theme", { detail: theme }));
}

export function setTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Not persisted (e.g. private mode); still applies for this page view.
  }
  applyTheme(theme);
}

export function useTheme() {
  const [theme, setThemeState] = useState(currentTheme);

  useEffect(() => {
    const onTheme = (e) => setThemeState(e.detail);
    window.addEventListener("expertos:theme", onTheme);

    // Follow OS changes only while the user hasn't chosen a theme.
    const mq = media();
    const onSystem = () => {
      if (!storedTheme()) applyTheme(systemTheme());
    };
    mq?.addEventListener?.("change", onSystem);

    return () => {
      window.removeEventListener("expertos:theme", onTheme);
      mq?.removeEventListener?.("change", onSystem);
    };
  }, []);

  return {
    theme,
    toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark"),
  };
}
