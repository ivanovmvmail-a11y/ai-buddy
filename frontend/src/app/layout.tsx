import type { Metadata, Viewport } from "next";
// Шрифт хранится в проекте (npm-пакет), а не грузится с Google Fonts:
// сборка работает без интернета (Codex cloud) и не зависит от доступности Google.
import "@fontsource-variable/inter";
import "./globals.css";
// Панель замечаний по интерфейсу для разработки (agentation): только в `npm run dev`, в сборку для экспертов не попадает.
import { Agentation } from "agentation";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "AI-buddy",
  description: "ИИ-помощник для стажёров",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className="antialiased">
        <Providers>{children}</Providers>
        {process.env.NODE_ENV === "development" && <Agentation endpoint="http://localhost:4747" />}
      </body>
    </html>
  );
}
