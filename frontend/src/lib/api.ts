// Клиент к backend. Контракт — docs/API.md. Каждый ответ проверяется схемой Zod (lib/types.ts).
import type { z } from "zod";
import type { ExplainKind } from "./types";
import {
  CatalogResponse, AbsenceFactsResponse, AbsenceRequest, AbsenceRequestsResponse, AccessRequest, Action, ActionsResponse, ChatHistory, ChatResponse, DaysResponse, DocumentView, MentorQuestion, MentorQuestionsResponse, ExplainedResponse, Health, InternsResponse, Metrics, Plan, PlanItem,
  PlanCompare, PracticeResult, Reminder, RemindersResponse, RequestsResponse, ResetResponse, ResourcesResponse, SkillLevel, SkillProfile,
  SkillSuggestion, SuggestionsResponse, WeeklySummary,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatMessage = { role: "user" | "assistant"; content: string };

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const OFFLINE = "Не получилось связаться с сервером.";

function detailText(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Проверь введённые данные.";
  return `Ошибка сервера: ${status}`;
}

async function request<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  userId: string,
  init?: { method?: string; body?: unknown; headers?: Record<string, string> },
): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: init?.method ?? "GET",
      // X-User-Id — имитация входа, в Авито заменяется SSO (docs/API.md)
      headers: { "Content-Type": "application/json", "X-User-Id": userId, ...init?.headers },
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new ApiError(OFFLINE, 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(detailText(body.detail, res.status), res.status);
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new ApiError("Сервер ответил в неожиданном формате.", res.status);
  return parsed.data;
}

/** Код-слово демо-кнопок на публичном сайте (docs/API.md). Кириллицу браузер в заголовке не пропустит — кодируем. */
export const DEMO_KEY_REQUIRED = "Нужно код-слово демо";
const demoKey = (key?: string): Record<string, string> => (key ? { "X-Demo-Key": encodeURIComponent(key) } : {});

const q = (internId?: string) => (internId ? `?intern_id=${encodeURIComponent(internId)}` : "");
const post = (body: unknown = {}) => ({ method: "POST", body });

