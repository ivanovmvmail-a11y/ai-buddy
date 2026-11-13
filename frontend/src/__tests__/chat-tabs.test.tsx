// Чекпоинт 2 (13.11): «разделите чаты — один для заданий, один для заявлений». У стажёра три вкладки:
// «Помощник», «Учёба», «Заявки». Ответ уходит во вкладку своей темы, модель видит переписку только этой вкладки.
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
  useSession.setState({ userId, internPick: null , section: "plan" });
  render(<Providers><Home /></Providers>);
}

const tab = (name: string) => screen.getByRole("tab", { name: new RegExp(`^${name}`) });

async function ask(text: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Сообщение" }), { target: { value: text } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
}

describe("вкладки чата стажёра", () => {
  it("три вкладки, приветствие — в «Помощнике»", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    expect(tab("Помощник").getAttribute("aria-selected")).toBe("true");
    expect(tab("Учёба")).toBeTruthy();
    expect(tab("Заявки")).toBeTruthy();
  });

  it("«Объяснить» в плане открывает «Учёбу»; в «Помощнике» объяснения нет", async () => {
    open();
    const item = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Объяснить" })));
    expect(tab("Учёба").getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByText(/Объясни пункт «Завести конспект/)).toBeTruthy();
    await act(async () => fireEvent.click(tab("Помощник")));
    expect(screen.queryByText(/Объясни пункт «Завести конспект/)).toBeNull();
  });

  it("вопрос про заявку из «Помощника» переезжает с ответом во «Заявки»", async () => {
    srv.chatReplies.push({ reply: "Подготовил черновик заявки на Grafana.", topic: "requests" });
    open();
    await screen.findByText(/2-й день стажировки/);
    await ask("нужен доступ к графане");
    expect(tab("Заявки").getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByText("Подготовил черновик заявки на Grafana.")).toBeTruthy();
    expect(screen.getByText("нужен доступ к графане")).toBeTruthy();
  });

  it("модель получает переписку только своей вкладки", async () => {
    srv.chatReplies.push({ reply: "Про доступ.", topic: "requests" }, { reply: "Про документы." });
    open();
    await screen.findByText(/2-й день стажировки/);
    await ask("нужен доступ к графане");
    await act(async () => fireEvent.click(tab("Помощник")));
    await ask("где почитать про ревью?");
    const last = srv.calls.filter((c) => c.path === "/chat").at(-1)!.body as { messages: Array<{ content: string }> };
    expect(last.messages.map((m) => m.content)).toEqual(["где почитать про ревью?"]);
  });

  it("новое в другой вкладке — точка на вкладке", async () => {
    open("intern-ivan"); // у Ивана при входе напоминание о зависшей заявке
    await screen.findByText(/8-й день стажировки/);
    expect(await screen.findByText(/Новые напоминания: «Учёба» — 1, «Заявки» — 1/)).toBeTruthy();
    expect(within(tab("Заявки")).getByLabelText("есть новое")).toBeTruthy();
    await act(async () => fireEvent.click(tab("Заявки")));
    expect(within(tab("Заявки")).queryByLabelText("есть новое")).toBeNull();
  });

  it("у наставника вкладок нет — одна лента", async () => {
    open("mentor-petr");
    await screen.findByText(/Привет, Пётр/);
    expect(screen.queryByRole("tab", { name: /^Учёба/ })).toBeNull();
  });
});
