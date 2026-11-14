// «Память» (13.11): «нет в документах» → «Отправить наставнику» → наставник отвечает и добавляет в базу знаний.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { questionOnly } from "@/components/ChatPanel";
import { useChat } from "@/lib/chat";
import { sectionFor } from "@/lib/notifications";
import { useSession } from "@/lib/store";
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
  useSession.setState({ userId, internPick: null, section: userId.startsWith("intern") ? "home" : "plan" }); // стажёру блоки — на «Главной»
  render(<Providers><Home /></Providers>);
}

const MISSING = "В документах, доступных тебе, этого нет — выдумывать не буду. Скорее всего подскажет твой наставник. " +
  "Черновик вопроса, можно скопировать:\n\n«Привет! Подскажи, пожалуйста: Где пароль от стенда? Я поискал в документах команды, но ответа не нашёл.»";

async function ask(text: string) {
  const box = await screen.findByRole("textbox", { name: "Сообщение" });
  fireEvent.change(box, { target: { value: text } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
}

describe("«память»: вопрос наставнику", () => {
  it("стажёр отправляет вопрос из чата одной кнопкой и видит его в «Мои вопросы наставнику»", async () => {
    srv.chatReplies = [{ reply: MISSING }];
    open("intern-anya");
    await ask("где пароль от стенда?");
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Отправить наставнику" })));
    expect(await screen.findByText(/Отправлено\. Ответ придёт в колокольчик/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Отправить наставнику" })).toBeNull();
    const sent = srv.calls.find((c) => c.path === "/mentor/questions" && c.method === "POST");
    expect(sent?.body).toEqual({ text: "Где пароль от стенда?" });
    const mine = await screen.findByRole("region", { name: "Вопросы наставнику" });
    expect(within(mine).getByText("Мои вопросы наставнику")).toBeTruthy();
    expect(within(mine).getByText("Ждёт ответа наставника")).toBeTruthy();
  });

  it("у сообщения для HR BP кнопки «Отправить наставнику» нет", async () => {
    srv.chatReplies = [{ reply: "Это организационный вопрос — к HR BP. Черновик сообщения, можно скопировать:\n\n«Здравствуйте! Как оформить отпуск?»" }];
    open("intern-anya");
    await ask("как оформить отпуск");
    expect(await screen.findByRole("button", { name: "Скопировать вопрос" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Отправить наставнику" })).toBeNull();
  });

  it("наставник отвечает с галочкой «в базу знаний» и может добавить старый ответ позже", async () => {
    srv.mentorQuestions.push(
      { id: "MQ-1", intern_id: "intern-anya", intern_name: "Аня Смирнова", mentor_id: "mentor-petr", question: "Где пароль?",
        created_day: 2, status: "pending", answer: null, publication_status: "not_requested", public_content: null },
      { id: "MQ-2", intern_id: "intern-kirill", intern_name: "Кирилл Егоров", mentor_id: "mentor-petr", question: "Как зовут чат?",
        created_day: 1, status: "answered", answer: "Песочница", publication_status: "not_requested", public_content: null },
    );
    open("mentor-petr");
    // 14.11: вопрос — карточкой в чате, ответ — обычным сообщением; в плане блока больше нет
    const card = await screen.findByRole("group", { name: "Вопрос: Аня Смирнова" });
    expect(screen.queryByRole("region", { name: "Вопросы наставнику" })).toBeNull();
    expect(within(card).getByText("Аня Смирнова: «Где пароль?»")).toBeTruthy();
    await act(async () => fireEvent.click(within(card).getByRole("button", { name: "Ответить" })));
    const publish = within(card).getByRole("checkbox") as HTMLInputElement;
    expect(publish.checked).toBe(true);
    expect(screen.getByText(/Ответ на вопрос «Где пароль\?» \(Аня Смирнова\)/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Ответ стажёру" }), { target: { value: "У наставника в канале" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
    const answered = srv.calls.find((c) => c.path === "/mentor/questions/MQ-1/answer");
    expect(answered?.body).toEqual({ text: "У наставника в канале", publish: true, topic: "Где пароль?" });
    expect(await screen.findByText(/Ответ отправлен: Аня Смирнова получит/)).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Сообщение" })).toBeTruthy(); // режим ответа снят

    const later = await screen.findByRole("group", { name: "Вопрос: Кирилл Егоров" });
    fireEvent.change(within(later).getByRole("textbox", { name: /Тема в базе знаний/ }), { target: { value: "Как называется чат стажёров" } });
    await act(async () => fireEvent.click(within(later).getByRole("button", { name: "Добавить ответ в базу знаний" })));
    expect(srv.calls.find((c) => c.path === "/mentor/questions/MQ-2/publish")?.body).toEqual({ topic: "Как называется чат стажёров" });
  });

  it("уведомление «Аня спрашивает» → чат, карточка вопроса подсвечена (Миша, 14.11)", async () => {
    srv.mentorQuestions.push({ id: "MQ-1", intern_id: "intern-anya", intern_name: "Аня Смирнова", mentor_id: "mentor-petr",
      question: "Где пароль?", created_day: 2, status: "pending", answer: null, publication_status: "not_requested", public_content: null });
    srv.state.notifications.push({ id: "R-Q", user_id: "mentor-petr", kind: "mentor_question", action: { label: "Ответить", target: "mentor_question" },
      intern_id: "intern-anya", absence_request_id: null, suggestion_id: null, plan_item_id: null, request_id: null,
      text: "Аня задала вопрос", status: "active", created_day: 2, snooze_until_day: null });
    open("mentor-petr");
    await screen.findByRole("group", { name: "Вопрос: Аня Смирнова" });
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: /Напоминания: \d/ })));
    const dialog = screen.getByRole("dialog", { name: "Напоминания" });
    await act(async () => fireEvent.click(within(dialog).getByRole("button", { name: "Ответить" })));
    const flashed = useChat.getState().flash;
    expect(flashed).toBeTruthy();
    expect(useChat.getState().messages.find((m) => m.id === flashed)?.decision).toEqual({ kind: "question", id: "MQ-1" });
  });

  it("стажёр видит ответ; у лида блока нет; уведомление ведёт в блок", async () => {
    srv.mentorQuestions.push({ id: "MQ-1", intern_id: "intern-anya", intern_name: "Аня Смирнова", mentor_id: "mentor-petr",
      question: "Где пароль?", created_day: 2, status: "answered", answer: "У наставника", publication_status: "published", public_content: "x" });
    open("intern-anya");
    const mine = await screen.findByRole("region", { name: "Вопросы наставнику" });
    expect(within(mine).getByText("У наставника")).toBeTruthy();
    cleanup();
    open("lead-olga");
    await screen.findByText(/Стажёры/);
    expect(screen.queryByRole("region", { name: "Вопросы наставнику" })).toBeNull();
    const reminder = { id: "R", user_id: "x", kind: "mentor_answer" as const, action: { label: "Открыть", target: "mentor_question" as const },
      plan_item_id: null, request_id: null, text: "", status: "active" as const, created_day: 1, snooze_until_day: null };
    expect(sectionFor(reminder)).toBe("Вопросы наставнику");
  });

  it("из черновика берётся только сам вопрос", () => {
    expect(questionOnly("Привет! Подскажи, пожалуйста: Где пароль? Я поискал в документах команды, но ответа не нашёл.")).toBe("Где пароль?");
    expect(questionOnly("просто текст")).toBe("просто текст");
  });
});
