// Поддельный backend для тестов интерфейса: те же адреса и формы ответов, что в docs/API.md,
// правила — упрощённая копия спеки 101 (настоящие правила и их тесты — в backend/tests/mcp).
import { vi } from "vitest";
import { DEMO_USERS, initialState, RESOURCES, type DemoState } from "./mock-data";
import type { Action, DemoUser, Plan, PlanItem, Reminder, SkillLevel, StageInfo } from "@/lib/types";

const WORKING = ["week1", "week2"];
const STEPS = [
  { title: "Недели 1–2", stages: ["week1", "week2"] },
  { title: "Месяц 1", stages: ["month1"] },
  { title: "Месяц 2", stages: ["month2"] },
  { title: "После 3 месяцев", stages: ["after3m"] },
];
const user = (id: string) => DEMO_USERS.find((u) => u.id === id)!;

function visible(actor: DemoUser): string[] {
  const interns = DEMO_USERS.filter((u) => u.role === "intern");
  if (actor.role === "intern") return [actor.id];
  if (actor.role === "mentor") return interns.filter((u) => u.mentor_id === actor.id).map((u) => u.id);
  if (actor.role === "lead") return interns.filter((u) => u.team === actor.team).map((u) => u.id);
  if (actor.role === "curator") return interns.map((u) => u.id);
  return [];
}

function derived(s: DemoState, item: PlanItem): PlanItem {
  const day = s.days[item.intern_id];
  const overdue = WORKING.includes(item.stage) && item.status !== "done" && item.due_day !== null && day > item.due_day
    && item.status !== "waiting";
  const req = s.requests.find((r) => r.plan_item_id === item.id && r.status === "pending_approval");
  return item.status === "waiting" && req
    ? { ...item, overdue, waiting_for: req.approver_id, waiting_days: day - req.created_day }
    : { ...item, overdue, waiting_for: null, waiting_days: null };
}

function plan(s: DemoState, internId: string, actor: DemoUser): Plan {
  const items = s.items.filter((i) => i.intern_id === internId).map((i) => derived(s, i));
  let found = false;
  const ladder: StageInfo[] = STEPS.map(({ title, stages }) => {
    const own = items.filter((i) => stages.includes(i.stage));
    const done = own.filter((i) => i.status === "done").length;
    let state: StageInfo["state"] = "ahead";
    if (own.length && done === own.length && !found) state = "passed";
    else if (!found) { state = "current"; found = true; }
    return { stage: stages[0] as StageInfo["stage"], title, total: own.length, done, state };
  });
  const mine = items
    .filter((i) => WORKING.includes(i.stage) && i.owner_role === actor.role && i.status !== "done" && i.status !== "waiting")
    .sort((a, b) => Number(b.overdue) - Number(a.overdue) || a.order - b.order);
  return {
    intern_id: internId, current_day: s.days[internId], items, ladder,
    next_step: { item: mine[0] ?? null, waiting: actor.role === "intern" ? items.filter((i) => i.status === "waiting") : [] },
  };
}

function reminders(s: DemoState, actor: DemoUser): Reminder[] {
  if (actor.role !== "intern") return [];
  return plan(s, actor.id, actor).items.flatMap((item) => {
    const waitingLong = item.status === "waiting" && (item.waiting_days ?? 0) >= 2;
    if (!waitingLong && !(item.overdue && item.owner_role === "intern")) return [];
    const id = `rem.${item.id}`;
    if (s.dismissedReminders.includes(id)) return [];
    return [{
      id, user_id: actor.id, plan_item_id: item.id, status: "active" as const,
      request_id: waitingLong
        ? s.requests.find((r) => r.plan_item_id === item.id && r.status === "pending_approval")?.id ?? null : null,
      text: waitingLong ? `Заявка «${item.title}» ждёт. Напомнить наставнику?` : `У пункта «${item.title}» прошёл срок.`,
      created_day: s.days[actor.id], snooze_until_day: null,
    }];
  });
}

type Route = { status: number; body: unknown };
const ok = (body: unknown): Route => ({ status: 200, body });
const err = (status: number, detail: string): Route => ({ status, body: { detail } });

export type FakeServer = {
  state: DemoState;
  actions: Action[];
  provider: string;
  chatReplies: Array<{ reply: string; actions?: Action[]; answerId?: string } | "fail" | "502">;
  calls: Array<{ method: string; path: string; user: string; body: unknown }>;
  feedback: Array<{ answer_id: string; useful: boolean }>;
  explainFails?: boolean;
  summaryFails?: boolean;
  /** GET /chat/history по пользователю (сервер хранит переписку, SPEC 9). */
  history: Record<string, Array<Record<string, unknown>>>;
  metrics: Record<string, unknown> | null;
  /** Код-слово демо-кнопок, как DEMO_KEY на сервере; не задано — кнопки открыты. */
  demoKey?: string;
};

