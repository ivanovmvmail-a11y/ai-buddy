// Лента чата и сценарные ответы макета. Свободный вопрос уходит в настоящий /chat;
// приветствие, объяснение пункта и черновик заявки собираются из тестовых данных (до задачи T4).
import { create } from "zustand";
import { RESOURCES, type DemoState } from "./mock-data";
import { buildPlan, findUser, waitedFor } from "./plan-logic";
import type { DemoUser, PlanItem, SkillLevel } from "./types";

export type Draft = {
  itemId: string;
  resourceTitle: string;
  level: "read" | "edit" | "admin";
  justification: string;
  approver: string;
  state: "pending" | "confirmed" | "cancelled";
};

export type BotAction = { label: string; kind: "do" | "explain"; itemId: string };

export type Msg = {
  id: string;
  role: "user" | "assistant";
  kind: "text" | "draft" | "error";
  content: string;
  sources?: string[];
  chips?: string[];
  action?: BotAction;
  draft?: Draft;
  scripted?: boolean;
};

let n = 0;
export const msgId = () => `m${++n}`;

type ChatStore = {
  messages: Msg[];
  busy: boolean;
  reset: (first: Msg[]) => void;
  push: (...m: Msg[]) => void;
  update: (id: string, patch: Partial<Msg>) => void;
  setBusy: (b: boolean) => void;
};

export const useChat = create<ChatStore>((set) => ({
  messages: [],
  busy: false,
  reset: (first) => set({ messages: first, busy: false }),
  push: (...m) => set((s) => ({ messages: [...s.messages, ...m] })),
  update: (id, patch) => set((s) => ({ messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) })),
  setBusy: (busy) => set({ busy }),
}));

export function actionFor(item: PlanItem): BotAction {
  return item.resource_id
    ? { label: "Сделать за меня", kind: "do", itemId: item.id }
    : { label: "Объяснить", kind: "explain", itemId: item.id };
}

/** Бот пишет первым (SPEC 3.3). */
export function greeting(state: DemoState, actor: DemoUser): Msg {
  const name = actor.name.split(" ")[0];
  if (actor.role === "intern") {
    const plan = buildPlan(state, actor.id, actor);
    const work = plan.items.filter((i) => i.stage === "week1" || i.stage === "week2");
    const done = work.filter((i) => i.status === "done").length;
    const lines = [`Привет, ${name}! Сегодня ${plan.current_day}-й день стажировки. Закрыто ${done} из ${work.length} пунктов недель 1–2.`];
    const next = plan.next_step.item;
    if (next) lines.push(`Следующий шаг${next.overdue ? " (срок уже прошёл)" : ""} — «${next.title}».`);
    for (const w of plan.next_step.waiting) {
      lines.push(`Ждём ответа (${findUser(w.waiting_for)?.name ?? "согласующий"}): «${w.title}», ${waitedFor(w.waiting_days ?? 0)}.`);
    }
    if (!next && plan.next_step.waiting.length === 0) lines.push("Недели 1–2 закрыты — дальше «Месяц 1».");
    return { id: msgId(), role: "assistant", kind: "text", content: lines.join("\n"), action: next ? actionFor(next) : undefined, scripted: true };
  }
  if (actor.role === "mentor") {
    const waiting = state.requests.filter((r) => r.approver_id === actor.id && r.status === "pending_approval");
    const text = waiting.length
      ? `Привет, ${name}! Ждут твоего одобрения заявок: ${waiting.length}. Они слева, над планом стажёра.`
      : `Привет, ${name}! Заявок на одобрение нет. Слева — план твоего стажёра и твои пункты в нём.`;
    return { id: msgId(), role: "assistant", kind: "text", content: text, scripted: true };
  }
  if (actor.role === "hrbp") {
    return { id: msgId(), role: "assistant", kind: "text", scripted: true,
      content: `Привет, ${name}! Я отвечаю по общим документам. Планы и профили стажёров тебе не показываю — так настроены права.` };
  }
  return { id: msgId(), role: "assistant", kind: "text", scripted: true,
    content: `Привет, ${name}! Слева — прогресс стажёров, только чтение.` };
}

const DEPTH: Record<SkillLevel, string> = {
  novice: "Разберём по шагам — эта тема у тебя только начинается, это нормально.",
  familiar: "Коротко по шагам:",
  confident: "Ты в этой теме уверенно, поэтому коротко:",
};

/** Объяснение пункта под уровень стажёра (SPEC 3.4, спека 102). Сценарный ответ макета. */
export function explain(state: DemoState, item: PlanItem): Msg {
  const profile = state.profiles.find((p) => p.intern_id === item.intern_id);
  const level = item.topic ? profile?.skills[item.topic] : undefined;
  const parts = [`«${item.title}» — ${item.summary}`];
  if (level) parts.push(DEPTH[level]);
  if (level === "novice") {
    parts.push("1. Открой связанный документ команды и прочитай раздел про этот шаг.\n2. Сделай по нему одно действие и запиши, что получилось.\n3. Если застрял больше чем на 30 минут — спроси наставника, вопрос я помогу сформулировать.");
  } else if (level) {
    parts.push("Детали — в документе по ссылке ниже.");
  }
  if (item.practice) parts.push(`Задание на практике: ${item.practice}`);
  return {
    id: msgId(), role: "assistant", kind: "text", scripted: true,
    content: parts.join("\n\n"),
    sources: item.doc_source_id ? [item.doc_source_id.replace("demo:", "")] : undefined,
    chips: ["Как это сделать по шагам?", "К кому идти, если не получается?"],
    action: item.resource_id && item.status !== "done" && item.status !== "waiting" ? actionFor(item) : undefined,
  };
}

/** Черновик заявки на доступ (SPEC 3.5). Стажёру — минимально достаточный уровень «чтение». */
export function draftFor(item: PlanItem, actor: DemoUser): Msg {
  const resource = RESOURCES.find((r) => r.id === item.resource_id);
  const approver = resource?.approver === "auto" ? "выдаётся автоматически" : findUser(actor.mentor_id)?.name ?? "наставник";
  return {
    id: msgId(), role: "assistant", kind: "draft",
    content: "Подготовил черновик заявки. Проверь и подтверди — без тебя ничего не отправлю.",
    draft: {
      itemId: item.id,
      resourceTitle: resource?.title ?? "—",
      level: "read",
      justification: `Стажировка в команде «${actor.team}»: ${item.title.toLowerCase()}`,
      approver,
      state: "pending",
    },
  };
}
