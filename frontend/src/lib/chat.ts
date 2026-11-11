// Лента чата. Приветствие и напоминания собираются из данных сервера (план, заявки, напоминания).
// Объяснение пункта: с настоящей моделью — вопрос в /chat; без ключа (LLM_PROVIDER=scenario или echo) —
// сценарный ответ из тех же данных плана и профиля (SPEC, раздел 8).
import { create } from "zustand";
import { findUser } from "./users";
import { waitedFor } from "./plan-logic";
import type {
  AccessRequest, AccessResource, Action, DemoUser, DocSource, ExplainKind, Plan, PlanItem, Reminder, SkillLevel, SkillProfile,
} from "./types";

export type BotAction =
  | { label: string; kind: "do" | "explain" | "steps" | "who"; itemId: string; internId: string }
  | { label: string; kind: "snooze"; reminderId: string };

export type Msg = {
  id: string;
  role: "user" | "assistant";
  kind: "text" | "draft" | "error";
  content: string;
  sources?: DocSource[];
  chips?: string[];
  actions?: BotAction[];
  followups?: BotAction[]; // подсказки, привязанные к пункту плана («по шагам», «к кому идти»)
  draft?: Action;
  retry?: string; // текст вопроса для «Повторить»
  answerId?: string; // ответ модели можно оценить (спека 302)
  rated?: "useful" | "not_useful";
  scripted?: boolean;
};

let n = 0;
export const msgId = () => `m${++n}`;

type ChatStore = {
  messages: Msg[];
  busy: boolean;
  seenReminders: string[];
  reset: (first: Msg[]) => void;
  push: (...m: Msg[]) => void;
  update: (id: string, patch: Partial<Msg>) => void;
  setBusy: (b: boolean) => void;
  markSeen: (ids: string[]) => void;
};

export const useChat = create<ChatStore>((set) => ({
  messages: [],
  busy: false,
  seenReminders: [],
  reset: (first) => set({ messages: first, busy: false, seenReminders: [] }),
  push: (...m) => set((s) => ({ messages: [...s.messages, ...m] })),
  update: (id, patch) => set((s) => ({ messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) })),
  setBusy: (busy) => set({ busy }),
  markSeen: (ids) => set((s) => ({ seenReminders: [...s.seenReminders, ...ids] })),
}));

export function actionFor(item: PlanItem): BotAction {
  return item.resource_id && item.status !== "waiting" && item.status !== "done"
    ? { label: "Сделать за меня", kind: "do", itemId: item.id, internId: item.intern_id }
    : { label: "Объяснить", kind: "explain", itemId: item.id, internId: item.intern_id };
}

const scripted = (content: string, extra: Partial<Msg> = {}): Msg => ({
  id: msgId(), role: "assistant", kind: "text", content, scripted: true, ...extra,
});

/** Бот пишет первым (SPEC 3.3). */
export function greeting(actor: DemoUser, plan: Plan | null, pendingApprovals: AccessRequest[]): Msg {
  const name = actor.name.split(" ")[0];
  if (actor.role === "intern" && plan) {
    const work = plan.items.filter((i) => i.stage === "week1" || i.stage === "week2");
    const done = work.filter((i) => i.status === "done").length;
    const lines = [`Привет, ${name}! Сегодня ${plan.current_day}-й день стажировки. Закрыто ${done} из ${work.length} пунктов недель 1–2.`];
    const next = plan.next_step.item;
    if (next) lines.push(`Следующий шаг${next.overdue ? " (срок уже прошёл)" : ""} — «${next.title}».`);
    for (const w of plan.next_step.waiting) {
      lines.push(`Ждём ответа (${findUser(w.waiting_for)?.name ?? "согласующий"}): «${w.title}», ${waitedFor(w.waiting_days ?? 0)}.`);
    }
    if (!next && plan.next_step.waiting.length === 0) lines.push("Недели 1–2 закрыты — дальше «Месяц 1».");
    return scripted(lines.join("\n"), { actions: next ? [actionFor(next)] : undefined });
  }
  if (actor.role === "mentor") {
    return scripted(
      pendingApprovals.length
        ? `Привет, ${name}! Ждут твоего одобрения заявок: ${pendingApprovals.length}. Они слева, над планом стажёра.`
        : `Привет, ${name}! Заявок на одобрение нет. Слева — план твоего стажёра и твои пункты в нём.`,
    );
  }
  if (actor.role === "hrbp") {
    return scripted(`Привет, ${name}! Я отвечаю по общим документам. Планы и профили стажёров тебе не показываю — так настроены права.`);
  }
  return scripted(`Привет, ${name}! Слева — прогресс стажёров${actor.role === "curator" ? ", только чтение" : ""}.`);
}

