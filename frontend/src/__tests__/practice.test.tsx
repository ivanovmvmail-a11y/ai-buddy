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
  useSession.setState({ userId, internPick: null });
  render(<Providers><Home /></Providers>);
}

const row = async (title: string) => (await screen.findByText(title)).closest("li")!;

describe("задание на практике (спека 107)", () => {
  it("стажёр сдаёт задание: сначала подсказка, потом «выполнено» с документом", async () => {
    open("intern-anya");
    const item = await row("Практикум: ветки и pull request");
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Сдать задание" })));
    const form = within(item).getByRole("form", { name: "Задание: Практикум: ветки и pull request" });
    expect(within(form).getByText(/Создай учебную ветку, коммит и pull request/)).toBeTruthy();
    const check = within(form).getByRole("button", { name: "Проверить" }) as HTMLButtonElement;
    expect(check.disabled).toBe(true); // пустой ответ не отправляется

    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "создала ветку и открыла PR" } });
    await act(async () => fireEvent.click(check));
    expect((await within(form).findByRole("status")).textContent).toMatch(/Почти/);

    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "создала ветку, сделала коммит, открыла PR" } });
    await act(async () => fireEvent.click(check));
    const status = await within(form).findByText(/Задание выполнено/);
    expect(status.textContent).toMatch(/«Готово»/);
    expect(within(form).getByText(/Учебный репозиторий — клонирование и ветки/)).toBeTruthy();
    expect(srv.calls.filter((c) => c.path.endsWith("/practice"))).toHaveLength(2);

    await act(async () => fireEvent.click(within(form).getByRole("button", { name: "Закрыть" })));
    expect(within(item).queryByRole("form")).toBeNull();
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
