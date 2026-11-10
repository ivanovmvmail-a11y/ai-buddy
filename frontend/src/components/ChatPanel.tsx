"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { sendChat, type ChatMessage } from "@/lib/api";
import { msgId, useChat, type BotAction, type Msg } from "@/lib/chat";
import { RESOURCES } from "@/lib/mock-data";
import { findUser } from "@/lib/plan-logic";
import { useDemo } from "@/lib/store";
import type { DemoUser } from "@/lib/types";

type Props = { actor: DemoUser; onAction: (a: BotAction) => void };

const LEVELS = { read: "чтение", edit: "редактирование", admin: "администрирование" } as const;

export function ChatPanel({ actor, onAction }: Props) {
  const { messages, busy, push, update, setBusy } = useChat();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, busy]);

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    const userMsg: Msg = { id: msgId(), role: "user", kind: "text", content: text.trim() };
    push(userMsg);
    setBusy(true);
    const history: ChatMessage[] = [...useChat.getState().messages]
      .filter((m) => m.kind === "text" && !m.scripted)
      .map((m) => ({ role: m.role, content: m.content }));
    try {
      const res = await sendChat(history, actor.id);
      push({ id: msgId(), role: "assistant", kind: "text", content: res.reply, sources: res.sources?.map((s) => s.title) });
    } catch (err) {
      push({
        id: msgId(), role: "assistant", kind: "error",
        content: err instanceof Error && err.message !== "Failed to fetch" ? err.message : "Не получилось связаться с сервером.",
        chips: [text.trim()],
      });
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const t = input;
    setInput("");
    void ask(t);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {messages.map((m) => (
          <Bubble key={m.id} m={m} actor={actor} onAction={onAction} onAsk={ask} update={update} />
        ))}
        {busy && <div className="text-sm text-black/55 dark:text-white/55">AI-buddy думает…</div>}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={onSubmit} className="flex gap-2 border-t border-black/10 p-3 dark:border-white/10">
        <input
          aria-label="Сообщение"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Спроси что угодно…"
          className="min-w-0 flex-1 rounded-xl border border-black/15 bg-transparent px-4 py-2.5 text-base outline-none focus:border-[#00aaff] dark:border-white/20"
        />
        <button type="submit" disabled={busy || !input.trim()} className="rounded-xl bg-[#00aaff] px-4 font-medium text-white disabled:opacity-40">
          Отправить
        </button>
      </form>
    </div>
  );
}

function Bubble({
  m, actor, onAction, onAsk, update,
}: { m: Msg; actor: DemoUser; onAction: Props["onAction"]; onAsk: (t: string) => void; update: (id: string, p: Partial<Msg>) => void }) {
  const createRequest = useDemo((s) => s.createRequest);
  const push = useChat((s) => s.push);

  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-[#00aaff] px-4 py-2 text-[15px] text-white">{m.content}</div>
      </div>
    );
  }

  function confirm() {
    if (!m.draft) return;
    const req = createRequest(m.draft.itemId, m.draft.level, m.draft.justification);
    update(m.id, { draft: { ...m.draft, state: "confirmed" } });
    if (!req) return;
    const res = RESOURCES.find((r) => r.id === req.resource_id);
    const text =
      req.status === "granted"
        ? `Готово: заявка ${req.id} — доступ к «${res?.title}» выдан. Пункт плана закрыт.`
        : `Заявка ${req.id} создана и ушла на согласование: ${findUser(req.approver_id)?.name}. Пункт плана ждёт ответа — я напомню, если затянется.`;
    push({ id: msgId(), role: "assistant", kind: "text", content: text, scripted: true });
  }

  return (
    <div className="flex justify-start">
      <div className={`max-w-[92%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${
        m.kind === "error" ? "bg-red-500/10 text-red-800 dark:text-red-300" : "bg-black/5 dark:bg-white/10"
      }`}>
        <div className="whitespace-pre-wrap">{m.content}</div>

        {m.draft && (
          <div className="mt-2 rounded-xl border border-black/10 bg-[var(--background)] p-3 text-sm dark:border-white/15">
            <div className="mb-1.5 font-semibold">Заявка на доступ · черновик</div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              <dt className="text-black/55 dark:text-white/55">Ресурс</dt><dd>{m.draft.resourceTitle}</dd>
              <dt className="text-black/55 dark:text-white/55">Права</dt><dd>{LEVELS[m.draft.level]} (минимально достаточные)</dd>
              <dt className="text-black/55 dark:text-white/55">Обоснование</dt><dd>{m.draft.justification}</dd>
              <dt className="text-black/55 dark:text-white/55">Согласует</dt><dd>{m.draft.approver}</dd>
            </dl>
            {m.draft.state === "pending" ? (
              <div className="mt-3 flex gap-2">
                <button onClick={confirm} className="rounded-lg bg-[#00aaff] px-3 py-1.5 font-medium text-white">Подтвердить</button>
                <button onClick={() => update(m.id, { draft: { ...m.draft!, state: "cancelled" } })} className="rounded-lg border border-black/15 px-3 py-1.5 dark:border-white/20">
                  Отменить
                </button>
              </div>
            ) : (
              <div className="mt-2 text-black/55 dark:text-white/55">{m.draft.state === "confirmed" ? "Подтверждено" : "Отменено — ничего не отправлено"}</div>
            )}
          </div>
        )}

        {m.sources && m.sources.length > 0 && (
          <div className="mt-2 text-xs text-black/55 dark:text-white/55">Источник: {m.sources.join(", ")} · демо-данные, не регламент Авито</div>
        )}
        {m.action && actor.role === "intern" && (
          <button onClick={() => onAction(m.action!)} className="mt-2 rounded-lg bg-[#00aaff] px-3 py-1.5 text-sm font-medium text-white">
            {m.action.label}
          </button>
        )}
        {m.chips && m.chips.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.chips.map((c) => (
              <button key={c} onClick={() => onAsk(c)} className="rounded-full border border-black/15 px-2.5 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
                {m.kind === "error" ? "Повторить" : c}
              </button>
            ))}
          </div>
        )}
        {m.scripted && m.kind === "text" && (
          <div className="mt-1.5 text-[11px] uppercase tracking-wide text-black/35 dark:text-white/35">макет · ответ из тестовых данных</div>
        )}
      </div>
    </div>
  );
}
