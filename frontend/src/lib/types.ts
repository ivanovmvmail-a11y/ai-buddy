// Модели онбординга. Повторяют контракт имитаций сервисов (docs/specs/101-plan-next-step/plan.md, 3.1)
// и docs/API.md. Zod проверяет каждый ответ сервера: если контракт разъехался — понятная ошибка,
// а не «undefined» где-то в интерфейсе.
import { z } from "zod";

export const Role = z.enum(["intern", "mentor", "lead", "hrbp", "curator"]);
export const Stage = z.enum(["week1", "week2", "month1", "month2", "after3m"]);
export const OwnerRole = z.enum(["intern", "mentor", "lead"]);
export const ItemStatus = z.enum(["not_started", "in_progress", "waiting", "done"]);
export const SkillLevel = z.enum(["novice", "familiar", "confident"]);
export const AccessLevel = z.enum(["read", "edit", "admin"]);

export type Role = z.infer<typeof Role>;
export type Stage = z.infer<typeof Stage>;
export type OwnerRole = z.infer<typeof OwnerRole>;
export type ItemStatus = z.infer<typeof ItemStatus>;
export type SkillLevel = z.infer<typeof SkillLevel>;
export type AccessLevel = z.infer<typeof AccessLevel>;

export type DemoUser = {
  id: string;
  name: string;
  role: Role;
  team: string;
  mentor_id?: string | null;
  lead_id?: string | null; // руководитель — решает заявки на отгул (SPEC 3.8)
};

export const PlanItem = z.object({
  id: z.string(),
  intern_id: z.string(),
  stage: Stage,
  order: z.number(),
  title: z.string(),
  summary: z.string(),
  owner_role: OwnerRole,
  topic: z.string().nullable(),
  doc_source_id: z.string().nullable(),
  resource_id: z.string().nullable(),
  due_day: z.number().nullable(),
  practice: z.string().nullable(),
  status: ItemStatus,
  status_reason: z.string().nullable(),
  updated_at: z.string(),
  updated_by: z.string().nullable(),
  overdue: z.boolean(),
  waiting_for: z.string().nullable(),
  waiting_days: z.number().nullable(),
  // SPEC 3.1, docs/API.md (11.11): общий пункт («для всех») или персональный («для тебя») с подписью «почему».
  // Сервер может ещё не присылать эти поля — тогда пункт общий, а уровень берётся из карты навыков.
  kind: z.enum(["common", "personal"]).default("common"),
  reason: z.string().nullable().default(null),
  skill_level: SkillLevel.nullable().optional(),
  known_marked: z.boolean().default(false),
  catalog_key: z.string().nullable().default(null),
});
export type PlanItem = z.infer<typeof PlanItem>;

export const StageInfo = z.object({
  stage: Stage,
  title: z.string(),
  total: z.number(),
  done: z.number(),
  state: z.enum(["passed", "current", "ahead"]),
});
export type StageInfo = z.infer<typeof StageInfo>;

export const Plan = z.object({
  intern_id: z.string(),
  current_day: z.number(),
  items: z.array(PlanItem),
  ladder: z.array(StageInfo),
  next_step: z.object({ item: PlanItem.nullable(), waiting: z.array(PlanItem) }),
});
export type Plan = z.infer<typeof Plan>;
export type NextStep = Plan["next_step"];

export const AccessResource = z.object({
  id: z.string(),
  title: z.string(),
  kind: z.enum(["base", "team_space"]),
  team: z.string().nullable(),
  approver: z.enum(["auto", "mentor"]),
});
export type AccessResource = z.infer<typeof AccessResource>;

export const AccessRequest = z.object({
  id: z.string(),
  intern_id: z.string(),
  resource_id: z.string(),
  level: AccessLevel,
  justification: z.string(),
  status: z.enum(["created", "pending_approval", "granted", "rejected"]),
  approver_id: z.string().nullable(),
  reject_reason: z.string().nullable(),
  plan_item_id: z.string().nullable(),
  created_day: z.number(),
  resource_title: z.string().optional(), // есть в GET /access/requests
});
export type AccessRequest = z.infer<typeof AccessRequest>;

export const SkillProfile = z.object({
  intern_id: z.string(),
  skills: z.record(z.string(), SkillLevel),
  strengths: z.array(z.string()),
  growth: z.array(z.string()),
  updated_by: z.string().nullable().optional(), // кто последним менял уровень (наставник)
});
export type SkillProfile = z.infer<typeof SkillProfile>;

export const Reminder = z.object({
  id: z.string(),
  user_id: z.string(),
  plan_item_id: z.string().nullable(),
  request_id: z.string().nullable(),
  text: z.string(),
  status: z.enum(["active", "snoozed", "done"]),
  created_day: z.number(),
  snooze_until_day: z.number().nullable(),
});
export type Reminder = z.infer<typeof Reminder>;

export const Action = z.object({
  id: z.string(),
  user_id: z.string(),
  tool: z.string(),
  title: z.string(),
  params: z.record(z.string(), z.unknown()),
  status: z.enum(["pending", "running", "done", "failed", "cancelled"]), // running — выполняется прямо сейчас
  result: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
});
export type Action = z.infer<typeof Action>;

