// Данные с сервера через TanStack Query: кэш, повтор, статус загрузки. Ключи включают пользователя,
// чтобы при «Войти как…» не мелькали чужие данные.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { DemoUser } from "./types";

export const keys = {
  health: ["health"] as const,
  interns: (u: string) => ["interns", u] as const,
  plan: (u: string, intern: string) => ["plan", u, intern] as const,
  requests: (u: string) => ["requests", u] as const,
  resources: (u: string) => ["resources", u] as const,
  profile: (u: string, intern: string) => ["profile", u, intern] as const,
  reminders: (u: string) => ["reminders", u] as const,
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

/** После любого изменения на сервере обновляем всё, что могло измениться. */
export function useRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["plan", "requests", "reminders", "profile"].map((k) => client.invalidateQueries({ queryKey: [k] })),
    );
}
