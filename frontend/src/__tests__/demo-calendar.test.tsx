// Миша 14.11: «день иногда скачет». Дата демо-календаря одна на всех и видна в демо-панели; при «Войти как» она не
// меняется (меняется номер дня — стажёры вышли в разные даты), а «Следующий день» сдвигает её у всех сразу.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { demoDate } from "@/components/Sidebar";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import { installFakeServer } from "./fake/server";

beforeEach(() => {
  installFakeServer();
  useChat.getState().reset([]);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const panel = () => screen.getByRole("region", { name: "Демо-панель" });

describe("демо-календарь", () => {
  it("формат даты без сдвига часового пояса", () => {
    expect(demoDate("2026-11-11")).toBe("ср, 11.11");
    expect(demoDate("2026-11-04", false)).toBe("04.11");
  });

  it("дата одна на всех: при «Войти как» не меняется, «Следующий день» сдвигает её", async () => {
    useSession.setState({ userId: "intern-anya", internPick: null, section: "home" });
    render(<Providers><Home /></Providers>);
    expect(await within(panel()).findByText("ср, 11.11")).toBeTruthy();
    expect(await screen.findByText(/с 10\.11/)).toBeTruthy(); // Аня вышла 10.11 — поэтому у неё день 2

    await act(async () => fireEvent.change(within(panel()).getByRole("combobox"), { target: { value: "intern-ivan" } }));
    expect(await screen.findByText(/с 04\.11/)).toBeTruthy(); // у Ивана день 8, а дата та же
    expect(within(panel()).getByText("ср, 11.11")).toBeTruthy();

    await act(async () => fireEvent.click(within(panel()).getByRole("button", { name: "Следующий день" })));
    expect(await within(panel()).findByText("чт, 12.11")).toBeTruthy();
  });
});
