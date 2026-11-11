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
const click = (el: HTMLElement) => act(async () => fireEvent.click(el));

function open(userId: string) {
  useSession.setState({ userId, internPick: null });
  render(<Providers><Home /></Providers>);
}

async function askModel(text: string) {
  await screen.findByText(/2-й день стажировки/);
  fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: text } });
  await act(async () => fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!));
}

describe("оценка ответов и метрики (спека 302)", () => {
  it("AC-6: «Полезно» под ответом модели отправляет оценку", async () => {
    srv.chatReplies = [{ reply: "Ответ модели", answerId: "ans_42" }];
    open("intern-anya");
    await askModel("Как отправить pull request?");
    const bubble = (await screen.findByText("Ответ модели")).parentElement!;
    await click(within(bubble).getByRole("button", { name: "Полезно" }));
    expect(await within(bubble).findByText(/Спасибо, учту\./)).toBeTruthy();
    expect(srv.feedback).toEqual([{ answer_id: "ans_42", useful: true }]);
  });

  it("«Не полезно» — подсказка про документ; сбой — сообщение", async () => {
    srv.chatReplies = [{ reply: "Первый", answerId: "ans_fail" }, { reply: "Второй", answerId: "ans_2" }];
    open("intern-anya");
    await askModel("Вопрос 1");
    const first = (await screen.findByText("Первый")).parentElement!;
    await click(within(first).getByRole("button", { name: "Не полезно" }));
    expect(await within(first).findByText("Не получилось сохранить оценку.")).toBeTruthy();
    await askModel("Вопрос 2");
    const second = (await screen.findByText("Второй")).parentElement!;
    await click(within(second).getByRole("button", { name: "Не полезно" }));
    expect(await within(second).findByText(/передам наставнику/)).toBeTruthy();
  });

  it("сценарные ответы без кнопок оценки", async () => {
    open("intern-anya");
    await screen.findByText(/2-й день стажировки/);
    expect(screen.queryByRole("button", { name: "Полезно" })).toBeNull();
  });

  it("AC-6: наставник видит сводку, частые темы и темы без ответа", async () => {
    srv.metrics = {
      interns: ["intern-anya"], questions: 5, closed_without_human: 3, with_source_share: 0.6, refused: 1, drafts: 1,
      avg_latency_ms: 1500, feedback: { useful: 2, not_useful: 1 },
      topics: [{ topic: "git", title: "git и ревью", count: 3 }, { topic: "access", title: "доступы", count: 2 }],
      unanswered_topics: [{ topic: "environment", title: "окружение и запуск", count: 1 }],
    };
    open("mentor-petr");
    const region = await screen.findByRole("region", { name: "Мои стажёры" });
    await waitFor(() => expect(within(region).getByLabelText("Метрики").textContent).toMatch(/Вопросов боту: 5 · закрыто без человека: 3 · с источником: 60% · полезно: 2 из 3 · ответ в среднем за 1.5 с/));
    expect(await within(region).findByText(/git и ревью — 3, доступы — 2/)).toBeTruthy();
    expect(within(region).getByText(/окружение и запуск — 1/)).toBeTruthy();
  });

  it("без вопросов — нулевая сводка и без тем", async () => {
    open("curator-dmitry");
    const region = await screen.findByRole("region", { name: "Стажёры" });
    await waitFor(() => expect(within(region).getByLabelText("Метрики").textContent).toMatch(/Вопросов боту: 0/));
    expect(within(region).queryByText(/Частые темы/)).toBeNull();
  });
});
