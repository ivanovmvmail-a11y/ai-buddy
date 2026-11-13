import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { questionDraft } from "@/components/ChatPanel";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import { installFakeServer, type FakeServer } from "./fake/server";

let srv: FakeServer;
const writeText = vi.fn();
beforeEach(() => {
  srv = installFakeServer();
  useChat.getState().reset([]);
  useSession.setState({ userId: "intern-anya", internPick: null , section: "plan" });
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  writeText.mockReset();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const REPLY = "В документах этого нет. Черновик вопроса, можно скопировать:\n\n«Привет! Где взять ноутбук?»";

async function ask() {
  render(<Providers><Home /></Providers>);
  await screen.findByText(/2-й день стажировки/);
  fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Где взять ноутбук?" } });
  await act(async () => fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!));
  return (await screen.findByText(/В документах этого нет/)).parentElement!;
}

describe("черновик вопроса наставнику (SPEC 3.7)", () => {
  it("выделяет текст черновика", () => {
    expect(questionDraft(REPLY)).toBe("Привет! Где взять ноутбук?");
    expect(questionDraft("Черновик сообщения:\n«Здравствуйте!»")).toBe("Здравствуйте!");
    expect(questionDraft("Обычный ответ")).toBeNull();
  });

  it("«Скопировать вопрос» кладёт текст в буфер", async () => {
    srv.chatReplies = [{ reply: REPLY }];
    writeText.mockResolvedValue(undefined);
    const bubble = await ask();
    await act(async () => fireEvent.click(within(bubble).getByRole("button", { name: "Скопировать вопрос" })));
    expect(writeText).toHaveBeenCalledWith("Привет! Где взять ноутбук?");
    expect(within(bubble).getByRole("button", { name: "Скопировано" })).toBeTruthy();
  });

  it("если буфер недоступен — подсказка скопировать вручную", async () => {
    srv.chatReplies = [{ reply: REPLY }];
    writeText.mockRejectedValue(new Error("denied"));
    const bubble = await ask();
    await act(async () => fireEvent.click(within(bubble).getByRole("button", { name: "Скопировать вопрос" })));
    expect(within(bubble).getByRole("alert").textContent).toMatch(/скопируй вручную/);
  });
});
