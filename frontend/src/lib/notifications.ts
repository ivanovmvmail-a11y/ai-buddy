// Единые уведомления (SPEC 3.6): у каждого — одна кнопка-действие. Куда она ведёт, решает action.target
// с сервера; у старого сервера (без kind/action) — как раньше, по ссылке на заявку или пункт.
import type { Reminder, ReminderKind, ReminderTarget } from "./types";

export const kindOf = (r: Reminder): ReminderKind => r.kind ?? (r.request_id ? "access_request" : "plan_item");

export function targetOf(r: Reminder): ReminderTarget {
  if (r.action) return r.action.target;
  return r.request_id ? "access_request" : "plan_item";
}

/** Сообщают факт и ничего не ждут: после «Открыть» уходят из колокольчика, «Напомнить завтра» им не нужно. */
const INFO: ReadonlySet<ReminderKind> = new Set(["skill_changed", "personal_item_added", "absence_decided", "absence_today", "absence_fact", "mentor_answer"]);
export const isInfo = (r: Reminder) => INFO.has(kindOf(r));
/** Своё напоминание стажёра («напомни в пятницу про 1:1»): можно отложить, а открыл — значит увидел. */
export const doneOnOpen = (r: Reminder) => isInfo(r) || kindOf(r) === "custom";

export function actionLabel(r: Reminder): string {
  if (r.action) return r.action.label;
  return "Открыть в чате";
}

/** Блок на левой панели, к которому ведёт уведомление (aria-label секции). */
export function sectionFor(r: Reminder): string | null {
  if (kindOf(r) === "custom") return null; // своё напоминание стажёра — показываем в чате
  switch (targetOf(r)) {
    case "skill_suggestion": return "Предложения бота";
    case "absence_request": return kindOf(r) === "absence_pending" ? null : "Заявки на отгул";
    case "intern": return "Мои стажёры";
    case "mentor_question": return "Вопросы наставнику";
    case "plan": return "Этапы стажировки";
    default: return null;
  }
}
