import { describe, expect, it } from "vitest";
import { initialState } from "./fake/mock-data";
import { canMarkDone, canRequestAccess, pluralDays, waitedFor } from "@/lib/plan-logic";
import { findUser, firstName } from "@/lib/users";
import { actionFor, approverText, explainScripted, greeting } from "@/lib/chat";
import type { Plan, SkillProfile } from "@/lib/types";

const u = (id: string) => findUser(id)!;
const items = initialState().items;
const item = (id: string) => items.find((i) => i.id === id)!;

describe("кнопки плана (спека 101)", () => {
  it("«Готово» — только свой ручной пункт рабочего этапа", () => {
    expect(canMarkDone(u("intern-anya"), item("anya.w1.notes"))).toBe(true);
    expect(canMarkDone(u("intern-anya"), item("anya.w1.chats"))).toBe(false);
    expect(canMarkDone(u("intern-anya"), item("anya.w1.access-base"))).toBe(false);
    expect(canMarkDone(u("intern-anya"), item("anya.m1.task"))).toBe(false);
    expect(canMarkDone(u("intern-anya"), item("anya.w1.team"))).toBe(false); // уже сделано
    expect(canMarkDone(u("mentor-petr"), item("anya.w1.chats"))).toBe(true);
    expect(canMarkDone(u("curator-dmitry"), item("anya.w1.notes"))).toBe(false);
  });

  it("«Сделать за меня» — стажёр, свой пункт с доступом, заявки ещё нет", () => {
    expect(canRequestAccess(u("intern-anya"), item("anya.w1.access-base"))).toBe(true);
    expect(canRequestAccess(u("intern-ivan"), item("anya.w1.access-base"))).toBe(false);
    expect(canRequestAccess(u("mentor-petr"), item("anya.w1.access-base"))).toBe(false);
    expect(canRequestAccess(u("intern-ivan"), item("ivan.w1.access-team"))).toBe(false); // ждёт
  });

  it("склонение и ожидание", () => {
    expect([1, 2, 5, 11, 21, 22].map(pluralDays)).toEqual(["1 день", "2 дня", "5 дней", "11 дней", "21 день", "22 дня"]);
    expect(waitedFor(0)).toBe("с сегодняшнего дня");
    expect(waitedFor(3)).toBe("3 дня");
    expect(firstName("intern-anya")).toBe("Аня");
    expect(firstName("nobody")).toBe("");
  });
});

describe("сценарные ответы", () => {
  it("приветствие: всё закрыто → дальше «Месяц 1»", () => {
    const plan: Plan = { intern_id: "intern-anya", current_day: 9, items: [], ladder: [], next_step: { item: null, waiting: [] } };
    expect(greeting(u("intern-anya"), plan, []).content).toMatch(/дальше «Месяц 1»/);
    expect(greeting(u("lead-olga"), null, []).content).toMatch(/прогресс стажёров\.$/);
    expect(greeting(u("curator-dmitry"), null, []).content).toMatch(/только чтение/);
  });

  it("объяснение без уровня по теме и без практики", () => {
    const msg = explainScripted(item("anya.w1.chats"), undefined);
    expect(msg.content).not.toMatch(/по шагам/);
    expect(msg.sources).toBeUndefined();
  });

  it("коротко для уверенного: ссылку обещаем, только если есть документ", () => {
    const base = { ...item("anya.w1.notes"), topic: "git" } as typeof items[number];
    const profile = { skills: { git: "confident" } } as unknown as SkillProfile;
    const noDoc = explainScripted({ ...base, doc_source_id: null }, profile);
    expect(noDoc.content).not.toMatch(/по ссылке ниже/);
    expect(noDoc.sources).toBeUndefined();
    const withDoc = explainScripted({ ...base, doc_source_id: "demo:01-first-days.md" }, profile);
    expect(withDoc.content).toMatch(/по ссылке ниже/);
    expect(withDoc.sources).toEqual(["01-first-days.md"]);
  });

  it("действие для пункта и согласующий", () => {
    expect(actionFor(item("anya.w1.notes")).kind).toBe("explain");
    expect(actionFor(item("anya.w1.access-base")).kind).toBe("do");
    expect(approverText(undefined, u("intern-anya"))).toBe("—");
    expect(approverText({ id: "x", title: "x", kind: "team_space", team: null, approver: "mentor" }, u("intern-ivan"))).toBe("Мария Орлова");
  });
});