export function installFakeServer(): FakeServer {
  const srv: FakeServer = {
    state: initialState(), actions: [], history: {}, provider: "echo", chatReplies: [], calls: [], feedback: [], metrics: null,
  };
  let reqN = 1003;
  let actN = 1;

  function handle(method: string, path: string, actor: DemoUser, body: Record<string, unknown>, demoKey?: string): Route {
    const s = srv.state;
    const url = new URL(path, "http://x");
    const p = url.pathname;
    const internId = url.searchParams.get("intern_id") ?? actor.id;
    const see = (id: string) => visible(actor).includes(id);

    if (p === "/health") return ok({ status: "ok", llm_provider: srv.provider });
    if (p === "/interns") return ok({ interns: DEMO_USERS.filter((u) => see(u.id)).map(({ id, name, team }) => ({ id, name, team })) });
    if (p === "/plan") return see(internId) ? ok(plan(s, internId, actor)) : err(404, "Не найдено");
    if (p === "/profile/skills" && method === "POST") {
      const prof = s.profiles.find((x) => x.intern_id === body.intern_id);
      if (!prof || !see(prof.intern_id)) return err(404, "Не найдено");
      if (actor.role !== "mentor") return err(403, "Нет прав");
      prof.skills = { ...prof.skills, [String(body.topic)]: body.level as SkillLevel };
      prof.updated_by = actor.id;
      return ok(prof);
    }
    if (p === "/profile/skills") {
      const prof = s.profiles.find((x) => x.intern_id === internId);
      return see(internId) && (actor.role === "intern" || actor.role === "mentor") && prof ? ok(prof) : err(404, "Не найдено");
    }
    if (p === "/plan/summary") {
      if (srv.summaryFails) return err(500, "Ошибка");
      if (!see(internId)) return err(404, "Не найдено");
      const own = s.items.filter((i) => i.intern_id === internId && WORKING.includes(i.stage));
      return ok({
        intern_id: internId, week: Number(url.searchParams.get("week") ?? 1),
        closed: own.filter((i) => i.status === "done").map((i) => ({ item_id: i.id, title: i.title, day: 1 })),
        access_granted: s.requests.filter((r) => r.intern_id === internId && r.status === "granted")
          .map((r) => ({ request_id: r.id, resource_id: r.resource_id, day: 1 })),
        carry_over: own.filter((i) => i.status !== "done").map((i) => derived(s, i)),
      });
    }
    if (p === "/access/resources") return ok({ resources: RESOURCES });
    if (p === "/access/requests") {
      const mine = s.requests.filter((r) => see(r.intern_id));
      return ok({ requests: mine.map((r) => ({ ...r, resource_title: RESOURCES.find((x) => x.id === r.resource_id)?.title })) });
    }
    if (p === "/reminders") return ok({ reminders: reminders(s, actor) });
    let m = p.match(/^\/reminders\/(.+)\/(snooze|done)$/);
    if (m) {
      s.dismissedReminders.push(m[1]);
      return ok({ id: m[1], user_id: actor.id, plan_item_id: null, request_id: null, text: "", status: m[2] === "done" ? "done" : "snoozed", created_day: 1, snooze_until_day: null });
    }
    m = p.match(/^\/plan\/items\/(.+)\/status$/);
    if (m) {
      const item = s.items.find((i) => i.id === m![1]);
      if (!item || !see(item.intern_id)) return err(404, "Не найдено");
      if (item.owner_role !== actor.role) return err(403, "Действие запрещено");
      item.status = body.status as PlanItem["status"];
      return ok(derived(s, item));
    }
    m = p.match(/^\/access\/requests\/(.+)\/decide$/);
    if (m) {
      const req = s.requests.find((r) => r.id === m![1]);
      if (!req || req.approver_id !== actor.id) return err(404, "Не найдено");
      if (!body.approve && !body.reason) return err(422, "Нужна причина");
      req.status = body.approve ? "granted" : "rejected";
      const item = s.items.find((i) => i.id === req.plan_item_id);
      if (item) { item.status = body.approve ? "done" : "in_progress"; item.status_reason = body.approve ? null : String(body.reason); }
      return ok(req);
    }
    if (p === "/chat/history") return ok({ messages: srv.history[actor.id] ?? [] });
    if (p === "/actions" && method === "GET") return ok({ actions: srv.actions.filter((a) => a.user_id === actor.id) });
    if (p === "/actions" && method === "POST") {
      if (actor.role !== "intern") return err(403, "Нет прав на это действие");
      const params = body.params as Record<string, unknown>;
      const res = RESOURCES.find((r) => r.id === params.resource_id);
      const action: Action = {
        id: `act_${actN++}`, user_id: actor.id, tool: String(body.tool), params, status: "pending", result: null, error: null,
        title: `Заявка на доступ: ${res?.title}, права — чтение`,
      };
      srv.actions.push(action);
      return { status: 201, body: action };
    }
    m = p.match(/^\/actions\/(.+)\/(confirm|cancel)$/);
    if (m) {
      const action = srv.actions.find((a) => a.id === m![1] && a.user_id === actor.id);
      if (!action) return err(404, "Действие не найдено");
      if (m[2] === "cancel") { action.status = "cancelled"; return ok(action); }
      const params = action.params as { resource_id: string; justification: string };
      const res = RESOURCES.find((r) => r.id === params.resource_id)!;
      const item = s.items.find((i) => i.intern_id === actor.id && i.resource_id === res.id)!;
      if (s.requests.some((r) => r.resource_id === res.id && r.intern_id === actor.id && r.status !== "rejected")) {
        action.status = "failed"; action.error = "Заявка на этот ресурс уже есть"; return ok(action);
      }
      const auto = res.approver === "auto";
      const req = {
        id: `REQ-${reqN++}`, intern_id: actor.id, resource_id: res.id, level: "read" as const, justification: params.justification,
        status: auto ? ("granted" as const) : ("pending_approval" as const), approver_id: auto ? null : actor.mentor_id ?? null,
        reject_reason: null, plan_item_id: item.id, created_day: s.days[actor.id],
      };
      s.requests.unshift(req);
      item.status = auto ? "done" : "waiting";
      action.status = "done";
      action.result = { status: "created", request: req };
      return ok(action);
    }
    if (p.startsWith("/demo/") && srv.demoKey && decodeURIComponent(demoKey ?? "") !== srv.demoKey) {
      return err(403, "Нужно код-слово демо");
    }
    if (p === "/demo/next-day") {
      for (const k of Object.keys(s.days)) s.days[k] += 1;
      return ok({ days: s.days });
    }
    if (p === "/demo/reset") {
      srv.state = initialState();
      return ok({ status: "reset" });
    }
    m = p.match(/^\/plan\/items\/(.+)\/explained$/);
    if (m && method === "POST") {
      if (srv.explainFails) return err(500, "Ошибка");
      if (!s.items.some((i) => i.id === m![1])) return err(404, "Не найдено");
      const item = s.items.find((i) => i.id === m![1])!;
      const kind = String(body.kind ?? "explain");
      const text = kind === "steps" ? `По шагам: ${item.title}` : kind === "who" ? `К кому идти: ${item.title}` : `Из документа: ${item.summary}`;
      const chips = ["Как это сделать по шагам?", "К кому идти, если не получается?"].filter((_, n) => kind !== ["steps", "who"][n]);
      return {
        status: 201,
        body: {
          answer_id: `ans_${kind}_${m[1]}`, text, chips,
          source: item.doc_source_id ? { title: "Первые дни стажёра", url: "https://example.org/doc" } : null,
        },
      };
    }
    if (p === "/feedback") {
      if (String(body.answer_id) === "ans_fail") return err(500, "Ошибка");
      srv.feedback.push(body as { answer_id: string; useful: boolean });
      return { status: 204, body: null };
    }
    if (p === "/metrics") {
      if (!["mentor", "lead", "curator"].includes(actor.role)) return err(404, "Не найдено");
      return srv.metrics ? ok(srv.metrics) : ok({
        interns: visible(actor), questions: 0, closed_without_human: 0, with_source_share: 0, refused: 0, drafts: 0,
        avg_latency_ms: 0, feedback: { useful: 0, not_useful: 0 }, topics: [], unanswered_topics: [], conflict_topics: [],
      });
    }
    if (p === "/chat") {
      const next = srv.chatReplies.shift() ?? { reply: "Ответ модели" };
      if (next === "fail") throw new TypeError("Failed to fetch");
      if (next === "502") return err(502, "Помощник временно недоступен.");
      return ok({
        answer_id: next.answerId ?? "ans_1", reply: next.reply, sources: [{ title: "Первые дни", url: null }], actions: next.actions ?? [],
      });
    }
    return err(404, "Нет такого адреса");
  }

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const full = String(input);
    const path = full.replace(/^https?:\/\/[^/]+/, "");
    const headers = (init?.headers ?? {}) as Record<string, string>;
    const actor = user(headers["X-User-Id"] ?? "intern-anya");
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const method = init?.method ?? "GET";
    srv.calls.push({ method, path, user: actor.id, body });
    const route = handle(method, path, actor, body, headers["X-Demo-Key"]);
    const payload = route.status === 204 ? null : JSON.stringify(route.body);
    return new Response(payload, { status: route.status, headers: { "Content-Type": "application/json" } });
  });
  return srv;
}
