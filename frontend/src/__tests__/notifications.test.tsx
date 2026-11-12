// SPEC 3.6 (11.11): единые уведомления — одна кнопка-действие по типу, факты без «Напомнить завтра».
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { useChat } from "@/lib/chat";
import { actionLabel, isInfo, kindOf, sectionFor, targetOf } from "@/lib/notifications";
import { useSession } from "@/lib/store";
import type { Reminder } from "@/lib/types";
import { installFakeServer, type FakeServer } from "./fake/server";

let srv: FakeServer;
beforeEach(() => {
  srv = installFakeServer();
  useChat.getState().reset([]);
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function open(userId: string) {
  useSession.setState({ userId, internPick: null });
  render(<Providers><Home /></Providers>);
}

const note = (patch: Partial<Reminder>): Reminder => ({
  id: "REM-x", user_id: "intern-anya", kind: "skill_changed", action: { label: "Открыть", target: "plan" },
  intern_id: "intern-anya", absence_request_id: null, suggestion_id: null, plan_item_id: null, request_id: null,
  text: "Наставник отметил: Git — знаком. План обновился", status: "active", created_day: 2, snooze_until_day: null,
  ...patch,
});

async function bell() {
  const button = await screen.findByRole("button", { name: /Напоминания: \d/ });
  await act(async () => fireEvent.click(button));
  return screen.getByRole("dialog", { name: "Напоминания" });
}

describe("логика уведомлений", () => {
  it("старое напоминание без kind — как раньше: в чат", () => {
    const old = note({ kind: undefined, action: undefined, request_id: "REQ-1" });
    expect([kindOf(old), targetOf(old), actionLabel(old), isInfo(old), sectionFor(old)])
      .toEqual(["access_request", "access_request", "Открыть в чате", false, null]);
  });

  it("куда ведёт каждое действие", () => {
    expect(sectionFor(note({ kind: "skill_suggestion", action: { label: "Решить", target: "skill_suggestion" } }))).toBe("Предложения бота");
    expect(sectionFor(note({ kind: "absence_new", action: { label: "Решить", target: "absence_request" } }))).toBe("Заявки на отгул");
    expect(sectionFor(note({ kind: "absence_pending", action: { label: "Напомнить", target: "absence_request" } }))).toBeNull();
    expect(sectionFor(note({ kind: "absence_fact", action: { label: "Открыть", target: "intern" } }))).toBe("Мои стажёры");
  });
});

describe("колокольчик и сообщения бота (SPEC 3.6)", () => {
  it("стажёр: «Наставник отметил…» — одна кнопка «Открыть», без «Напомнить завтра»; после открытия уходит", async () => {
    srv.state.notifications.push(note({}));
    open("intern-anya");
    expect(await screen.findByText("🔔 Наставник отметил: Git — знаком. План обновился")).toBeTruthy();
    const dialog = await bell();
    const item = within(dialog).getByText(/Наставник отметил/).closest("li")!;
    expect(within(item).queryByRole("button", { name: "Напомнить завтра" })).toBeNull();
    expect(within(item).getAllByRole("button")).toHaveLength(1); // проверка 12.11: одна кнопка, без «Готово»
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Открыть" })));
    await waitFor(() => expect(srv.calls.some((c) => c.path === "/reminders/REM-x/done")).toBe(true));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Напоминания: \d/ })).toBeNull());
  });

  it("«В план добавлен пункт…» уходит из колокольчика после «Открыть», хотя ведёт в чат", async () => {
    srv.state.notifications.push(note({
      id: "REM-p", kind: "personal_item_added", action: { label: "Открыть", target: "plan_item" },
      text: "В план добавлен пункт для тебя: Практикум: SQL (добавил наставник)",
    }));
    open("intern-anya");
    const dialog = await bell();
    const item = within(dialog).getByText(/В план добавлен пункт/).closest("li")!;
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Открыть" })));
    await waitFor(() => expect(srv.calls.some((c) => c.path === "/reminders/REM-p/done")).toBe(true));
  });

  it("наставник: «Бот предлагает…» — «Решить» ведёт к блоку предложений и не закрывает уведомление", async () => {
    srv.state.suggestions.push({
      id: "sug_1", intern_id: "intern-anya", intern_name: "Аня Смирнова", topic: "git", topic_title: "Git",
      from_level: "novice", to_level: "familiar", basis: "закрыто 2 пункта по теме Git", created_day: 4,
      status: "pending", decided_day: null,
    });
    srv.state.notifications.push(note({
      id: "REM-s", user_id: "mentor-petr", kind: "skill_suggestion", action: { label: "Решить", target: "skill_suggestion" },
      suggestion_id: "sug_1", text: "Бот предлагает поднять уровень: Аня Смирнова, Git (закрыто 2 пункта по теме Git)",
    }));
    open("mentor-petr");
    const dialog = await bell();
    const item = within(dialog).getByText(/Бот предлагает/).closest("li")!;
    expect(within(item).getByRole("button", { name: "Напомнить завтра" })).toBeTruthy();
    expect(within(item).queryByRole("button", { name: "Готово" })).toBeNull();
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Решить" })));
    expect(await screen.findByRole("region", { name: "Предложения бота" })).toBeTruthy();
    expect(srv.calls.some((c) => c.path === "/reminders/REM-s/done")).toBe(false);
  });

  it("стажёр: заявка на отгул ждёт — «Напомнить» даёт черновик сообщения руководителю", async () => {
    srv.state.notifications.push(note({
      id: "REM-a", kind: "absence_pending", action: { label: "Напомнить", target: "absence_request" },
      absence_request_id: "ABS-1", text: "Заявка на отгул ждёт решения 2 дня — напомнить руководителю?",
    }));
    open("intern-anya");
    const msg = (await screen.findByText(/Заявка на отгул ждёт решения 2 дня/)).closest("div")!.parentElement!;
    await act(async () => fireEvent.click(within(msg).getByRole("button", { name: "Написать руководителю" })));
    expect(await screen.findByText(/Черновик сообщения руководителю \(Ольга Новикова\)/)).toBeTruthy();

    const dialog = await bell();
    const item = within(dialog).getByText(/Заявка на отгул ждёт/).closest("li")!;
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Напомнить" })));
    await waitFor(() => expect(screen.getAllByText(/Черновик сообщения руководителю/)).toHaveLength(2));
  });

  it("наставник: «Аня отсутствует 12.11» — открывает карточку стажёра", async () => {
    srv.state.notifications.push(note({
      id: "REM-f", user_id: "mentor-petr", kind: "absence_fact", action: { label: "Открыть", target: "intern" },
      text: "Аня Смирнова отсутствует 12.11",
    }));
    open("mentor-petr");
    const dialog = await bell();
    await act(async () => fireEvent.click(within(dialog).getByRole("button", { name: "Открыть" })));
    await waitFor(() => expect(srv.calls.some((c) => c.path === "/reminders/REM-f/done")).toBe(true));
    expect(useSession.getState().internPick).toBe("intern-anya");
  });
});
