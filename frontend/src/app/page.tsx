"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { PlanPanel } from "@/components/PlanPanel";
import { HomePanel } from "@/components/HomePanel";
import { ProfilePanel } from "@/components/ProfilePanel";
import { SECTIONS, Sidebar, demoDate, type Section } from "@/components/Sidebar";
import { ReminderBell } from "@/components/ReminderBell";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api, ApiError, DEMO_KEY_REQUIRED } from "@/lib/api";
import {
  absenceNudgeMsg, accessDraftParams, explainScripted, finishedWeek, followupsFor, greeting, itemActions, msgId, reminderMsg,
  nudgeMsg, useChat, weeklySummaryMsg,
  guessTopic, reminderTopic, TOPICS, type BotAction, type Msg, type Topic,
} from "@/lib/chat";
import { doneOnOpen, kindOf, sectionFor, targetOf } from "@/lib/notifications";
import { keys, useHealth, useRefresh } from "@/lib/queries";
import { savedUserId, useSession } from "@/lib/store";
import type { AccessRequest, DemoUser, ExplainKind, Plan, PlanItem, Reminder } from "@/lib/types";
import { findUser } from "@/lib/users";

const DEMO_KEY_STORAGE = "ai-buddy-demo-key";
const EXPLAIN_LABEL = "по документу пункта · глубина по карте навыков";

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
  const pickIntern = useSession((s) => s.pickIntern);
  const actor = findUser(userId)!;
  const [tab, setTab] = useState<"plan" | "chat">("plan");
  // Раздел в центре (редизайн 13.11): у стажёра «Главная» из карточек, «Мой план», «Мой профиль»; у остальных — план.
  const view = useSession((s) => s.section);
  const setView = useSession((s) => s.setSection);
  const [menuOpen, setMenuOpen] = useState(false); // телефон: левая колонка выезжает по кнопке ☰
  const section: Section = actor.role === "intern" ? view : "plan";
  const client = useQueryClient();
  const refresh = useRefresh();
  const health = useHealth(userId);
  const scriptedMode = ["scenario", "echo"].includes(health.data?.llm_provider ?? "");
  const [demoError, setDemoError] = useState<string | null>(null);

  const say = useChat((s) => s.push);
  // Телефон: бот написал, пока открыт план, — точка на вкладке «Чат» (аудит, мелочи)
  const messageCount = useChat((s) => s.messages.length);
  const [seenCount, setSeenCount] = useState(0);
  useEffect(() => {
    if (tab === "chat") setSeenCount(messageCount);
  }, [tab, messageCount]);
  const unread = messageCount > seenCount;

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
      // У стажёра напоминания лежат во вкладках своих тем — в открытой вкладке говорим, где новое.
      const elsewhere = who.role === "intern" ? fresh.filter((r) => reminderTopic(r) !== useChat.getState().tab) : [];
      if (elsewhere.length) {
        const counts = TOPICS.filter((t) => elsewhere.some((r) => reminderTopic(r) === t.id))
          .map((t) => `«${t.title}» — ${elsewhere.filter((r) => reminderTopic(r) === t.id).length}`);
        say({ id: msgId(), role: "assistant", kind: "text", scripted: true, content: `🔔 Новые напоминания: ${counts.join(", ")}.` });
      }
      return fresh.length;
    } catch {
      return 0;
    }
  }

  /** Прошлая переписка и неподтверждённые черновики — с сервера (SPEC 9, аудит D7). Сбой — начинаем с чистого чата. */
  async function restoreChat(who: DemoUser, stale: () => boolean) {
    const [past, drafts] = await Promise.all([
      api.history(who.id).then((h) => h.messages).catch(() => []),
      api.actions(who.id).then((a) => a.actions.filter((x) => x.status === "pending")).catch(() => []),
    ]);
    if (stale()) return;
    // Вкладку сервер не хранит: вопрос кладём туда же, куда ответ (по словам ответа видно тему лучше).
    for (let i = 0; i < past.length; i++) {
      const m = past[i];
      const answer = m.role === "user" ? past[i + 1] : m;
      const question = m.role === "user" ? m : past[i - 1]?.role === "user" ? past[i - 1] : undefined;
      const topic: Topic = guessTopic(answer?.content ?? m.content, question?.content);
      say({
        id: msgId(), role: m.role, kind: "text", content: m.content, server: m.scripted || undefined, topic,
        sources: m.sources.length ? m.sources : undefined, answerId: m.answer_id ?? undefined,
      });
    }
    for (const draft of [...drafts].reverse()) {
      say({ id: msgId(), role: "assistant", kind: "draft", content: "Черновик ждёт твоего решения.", draft, topic: "requests" });
    }
  }

  // Номер последнего запуска приветствия. Запуски не отменяются сами: на Railway (медленный ответ) переключение
  // туда-обратно, «Сброс» или повтор эффекта давали 2–3 одинаковых приветствия (Миша, 14.11). Дописывает только последний.
  const welcomeRun = useRef(0);

  async function welcome() {
    const who = actor;
    const run = ++welcomeRun.current;
    const stale = () => run !== welcomeRun.current || useSession.getState().userId !== who.id;
    useChat.getState().reset([]);
    await restoreChat(who, stale);
    const plan = who.role === "intern" ? await loadPlan(who.id) : null;
    let approvals: AccessRequest[] = [];
    if (who.role === "mentor") {
      approvals = await api.requests(who.id).then((r) => r.requests.filter((x) => x.status === "pending_approval" && x.approver_id === who.id)).catch(() => []);
    }
    if (stale()) return; // запущено новое приветствие или вошли под другим пользователем
    useChat.getState().setTab("assistant");
    if (who.role === "intern" && !plan) {
      say({ id: msgId(), role: "assistant", kind: "error", content: "Не получилось загрузить план. Проверь, что сервер запущен, и нажми «Сброс» или обнови страницу." });
      return;
    }
    say(greeting(who, plan, approvals));
    if (plan) await showWeekly(who, plan.current_day, stale);
    if (stale()) return;
    await showReminders(who, plan);
  }

  /** Начало новой недели — бот сам присылает итоги прошедшей (SPEC 3.2). Сбой сводки остальному не мешает. */
  async function showWeekly(who: DemoUser, day: number, stale: () => boolean = () => false) {
    const week = finishedWeek(day);
    if (week === null) return;
    try {
      const [summary, resources] = await Promise.all([
        api.summary(who.id, who.id, week),
        api.resources(who.id).then((r) => r.resources).catch(() => []),
      ]);
      if (stale()) return;
      say(weeklySummaryMsg(summary, Object.fromEntries(resources.map((r) => [r.id, r.title]))));
    } catch {
      /* сводка — дополнение к приветствию */
    }
  }

  useEffect(() => {
    const saved = savedUserId();
    if (saved && saved !== userId && findUser(saved)) setUser(saved); // вернуться под тем же пользователем
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  /** Открыть чат на нужной вкладке (чекпоинт 2: чаты разделены по темам). */
  function openChat(topic: Topic) {
    setTab("chat");
    useChat.getState().setTab(topic);
  }

  async function onExplain(item: PlanItem, kind: ExplainKind = "explain") {
    openChat("study");
    const asked: Msg = { id: msgId(), role: "user", kind: "text", content: ASKED[kind](item) };
    try {
      // Ответ строит сервер по документу пункта и под уровень стажёра — и с ключом модели, и без (проверка 13.11:
      // с GigaChat «Объяснить» давало пустые шаги, 5–7 источников и не учитывало уровень). Пишется в события.
      const res = await api.explained(actor.id, item.id, item.intern_id, kind);
      say(asked, {
        id: msgId(), role: "assistant", kind: "text", scripted: true, label: EXPLAIN_LABEL, content: res.text, answerId: res.answer_id,
        sources: res.source ? [res.source] : undefined, followups: followupsFor(item, res.chips),
        // Под объяснением — остальные кнопки пункта: сделать, сдать задание, «Готово» (чекпоинт 2: всё и из чата).
        actions: kind === "explain" && itemActions(item, actor, ["explain"]).length ? itemActions(item, actor, ["explain"]) : undefined,
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

  /** «Сделать за меня» (чекпоинт 2): нажатие кнопки — уже согласие. Простой доступ сервер оформляет сразу;
   *  доступ к коду команды и всё, что согласует человек, — черновик с «Подтвердить». */
  async function onDo(item: PlanItem) {
    openChat("requests");
    // Место для ответа — сразу под вопросом и во вкладке «Заявки» (Миша, Railway 14.11: нажал «Сделать за меня» у двух
    // пунктов подряд — ответ на первый, более долгий, уехал ниже черновика второго и казался потерянным).
    const slot = msgId();
    say(
      { id: msgId(), role: "user", kind: "text", content: `Сделай за меня: ${item.title}`, topic: "requests" },
      { id: slot, role: "assistant", kind: "text", content: "Оформляю заявку…", topic: "requests" },
    );
    const answer = (patch: Partial<Msg>) => useChat.getState().update(slot, patch);
    try {
      const action = await api.quickDraft(actor.id, "create_access_request", accessDraftParams(item, actor));
      if (action.status === "pending") {
        answer({
          kind: "draft", draft: action,
          content: "Это доступ к рабочему пространству команды — такие заявки я не отправляю без тебя. Проверь черновик и подтверди.",
        });
        return;
      }
      if (action.status === "failed") {
        answer({ kind: "error", content: `Не получилось: ${action.error}` });
        return;
      }
      const req = (action.result as { request?: AccessRequest } | null)?.request;
      const resources = await api.resources(actor.id).then((r) => r.resources).catch(() => []);
      const title = resources.find((r) => r.id === req?.resource_id)?.title ?? req?.resource_id ?? "ресурс";
      await refresh();
      await sayNext(req?.status === "granted"
        ? `Готово: заявка ${req.id} — доступ к «${title}» на чтение выдан. Подтверждать не нужно: это учебный сервис только на чтение. Пункт плана закрыт.`
        : `Заявка ${req?.id ?? ""} отправлена: ${findUser(req?.approver_id)?.name ?? "согласующий"} получит её на согласование. Я напомню, если затянется.`,
      slot);
    } catch (err) {
      answer({ kind: "error", content: (err as Error).message });
    }
  }

  /** Сообщение бота + следующий шаг плана с его кнопками. С `slot` — заполняет уже показанное место для ответа. */
  async function sayNext(text: string, slot?: string) {
    const plan = await loadPlan(actor.id);
    const next = plan?.next_step.item;
    const buttons = next ? itemActions(next, actor) : [];
    const msg = {
      role: "assistant" as const, kind: "text" as const, scripted: true, actions: buttons.length ? buttons : undefined,
      content: text + (next ? `\n\nСледующий шаг — «${next.title}».` : ""),
    };
    if (slot) useChat.getState().update(slot, msg);
    else say({ id: msgId(), ...msg });
  }

  /** «Сдать задание» — в чате (чекпоинт 2): бот даёт задание, следующее сообщение стажёра уходит на проверку. */
  function onPractice(item: PlanItem) {
    openChat("study");
    say(
      { id: msgId(), role: "user", kind: "text", content: `Сдать задание: ${item.title}` },
      {
        id: msgId(), role: "assistant", kind: "text", scripted: true, label: "задание пункта плана",
        content: `Задание: ${item.practice}\n\nНапиши ответ следующим сообщением: своими словами — что и как сделано. `
          + "Я сверю его с учебным документом пункта и подскажу, чего не хватает. Уровень по-прежнему решает наставник.",
      },
    );
    useChat.getState().setPractice({ itemId: item.id, title: item.title });
  }

  async function onMarkDone(item: PlanItem) {
    openChat("study");
    say({ id: msgId(), role: "user", kind: "text", content: `Готово: ${item.title}` });
    try {
      await api.setStatus(actor.id, item.id, "done");
      await refresh();
      await sayNext(`Отметил «${item.title}» — сделано.`);
    } catch (err) {
      say({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message });
    }
  }

  async function onAction(a: BotAction) {
    if (a.kind === "nudge") {
      openChat("requests");
      say(nudgeMsg(a.requestId, a.itemTitle));
      return;
    }
    if (a.kind === "nudge-lead") {
      openChat("requests");
      say(absenceNudgeMsg(findUser(actor.lead_id)?.name ?? ""));
      return;
    }
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
    else if (a.kind === "practice") onPractice(item);
    else if (a.kind === "done") await onMarkDone(item);
    else await onExplain(item, a.kind);
  }

  /** Из колокольчика (SPEC 3.6): кнопка ведёт туда, где действие, — к блоку на панели плана или в чат. */
  async function openReminder(r: Reminder) {
    // Факт прочитан — из колокольчика уходит, куда бы ни вела кнопка (кнопки «Готово» больше нет).
    if (doneOnOpen(r)) void api.doneReminder(actor.id, r.id).then(refresh, () => undefined);
    const section = sectionFor(r);
    if (section) {
      setTab("plan");
      setView(sectionFor(r) === "Мой профиль" ? "profile" : "home");
      if (targetOf(r) === "intern" && r.intern_id) pickIntern(r.intern_id);
      setTimeout(() => document.querySelector(`[aria-label="${section}"]`)?.scrollIntoView?.({ behavior: "smooth", block: "start" }), 50);
      return;
    }
    if (kindOf(r) === "absence_pending") {
      openChat("requests");
      say(absenceNudgeMsg(findUser(actor.lead_id)?.name ?? ""));
      return;
    }
    openChat(reminderTopic(r));
    const plan = actor.role === "intern" ? await loadPlan(actor.id) : null;
    say(reminderMsg(r, plan?.items.find((i) => i.id === r.plan_item_id)));
  }

  async function nextDay() {
    setDemoError(null);
    try {
      await withDemoKey((key) => api.nextDay(actor.id, key));
      await refresh();
      const plan = actor.role === "intern" ? await loadPlan(actor.id) : null;
      if (plan) await showWeekly(actor, plan.current_day);
      const shown = await showReminders(actor, plan);
      const today = (await api.calendar(actor.id).catch(() => null))?.today;
      const when = today ? `Новый день в демо: ${demoDate(today)} — у всех стажёров сразу.` : "Новый день.";
      if (!shown) say({ id: msgId(), role: "assistant", kind: "text", scripted: true, topic: "assistant", content: `${when} Зависших пунктов нет.` });
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

  const mobileTabs: Array<{ id: Section | "chat"; label: string }> = [
    ...(actor.role === "intern" ? (["home", "plan", "profile"] as Section[]) : (["plan"] as Section[]))
      // На телефоне коротко: «Мой профиль» сдвигал «Чат» за правый край 375 px (финальная проверка 13.11).
      .map((id) => ({ id, label: actor.role === "intern" ? (id === "profile" ? "Профиль" : SECTIONS[id]) : "План" })),
    { id: "chat", label: "Чат" },
  ];

  return (
    <div className="flex h-dvh bg-background">
      {/* Левая колонка: на компьютере всегда, на телефоне — выезжает по ☰. Один экземпляр в DOM. */}
      <div className={menuOpen ? "fixed inset-0 z-40 flex" : "hidden lg:flex"}>
        <div className="w-[272px] shrink-0">
          <Sidebar
            actor={actor}
            section={section}
            onSection={(s) => { setView(s); setTab("plan"); setMenuOpen(false); }}
            onUser={(id) => { setUser(id); setMenuOpen(false); }}
            onNextDay={nextDay}
            onReset={reset}
            scriptedMode={scriptedMode}
            demoError={demoError}
          />
        </div>
        {menuOpen && <button aria-label="Закрыть меню" onClick={() => setMenuOpen(false)} className="flex-1 bg-black/40 lg:hidden" />}
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 px-4 py-2.5 sm:px-6">
          <button
            onClick={() => setMenuOpen(true)}
            aria-label="Меню"
            className="grid size-9 place-items-center rounded-full hover:bg-black/5 lg:hidden dark:hover:bg-white/10"
          >
            <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
          <span className="truncate text-base font-semibold lg:text-lg">
            {actor.role === "intern" ? SECTIONS[section] : "План стажёров"}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <ReminderBell actor={actor} onOpen={openReminder} />
          </div>
        </header>

        <div className="flex gap-1 overflow-x-auto px-3 pb-2 md:hidden" role="tablist" aria-label="Разделы на телефоне">
          {mobileTabs.map((t) => {
            const selected = t.id === "chat" ? tab === "chat" : tab === "plan" && section === t.id;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={selected}
                onClick={() => (t.id === "chat" ? setTab("chat") : (setView(t.id), setTab("plan")))}
                className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium ${selected ? "bg-foreground text-background" : "text-[var(--muted)]"}`}
              >
                {t.label}
                {t.id === "chat" && unread && tab !== "chat" && (
                  <span aria-label="новые сообщения" className="ml-1.5 inline-block size-2 rounded-full bg-accent align-middle" />
                )}
              </button>
            );
          })}
        </div>

        <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_minmax(340px,0.85fr)] xl:grid-cols-[minmax(0,1fr)_440px]">
          <div className={`min-h-0 overflow-y-auto overscroll-contain md:block ${tab === "plan" ? "block" : "hidden"}`}>
            {section === "home" ? (
              <HomePanel
                actor={actor}
                onExplain={onExplain}
                onDo={onDo}
                onPractice={onPractice}
                onDone={onMarkDone}
                onReminder={openReminder}
                onPlan={() => setView("plan")}
              />
            ) : section === "profile" ? (
              <ProfilePanel actor={actor} />
            ) : (
              <PlanPanel actor={actor} onExplain={onExplain} onDo={onDo} onPractice={onPractice} />
            )}
          </div>
          {/* Чат — отдельной карточкой справа: сердце продукта. */}
          <div className={`min-h-0 p-0 md:block md:pb-4 md:pr-4 ${tab === "chat" ? "block" : "hidden"}`}>
            <div className="h-full min-h-0 overflow-hidden md:card">
              <ChatPanel actor={actor} onAction={onAction} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
