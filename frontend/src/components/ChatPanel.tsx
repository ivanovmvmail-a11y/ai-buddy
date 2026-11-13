"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type ChatMessage } from "@/lib/api";
import { approverText, msgId, useChat, type BotAction, type Msg } from "@/lib/chat";
import { useRefresh, useResources } from "@/lib/queries";
import { findUser } from "@/lib/users";
import { dayText } from "./AbsencePanel";
import { SourceLink } from "./SourceViewer";
import type { AccessRequest, DemoUser } from "@/lib/types";

type Props = { actor: DemoUser; onAction: (a: BotAction) => void };

const LEVELS: Record<string, string> = { read: "чтение", edit: "редактирование", admin: "администрирование" };

/** Отправить вопрос модели. Используется и полем ввода, и кнопками «Объяснить» / подсказками. */
export async function askBot(actor: DemoUser, text: string) {
  const chat = useChat.getState();
  if (!text.trim() || chat.busy) return;
  chat.push({ id: msgId(), role: "user", kind: "text", content: text.trim() });
  chat.setBusy(true);
  const history: ChatMessage[] = useChat
    .getState()
    .messages.filter((m) => m.kind === "text" && !m.scripted)
    .map((m) => ({ role: m.role, content: m.content }));
  try {
    const res = await api.chat(actor.id, history);
    chat.push({
      id: msgId(), role: "assistant", kind: "text", content: res.reply, sources: res.sources,
      answerId: res.answer_id ?? undefined,
    });
    for (const action of res.actions) {
      chat.push({ id: msgId(), role: "assistant", kind: "draft", content: "Черновик — проверь и подтверди.", draft: action });
    }
  } catch (err) {
    chat.push({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message, retry: text.trim() });
  } finally {
    chat.setBusy(false);
  }
}