export const Source = z.object({ title: z.string(), url: z.string().nullable() });
export const ChatResponse = z.object({
  answer_id: z.string().nullable().optional(), // для оценки «полезно / не полезно» (спека 302)
  reply: z.string(),
  sources: z.array(Source).default([]),
  actions: z.array(Action).default([]),
});
export type ChatResponse = z.infer<typeof ChatResponse>;

export const DocSource = z.object({ title: z.string(), url: z.string().nullable() });
export type DocSource = z.infer<typeof DocSource>;
/** Объяснение пункта без модели: текст из раздела документа пункта (аудит S1, S7); записано в события. */
export const ExplainedResponse = z.object({
  answer_id: z.string(), text: z.string(), source: DocSource.nullable(), chips: z.array(z.string()),
});
export type ExplainKind = "explain" | "steps" | "who";
export const Health = z.object({ status: z.string(), llm_provider: z.string() });
export const InternsResponse = z.object({ interns: z.array(z.object({ id: z.string(), name: z.string(), team: z.string() })) });
export const RequestsResponse = z.object({ requests: z.array(AccessRequest) });
export const ResourcesResponse = z.object({ resources: z.array(AccessResource) });
export const RemindersResponse = z.object({ reminders: z.array(Reminder) });
export const DaysResponse = z.object({ days: z.record(z.string(), z.number()) });
export const ResetResponse = z.object({ status: z.string() });

// GET /plan/summary — «Итоги недели» (SPEC 3.2): только факты из событий, без оценок.
export const WeeklySummary = z.object({
  intern_id: z.string(),
  week: z.number(),
  closed: z.array(z.object({ item_id: z.string(), title: z.string(), day: z.number() })),
  access_granted: z.array(z.object({ request_id: z.string(), resource_id: z.string(), day: z.number() })),
  carry_over: z.array(PlanItem),
});
export type WeeklySummary = z.infer<typeof WeeklySummary>;

// GET /metrics — только темы и количество, без текстов вопросов (спека 302).
const TopicCount = z.object({ topic: z.string(), title: z.string(), count: z.number() });
export const Metrics = z.object({
  interns: z.array(z.string()),
  questions: z.number(),
  closed_without_human: z.number(),
  with_source_share: z.number(),
  refused: z.number(),
  drafts: z.number(),
  avg_latency_ms: z.number(),
  feedback: z.object({ useful: z.number(), not_useful: z.number() }),
  topics: z.array(TopicCount),
  unanswered_topics: z.array(TopicCount),
  conflict_topics: z.array(TopicCount).default([]), // документы противоречат друг другу (SPEC 3.7)
});
export type Metrics = z.infer<typeof Metrics>;

// GET /chat/history — своя переписка, старые сверху (SPEC 9).
export const ChatHistory = z.object({
  messages: z.array(z.object({
    id: z.string(),
    role: z.enum(["user", "assistant"]),
    content: z.string(),
    sources: z.array(DocSource),
    answer_id: z.string().nullable(),
    scripted: z.boolean(),
  })),
});
export const ActionsResponse = z.object({ actions: z.array(Action) });

// SPEC 4 (11.11): бот предлагает поднять уровень, решает наставник. Стажёру эндпоинт отвечает 404.
export const SkillSuggestion = z.object({
  id: z.string(),
  intern_id: z.string(),
  intern_name: z.string(),
  topic: z.string(),
  topic_title: z.string(),
  from_level: SkillLevel,
  to_level: SkillLevel,
  basis: z.string(),
  created_day: z.number(),
  status: z.enum(["pending", "accepted", "dismissed"]),
  decided_day: z.number().nullable(),
});
export type SkillSuggestion = z.infer<typeof SkillSuggestion>;
export const SuggestionsResponse = z.object({ suggestions: z.array(SkillSuggestion) });

// SPEC 5 (11.11): два плана рядом — общие пункты совпадают, персональные различаются. Не рейтинг.
export const PlanCompare = z.object({
  interns: z.array(z.object({ id: z.string(), name: z.string() })),
  common: z.array(z.object({
    key: z.string(),
    title: z.string(),
    stage: Stage,
    topic: z.string().nullable(),
    by_intern: z.record(z.string(), z.object({ status: ItemStatus, skill_level: SkillLevel.nullable() })),
  })),
  personal: z.record(z.string(), z.array(PlanItem)),
});
export type PlanCompare = z.infer<typeof PlanCompare>;

// SPEC 3.8 (11.11): отгул на один день. Причина — закрытый список, без медицинских подробностей.
export const AbsenceRequest = z.object({
  id: z.string(),
  intern_id: z.string(),
  intern_name: z.string(),
  lead_id: z.string(),
  day: z.string(),
  reason: z.enum(["personal", "family", "study"]),
  reason_title: z.string(),
  status: z.enum(["pending", "approved", "rejected"]),
  created_day: z.number(),
  decided_day: z.number().nullable().optional(),
});
export type AbsenceRequest = z.infer<typeof AbsenceRequest>;
export const AbsenceRequestsResponse = z.object({ requests: z.array(AbsenceRequest) });
/** Наставнику — только факт «отсутствует <дата>», без причины и номера заявки. */
export const AbsenceFactsResponse = z.object({ facts: z.array(z.object({ intern_id: z.string(), day: z.string() })) });
