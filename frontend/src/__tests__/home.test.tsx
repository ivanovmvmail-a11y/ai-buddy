// Редизайн 13.11: «Главная» стажёра — карточки; одна главная кнопка у «Следующего шага» (Миша: «слишком много
// кнопок, главные сливаются»). Тёмная колонка слева — профиль с прогрессом и разделы.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import { installFakeServer, type FakeServer } from "./fake/server";

let srv: FakeServer;
beforeEach(() => {
  srv = installFakeServer();
  useChat.getState().reset([]);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function open(userId = "intern-anya") {
  useSession.setState({ userId, internPick: null, section: "home" });
  render(<Providers><Home /></Providers>);
}

describe("«Главная» стажёра", () => {
  it("следующий шаг — одной главной кнопкой; рядом только ссылка «Объяснить»", async () => {
    open();
    const step = await screen.findByRole("region", { name: "Следующий шаг" });
    expect(within(step).getByRole("heading", { name: /Запросить доступ|Запросить базовые/ })).toBeTruthy();
    const buttons = within(step).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Сделать за меня", "Объяснить, что делать"]);
    await act(async () => fireEvent.click(buttons[0]));
    expect(await screen.findByText(/на чтение выдан/)).toBeTruthy(); // простой доступ — в один клик
  });

  it("прогресс, команда и переход к плану", async () => {
    open();
    const progress = await screen.findByRole("region", { name: "Прогресс адаптации" });
    expect(within(progress).getByText(/Закрыто \d+ из \d+/)).toBeTruthy();
    const team = screen.getByRole("region", { name: "Моя команда" });
    expect(within(team).getByText("Пётр Волков")).toBeTruthy();
    expect(within(team).getByText(/HR BP/)).toBeTruthy();
    await act(async () => fireEvent.click(within(progress).getByRole("button", { name: "Весь план →" })));
    expect(await screen.findByRole("heading", { name: "Мой план" })).toBeTruthy();
  });

  it("левая колонка: профиль, день и разделы; демо-панель внизу", async () => {
    open();
    const profile = await screen.findByRole("region", { name: "Профиль" });
    expect(within(profile).getByText("Аня Смирнова")).toBeTruthy();
    expect(await within(profile).findByText("День 2")).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "Разделы" });
    expect(within(nav).getByRole("button", { name: "Главная" }).getAttribute("aria-current")).toBe("page");
    expect(within(screen.getByRole("region", { name: "Демо-панель" })).getByLabelText("Войти как")).toBeTruthy();
  });

  it("у наставника нет «Главной» стажёра — сразу его экран", async () => {
    open("mentor-petr");
    expect(await screen.findByRole("region", { name: "Мои стажёры" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Следующий шаг" })).toBeNull();
    expect(srv.calls.length).toBeGreaterThan(0);
  });
});

describe("переключатель темы", () => {
  it("переключает и запоминает тему", async () => {
    open();
    const btn = await screen.findByRole("button", { name: /тема$/ });
    const before = btn.getAttribute("aria-label");
    await act(async () => fireEvent.click(btn));
    const theme = document.documentElement.dataset.theme;
    expect(theme === "dark" || theme === "light").toBe(true);
    expect(localStorage.getItem("ai-buddy-theme")).toBe(theme);
    expect(screen.getByRole("button", { name: /тема$/ }).getAttribute("aria-label")).not.toBe(before);
    delete document.documentElement.dataset.theme;
  });
});
