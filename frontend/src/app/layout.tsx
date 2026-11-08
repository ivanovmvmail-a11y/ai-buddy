import type { Metadata, Viewport } from "next";
// Шрифт хранится в проекте (npm-пакет), а не грузится с Google Fonts:
// сборка работает без интернета (Codex cloud) и не зависит от доступности Google.
import "@fontsource-variable/inter";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI-buddy",
  description: "ИИ-помощник для стажёров",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
