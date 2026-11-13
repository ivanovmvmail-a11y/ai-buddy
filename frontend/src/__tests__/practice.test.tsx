// Спека 107: «Сдать задание» — ответ на задание на практике проверяется по документу пункта.
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

function open(userId: string) {
  useSession.setState({ userId, internPick: null , section: "plan" });
  render(<Providers><Home /></Providers>);
}

const row = async (title: string) => (await screen.findByText(title)).closest("li")!;

describe("задание на практике (спека 107)", () => {
  it("стажёр сдаёт задание в чате (чекпоинт 2): задание, подсказка, потом «выполнено» с документом", async () => {
    open("intern-anya");
    const item = await row("Практикум: ветки и pull request");
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Сдать задание" })));
    expect(await screen.findByText(/Задание: Создай учебную ветку, коммит и pull request/)).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(/Сдаёшь задание: «Практикум: ветки и pull request»/);
    const input = screen.getByRole("textbox", { name: "Ответ на задание" });

    fireEvent.change(input, { target: { value: "создала ветку и открыла PR" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
    expect(await screen.findByText(/Почти/)).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Ответ на задание" })).toBeTruthy(); // режим сдачи остаётся

    fireEvent.change(screen.getByRole("textbox", { name: "Ответ на задание" }), { target: { value: "создала ветку, сделала коммит, открыла PR" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
    const done = await screen.findByText(/Задание выполнено/);
    expect(done.textContent).toMatch(/«Готово»/);
    expect(screen.getAllByText(/Учебный репозиторий — клонирование и ветки/).length).toBeGreaterThan(0);
    expect(srv.calls.filter((c) => c.path.endsWith("/practice"))).toHaveLength(2);
    expect(screen.getByRole("textbox", { name: "Сообщение" })).toBeTruthy(); // обычный чат вернулся
  });

  it("сдачу задания можно отменить", async () => {
    open("intern-anya");
    const item = await row("Практикум: ветки и pull request");
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Сдать задание" })));
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Отменить" })));
    expect(screen.getByRole("textbox", { name: "Сообщение" })).toBeTruthy();
    expect(srv.calls.filter((c) => c.path.endsWith("/practice"))).toHaveLength(0);
  });

  it("кнопки нет у пункта без проверяемого задания и у наставника", async () => {
    open("intern-anya");
    const common = await row("Познакомиться с командой");
    expect(within(common).queryByRole("button", { name: "Сдать задание" })).toBeNull();
    cleanup();
    open("mentor-petr");
    await screen.findByRole("region", { name: "Мои стажёры" });
    expect(screen.queryByRole("button", { name: "Сдать задание" })).toBeNull();
  });
});