export function reminderMsg(r: Reminder, item: PlanItem | undefined): Msg {
  const actions: BotAction[] = [];
  if (item) actions.push({ ...actionFor(item), label: item.resource_id && item.status !== "waiting" ? "Сделать сейчас" : "Объяснить" });
  actions.push({ label: "Напомнить позже", kind: "snooze", reminderId: r.id });
  return scripted(`🔔 ${r.text}`, { actions });
}

const DEPTH: Record<SkillLevel, string> = {
  novice: "Разберём подробно, с примерами.",
  familiar: "Коротко по шагам:",
  confident: "Ты в этой теме уверенно, поэтому коротко:",
};

export const explainQuestion = (item: PlanItem) =>
  `Объясни пункт плана «${item.title}» (id ${item.id}): зачем он нужен, как его выполнить и к кому идти.`;

export const FOLLOWUP_KIND: Record<string, ExplainKind> = {
  "Как это сделать по шагам?": "steps",
  "К кому идти, если не получается?": "who",
};

/** Подсказки сервера → кнопки, которые помнят пункт: без модели ответ строится по документу этого пункта. */
export function followupsFor(item: PlanItem, chips: string[]): BotAction[] {
  return chips
    .filter((c) => c in FOLLOWUP_KIND)
    .map((label) => ({ label, kind: FOLLOWUP_KIND[label] as "steps" | "who", itemId: item.id, internId: item.intern_id }));
}

/** Вопрос модели по подсказке — с названием пункта, чтобы поиск не потерял контекст. */
export function followupQuestion(item: PlanItem, kind: ExplainKind): string {
  if (kind === "steps") return `Как выполнить пункт плана «${item.title}» по шагам?`;
  if (kind === "who") return `К кому идти, если не получается пункт плана «${item.title}»?`;
  return explainQuestion(item);
}

/** Запасной сценарный ответ, если сервер объяснений не ответил: глубина по карте навыков (SPEC 3.4, 4). */
export function explainScripted(item: PlanItem, profile: SkillProfile | undefined): Msg {
  const level = item.topic ? profile?.skills[item.topic] : undefined;
  const parts = [`«${item.title}» — ${item.summary}`];
  if (level) parts.push(DEPTH[level]);
  if (level === "novice") {
    parts.push("1. Открой связанный документ команды и прочитай раздел про этот шаг.\n2. Сделай по нему одно действие и запиши, что получилось.\n3. Если застрял больше чем на 30 минут — спроси наставника, вопрос я помогу сформулировать.");
  } else if (level) {
    // Ссылку обещаем, только если у пункта есть документ, — иначе предлагаем разобрать по шагам.
    parts.push(item.doc_source_id ? "Детали — в документе, он указан в источнике ниже." : "Если нужно подробнее — спроси «Как это сделать по шагам?».");
  }
  if (item.practice) parts.push(`Задание на практике: ${item.practice}`);
  return scripted(parts.join("\n\n"), {
    sources: item.doc_source_id ? [{ title: item.doc_source_id.replace("demo:", ""), url: null }] : undefined,
    followups: followupsFor(item, ["Как это сделать по шагам?", "К кому идти, если не получается?"]),
    actions: item.resource_id && item.status !== "done" && item.status !== "waiting" ? [actionFor(item)] : undefined,
  });
}

/** Параметры черновика заявки: стажёру — минимально достаточный уровень «чтение» (SPEC 3.5). */
export function accessDraftParams(item: PlanItem, actor: DemoUser) {
  return {
    resource_id: item.resource_id,
    level: "read",
    justification: `Стажировка в команде «${actor.team}»: ${item.title.toLowerCase()}`,
  };
}

export function approverText(resource: AccessResource | undefined, actor: DemoUser): string {
  if (!resource) return "—";
  return resource.approver === "auto" ? "выдаётся автоматически" : findUser(actor.mentor_id)?.name ?? "наставник";
}
