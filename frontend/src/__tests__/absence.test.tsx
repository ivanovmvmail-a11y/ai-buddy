// SPEC 3.8 (11.11): отгул на один день — черновик в чате, решение руководителя, наставник видит только дату.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { dayText } from "@/components/AbsencePanel";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import type { AbsenceRequest, Action } from "@/lib/types";
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
  useSession.setState({ userId, internPick: null, section: userId.startsWith("intern") ? "home" : "plan" }); // стажёру блоки — на «Главной»
  render(<Providers><Home /></Providers>);
}

const draft = (): Action => ({
  id: "act_abs", user_id: "intern-anya", tool: "create_absence_request", title: "Заявление на отгул: 12.11 (чт)",
  params: { day: "2026-11-12", reason: "personal" }, status: "pending", result: null, error: null,
});

const request = (patch: Partial<AbsenceRequest> = {}): AbsenceRequest => ({
  id: "ABS-1", intern_id: "intern-anya", intern_name: "Аня Смирнова", lead_id: "lead-olga", day: "2026-11-12",
  reason: "personal", reason_title: "Личные дела", status: "pending", created_day: 2, decided_day: null, ...patch,
});

describe("отгул на один день (SPEC 3.8)", () => {
  it("dayText: дата демо-часов с днём недели, без часового пояса", () => {
    expect(dayText("2026-11-12")).toBe("12.11 (чт)");
    expect(dayText("2026-11-01")).toBe("01.11 (вс)");
  });

  it("стажёр: «мне завтра к врачу» → карточка заявления без подробностей → подтверждение уходит руководителю", async () => {
    srv.chatReplies.push({ reply: "Подготовил черновик заявления.", actions: [draft()] });
    open("intern-anya");
    const input = await screen.findByPlaceholderText(/Спроси/);
    await screen.findByText(/день стажировки/); // приветствие уже показано — черновик ещё не на сервере
    srv.actions.push(draft());
    await act(async () => {
      fireEvent.change(input, { target: { value: "мне завтра к врачу" } });
      fireEvent.submit(input.closest("form")!);
    });
    const card = (await screen.findByText("Заявление на отгул · черновик")).parentElement!;
    expect(within(card).getByText(/12\.11 \(чт\), один день/)).toBeTruthy();
    expect(within(card).getByText("личные дела")).toBeTruthy();
    expect(within(card).getByText("Ольга Новикова")).toBeTruthy();
    expect(within(card).queryByText(/врач/)).toBeNull();

    await act(async () => fireEvent.click(within(card).getByRole("button", { name: "Подтвердить" })));
    expect(await screen.findByText(/Заявление ушло руководителю: Ольга Новикова/)).toBeTruthy();
    expect(srv.state.absences).toHaveLength(1);
    const mine = await screen.findByRole("region", { name: "Заявки на отгул" });
    expect(within(mine).getByText("ждёт решения")).toBeTruthy();
  });

  it("повтор на тот же день — понятная ошибка", async () => {
    srv.state.absences.push(request());
    srv.chatReplies.push({ reply: "Черновик.", actions: [draft()] });
    open("intern-anya");
    const input = await screen.findByPlaceholderText(/Спроси/);
    await screen.findByText(/день стажировки/);
    srv.actions.push(draft());
    await act(async () => {
      fireEvent.change(input, { target: { value: "отгул завтра" } });
      fireEvent.submit(input.closest("form")!);
    });
    const card = (await screen.findByText("Заявление на отгул · черновик")).parentElement!;
    await act(async () => fireEvent.click(within(card).getByRole("button", { name: "Подтвердить" })));
    expect(await screen.findByText("Не получилось: Отгул на этот день уже запрошен")).toBeTruthy();
  });

  it("руководитель согласует — стажёр видит «согласован», наставник только дату", async () => {
    srv.state.absences.push(request());
    open("lead-olga");
    const box = await screen.findByRole("region", { name: "Заявки на отгул" });
    expect(within(box).getByText("Аня Смирнова")).toBeTruthy();
    expect(within(box).getByText(/12\.11 \(чт\) · личные дела/)).toBeTruthy();
    await act(async () => fireEvent.click(within(box).getByRole("button", { name: "Согласовать" })));
    await waitFor(() => expect(srv.state.absences[0].status).toBe("approved"));
    expect(srv.calls.find((c) => c.path === "/absence/requests/ABS-1/decide")?.body).toEqual({ approve: true });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Заявки на отгул" })).toBeNull());
    cleanup();

    open("mentor-petr");
    const cards = await screen.findByRole("region", { name: "Мои стажёры" });
    expect(await within(cards).findByText("12.11 (чт)")).toBeTruthy();
    expect(within(cards).queryByText(/личные дела/i)).toBeNull(); // причина наставнику не показывается
    cleanup();

    open("intern-anya");
    const mine = await screen.findByRole("region", { name: "Заявки на отгул" });
    expect(within(mine).getByText("согласован")).toBeTruthy();
  });

  it("руководитель отклоняет", async () => {
    srv.state.absences.push(request());
    open("lead-olga");
    const box = await screen.findByRole("region", { name: "Заявки на отгул" });
    await act(async () => fireEvent.click(within(box).getByRole("button", { name: "Отклонить" })));
    await waitFor(() => expect(srv.state.absences[0].status).toBe("rejected"));
  });

  it("чужой руководитель заявку не видит; сервер без отгула (404) — блока нет, ошибок нет", async () => {
    srv.state.absences.push(request());
    open("lead-sergey");
    await screen.findByText(/План:/);
    expect(screen.queryByRole("region", { name: "Заявки на отгул" })).toBeNull();
    cleanup();

    srv.noAdaptive = true;
    open("lead-olga");
    await screen.findByText(/План:/);
    await waitFor(() => expect(srv.calls.some((c) => c.path === "/absence/requests" && c.user === "lead-olga")).toBe(true));
    expect(screen.queryByRole("region", { name: "Заявки на отгул" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
