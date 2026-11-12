// Данные с сервера через TanStack Query: кэш, повтор, статус загрузки. Ключи включают пользователя,
// чтобы при «Войти как…» не мелькали чужие данные.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { DemoUser } from "./types";

export const keys = {
  health: ["health"] as const,
  interns: (u: string) => ["interns", u] as const,
  plan: (u: string, intern: string) => ["plan", u, intern] as const,
  requests: (u: string) => ["requests", u] as const,
  resources: (u: string) => ["resources", u] as const,
  profile: (u: string, intern: string) => ["profile", u, intern] as const,
  reminders: (u: string) => ["reminders", u] as const,
  summary: (u: string, intern: string, week: number) => ["summary", u, intern, week] as const,
  metrics: (u: string, intern: string) => ["metrics", u, intern] as const,
  suggestions: (u: string) => ["suggestions", u] as const,
  compare: (u: string, a: string, b: string) => ["compare", u, a, b] as const,
  absence: (u: string) => ["absence", u] as const,
  catalog: (u: string, intern: string) => ["catalog", u, intern] as const,
  absenceFacts: (u: string, intern: string) => ["absence-facts", u, intern] as const,
};

const PLAN_ROLES = new Set(["intern", "mentor", "lead", "curator"]);

export const useHealth = (u: string) => useQuery({ queryKey: keys.health, queryFn: () => api.health(u), staleTime: 60_000 });

export const useInterns = (actor: DemoUser) =>
  useQuery({
    queryKey: keys.interns(actor.id),
    queryFn: async () => (await api.interns(actor.id)).interns,
    enabled: PLAN_ROLES.has(actor.role),
  });

export const usePlan = (actor: DemoUser, internId: string | undefined) =>
  useQuery({
    queryKey: keys.plan(actor.id, internId ?? ""),
    queryFn: () => api.plan(actor.id, internId),
    enabled: !!internId,
  });

export const useProfile = (actor: DemoUser, internId: string | undefined) =>
  useQuery({
    queryKey: keys.profile(actor.id, internId ?? ""),
    queryFn: () => api.profile(actor.id, internId),
    enabled: !!internId && (actor.role === "intern" || actor.role === "mentor"),
  });

export const useRequests = (actor: DemoUser) =>
  useQuery({
    queryKey: keys.requests(actor.id),
    queryFn: async () => (await api.requests(actor.id)).requests,
    enabled: actor.role === "intern" || actor.role === "mentor",
  });

export const useResources = (actor: DemoUser) =>
  useQuery({
    queryKey: keys.resources(actor.id),
    queryFn: async () => (await api.resources(actor.id)).resources,
    enabled: actor.role === "intern",
    staleTime: 60_000,
  });

/** Активные напоминания текущего пользователя — для колокольчика (спека 301). */
export const useReminders = (actor: DemoUser) =>
  useQuery({
    queryKey: keys.reminders(actor.id),
    queryFn: async () => (await api.reminders(actor.id)).reminders,
    enabled: actor.role !== "hrbp",
  });

export const useSummary = (actor: DemoUser, internId: string, week: number, enabled: boolean) =>
  useQuery({
    queryKey: keys.summary(actor.id, internId, week),
    queryFn: () => api.summary(actor.id, internId, week),
    enabled,
  });

export const useMetrics = (actor: DemoUser, internId?: string) =>
  useQuery({
    queryKey: keys.metrics(actor.id, internId ?? ""),
    queryFn: () => api.metrics(actor.id, internId),
    enabled: ["mentor", "lead", "curator"].includes(actor.role),
  });

/** Новые эндпоинты 11.11 могут ещё не быть на сервере: 404 → «пока пусто», а не ошибка на экране. */
async function orEmpty<T>(load: () => Promise<T>, empty: T): Promise<T> {
  try {
    return await load();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return empty;
    throw e;
  }
}

/** Предложения бота поднять уровень (SPEC 4) — только наставнику. */
export const useSuggestions = (actor: DemoUser) =>
  useQuery({
    queryKey: keys.suggestions(actor.id),
    queryFn: () => orEmpty(async () => (await api.suggestions(actor.id)).suggestions, []),
    enabled: actor.role === "mentor",
    retry: false, // пока адреса нет на сервере, браузер видит сбой CORS — не повторяем впустую
  });

/** Два плана рядом (SPEC 5). null — сервер сравнение пока не умеет. */
export const useCompare = (actor: DemoUser, a: string, b: string, enabled: boolean) =>
  useQuery({
    queryKey: keys.compare(actor.id, a, b),
    queryFn: () => orEmpty(() => api.compare(actor.id, a, b), null),
    enabled: enabled && actor.role === "mentor" && !!a && !!b && a !== b,
    retry: false,
  });

/** Каталог персональных пунктов команды стажёра — только наставнику (SPEC 3.1). */
export const useCatalog = (actor: DemoUser, internId: string | undefined) =>
  useQuery({
    queryKey: keys.catalog(actor.id, internId ?? ""),
    queryFn: () => orEmpty(async () => (await api.catalog(actor.id, internId!)).items, []),
    enabled: actor.role === "mentor" && !!internId,
    retry: false,
  });

/** Заявки на отгул (SPEC 3.8): стажёру — свои, руководителю — своей команды. */
export const useAbsenceRequests = (actor: DemoUser) =>
  useQuery({
    queryKey: keys.absence(actor.id),
    queryFn: () => orEmpty(async () => (await api.absenceRequests(actor.id)).requests, []),
    enabled: actor.role === "intern" || actor.role === "lead",
    retry: false,
  });

/** Наставнику — только даты отсутствия своего стажёра. */
export const useAbsenceFacts = (actor: DemoUser, internId: string) =>
  useQuery({
    queryKey: keys.absenceFacts(actor.id, internId),
    queryFn: () => orEmpty(async () => (await api.absenceFacts(actor.id, internId)).facts, []),
    enabled: actor.role === "mentor",
    retry: false,
  });

/** После любого изменения на сервере обновляем всё, что могло измениться. */
export function useRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["plan", "requests", "reminders", "profile", "summary", "metrics", "suggestions", "compare", "absence", "absence-facts", "catalog"].map((k) =>
        client.invalidateQueries({ queryKey: [k] }),
      ),
    );
}
