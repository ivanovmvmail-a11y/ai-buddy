// Клиент к backend. Контракт — docs/API.md. Каждый ответ проверяется схемой Zod (lib/types.ts).
import type { z } from "zod";
import {
  AccessRequest, Action, ChatResponse, DaysResponse, Health, InternsResponse, Plan, PlanItem,
  Reminder, RemindersResponse, RequestsResponse, ResetResponse, ResourcesResponse, SkillProfile, WeeklySummary,
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
  init?: { method?: string; body?: unknown },
): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: init?.method ?? "GET",
      // X-User-Id — имитация входа, в Авито заменяется SSO (docs/API.md)
      headers: { "Content-Type": "application/json", "X-User-Id": userId },
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

const q = (internId?: string) => (internId ? `?intern_id=${encodeURIComponent(internId)}` : "");
const post = (body: unknown = {}) => ({ method: "POST", body });

export const api = {
  health: (u: string) => request("/health", Health, u),
  chat: (u: string, messages: ChatMessage[]) => request("/chat", ChatResponse, u, post({ messages })),
  interns: (u: string) => request("/interns", InternsResponse, u),
  plan: (u: string, internId?: string) => request(`/plan${q(internId)}`, Plan, u),
  setStatus: (u: string, itemId: string, status: "done" | "in_progress", reason?: string) =>
    request(`/plan/items/${encodeURIComponent(itemId)}/status`, PlanItem, u, post({ status, reason })),
  summary: (u: string, internId: string, week: number) =>
    request(`/plan/summary?intern_id=${encodeURIComponent(internId)}&week=${week}`, WeeklySummary, u),
  resources: (u: string) => request("/access/resources", ResourcesResponse, u),
  requests: (u: string, internId?: string) => request(`/access/requests${q(internId)}`, RequestsResponse, u),
  decide: (u: string, requestId: string, approve: boolean, reason?: string) =>
    request(`/access/requests/${encodeURIComponent(requestId)}/decide`, AccessRequest, u, post({ approve, reason })),
  profile: (u: string, internId?: string) => request(`/profile/skills${q(internId)}`, SkillProfile, u),
  reminders: (u: string) => request("/reminders", RemindersResponse, u),
  snooze: (u: string, id: string) => request(`/reminders/${encodeURIComponent(id)}/snooze`, Reminder, u, post({ days: 1 })),
  doneReminder: (u: string, id: string) => request(`/reminders/${encodeURIComponent(id)}/done`, Reminder, u, post()),
  draft: (u: string, tool: string, params: Record<string, unknown>) => request("/actions", Action, u, post({ tool, params })),
  confirm: (u: string, id: string) => request(`/actions/${encodeURIComponent(id)}/confirm`, Action, u, post()),
  cancel: (u: string, id: string) => request(`/actions/${encodeURIComponent(id)}/cancel`, Action, u, post()),
  nextDay: (u: string) => request("/demo/next-day", DaysResponse, u, post()),
  reset: (u: string) => request("/demo/reset", ResetResponse, u, post()),
};
