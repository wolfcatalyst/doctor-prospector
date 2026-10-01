import { create } from "zustand";

export type Theme = "light" | "dark" | "grey";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

function getInitialTheme(): Theme {
  const stored = localStorage.getItem("dg-theme");
  if (stored === "light" || stored === "dark" || stored === "grey") {
    return stored;
  }
  return "light";
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: getInitialTheme(),

  setTheme: (theme) => {
    localStorage.setItem("dg-theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
    set({ theme });
  },
}));

// Apply theme on module load (before first render)
document.documentElement.setAttribute("data-theme", getInitialTheme());
