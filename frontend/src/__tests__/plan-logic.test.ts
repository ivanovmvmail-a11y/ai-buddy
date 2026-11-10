import { describe, expect, it } from "vitest";
import { DEMO_USERS, initialState } from "@/lib/mock-data";
import { buildPlan, canMarkDone, findUser, pluralDays, remindersFor, visibleInterns, waitedFor } from "@/lib/plan-logic";

const u = (id: string) => findUser(id)!;
const working = (items: { stage: string }[]) => items.filter((i) => i.stage === "week1" || i.stage === "week2");

describe("план стажёра (спека 101)", () => {
  it("AC-1: у Ани 10 пунктов недель 1–2 и этапы-контуры", () => {
    const plan = buildPlan(initialState(), "intern-anya", u("intern-anya"));
    expect(working(plan.items)).toHaveLength(10);
    expect(plan.items.some((i) => i.stage === "month1")).toBe(true);
    expect(plan.ladder.map((s) => s.state)).toEqual(["current", "ahead", "ahead", "ahead"]);
  });

  it("AC-2: пункты команды разные, общие одинаковые", () => {
    const s = initialState();
    const a = buildPlan(s, "intern-anya", u("intern-anya")).items.map((i) => i.title);
    const b = buildPlan(s, "intern-ivan", u("intern-ivan")).items.map((i) => i.title);
    expect(a).toContain("Поднять песочницу Платформы объявлений");
    expect(b).not.toContain("Поднять песочницу Платформы объявлений");
    expect(b).toContain("Познакомиться с командой");
  });

  it("AC-3: у Ивана в день 8 просроченный пункт — следующий шаг", () => {
    const plan = buildPlan(initialState(), "intern-ivan", u("intern-ivan"));
    expect(plan.next_step.item?.overdue).toBe(true);
    expect(plan.next_step.item?.title).toBe("Завести конспект встреч с наставником");
    expect(plan.next_step.waiting[0]).toMatchObject({ waiting_for: "mentor-maria", waiting_days: 3 });
  });

  it("AC-4: если все свои пункты закрыты или ждут других, шага нет", () => {
    const s = initialState();
    s.items = s.items.map((i) => (i.intern_id === "intern-anya" && i.owner_role === "intern" ? { ...i, status: "done" } : i));
    expect(buildPlan(s, "intern-anya", u("intern-anya")).next_step.item).toBeNull();
  });

  it("AC-6, AC-9: отметить можно только свой ручной пункт", () => {
    const items = initialState().items;
    const notes = items.find((i) => i.id === "anya.w1.notes")!;
    const chats = items.find((i) => i.id === "anya.w1.chats")!;
    const access = items.find((i) => i.id === "anya.w1.access-base")!;
    expect(canMarkDone(u("intern-anya"), notes)).toBe(true);
    expect(canMarkDone(u("intern-anya"), chats)).toBe(false);
    expect(canMarkDone(u("intern-anya"), access)).toBe(false);
    expect(canMarkDone(u("mentor-petr"), chats)).toBe(true);
    expect(canMarkDone(u("mentor-maria"), chats)).toBe(false);
    expect(canMarkDone(u("curator-dmitry"), notes)).toBe(false);
  });

  it("AC-8: кто чей план видит", () => {
    const ids = (id: string) => visibleInterns(u(id)).map((x) => x.id);
    expect(ids("intern-anya")).toEqual(["intern-anya"]);
    expect(ids("mentor-maria")).toEqual(["intern-ivan"]);
    expect(ids("lead-olga")).toEqual(["intern-anya"]);
    expect(ids("curator-dmitry")).toHaveLength(2);
    expect(ids("hrbp-elena")).toEqual([]);
  });

  it("AC-10: ступень пройдена, когда закрыты все её пункты", () => {
    const s = initialState();
    s.items = s.items.map((i) =>
      i.intern_id === "intern-anya" && (i.stage === "week1" || i.stage === "week2") ? { ...i, status: "done" } : i,
    );
    const plan = buildPlan(s, "intern-anya", u("intern-anya"));
    expect(plan.ladder[0].state).toBe("passed");
    expect(plan.ladder[1].state).toBe("current");
  });

  it("напоминания: одно на зависший пункт, только стажёру", () => {
    const s = initialState();
    const r = remindersFor(s, u("intern-ivan"));
    expect(r.map((x) => x.plan_item_id).sort()).toEqual(["ivan.w1.access-team", "ivan.w1.notes"]);
    expect(r.find((x) => x.plan_item_id === "ivan.w1.access-team")?.text).toMatch(/3 дня/);
    s.dismissedReminders = r.map((x) => x.id);
    expect(remindersFor(s, u("intern-ivan"))).toHaveLength(0);
    expect(remindersFor(s, u("mentor-maria"))).toHaveLength(0);
  });

  it("склонение дней", () => {
    expect([1, 2, 5, 11, 21, 22].map(pluralDays)).toEqual(["1 день", "2 дня", "5 дней", "11 дней", "21 день", "22 дня"]);
    expect(DEMO_USERS).toHaveLength(8);
    expect(waitedFor(0)).toBe("с сегодняшнего дня");
  });
});
