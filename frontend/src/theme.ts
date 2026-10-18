import { useCallback, useState } from "react";

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
}

/** Follows the system setting until the person picks a theme. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() => {
    const initial = storedTheme() ?? systemTheme();
    apply(initial);
    return initial;
  });
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    apply(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    setTheme(next);
  }, [theme]);
  return { theme, toggle };
}
