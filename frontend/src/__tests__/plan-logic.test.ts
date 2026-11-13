import { describe, expect, it } from "vitest";
import { initialState } from "./fake/mock-data";
import { canMarkDone, canRequestAccess, pluralDays, waitedFor } from "@/lib/plan-logic";
import { findUser, firstName } from "@/lib/users";
import {
  actionFor, approverText, explainScripted, finishedWeek, followupsFor, greeting, weeklySummaryMsg,
} from "@/lib/chat";
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
    expect(noDoc.content).not.toMatch(/в источнике ниже/);
    expect(noDoc.sources).toBeUndefined();
    const withDoc = explainScripted({ ...base, doc_source_id: "demo:01-first-days.md" }, profile);
    expect(withDoc.content).toMatch(/в источнике ниже/);
    expect(withDoc.sources).toEqual([{ title: "01-first-days.md", url: null }]);
  });

  it("подсказки помнят пункт; модели уходит вопрос с названием пункта", () => {
    const notes = item("anya.w1.notes");
    expect(followupsFor(notes, ["Как это сделать по шагам?", "Неизвестная"])).toEqual([
      { label: "Как это сделать по шагам?", kind: "steps", itemId: "anya.w1.notes", internId: "intern-anya" },
    ]);
  });

  it("действие для пункта и согласующий", () => {
    expect(actionFor(item("anya.w1.notes")).kind).toBe("explain");
    expect(actionFor(item("anya.w1.access-base")).kind).toBe("do");
    expect(approverText(undefined, u("intern-anya"))).toBe("—");
    expect(approverText({ id: "x", title: "x", kind: "team_space", team: null, approver: "mentor" }, u("intern-ivan"))).toBe("Мария Орлова");
  });
});

describe("итоги недели (SPEC 3.2)", () => {
  it("неделя заканчивается только при переходе на 8, 15, … день", () => {
    expect([1, 2, 7, 8, 9, 14, 15].map(finishedWeek)).toEqual([null, null, null, 1, null, null, 2]);
  });

  it("сводка — факты с названиями ресурсов и кнопкой к следующему своему пункту", () => {
    const notes = item("anya.w1.notes");
    const msg = weeklySummaryMsg({
      intern_id: "intern-anya", week: 1, closed: [], carry_over: [notes],
      access_granted: [{ request_id: "REQ-1", resource_id: "jira", day: 2 }, { request_id: "REQ-2", resource_id: "x", day: 3 }],
    }, { jira: "Учебный Jira" });
    expect(msg.content).toContain("Закрыто: пока ничего");
    expect(msg.content).toContain("Получены доступы: «Учебный Jira», «x»");
    expect(msg.content).toContain(`Переходит на следующую неделю: «${notes.title}»`);
    expect(msg.actions?.[0]).toMatchObject({ itemId: notes.id });
    const empty = weeklySummaryMsg({ intern_id: "intern-anya", week: 2, closed: [], access_granted: [], carry_over: [] });
    expect(empty.content).toContain("Получены доступы: нет");
    expect(empty.actions).toBeUndefined();
  });
});

describe("кто согласует заявку (аудит S4)", () => {
  it("автоматически — только чтение; повышенные права — наставник", () => {
    const jira = { id: "jira", title: "Учебный Jira", kind: "tool", team: null, approver: "auto" } as never;
    expect(approverText(jira, u("intern-anya"))).toBe("выдаётся автоматически");
    expect(approverText(jira, u("intern-anya"), "edit")).toBe("Пётр Волков");
    expect(approverText(undefined, u("intern-anya"))).toBe("—");
  });
});
