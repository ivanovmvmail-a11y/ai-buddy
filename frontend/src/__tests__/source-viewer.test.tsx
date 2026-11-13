// Проверка 12.11: «Источник» открывает документ в окне (раньше ссылка вела на несуществующий адрес).
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Providers } from "@/app/providers";
import { DocumentText, SourceLink } from "@/components/SourceViewer";
import { findUser } from "@/lib/users";
import { installFakeServer, type FakeServer } from "./fake/server";

let srv: FakeServer;
beforeEach(() => {
  srv = installFakeServer();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function link(userId: string, title: string) {
  render(<Providers><p>Источник: <SourceLink actor={findUser(userId)!} title={title} /></p></Providers>);
  const button = screen.getByRole("button", { name: title });
  button.focus(); // в браузере клик ставит фокус на кнопку; в тестовой среде — нет
  return button;
}

describe("окно документа из «Источник»", () => {
  it("открывается по клику, показывает текст и закрывается Escape и кнопкой", async () => {
    const button = link("intern-anya", "Учебный репозиторий — клонирование и ветки");
    await act(async () => fireEvent.click(button));
    const dialog = screen.getByRole("dialog", { name: "Документ: Учебный репозиторий — клонирование и ветки" });
    expect(await within(dialog).findByText("Каждая задача делается в своей ветке.")).toBeTruthy();
    expect(within(dialog).getByText("Общий документ для всех команд", { exact: false })).toBeTruthy();
    expect(within(dialog).getByText("git pull").tagName).toBe("STRONG");
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Закрыть" }));
    expect(srv.calls.some((c) => c.path.startsWith("/documents?title="))).toBe(true);

    await act(async () => fireEvent.keyDown(window, { key: "Escape" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(button);

    await act(async () => fireEvent.click(button));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Закрыть" })));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("документ чужой команды не показывается", async () => {
    const button = link("intern-anya", "Авито Доставка — о команде");
    await act(async () => fireEvent.click(button));
    expect(await screen.findByText(/Документ недоступен/)).toBeTruthy();
    expect(screen.queryByText("Учебный стенд маршрутов.")).toBeNull();
  });

  it("свой документ команды — с подписью команды; клик по фону закрывает", async () => {
    const button = link("intern-ivan", "Авито Доставка — о команде");
    await act(async () => fireEvent.click(button));
    expect(await screen.findByText("Учебный стенд маршрутов.")).toBeTruthy();
    expect(screen.getByText(/Документ команды «Авито Доставка»/)).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByRole("dialog").parentElement!));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("разметка: заголовки, нумерованные пункты, абзацы", () => {
    render(<DocumentText text={"# Заголовок\nПервый абзац\nпродолжение\n\n1. шаг один\n2. шаг два\n\nКонец"} />);
    expect(screen.getByRole("heading", { name: "Заголовок" }).tagName).toBe("H3");
    expect(screen.getByText("Первый абзац продолжение")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Конец")).toBeTruthy();
  });
});
