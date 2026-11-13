"use client";

// Переключатель темы (Миша, 13.11). По умолчанию — как в системе; выбор запоминается в браузере (удобство одного
// зрителя). better-ui: на время смены темы переходы выключены — иначе все цвета анимируются разом и «смазываются».
import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const KEY = "ai-buddy-theme";

function current(): Theme {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(theme: Theme) {
  const root = document.documentElement;
  const style = document.createElement("style");
  style.textContent = "*,*::before,*::after{transition:none!important}";
  document.head.appendChild(style);
  root.dataset.theme = theme;
  void getComputedStyle(root).color; // применить стили до возврата переходов
  requestAnimationFrame(() => style.remove());
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* приватное окно — тема просто не запомнится */
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);
  useEffect(() => setTheme(current()), []);
  if (!theme) return <span className="size-9" aria-hidden />;
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      onClick={() => {
        apply(next);
        setTheme(next);
      }}
      aria-label={next === "dark" ? "Тёмная тема" : "Светлая тема"}
      title={next === "dark" ? "Тёмная тема" : "Светлая тема"}
      className="grid size-9 place-items-center rounded-full text-foreground/75 hover:bg-surface-2 hover:text-foreground"
    >
      <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
        {next === "dark" ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
        ) : (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2.5v2M12 19.5v2M4.5 12h-2M21.5 12h-2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
          </>
        )}
      </svg>
    </button>
  );
}
