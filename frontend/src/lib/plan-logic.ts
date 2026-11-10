// Правила плана для макета — те же, что в docs/specs/101-plan-next-step/plan.md, раздел 3.2.
// Настоящие правила живут в имитациях сервисов на сервере (задача T1, Codex); здесь — копия для макета.
import { DEMO_USERS, type DemoState } from "./mock-data";
import type { DemoUser, Plan, PlanItem, Reminder, Stage, StageInfo } from "./types";

const WORKING: Stage[] = ["week1", "week2"];
const STEPS: { title: string; stages: Stage[] }[] = [
  { title: "Недели 1–2", stages: ["week1", "week2"] },
  { title: "Месяц 1", stages: ["month1"] },
  { title: "Месяц 2", stages: ["month2"] },
  { title: "После 3 месяцев", stages: ["after3m"] },
];

export const STAGE_TITLES: Record<Stage, string> = {
  week1: "Неделя 1",
  week2: "Неделя 2",
  month1: "Месяц 1",
  month2: "Месяц 2",
  after3m: "После 3 месяцев",
};

export const isWorking = (stage: Stage) => WORKING.includes(stage);

export function findUser(id: string | null | undefined): DemoUser | undefined {
  return DEMO_USERS.find((u) => u.id === id);
}

/** Чей план может видеть пользователь (спека 101, раздел 2). */
export function visibleInterns(actor: DemoUser): DemoUser[] {
  const interns = DEMO_USERS.filter((u) => u.role === "intern");
  switch (actor.role) {
    case "intern":
      return interns.filter((u) => u.id === actor.id);
    case "mentor":
      return interns.filter((u) => u.mentor_id === actor.id);
    case "lead":
      return interns.filter((u) => u.team === actor.team);
    case "curator":
      return interns;
    default:
      return [];
  }
}

/** Можно ли отметить пункт вручную: только свой, без сервиса, на рабочем этапе. */
export function canMarkDone(actor: DemoUser, item: PlanItem): boolean {
  if (!isWorking(item.stage) || item.resource_id || item.status === "done") return false;
  if (actor.role === "curator" || actor.role === "hrbp") return false;
  if (item.owner_role !== actor.role) return false;
  return visibleInterns(actor).some((u) => u.id === item.intern_id);
}

function withDerived(state: DemoState, item: PlanItem): PlanItem {
  const day = state.days[item.intern_id] ?? 1;
  const overdue = isWorking(item.stage) && item.status !== "done" && item.due_day !== null && day > item.due_day;
  if (item.status !== "waiting") return { ...item, overdue, waiting_for: null, waiting_days: null };
  const req = state.requests.find((r) => r.plan_item_id === item.id && r.status === "pending_approval");
  return {
    ...item,
    overdue,
    waiting_for: req?.approver_id ?? null,
    waiting_days: req ? Math.max(0, day - req.created_day) : null,
  };
}

export function buildLadder(items: PlanItem[]): StageInfo[] {
  let currentFound = false;
  return STEPS.map(({ title, stages }) => {
    const own = items.filter((i) => stages.includes(i.stage));
    const done = own.filter((i) => i.status === "done").length;
    const passed = own.length > 0 && done === own.length;
    let state: StageInfo["state"] = "ahead";
    if (passed && !currentFound) state = "passed";
    else if (!currentFound) {
      state = "current";
      currentFound = true;
    }
    return { stage: stages[0], title, total: own.length, done, state };
  });
}

export function buildPlan(state: DemoState, internId: string, actor: DemoUser): Plan {
  const items = state.items.filter((i) => i.intern_id === internId).map((i) => withDerived(state, i));
  const mine = items.filter(
    (i) => isWorking(i.stage) && i.owner_role === actor.role && i.status !== "done" && i.status !== "waiting",
  );
  mine.sort((a, b) => Number(b.overdue) - Number(a.overdue) || a.order - b.order);
  const waiting = actor.role === "intern" ? items.filter((i) => i.status === "waiting") : [];
  return {
    intern_id: internId,
    current_day: state.days[internId] ?? 1,
    items,
    ladder: buildLadder(items),
    next_step: { item: mine[0] ?? null, waiting },
  };
}

/** Напоминания (имитация ИИ-крона, спека 301): одно на зависший пункт. */
export function remindersFor(state: DemoState, actor: DemoUser): Reminder[] {
  if (actor.role !== "intern") return [];
  const day = state.days[actor.id] ?? 1;
  const plan = buildPlan(state, actor.id, actor);
  const out: Reminder[] = [];
  for (const item of plan.items) {
    let text: string | null = null;
    if (item.status === "waiting" && (item.waiting_days ?? 0) >= 2) {
      const who = findUser(item.waiting_for)?.name.split(" ")[0] ?? "согласующего";
      text = `Заявка «${item.title}» ждёт ${pluralDays(item.waiting_days ?? 0)}. Напомнить ${who}?`;
    } else if (item.overdue && item.owner_role === "intern") {
      text = `Пункт «${item.title}» просрочен. Сделаем сейчас?`;
    }
    const id = `rem.${item.id}`;
    if (text && !state.dismissedReminders.includes(id)) {
      out.push({ id, user_id: actor.id, plan_item_id: item.id, request_id: null, text, status: "active", created_day: day, snooze_until_day: null });
    }
  }
  return out;
}

/** «сегодня» / «2 дня» — сколько уже ждём. */
export function waitedFor(n: number): string {
  return n <= 0 ? "с сегодняшнего дня" : pluralDays(n);
}

export function pluralDays(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return `${n} день`;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return `${n} дня`;
  return `${n} дней`;
}
