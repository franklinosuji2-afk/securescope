import { useCallback, useSyncExternalStore } from "react";

export type Theme = "dark" | "light";
const KEY = "securescope-theme";

function systemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  } catch {
    return "dark";
  }
}

function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage can be blocked; the choice then lasts for this visit only
  }
}

function apply(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  // The browser's own toolbar colour follows the page.
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "light" ? "#eef3f8" : "#050505");
}

/** Fades colours across the page for a moment so the switch is not a hard flash. Skipped for reduced motion. */
function softSwitch(): void {
  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  } catch {
    return;
  }
  const root = document.documentElement;
  root.classList.add("theme-switching");
  window.setTimeout(() => root.classList.remove("theme-switching"), 360);
}

let current: Theme | null = null;
const listeners = new Set<() => void>();

function read(): Theme {
  if (current === null) {
    current = storedTheme() ?? systemTheme();
    apply(current);
  }
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Follows the system setting until the person picks a theme. Every toggle on the page shares one choice. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const theme = useSyncExternalStore(subscribe, read, () => "dark" as Theme);
  const toggle = useCallback(() => {
    const next: Theme = read() === "dark" ? "light" : "dark";
    current = next;
    softSwitch();
    apply(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    listeners.forEach((listener) => listener());
  }, []);
  return { theme, toggle };
}
