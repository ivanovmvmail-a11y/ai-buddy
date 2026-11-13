// SPEC 3.1 (11.11): общие пункты «для всех», персональные «для тебя» с подписью «почему»,
// по сильной теме — «ты это умеешь — коротко». Карту навыков видят только стажёр и наставник.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import { PlanItem } from "@/lib/types";
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
const row = async (title: string) => (await screen.findByText(title)).closest("li")!;

describe("общие и персональные пункты плана (SPEC 3.1)", () => {
  it("Аня: персональный пункт «для тебя» с причиной, общие — «для всех»", async () => {
    open("intern-anya");
    const personal = await row("Практикум: ветки и pull request");
    expect(within(personal).getByText("для тебя")).toBeTruthy();
    expect(within(personal).getByText("Почему: в карте навыков Git — новичок")).toBeTruthy();
    const common = await row("Завести конспект встреч с наставником");
    expect(within(common).getByText("для всех")).toBeTruthy();
    expect(within(common).queryByText(/Почему:/)).toBeNull();
  });

  it("сильная тема: общий пункт остаётся с меткой «ты это умеешь — коротко»", async () => {
    srv.state.profiles[0].skills.monitoring = "confident";
    open("intern-anya");
    const docs = await row("Изучить документы и мануалы команды");
    expect(await within(docs).findByText("ты это умеешь — коротко")).toBeTruthy();
    expect(within(docs).getByText("для всех")).toBeTruthy();
    expect(within(docs).getByRole("button", { name: "Объяснить" })).toBeTruthy(); // пункт не пропадает
  });

  it("уровень из поля пункта важнее карты навыков", async () => {
    srv.state.items.find((i) => i.id === "anya.w1.notes")!.skill_level = "confident";
    open("intern-anya");
    expect(await within(await row("Завести конспект встреч с наставником")).findByText("ты это умеешь — коротко")).toBeTruthy();
  });

  it("наставник видит «персональный» и причину", async () => {
    open("mentor-petr");
    const personal = await row("Практикум: ветки и pull request");
    expect(within(personal).getByText("персональный")).toBeTruthy();
    expect(within(personal).getByText(/Почему: в карте навыков Git/)).toBeTruthy();
  });

  it("куратор видит тип пункта, но не причину (карта навыков ему недоступна)", async () => {
    open("curator-dmitry");
    const personal = await row("Практикум: ветки и pull request");
    expect(within(personal).getByText("персональный")).toBeTruthy();
    expect(within(personal).queryByText(/Почему:/)).toBeNull();
  });

  it("старый сервер без новых полей: пункт считается общим", () => {
    const old = {
      id: "x", intern_id: "intern-anya", stage: "week1", order: 0, title: "t", summary: "s", owner_role: "intern",
      topic: null, doc_source_id: null, resource_id: null, due_day: null, practice: null, status: "not_started",
      status_reason: null, updated_at: "2026-11-11T09:00:00Z", updated_by: null, overdue: false, waiting_for: null,
      waiting_days: null,
    };
    const parsed = PlanItem.parse(old);
    expect(parsed.kind).toBe("common");
    expect(parsed.reason).toBeNull();
    expect(parsed.known_marked).toBe(false);
  });
});
