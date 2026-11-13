// Чекпоинт 2 (13.11): всё, что есть кнопками в плане, — и в чате. Ответ о пункте приходит с его кнопками,
// «Готово» и сдача задания работают прямо из чата.
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
  useSession.setState({ userId, internPick: null });
  render(<Providers><Home /></Providers>);
}

async function ask(text: string) {
  await screen.findByText(/2-й день стажировки/);
  fireEvent.change(screen.getByRole("textbox", { name: "Сообщение" }), { target: { value: text } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
}

describe("кнопки пункта плана в чате", () => {
  it("ответ о пункте — с кнопками пункта; «Готово» из чата закрывает пункт и называет следующий шаг", async () => {
    srv.chatReplies.push({ reply: "«Завести конспект встреч с наставником». Собери вопросы в одной заметке.", itemId: "anya.w1.notes" });
    open();
    await ask("объясни пункт про конспект");
    const bubble = (await screen.findByText(/Собери вопросы в одной заметке/)).closest("[class*=rounded-2xl]") as HTMLElement;
    expect(within(bubble).getByRole("button", { name: "Объяснить" })).toBeTruthy();
    await act(async () => fireEvent.click(within(bubble).getByRole("button", { name: "Готово" })));
    expect(await screen.findByText(/Отметил «Завести конспект встреч с наставником» — сделано/)).toBeTruthy();
    expect(srv.state.items.find((i) => i.id === "anya.w1.notes")?.status).toBe("done");
  });

  it("«хочу сдать задание» в чате → следующий ответ уходит на проверку задания", async () => {
    srv.chatReplies.push({ reply: "Задание по пункту «Практикум: ветки и pull request»: …", itemId: "anya.p.git", mode: "practice" });
    open();
    await ask("хочу сдать задание по гиту");
    expect(await screen.findByRole("textbox", { name: "Ответ на задание" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Ответ на задание" }), {
      target: { value: "создала ветку, сделала коммит, открыла PR" },
    });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
    expect(await screen.findByText(/Задание выполнено/)).toBeTruthy();
    expect(srv.calls.filter((c) => c.path.endsWith("/practice"))).toHaveLength(1);
    expect(srv.calls.filter((c) => c.path === "/chat")).toHaveLength(1); // ответ на задание не ушёл модели
  });

  it("у наставника кнопок пункта стажёра в чате нет", async () => {
    srv.chatReplies.push({ reply: "Ответ про пункт", itemId: "anya.w1.notes" });
    open("mentor-petr");
    await screen.findByText(/Привет, Пётр/);
    fireEvent.change(screen.getByRole("textbox", { name: "Сообщение" }), { target: { value: "что у Ани" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Отправить" })));
    const bubble = (await screen.findByText("Ответ про пункт")).closest("[class*=rounded-2xl]") as HTMLElement;
    expect(within(bubble).queryByRole("button", { name: "Готово" })).toBeNull();
  });
});
