"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { askBot, ChatPanel } from "@/components/ChatPanel";
import { PlanPanel } from "@/components/PlanPanel";
import { ProfilePanel } from "@/components/ProfilePanel";
import { ReminderBell } from "@/components/ReminderBell";
import { api, ApiError, DEMO_KEY_REQUIRED } from "@/lib/api";
import {
  accessDraftParams, actionFor, explainScripted, followupQuestion, followupsFor, greeting, msgId, reminderMsg, useChat,
  type BotAction, type Msg,
} from "@/lib/chat";
import { keys, useHealth, useRefresh } from "@/lib/queries";
import { useSession } from "@/lib/store";
import type { AccessRequest, DemoUser, ExplainKind, Plan, PlanItem, Reminder } from "@/lib/types";
import { DEMO_USERS, findUser, ROLE_TITLES } from "@/lib/users";

const DEMO_KEY_STORAGE = "ai-buddy-demo-key";

function storedDemoKey(): string | undefined {
  try {
    return sessionStorage.getItem(DEMO_KEY_STORAGE) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Демо-кнопка на публичном сайте: если сервер просит код-слово — спросить один раз за вкладку (аудит D6). */
async function withDemoKey<T>(call: (key?: string) => Promise<T>): Promise<T> {
  const needsKey = (err: unknown) => err instanceof ApiError && err.status === 403 && err.message === DEMO_KEY_REQUIRED;
  try {
    return await call(storedDemoKey());
  } catch (err) {
    if (!needsKey(err)) throw err;
  }
  const key = window.prompt("Код-слово для демо-кнопок")?.trim();
  if (!key) throw new ApiError("Без код-слова демо-кнопки на этом сайте не работают.", 403);
  try {
    const result = await call(key);
    try {
      sessionStorage.setItem(DEMO_KEY_STORAGE, key);
    } catch {
      /* приватное окно — спросим снова в следующий раз */
    }
    return result;
  } catch (err) {
    throw needsKey(err) ? new ApiError("Код-слово не подошло.", 403) : err;
  }
}

export default function Home() {
  const userId = useSession((s) => s.userId);
  const setUser = useSession((s) => s.setUser);
  const actor = findUser(userId)!;
  const [tab, setTab] = useState<"plan" | "chat">("plan");
  const [view, setView] = useState<"plan" | "profile">("plan"); // левая колонка стажёра: план или «Мой профиль»
  const client = useQueryClient();
  const refresh = useRefresh();
  const health = useHealth(userId);
  const scriptedMode = ["scenario", "echo"].includes(health.data?.llm_provider ?? "");
  const [demoError, setDemoError] = useState<string | null>(null);

  const say = useChat((s) => s.push);

  async function loadPlan(internId: string): Promise<Plan | null> {
    try {
      return await client.fetchQuery({ queryKey: keys.plan(actor.id, internId), queryFn: () => api.plan(actor.id, internId) });
    } catch {
      return null;
    }
  }

  /** Новые напоминания — сообщением бота, по одному разу (имитация ИИ-крона, спека 301). */
  async function showReminders(who: DemoUser, plan: Plan | null) {
    try {
      const { reminders } = await api.reminders(who.id);
      const fresh = reminders.filter((r) => !useChat.getState().seenReminders.includes(r.id));
      useChat.getState().markSeen(fresh.map((r) => r.id));
      for (const r of fresh) say(reminderMsg(r, plan?.items.find((i) => i.id === r.plan_item_id)));
      return fresh.length;
    } catch {
      return 0;
    }
  }

  async function welcome() {
    const who = actor;
    useChat.getState().reset([]);
    const plan = who.role === "intern" ? await loadPlan(who.id) : null;
    let approvals: AccessRequest[] = [];
    if (who.role === "mentor") {
      approvals = await api.requests(who.id).then((r) => r.requests.filter((x) => x.status === "pending_approval" && x.approver_id === who.id)).catch(() => []);
    }
    if (useSession.getState().userId !== who.id) return; // успели войти под другим пользователем
    if (who.role === "intern" && !plan) {
      say({ id: msgId(), role: "assistant", kind: "error", content: "Не получилось загрузить план. Проверь, что сервер запущен, и нажми «Сброс» или обнови страницу." });
      return;
    }
    say(greeting(who, plan, approvals));
    await showReminders(who, plan);
  }

  useEffect(() => {
    void welcome();
    // приветствие — при каждом входе под другим пользователем
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const ASKED: Record<ExplainKind, (item: PlanItem) => string> = {
    explain: (item) => `Объясни пункт «${item.title}»`,
    steps: () => "Как это сделать по шагам?",
    who: () => "К кому идти, если не получается?",
  };

  async function onExplain(item: PlanItem, kind: ExplainKind = "explain") {
    setTab("chat");
    if (!scriptedMode) return askBot(actor, followupQuestion(item, kind));
    const asked: Msg = { id: msgId(), role: "user", kind: "text", content: ASKED[kind](item) };
    try {
      // Без модели ответ строит сервер по документу пункта и записывает в события (метрики, «полезно»).
      const res = await api.explained(actor.id, item.id, item.intern_id, kind);
      say(asked, {
        id: msgId(), role: "assistant", kind: "text", scripted: true, content: res.text, answerId: res.answer_id,
        sources: res.source ? [res.source] : undefined, followups: followupsFor(item, res.chips),
        actions: kind === "explain" && item.resource_id && item.status !== "done" && item.status !== "waiting" ? [actionFor(item)] : undefined,
      });
    } catch {
      if (kind !== "explain") {
        say(asked, { id: msgId(), role: "assistant", kind: "error", content: "Не получилось связаться с сервером." });
        return;
      }
      const profile = await client
        .fetchQuery({ queryKey: keys.profile(actor.id, item.intern_id), queryFn: () => api.profile(actor.id, item.intern_id) })
        .catch(() => undefined);
      say(asked, explainScripted(item, profile));
    }
  }

  async function onDo(item: PlanItem) {
    setTab("chat");
    say({ id: msgId(), role: "user", kind: "text", content: `Сделай за меня: ${item.title}` });
    try {
      const draft = await api.draft(actor.id, "create_access_request", accessDraftParams(item, actor));
      say({ id: msgId(), role: "assistant", kind: "draft", content: "Подготовил черновик заявки. Проверь и подтверди — без тебя ничего не отправлю.", draft });
    } catch (err) {
      say({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message });
    }
  }

  async function onAction(a: BotAction) {
    if (a.kind === "snooze") {
      await api.snooze(actor.id, a.reminderId).catch(() => undefined);
      await refresh();
      say({ id: msgId(), role: "assistant", kind: "text", scripted: true, content: "Хорошо, напомню завтра." });
      return;
    }
    const plan = await loadPlan(a.internId);
    const item = plan?.items.find((i) => i.id === a.itemId);
    if (!item) return;
    if (a.kind === "do") await onDo(item);
    else await onExplain(item, a.kind);
  }

  /** Из колокольчика: показать напоминание в чате с кнопками действия. */
  async function openReminder(r: Reminder) {
    setTab("chat");
    const plan = actor.role === "intern" ? await loadPlan(actor.id) : null;
    say(reminderMsg(r, plan?.items.find((i) => i.id === r.plan_item_id)));
  }

  async function nextDay() {
    setDemoError(null);
    try {
      await withDemoKey((key) => api.nextDay(actor.id, key));
      await refresh();
      const plan = actor.role === "intern" ? await loadPlan(actor.id) : null;
      const shown = await showReminders(actor, plan);
      if (!shown) say({ id: msgId(), role: "assistant", kind: "text", scripted: true, content: "Новый день. Зависших пунктов нет." });
    } catch (err) {
      setDemoError((err as Error).message);
    }
  }

  async function reset() {
    setDemoError(null);
    try {
      await withDemoKey((key) => api.reset(actor.id, key));
      await client.invalidateQueries();
      await welcome();
    } catch (err) {
      setDemoError((err as Error).message);
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-black/10 px-4 py-2.5 dark:border-white/10">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-full bg-[#00aaff] text-sm font-bold text-white">AI</span>
          <h1 className="text-lg font-semibold">AI-buddy</h1>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-black/55 dark:text-white/55">Войти как</span>
          <select
            value={userId}
            onChange={(e) => setUser(e.target.value)}
            className="rounded-lg border border-black/15 bg-transparent px-2 py-1 dark:border-white/20"
          >
            {DEMO_USERS.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} — {ROLE_TITLES[u.role]}
              </option>
            ))}
          </select>
        </label>
        <div className="ml-auto">
          <ReminderBell actor={actor} onOpen={openReminder} />
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-dashed border-black/20 px-2 py-1 text-xs dark:border-white/20">
          <span className="text-black/45 dark:text-white/45">
            Демо-панель{scriptedMode ? " · сценарный режим (без ключа модели)" : ""}
          </span>
          <button onClick={nextDay} className="rounded-md bg-black/5 px-2 py-1 hover:bg-black/10 dark:bg-white/10">Следующий день</button>
          <button onClick={reset} className="rounded-md px-2 py-1 hover:bg-black/5 dark:hover:bg-white/10">Сброс</button>
        </div>
        {demoError && <p role="alert" className="w-full text-xs text-red-700 dark:text-red-300">{demoError}</p>}
      </header>

      <div className="flex border-b border-black/10 md:hidden dark:border-white/10" role="tablist">
        {(["plan", "chat"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2 text-sm font-medium ${tab === t ? "border-b-2 border-[#00aaff]" : "text-black/50 dark:text-white/50"}`}
          >
            {t === "plan" ? "План" : "Чат"}
          </button>
        ))}
      </div>

      <main className="grid min-h-0 flex-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className={`min-h-0 overflow-y-auto overscroll-contain border-black/10 md:block md:border-r dark:border-white/10 ${tab === "plan" ? "block" : "hidden"}`}>
          {actor.role === "intern" && (
            <div className="flex gap-1 px-4 pt-4 sm:px-5" role="tablist" aria-label="Левая колонка">
              {([["plan", "Мой план"], ["profile", "Мой профиль"]] as const).map(([v, label]) => (
                <button
                  key={v}
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => setView(v)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${view === v ? "bg-black/5 dark:bg-white/10" : "text-black/55 hover:bg-black/5 dark:text-white/55 dark:hover:bg-white/10"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          {actor.role === "intern" && view === "profile"
            ? <ProfilePanel actor={actor} />
            : <PlanPanel actor={actor} onExplain={onExplain} onDo={onDo} />}
        </div>
        <div className={`min-h-0 md:block ${tab === "chat" ? "block" : "hidden"}`}>
          <ChatPanel actor={actor} onAction={onAction} />
        </div>
      </main>
    </div>
  );
}
