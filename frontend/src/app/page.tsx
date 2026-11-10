"use client";

import { useEffect, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { PlanPanel } from "@/components/PlanPanel";
import { actionFor, draftFor, explain, greeting, msgId, useChat, type BotAction } from "@/lib/chat";
import { DEMO_USERS, ROLE_TITLES } from "@/lib/mock-data";
import { findUser, remindersFor } from "@/lib/plan-logic";
import { useDemo } from "@/lib/store";
import type { PlanItem } from "@/lib/types";

export default function Home() {
  const userId = useDemo((s) => s.userId);
  const setUser = useDemo((s) => s.setUser);
  const actor = findUser(userId)!;
  const [tab, setTab] = useState<"plan" | "chat">("plan");
  const resetChat = useChat((s) => s.reset);
  const push = useChat((s) => s.push);

  useEffect(() => {
    resetChat([greeting(useDemo.getState(), actor)]);
    // приветствие — при каждом входе под другим пользователем
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  function onExplain(item: PlanItem) {
    push({ id: msgId(), role: "user", kind: "text", content: `Объясни пункт «${item.title}»` }, explain(useDemo.getState(), item));
    setTab("chat");
  }

  function onDo(item: PlanItem) {
    push({ id: msgId(), role: "user", kind: "text", content: `Сделай за меня: ${item.title}` }, draftFor(item, actor));
    setTab("chat");
  }

  function onAction(a: BotAction) {
    const item = useDemo.getState().items.find((i) => i.id === a.itemId);
    if (!item) return;
    if (a.kind === "do") onDo(item);
    else onExplain(item);
  }

  function nextDay() {
    useDemo.getState().nextDay();
    const state = useDemo.getState();
    const reminders = remindersFor(state, actor);
    for (const r of reminders) {
      const item = state.items.find((i) => i.id === r.plan_item_id);
      push({
        id: msgId(), role: "assistant", kind: "text", scripted: true, content: `🔔 ${r.text}`,
        action: item && item.status !== "waiting" ? actionFor(item) : undefined,
      });
      state.dismissReminder(r.id); // одно напоминание на пункт — без повторов
    }
    if (!reminders.length) push({ id: msgId(), role: "assistant", kind: "text", scripted: true, content: "Новый день. Зависших пунктов нет." });
  }

  function reset() {
    useDemo.getState().reset();
    resetChat([greeting(useDemo.getState(), actor)]);
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
        <div className="ml-auto flex items-center gap-2 rounded-lg border border-dashed border-black/20 px-2 py-1 text-xs dark:border-white/20">
          <span className="text-black/45 dark:text-white/45">Демо-панель</span>
          <button onClick={nextDay} className="rounded-md bg-black/5 px-2 py-1 hover:bg-black/10 dark:bg-white/10">Следующий день</button>
          <button onClick={reset} className="rounded-md px-2 py-1 hover:bg-black/5 dark:hover:bg-white/10">Сброс</button>
        </div>
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
          <PlanPanel actor={actor} onExplain={onExplain} onDo={onDo} />
        </div>
        <div className={`min-h-0 md:block ${tab === "chat" ? "block" : "hidden"}`}>
          <ChatPanel actor={actor} onAction={onAction} />
        </div>
      </main>
    </div>
  );
}
