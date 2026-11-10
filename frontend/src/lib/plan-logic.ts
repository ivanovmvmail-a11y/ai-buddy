// Помощники отображения плана. Правила и права считает сервер (имитации сервисов, спека 101);
// здесь только то, что нужно, чтобы не показывать заведомо недоступные кнопки.
import type { DemoUser, PlanItem, Stage } from "./types";

const WORKING: Stage[] = ["week1", "week2"];

export const STAGE_TITLES: Record<Stage, string> = {
  week1: "Неделя 1",
  week2: "Неделя 2",
  month1: "Месяц 1",
  month2: "Месяц 2",
  after3m: "После 3 месяцев",
};

export const isWorking = (stage: Stage) => WORKING.includes(stage);

/** Кнопка «Готово»: свой ручной пункт рабочего этапа. Окончательно права проверяет сервер. */
export function canMarkDone(actor: DemoUser, item: PlanItem): boolean {
  if (!isWorking(item.stage) || item.resource_id || item.status === "done") return false;
  if (actor.role === "curator" || actor.role === "hrbp") return false;
  return item.owner_role === actor.role;
}

/** «Сделать за меня»: стажёр, свой пункт с доступом, заявка ещё не подана. */
export function canRequestAccess(actor: DemoUser, item: PlanItem): boolean {
  return actor.role === "intern" && actor.id === item.intern_id && isWorking(item.stage) && !!item.resource_id
    && (item.status === "not_started" || item.status === "in_progress");
}

export function pluralDays(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return `${n} день`;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return `${n} дня`;
  return `${n} дней`;
}

/** «с сегодняшнего дня» / «2 дня» — сколько уже ждём. */
export function waitedFor(n: number): string {
  return n <= 0 ? "с сегодняшнего дня" : pluralDays(n);
}