export const api = {
  health: (u: string) => request("/health", Health, u),
  chat: (u: string, messages: ChatMessage[]) => request("/chat", ChatResponse, u, post({ messages })),
  interns: (u: string) => request("/interns", InternsResponse, u),
  plan: (u: string, internId?: string) => request(`/plan${q(internId)}`, Plan, u),
  setStatus: (u: string, itemId: string, status: "done" | "in_progress", reason?: string) =>
    request(`/plan/items/${encodeURIComponent(itemId)}/status`, PlanItem, u, post({ status, reason })),
  explained: (u: string, itemId: string, internId?: string, kind: ExplainKind = "explain") =>
    request(`/plan/items/${encodeURIComponent(itemId)}/explained${q(internId)}`, ExplainedResponse, u, post({ kind })),
  summary: (u: string, internId: string, week: number) =>
    request(`/plan/summary?intern_id=${encodeURIComponent(internId)}&week=${week}`, WeeklySummary, u),
  resources: (u: string) => request("/access/resources", ResourcesResponse, u),
  requests: (u: string, internId?: string) => request(`/access/requests${q(internId)}`, RequestsResponse, u),
  decide: (u: string, requestId: string, approve: boolean, reason?: string) =>
    request(`/access/requests/${encodeURIComponent(requestId)}/decide`, AccessRequest, u, post({ approve, reason })),
  profile: (u: string, internId?: string) => request(`/profile/skills${q(internId)}`, SkillProfile, u),
  setSkill: (u: string, internId: string, topic: string, level: SkillLevel) =>
    request("/profile/skills", SkillProfile, u, post({ intern_id: internId, topic, level })),
  reminders: (u: string) => request("/reminders", RemindersResponse, u),
  snooze: (u: string, id: string) => request(`/reminders/${encodeURIComponent(id)}/snooze`, Reminder, u, post({ days: 1 })),
  doneReminder: (u: string, id: string) => request(`/reminders/${encodeURIComponent(id)}/done`, Reminder, u, post()),
  history: (u: string) => request("/chat/history", ChatHistory, u),
  mentorQuestions: (u: string) => request("/mentor/questions", MentorQuestionsResponse, u),
  askMentor: (u: string, text: string) => request("/mentor/questions", MentorQuestion, u, post({ text })),
  answerMentor: (u: string, id: string, text: string, publish: boolean, topic?: string) =>
    request(`/mentor/questions/${encodeURIComponent(id)}/answer`, MentorQuestion, u, post({ text, publish, topic })),
  publishMentor: (u: string, id: string, topic?: string) =>
    request(`/mentor/questions/${encodeURIComponent(id)}/publish`, MentorQuestion, u, post({ topic })),
  document: (u: string, title: string) => request(`/documents?title=${encodeURIComponent(title)}`, DocumentView, u),
  actions: (u: string) => request("/actions", ActionsResponse, u),
  draft: (u: string, tool: string, params: Record<string, unknown>) => request("/actions", Action, u, post({ tool, params })),
  // «Сделать за меня» (чекпоинт 2): простой доступ сервер оформляет сразу (status "done"), остальное — черновик.
  quickDraft: (u: string, tool: string, params: Record<string, unknown>) =>
    request("/actions", Action, u, post({ tool, params, quick: true })),
  confirm: (u: string, id: string) => request(`/actions/${encodeURIComponent(id)}/confirm`, Action, u, post()),
  cancel: (u: string, id: string) => request(`/actions/${encodeURIComponent(id)}/cancel`, Action, u, post()),
  feedback: async (u: string, answerId: string, useful: boolean) => {
    let res: Response;
    try {
      res = await fetch(`${API_URL}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-Id": u },
        body: JSON.stringify({ answer_id: answerId, useful }),
      });
    } catch {
      throw new ApiError(OFFLINE, 0);
    }
    if (!res.ok) throw new ApiError(`Ошибка сервера: ${res.status}`, res.status);
  },
  metrics: (u: string, internId?: string) => request(`/metrics${q(internId)}`, Metrics, u),
  catalog: (u: string, internId: string) => request(`/plan/catalog${q(internId)}`, CatalogResponse, u),
  addPersonal: (u: string, internId: string, catalogKey: string) =>
    request("/plan/items", PlanItem, u, post({ intern_id: internId, catalog_key: catalogKey })),
  /** DELETE отвечает 204 без тела — поэтому мимо общего request(). */
  removePersonal: async (u: string, itemId: string) => {
    let res: Response;
    try {
      res = await fetch(`${API_URL}/plan/items/${encodeURIComponent(itemId)}`, { method: "DELETE", headers: { "X-User-Id": u } });
    } catch {
      throw new ApiError(OFFLINE, 0);
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(detailText(body.detail, res.status), res.status);
    }
  },
  practice: (u: string, itemId: string, answer: string) =>
    request(`/plan/items/${encodeURIComponent(itemId)}/practice`, PracticeResult, u, post({ answer })),
  markKnown: (u: string, itemId: string, known: boolean) =>
    request(`/plan/items/${encodeURIComponent(itemId)}/known`, PlanItem, u, post({ known })),
  suggestions: (u: string) => request("/skills/suggestions?status=pending", SuggestionsResponse, u),
  decideSuggestion: (u: string, id: string, accept: boolean) =>
    request(`/skills/suggestions/${encodeURIComponent(id)}/decide`, SkillSuggestion, u, post({ accept })),
  absenceRequests: (u: string) => request("/absence/requests", AbsenceRequestsResponse, u),
  decideAbsence: (u: string, id: string, approve: boolean) =>
    request(`/absence/requests/${encodeURIComponent(id)}/decide`, AbsenceRequest, u, post({ approve })),
  absenceFacts: (u: string, internId: string) => request(`/absence/facts${q(internId)}`, AbsenceFactsResponse, u),
  compare: (u: string, a: string, b: string) =>
    request(`/plan/compare?intern_ids=${encodeURIComponent(a)},${encodeURIComponent(b)}`, PlanCompare, u),
  nextDay: (u: string, key?: string) => request("/demo/next-day", DaysResponse, u, { ...post(), headers: demoKey(key) }),
  reset: (u: string, key?: string) => request("/demo/reset", ResetResponse, u, { ...post(), headers: demoKey(key) }),
};
