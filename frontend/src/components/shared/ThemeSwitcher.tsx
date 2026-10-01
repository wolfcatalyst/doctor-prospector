import { useThemeStore, type Theme } from "../../stores/themeStore";

const themes: { value: Theme; label: string; icon: string }[] = [
  { value: "light", label: "Light", icon: "☀" },
  { value: "dark", label: "Dark", icon: "☾" },
  { value: "grey", label: "Grey", icon: "◐" },
];

export default function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore();

  return (
    <div className="flex items-center rounded-lg border border-gray-200 p-0.5">
      {themes.map((t) => (
        <button
          key={t.value}
          onClick={() => setTheme(t.value)}
          title={t.label}
          className={`rounded-md px-2 py-1 text-sm transition-colors ${
            theme === t.value
              ? "bg-brand-600 text-white"
              : "text-gray-500 hover:text-gray-900"
          }`}
        >
          {t.icon}
        </button>
      ))}
    </div>
  );
}
