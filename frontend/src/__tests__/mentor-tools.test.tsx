// SPEC 4, 5 (11.11): бот предлагает поднять уровень — решает наставник; сравнение двух планов — не рейтинг.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import type { SkillSuggestion } from "@/lib/types";
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
  useSession.setState({ userId, internPick: null , section: "plan" });
  render(<Providers><Home /></Providers>);
}

const gitSuggestion = (): SkillSuggestion => ({
  id: "sug_1", intern_id: "intern-anya", intern_name: "Аня Смирнова", topic: "git", topic_title: "Git",
  from_level: "novice", to_level: "familiar", basis: "закрыла 2 пункта по Git", created_day: 4,
  status: "pending", decided_day: null,
});

describe("предложения по уровню (SPEC 4)", () => {
  it("наставник видит предложение с основанием и поднимает уровень — план пересобирается", async () => {
    srv.state.suggestions.push(gitSuggestion());
    open("mentor-petr");
    const box = await screen.findByRole("region", { name: "Предложения бота" });
    expect(within(box).getByText(/новичок → знаком/)).toBeTruthy();
    expect(within(box).getByText("Основание: закрыла 2 пункта по Git")).toBeTruthy();
    expect(await screen.findByText("Практикум: ветки и pull request")).toBeTruthy();

    await act(async () => fireEvent.click(within(box).getByRole("button", { name: "Поднять уровень" })));
    await waitFor(() => expect(srv.state.suggestions[0].status).toBe("accepted"));
    expect(srv.calls.find((c) => c.path === "/skills/suggestions/sug_1/decide")?.body).toEqual({ accept: true });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Предложения бота" })).toBeNull());
    await waitFor(() => expect(screen.queryByText("Практикум: ветки и pull request")).toBeNull()); // незакрытый персональный снят
    expect(srv.state.profiles[0].skills.git).toBe("familiar");
  });

  it("«Оставить» — уровень не меняется", async () => {
    srv.state.suggestions.push(gitSuggestion());
    open("mentor-petr");
    const box = await screen.findByRole("region", { name: "Предложения бота" });
    await act(async () => fireEvent.click(within(box).getByRole("button", { name: "Оставить" })));
    await waitFor(() => expect(srv.state.suggestions[0].status).toBe("dismissed"));
    expect(srv.state.profiles[0].skills.git).toBe("novice");
  });

  it("стажёр предложений не видит и не запрашивает", async () => {
    srv.state.suggestions.push(gitSuggestion());
    open("intern-anya");
    await screen.findByText("Практикум: ветки и pull request");
    expect(screen.queryByRole("region", { name: "Предложения бота" })).toBeNull();
    expect(srv.calls.some((c) => c.path.startsWith("/skills/suggestions"))).toBe(false);
  });

  it("сервер ещё без предложений (404) — блока нет и ошибки нет", async () => {
    srv.noAdaptive = true;
    open("mentor-petr");
    await screen.findByRole("region", { name: "Мои стажёры" });
    await waitFor(() => expect(srv.calls.some((c) => c.path.startsWith("/skills/suggestions"))).toBe(true));
    expect(screen.queryByRole("region", { name: "Предложения бота" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("сравнение двух планов (SPEC 5)", () => {
  it("Пётр сравнивает Аню и Кирилла: общие совпадают, персональные разные, с причиной", async () => {
    srv.addKirill();
    open("mentor-petr");
    // Проверка 12.11: сравнение открыто сразу и стоит выше карточек стажёров.
    const region = await screen.findByRole("region", { name: "Сравнение планов" });
    expect(within(region).getByRole("heading", { name: "Сравнить планы: Аня и Кирилл" })).toBeTruthy();
    const cards = screen.getByRole("region", { name: "Мои стажёры" });
    expect(region.compareDocumentPosition(cards) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const anya = await screen.findByRole("group", { name: "План: Аня Смирнова" });
    const kirill = screen.getByRole("group", { name: "План: Кирилл Егоров" });
    expect(within(anya).getByText("Практикум: ветки и pull request")).toBeTruthy();
    expect(within(anya).getByText("Почему: в карте навыков Git — новичок")).toBeTruthy();
    expect(within(kirill).getByText("Практикум: запросы к учебной базе объявлений")).toBeTruthy();
    expect(within(kirill).queryByText("Практикум: ветки и pull request")).toBeNull();
    expect(within(region).getByText("Персональные")).toBeTruthy();
    expect(within(region).queryByText(/для тебя/i)).toBeNull(); // у наставника не «для тебя»
    expect(within(region).getByText(/Для всех · 14/)).toBeTruthy();
    // общие приглушены и свёрнуты до 4, остальные — по кнопке
    const common = within(region).getByRole("list", { name: "Общие пункты" });
    expect(within(common).getAllByRole("listitem")).toHaveLength(4);
    await act(async () => fireEvent.click(within(region).getByRole("button", { name: "Показать все общие (14)" })));
    expect(within(common).getAllByRole("listitem")).toHaveLength(14);
    expect(within(region).getAllByText(/^оба: |: .* · /).length).toBeGreaterThan(0);
    expect(within(region).getByText(/Это не рейтинг/)).toBeTruthy();
    expect(within(region).queryByText(/%/)).toBeNull(); // без процентов «кто лучше»
  });

  it("у наставника один стажёр — сравнения нет", async () => {
    open("mentor-petr");
    await screen.findByRole("region", { name: "Мои стажёры" });
    expect(screen.queryByRole("region", { name: "Сравнение планов" })).toBeNull();
  });

  it("сравнение можно свернуть и развернуть", async () => {
    srv.addKirill();
    open("mentor-petr");
    await screen.findByRole("group", { name: "План: Аня Смирнова" });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Свернуть" })));
    expect(screen.queryByRole("group", { name: "План: Аня Смирнова" })).toBeNull();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Развернуть" })));
    expect(await screen.findByRole("group", { name: "План: Аня Смирнова" })).toBeTruthy();
  });

  it("сервер ещё без сравнения (404) — понятная подпись", async () => {
    srv.addKirill();
    srv.noAdaptive = true;
    open("mentor-petr");
    expect(await screen.findByText("Сравнение планов пока недоступно на сервере.")).toBeTruthy();
  });
});

describe("«это я уже знаю» (SPEC 4)", () => {
  const row = async (title: string) => (await screen.findByText(title)).closest("li")!;

  it("стажёр отмечает пункт — пункт не закрыт, отметку можно убрать", async () => {
    open("intern-anya");
    const item = await row("Практикум: ветки и pull request");
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Это я уже знаю" })));
    await waitFor(() => expect(srv.calls.find((c) => c.path === "/plan/items/anya.p.git/known")?.body).toEqual({ known: true }));
    const marked = await row("Практикум: ветки и pull request");
    expect(await within(marked).findByText(/Отмечено: это я уже знаю. Наставник решит, поднять ли уровень/)).toBeTruthy();
    expect(within(marked).queryByRole("button", { name: "Это я уже знаю" })).toBeNull();
    expect(srv.state.items.find((i) => i.id === "anya.p.git")!.status).toBe("not_started");

    await act(async () => fireEvent.click(within(marked).getByRole("button", { name: "Убрать отметку" })));
    await waitFor(() => expect(srv.state.items.find((i) => i.id === "anya.p.git")!.known_marked).toBe(false));
  });

  it("нет кнопки: пункт без темы, сильная тема, чужой план", async () => {
    srv.state.profiles[0].skills.monitoring = "confident";
    open("intern-anya");
    expect(within(await row("Познакомиться с командой")).queryByRole("button", { name: "Это я уже знаю" })).toBeNull();
    expect(within(await row("Изучить документы и мануалы команды")).queryByRole("button", { name: "Это я уже знаю" })).toBeNull();
    cleanup();
    open("mentor-petr");
    expect(within(await row("Практикум: ветки и pull request")).queryByRole("button", { name: "Это я уже знаю" })).toBeNull();
  });
});

describe("наставник правит персональные пункты (SPEC 3.1)", () => {
  const row = async (title: string) => (await screen.findByText(title)).closest("li")!;

  it("убирает персональный пункт; у общего кнопки нет", async () => {
    open("mentor-petr");
    const item = await row("Практикум: ветки и pull request");
    await act(async () => fireEvent.click(within(item).getByRole("button", { name: "Убрать из плана" })));
    await waitFor(() => expect(srv.state.items.some((i) => i.id === "anya.p.git")).toBe(false));
    await waitFor(() => expect(screen.queryByText("Практикум: ветки и pull request")).toBeNull());
    expect(within(await row("Завести конспект встреч с наставником")).queryByRole("button", { name: "Убрать из плана" })).toBeNull();
  });

  it("добавляет пункт из каталога команды — «для тебя» с причиной «добавил наставник»", async () => {
    open("mentor-petr");
    const box = await screen.findByRole("region", { name: "Каталог пунктов" });
    expect(within(box).getByText("Добавить пункт в план: Аня")).toBeTruthy();
    expect(within(box).queryByText(/ветки и pull request/)).toBeNull(); // уже в плане
    expect(within(box).queryByText(/учебной базе доставок/)).toBeNull(); // каталог чужой команды
    await act(async () => fireEvent.click(within(box).getByRole("button", { name: "Добавить в план: Практикум: красный пайплайн" })));
    const added = await row("Практикум: красный пайплайн");
    expect(within(added).getByText("персональный")).toBeTruthy();
    expect(within(added).getByText("Почему: добавил наставник")).toBeTruthy();
    expect(srv.calls.find((c) => c.method === "POST" && c.path === "/plan/items")?.body)
      .toEqual({ intern_id: "intern-anya", catalog_key: "platform.ci" });
  });

  it("стажёр и сервер без каталога (404) — ни кнопок, ни ошибок", async () => {
    open("intern-anya");
    expect(within(await row("Практикум: ветки и pull request")).queryByRole("button", { name: "Убрать из плана" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Каталог пунктов" })).toBeNull();
    cleanup();
    srv.noAdaptive = true;
    open("mentor-petr");
    await screen.findByRole("region", { name: "Мои стажёры" });
    expect(screen.queryByRole("region", { name: "Каталог пунктов" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