export function ChatPanel({ actor, onAction }: Props) {
  const messages = useChat((s) => s.messages);
  const busy = useChat((s) => s.busy);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    bottomRef.current?.scrollIntoView?.({ behavior: calm ? "auto" : "smooth" });
  }, [messages, busy]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const t = input;
    setInput("");
    void askBot(actor, t);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-4" aria-live="polite">
        {messages.map((m) => (
          <Bubble key={m.id} m={m} actor={actor} onAction={onAction} />
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

function Bubble({ m, actor, onAction }: { m: Msg; actor: DemoUser; onAction: Props["onAction"] }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-[#00aaff] px-4 py-2 text-[15px] text-white">{m.content}</div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className={`max-w-[92%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${
        m.kind === "error" ? "bg-red-500/10 text-red-800 dark:text-red-300" : "bg-black/5 dark:bg-white/10"
      }`}>
        <div className="whitespace-pre-wrap">{m.content}</div>
        {m.draft && <DraftCard m={m} actor={actor} />}
        {m.sources && m.sources.length > 0 && (
          <div className="mt-2 text-xs text-black/55 dark:text-white/55">
            Источник:{" "}
            {m.sources.map((s, i) => (
              <span key={s.title}>
                {i > 0 && ", "}
                <SourceLink actor={actor} title={s.title} />
              </span>
            ))}{" "}
            · демо-данные, не регламент Авито
          </div>
        )}
        {m.actions && m.actions.length > 0 && actor.role === "intern" && (
          <div className="mt-2 flex flex-wrap gap-2">
            {m.actions.map((a, i) => (
              <button
                key={a.label}
                onClick={() => onAction(a)}
                className={i === 0 && a.kind !== "snooze"
                  ? "rounded-lg bg-[#00aaff] px-3 py-1.5 text-sm font-medium text-white"
                  : "rounded-lg border border-black/15 px-3 py-1.5 text-sm dark:border-white/20"}
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
        {m.followups && m.followups.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.followups.map((a) => (
              <button key={a.label} onClick={() => onAction(a)} className="rounded-full border border-black/15 px-2.5 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
                {a.label}
              </button>
            ))}
          </div>
        )}
        {(m.chips?.length || m.retry) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.retry && (
              <button onClick={() => askBot(actor, m.retry!)} className="rounded-full border border-current px-2.5 py-1 text-sm">Повторить</button>
            )}
            {m.chips?.map((c) => (
              <button key={c} onClick={() => askBot(actor, c)} className="rounded-full border border-black/15 px-2.5 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
                {c}
              </button>
            ))}
          </div>
        )}
        {questionDraft(m.content) && (
          <CopyDraft text={questionDraft(m.content)!} toMentor={actor.role === "intern" && /Черновик вопроса/.test(m.content) ? actor : null} />
        )}
        {m.answerId && <Feedback m={m} actor={actor} />}
        {m.scripted && m.kind === "text" && (
          <div className="mt-1.5 text-[11px] uppercase tracking-wide text-black/35 dark:text-white/35">сценарный ответ · из данных плана</div>
        )}
      </div>
    </div>
  );
}

// Закрытый список причин (SPEC 3.8): подробности вроде врача в заявление не попадают.
const ABSENCE_REASONS: Record<string, string> = { personal: "личные дела", family: "семейные дела", study: "учебные дела" };

function DraftCard({ m, actor }: { m: Msg; actor: DemoUser }) {
  const update = useChat((s) => s.update);
  const push = useChat((s) => s.push);
  const resources = useResources(actor);
  const refresh = useRefresh();
  const [pending, setPending] = useState(false);
  const draft = m.draft!;
  const params = draft.params as Record<string, string | undefined>;
  const resource = resources.data?.find((r) => r.id === params.resource_id);
  const isAccess = draft.tool === "create_access_request";
  const isAbsence = draft.tool === "create_absence_request";

  async function run(kind: "confirm" | "cancel") {
    setPending(true);
    try {
      const result = kind === "confirm" ? await api.confirm(actor.id, draft.id) : await api.cancel(actor.id, draft.id);
      update(m.id, { draft: result });
      if (result.status === "done" && isAccess) {
        const req = (result.result as { request?: AccessRequest } | null)?.request;
        push({
          id: msgId(), role: "assistant", kind: "text", scripted: true,
          content: req?.status === "granted"
            ? `Готово: заявка ${req.id} — доступ к «${resource?.title ?? req.resource_id}» выдан. Пункт плана закрыт.`
            : `Заявка ${req?.id} создана и ушла на согласование: ${findUser(req?.approver_id)?.name ?? "согласующий"}. Пункт плана ждёт ответа — я напомню, если затянется.`,
        });
      } else if (result.status === "done" && isAbsence) {
        push({
          id: msgId(), role: "assistant", kind: "text", scripted: true,
          content: `Заявление ушло руководителю: ${findUser(actor.lead_id)?.name ?? "руководитель команды"}. Решение придёт уведомлением, а если затянется — я напомню.`,
        });
      } else if (result.status === "failed") {
        push({ id: msgId(), role: "assistant", kind: "error", content: `Не получилось: ${result.error}` });
      }
      await refresh();
    } catch (err) {
      push({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message });
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-2 rounded-xl border border-black/10 bg-[var(--background)] p-3 text-sm dark:border-white/15">
      <div className="mb-1.5 font-semibold">
        {isAccess ? "Заявка на доступ · черновик" : isAbsence ? "Заявление на отгул · черновик" : "Черновик действия"}
      </div>
      {isAccess ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-black/55 dark:text-white/55">Ресурс</dt><dd>{resource?.title ?? params.resource_id}</dd>
          <dt className="text-black/55 dark:text-white/55">Права</dt><dd>{LEVELS[params.level ?? "read"]} (минимально достаточные)</dd>
          <dt className="text-black/55 dark:text-white/55">Обоснование</dt><dd>{params.justification}</dd>
          <dt className="text-black/55 dark:text-white/55">Согласует</dt><dd>{approverText(resource, actor, params.level ?? "read")}</dd>
        </dl>
      ) : isAbsence ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-black/55 dark:text-white/55">Дата</dt><dd>{params.day ? dayText(params.day) : "—"}, один день</dd>
          <dt className="text-black/55 dark:text-white/55">Причина</dt><dd>{ABSENCE_REASONS[params.reason ?? "personal"]}</dd>
          <dt className="text-black/55 dark:text-white/55">Решает</dt><dd>{findUser(actor.lead_id)?.name ?? "руководитель команды"}</dd>
        </dl>
      ) : (
        <div>{draft.title}</div>
      )}
      {draft.status === "pending" ? (
        <div className="mt-3 flex gap-2">
          <button disabled={pending} onClick={() => run("confirm")} className="rounded-lg bg-[#00aaff] px-3 py-1.5 font-medium text-white disabled:opacity-50">Подтвердить</button>
          <button disabled={pending} onClick={() => run("cancel")} className="rounded-lg border border-black/15 px-3 py-1.5 disabled:opacity-50 dark:border-white/20">
            Отменить
          </button>
        </div>
      ) : (
        <div className="mt-2 text-black/55 dark:text-white/55">
          {draft.status === "done" ? "Подтверждено" : draft.status === "cancelled" ? "Отменено — ничего не отправлено"
            : draft.status === "running" ? "Выполняется…" : "Не выполнено"}
        </div>
      )}
    </div>
  );
}

/** «Полезно / Не полезно» под ответом модели (SPEC 6, спека 302). Оценка — одна, без текста вопроса. */
function Feedback({ m, actor }: { m: Msg; actor: DemoUser }) {
  const update = useChat((s) => s.update);
  const [error, setError] = useState(false);
  if (m.rated) {
    return <div className="mt-2 text-xs text-black/50 dark:text-white/50">Спасибо, учту{m.rated === "not_useful" ? " — передам наставнику как тему для документа" : ""}.</div>;
  }
  async function rate(useful: boolean) {
    setError(false);
    try {
      await api.feedback(actor.id, m.answerId!, useful);
      update(m.id, { rated: useful ? "useful" : "not_useful" });
    } catch {
      setError(true);
    }
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      <button onClick={() => rate(true)} className="rounded-full border border-black/15 px-2.5 py-1 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">Полезно</button>
      <button onClick={() => rate(false)} className="rounded-full border border-black/15 px-2.5 py-1 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">Не полезно</button>
      {error && <span role="alert" className="text-red-700 dark:text-red-300">Не получилось сохранить оценку.</span>}
    </div>
  );
}

/** Текст черновика вопроса наставнику / сообщения HR BP из ответа бота (SPEC 3.7): «…» после слова «Черновик». */
export function questionDraft(content: string): string | null {
  const match = content.match(/Черновик (?:вопроса|сообщения)[^«]*«([\s\S]+)»/);
  return match ? match[1].trim() : null;
}

/** «Скопировать» и, для вопроса наставнику, «Отправить наставнику»: вопрос уходит во входящие наставника;
 *  ответ придёт уведомлением, а с согласия наставника попадёт в базу знаний команды («память», 13.11). */
function CopyDraft({ text, toMentor }: { text: string; toMentor: DemoUser | null }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const refresh = useRefresh();
  const send = useMutation({ mutationFn: () => api.askMentor(toMentor!.id, questionOnly(text)), onSuccess: refresh });
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
      <button onClick={copy} className="rounded-lg border border-black/15 px-2.5 py-1 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
        {state === "copied" ? "Скопировано" : "Скопировать вопрос"}
      </button>
      {toMentor && !send.isSuccess && (
        <button
          onClick={() => send.mutate()}
          disabled={send.isPending}
          className="rounded-lg bg-[#00aaff] px-2.5 py-1 font-medium text-white disabled:opacity-50"
        >
          Отправить наставнику
        </button>
      )}
      {send.isSuccess && (
        <span role="status" className="text-xs text-black/60 dark:text-white/60">
          Отправлено. Ответ придёт в колокольчик 🔔 и в «Мои вопросы наставнику».
        </span>
      )}
      {send.isError && <span role="alert" className="text-xs text-red-700 dark:text-red-300">{send.error.message}</span>}
      {state === "failed" && <span role="alert" className="text-xs text-red-700 dark:text-red-300">Не получилось — выдели текст и скопируй вручную.</span>}
    </div>
  );
}

/** Из черновика «Привет! Подскажи, пожалуйста: <вопрос> Я поискал…» — только сам вопрос. */
export function questionOnly(draft: string): string {
  const match = draft.match(/Подскажи, пожалуйста:\s*([\s\S]+?)\s*Я поискал/);
  return (match ? match[1] : draft).trim();
}
