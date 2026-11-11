import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const cards = () => screen.findByRole("region", { name: /стажёры/i });

describe("экран наставника (спека 201)", () => {
  it("AC-1, AC-2: Пётр видит только Аню — прогресс, что зависло, сильные стороны", async () => {
    open("mentor-petr");
    const region = await cards();
    expect(within(region).getAllByRole("listitem").filter((li) => li.parentElement?.parentElement === region)).toHaveLength(1);
    await waitFor(() => expect(within(region).getByText(/Недели 1–2: закрыто 1 из 11/)).toBeTruthy());
    expect(within(region).getByText("Ничего не зависло.")).toBeTruthy();
    await waitFor(() => expect(within(region).getByText(/Сильные стороны:/)).toBeTruthy());
    expect(within(region).getByText(/Темы для роста:/)).toBeTruthy();
  });

  it("спека 104: наставник меняет уровень по теме, куратор — нет", async () => {
    open("mentor-petr");
    const region = await cards();
    const git = await within(region).findByRole("combobox", { name: "Уровень: Git" });
    expect((git as HTMLSelectElement).value).toBe("novice");
    expect(within(region).getByRole("combobox", { name: "Уровень: CI и тесты" })).toBeTruthy();
    await act(async () => fireEvent.change(git, { target: { value: "confident" } }));
    await waitFor(() => expect(srv.calls.some((c) => c.method === "POST" && c.path === "/profile/skills")).toBe(true));
    expect(srv.calls.find((c) => c.method === "POST" && c.path === "/profile/skills")?.body).toEqual({
      intern_id: "intern-anya", topic: "git", level: "confident",
    });
    await waitFor(() => expect((within(region).getByRole("combobox", { name: "Уровень: Git" }) as HTMLSelectElement).value).toBe("confident"));
  });

  it("Мария: у Ивана зависли заявка и просроченный пункт", async () => {
    open("mentor-maria");
    const region = await cards();
    await waitFor(() => expect(within(region).getByText(/ждёт: Мария Орлова, 3 дня/)).toBeTruthy());
    expect(within(region).getAllByText(/срок прошёл/).length).toBeGreaterThan(0);
  });

  it("AC-3: итоги недели — факты без оценок", async () => {
    open("mentor-maria");
    const region = await cards();
    await click(await within(region).findByRole("button", { name: /Итоги недели 2/ }));
    expect(await within(region).findByText(/Получено доступов: 1/)).toBeTruthy();
    expect(within(region).getByText(/Закрыто: «Познакомиться с командой»/)).toBeTruthy();
    expect(within(region).getByText(/Переходит дальше:.*«Завести конспект/)).toBeTruthy();
    expect(within(region).getByText(/без оценок/)).toBeTruthy();
  });

  it("AC-2, AC-4: куратор без карты навыков, клик по карточке открывает план", async () => {
    open("curator-dmitry");
    const region = await cards();
    await waitFor(() => expect(within(region).getAllByText(/закрыто/)).toHaveLength(2));
    expect(within(region).queryByText(/Сильные стороны/)).toBeNull();
    expect(srv.calls.some((c) => c.path.startsWith("/profile"))).toBe(false);
    await click(within(region).getByRole("button", { name: /Иван Кузнецов/ }));
    expect(await screen.findByText("План: Иван Кузнецов")).toBeTruthy();
  });

  it("AC-5: стажёр и HR BP блок не видят", async () => {
    open("intern-anya");
    await screen.findByText(/2-й день стажировки/);
    expect(screen.queryByRole("region", { name: /стажёры/i })).toBeNull();
    cleanup();
    open("hrbp-elena");
    await screen.findByText(/для твоей роли недоступны/);
    expect(screen.queryByRole("region", { name: /стажёры/i })).toBeNull();
  });

  it("AC-6: ошибка итогов недели показывается в карточке", async () => {
    open("mentor-petr");
    const region = await cards();
    const btn = await within(region).findByRole("button", { name: /Итоги недели/ });
    const real = vi.mocked(globalThis.fetch).getMockImplementation()!;
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) =>
      String(input).includes("/plan/summary") ? new Response('{"detail":"Сервис итогов недоступен"}', { status: 503 }) : real(input, init));
    await click(btn);
    expect(await within(region).findByText("Сервис итогов недоступен", {}, { timeout: 4000 })).toBeTruthy();
  });
});

const click = (el: HTMLElement) => act(async () => fireEvent.click(el));
