"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type ChatMessage } from "@/lib/api";
import { approverText, itemActions, msgId, TOPICS, useChat, type BotAction, type Msg } from "@/lib/chat";
import { usePlan, useRefresh, useResources } from "@/lib/queries";
import { findUser } from "@/lib/users";
import { dayText } from "./AbsencePanel";
import { DecisionCard } from "./DecisionCard";
import { RichText } from "./RichText";
import { SourceLink } from "./SourceViewer";
import type { AccessRequest, DemoUser, PlanItem } from "@/lib/types";

type Props = { actor: DemoUser; onAction: (a: BotAction) => void };

const LEVELS: Record<string, string> = { read: "чтение", edit: "редактирование", admin: "администрирование" };

/** Отправить вопрос модели. Используется и полем ввода, и кнопками «Объяснить» / подсказками. */
const MAX_HISTORY = 20;

export async function askBot(actor: DemoUser, text: string) {
  const chat = useChat.getState();
  if (!text.trim() || chat.busy) return;
  const asked = msgId();
  const topic = chat.tab;
  chat.push({ id: asked, role: "user", kind: "text", content: text.trim() });
  chat.setBusy(true);
  // Модели — переписка только этой вкладки (чекпоинт 2): соседняя тема не уводит ответ в сторону.
  const history: ChatMessage[] = useChat
    .getState()
    .messages.filter((m) => m.kind === "text" && !m.scripted && (actor.role !== "intern" || m.topic === topic))
    .map((m) => ({ role: m.role, content: m.content }))
    // Модели нужна недавняя переписка; вся история после ~20 вопросов упиралась в лимит сервера (проверка 13.11).
    .slice(-MAX_HISTORY);
  try {
    const res = await api.chat(actor.id, history);
    // Ответ о заявке или о задании — во вкладку своей темы, вместе с вопросом (у стажёра; у остальных одна лента).
    if (actor.role === "intern" && res.topic !== topic) {
      chat.update(asked, { topic: res.topic });
      // След в исходной вкладке: видно, куда ушёл вопрос (Миша, 13.11: переброс был незаметен).
      const where = TOPICS.find((t) => t.id === res.topic)?.title ?? "";
      chat.push({
        id: msgId(), role: "assistant", kind: "text", scripted: true, topic, label: "переход между вкладками",
        content: `↪ «${text.trim()}» — это про другое, перенёс во вкладку «${where}». Ответ там.`,
      });
      chat.setTab(res.topic);
    }
    // Ответ о пункте плана — с кнопками этого пункта, как в плане (чекпоинт 2).
    const item = res.item_id ? await api.plan(actor.id).then((p) => p.items.find((i) => i.id === res.item_id)).catch(() => undefined) : undefined;
    if (res.mode === "practice" && item) chat.setPractice({ itemId: item.id, title: item.title });
    const actions = item ? itemActions(item, actor, res.mode === "practice" ? ["practice"] : []) : [];
    const where = actor.role === "intern" ? res.topic : undefined;
    // Первый черновик — карточкой в том же ответе: отдельное «Черновик — проверь и подтверди» повторяло ответ
    // (финальная проверка 13.11).
    const [first, ...more] = res.actions;
    chat.push({
      id: msgId(), role: "assistant", kind: "text", content: res.reply, sources: res.sources, topic: where,
      answerId: res.answer_id ?? undefined, actions: actions.length ? actions : undefined, draft: first,
      server: res.scripted || undefined,
    });
    for (const action of more) {
      chat.push({ id: msgId(), role: "assistant", kind: "draft", content: "Черновик — проверь и подтверди.", draft: action, topic: where });
    }
  } catch (err) {
    chat.push({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message, retry: text.trim() });
  } finally {
    chat.setBusy(false);
  }
}

/** Ответ на задание практикума прямо в чате (чекпоинт 2): сервер сверяет с учебным документом пункта. */
export async function submitPractice(actor: DemoUser, text: string, onDone?: () => Promise<unknown>) {
  const chat = useChat.getState();
  const mode = chat.practice;
  if (!mode || !text.trim() || chat.busy) return;
  chat.push({ id: msgId(), role: "user", kind: "text", content: text.trim() });
  chat.setBusy(true);
  try {
    const result = await api.practice(actor.id, mode.itemId, text.trim());
    const item = await api.plan(actor.id).then((p) => p.items.find((i) => i.id === mode.itemId)).catch(() => undefined);
    if (result.passed) chat.setPractice(null);
    const actions = result.passed && item ? itemActions(item, actor, ["practice", "explain", "do"], true) : [];
    chat.push({
      id: msgId(), role: "assistant", kind: "text", scripted: true, label: "проверка задания по документу пункта",
      content: (result.passed ? "✓ " : "") + result.text + (result.passed ? "" : "\n\nПопробуй ещё раз — напиши ответ следующим сообщением."),
      sources: result.source ? [result.source] : undefined, actions: actions.length ? actions : undefined,
    });
    await onDone?.();
  } catch (err) {
    chat.push({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message });
  } finally {
    chat.setBusy(false);
  }
}

/** Ответ наставника на вопрос стажёра — обычным сообщением чата (14.11: раньше — форма посреди плана). */
export async function submitReply(actor: DemoUser, text: string, onDone?: () => Promise<unknown>) {
  const chat = useChat.getState();
  const mode = chat.reply;
  if (!mode || !text.trim() || chat.busy) return;
  chat.push({ id: msgId(), role: "user", kind: "text", content: text.trim() });
  chat.setBusy(true);
  try {
    const topic = mode.topic.trim() || mode.question;
    await api.answerMentor(actor.id, mode.questionId, text.trim(), mode.publish, mode.publish ? topic : undefined);
    chat.setReply(null);
    chat.push({
      id: msgId(), role: "assistant", kind: "text", scripted: true, label: "из данных сервиса",
      content: `Ответ отправлен: ${mode.internName} получит его в колокольчик 🔔.`
        + (mode.publish ? ` Добавил в базу знаний команды по теме «${topic}»: следующему стажёру отвечу сам, без имён и контактов.` : ""),
    });
    await onDone?.();
  } catch (err) {
    chat.push({ id: msgId(), role: "assistant", kind: "error", content: (err as Error).message });
  } finally {
    chat.setBusy(false);
  }
}

const EMPTY: Record<string, string> = {
  assistant: "Здесь — вопросы о стажировке и документах команды.",
  study: "Здесь — объяснения пунктов плана и задания практикумов. Нажми «Объяснить» у пункта или напиши «объясни пункт про песочницу».",
  requests: "Здесь — заявки на доступ, отгулы и напоминания. Нажми «Сделать за меня» у пункта или напиши «мне завтра к врачу».",
};
const PLACEHOLDER: Record<string, string> = {
  assistant: "Спроси что угодно…",
  study: "Спроси про пункт плана…",
  requests: "Доступ, отгул, напоминание…",
};

export function ChatPanel({ actor, onAction }: Props) {
  const messages = useChat((s) => s.messages);
  const busy = useChat((s) => s.busy);
  const practice = useChat((s) => s.practice);
  const setPractice = useChat((s) => s.setPractice);
  const tab = useChat((s) => s.tab);
  const setTab = useChat((s) => s.setTab);
  const unread = useChat((s) => s.unread);
  // Вкладки — у стажёра: у него и заявки, и учёба, и вопросы. У остальных ролей лента одна.
  const tabbed = actor.role === "intern";
  const shown = tabbed ? messages.filter((m) => (m.topic ?? "assistant") === tab) : messages;
  const practicing = practice && (!tabbed || tab === "study");
  const reply = useChat((s) => s.reply);
  const setReply = useChat((s) => s.setReply);
  const refresh = useRefresh();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    bottomRef.current?.scrollIntoView?.({ behavior: calm ? "auto" : "smooth" });
  }, [messages, busy, tab]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const t = input;
    setInput("");
    if (reply) void submitReply(actor, t, refresh);
    else if (practicing) void submitPractice(actor, t, refresh);
    else void askBot(actor, t);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {tabbed && (
        <div role="tablist" aria-label="Темы чата" className="flex gap-1 border-b border-line p-2">
          {TOPICS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
                tab === t.id ? "bg-foreground text-background" : "text-[var(--muted)] hover:bg-surface-2 hover:text-foreground"
              }`}
            >
              {t.title}
              {unread.includes(t.id) && tab !== t.id && (
                <span aria-label="есть новое" className="ml-1.5 inline-block size-2 rounded-full bg-accent align-middle" />
              )}
            </button>
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-4" aria-live="polite">
        {tabbed && shown.length === 0 && (
          <p className="text-sm text-black/50 dark:text-white/50">{EMPTY[tab]}</p>
        )}
        {shown.map((m) => (
          <Bubble key={m.id} m={m} actor={actor} onAction={onAction} />
        ))}
        {busy && <div className="text-sm text-black/55 dark:text-white/55">AI-buddy думает…</div>}
        <div ref={bottomRef} />
      </div>
      {practicing && practice && (
        <div role="status" className="flex items-center gap-2 border-t border-violet-500/30 bg-violet-500/[0.06] px-3 py-1.5 text-sm">
          <span className="min-w-0 flex-1 truncate">Сдаёшь задание: «{practice.title}» — ответ следующим сообщением</span>
          <button
            onClick={() => {
              setPractice(null);
              useChat.getState().push({ id: msgId(), role: "assistant", kind: "text", scripted: true, content: "Хорошо, задание отложим. Вернуться к нему — кнопка «Сдать задание» у пункта." });
            }}
            className="rounded-md px-2 py-0.5 text-black/60 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10"
          >
            Отменить
          </button>
        </div>
      )}
      {reply && (
        <div role="status" className="flex items-center gap-2 border-t border-accent/30 bg-accent/[0.06] px-3 py-1.5 text-sm">
          <span className="min-w-0 flex-1 truncate">Ответ на вопрос «{reply.question}» ({reply.internName}) — следующим сообщением</span>
          <button
            onClick={() => setReply(null)}
            className="rounded-md px-2 py-0.5 text-black/60 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10"
          >
            Отменить
          </button>
        </div>
      )}
      <form onSubmit={onSubmit} className="flex items-center gap-2 border-t border-line p-3">
        <input
          aria-label={reply ? "Ответ стажёру" : practicing ? "Ответ на задание" : "Сообщение"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={reply ? "Ответ стажёру…" : practicing ? "Что и как сделано — своими словами…" : PLACEHOLDER[tabbed ? tab : "assistant"]}
          className="min-w-0 flex-1 rounded-full border border-transparent bg-surface-2 px-4 py-2.5 text-base outline-none focus:border-accent"
        />
        <button
          type="submit"
          aria-label="Отправить"
          disabled={busy || !input.trim()}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-accent text-black hover:bg-accent-hover disabled:opacity-40"
        >
          <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </form>
    </div>
  );
}

/** Кнопки пункта в старых сообщениях — по актуальному плану: закрытый пункт кнопок «сделать / сдать / готово» не
 *  показывает, ждущий согласования — «Сделать за меня» (иначе повторное нажатие давало «заявка уже есть»). */
function liveActions(actions: BotAction[] | undefined, items: PlanItem[] | undefined): BotAction[] {
  if (!actions || !items) return actions ?? [];
  return actions.filter((a) => {
    if (!("itemId" in a) || !["do", "practice", "done"].includes(a.kind)) return true;
    const item = items.find((i) => i.id === a.itemId);
    if (!item) return true;
    if (item.status === "done") return false;
    return !(a.kind === "do" && item.status === "waiting");
  });
}

function Bubble({ m, actor, onAction }: { m: Msg; actor: DemoUser; onAction: Props["onAction"] }) {
  const plan = usePlan(actor, actor.role === "intern" ? actor.id : undefined);
  const actions = liveActions(m.actions, plan.data?.items);
  // Переход из уведомления (Миша, 14.11: «нажимаешь "Ответить" — ничего не происходит»): прокрутить к карточке и
  // подсветить её на пару секунд. Подсветка — рамкой, без движения.
  const flashed = useChat((s) => s.flash === m.id);
  useEffect(() => {
    if (!flashed) return;
    const show = setTimeout(() => document.querySelector(`[data-msg="${m.id}"]`)?.scrollIntoView?.({ block: "center" }), 60);
    const off = setTimeout(() => useChat.getState().setFlash(null), 2200);
    return () => { clearTimeout(show); clearTimeout(off); };
  }, [flashed, m.id]);
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-[20px] rounded-br-md bg-foreground px-4 py-2.5 text-[15px] text-background">{m.content}</div>
      </div>
    );
  }
  return (
    <div className="flex justify-start" data-msg={m.id}>
      <div className={`max-w-[92%] rounded-[20px] rounded-bl-md px-4 py-3 text-[15px] leading-relaxed transition-shadow duration-300 ${
        m.kind === "error" ? "bg-red-500/10 text-red-800 dark:text-red-300" : "bg-surface-2"
      } ${flashed ? "shadow-[0_0_0_2px_var(--accent)]" : ""}`}>
        <RichText text={m.content} />
        {m.draft && <DraftCard m={m} actor={actor} />}
        {m.decision && <DecisionCard d={m.decision} actor={actor} />}
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
        {actions.length > 0 && actor.role === "intern" && (
          <div className="mt-2 flex flex-wrap gap-2">
            {actions.map((a, i) => (
              <button
                key={a.label}
                onClick={() => onAction(a)}
                // Первая кнопка — контурная: главная (залитая синяя) на экране одна — в карточке «Следующий шаг»
                // (финальная проверка 13.11: рядом были две главные «Сделать за меня»).
                className={i === 0 && a.kind !== "snooze"
                  ? "rounded-full border border-foreground/30 px-4 py-1.5 text-sm font-semibold hover:bg-foreground/5"
                  : "rounded-full px-2 py-1.5 text-sm font-medium text-accent-ink underline-offset-4 hover:underline"}
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
        {/* Подпись — откуда ответ (проверка 13.11: с ключом приветствие было «сценарным», а у ответов модели подписи не было). */}
        {m.kind === "text" && (m.scripted || m.answerId) && (
          <div className="mt-1.5 text-[11px] uppercase tracking-wide text-black/60 dark:text-white/60">
            {m.scripted || m.server ? (m.label ?? "из данных плана") : "ответ ИИ · сверяй с источником"}
          </div>
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
          id: msgId(), role: "assistant", kind: "text", scripted: true, topic: m.topic,
          content: req?.status === "granted"
            ? `Готово: заявка ${req.id} — доступ к «${resource?.title ?? req.resource_id}» выдан. Пункт плана закрыт.`
            : `Заявка ${req?.id} создана и ушла на согласование: ${findUser(req?.approver_id)?.name ?? "согласующий"}. Пункт плана ждёт ответа — я напомню, если затянется.`,
        });
      } else if (result.status === "done" && isAbsence) {
        push({
          id: msgId(), role: "assistant", kind: "text", scripted: true, topic: m.topic,
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
          <button disabled={pending} onClick={() => run("confirm")} className="rounded-full bg-accent px-4 py-1.5 font-semibold text-black hover:bg-accent-hover disabled:opacity-50">Подтвердить</button>
          <button disabled={pending} onClick={() => run("cancel")} className="rounded-full border border-line px-3.5 py-1.5 disabled:opacity-50 dark:border-white/20">
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
      <button onClick={copy} className="rounded-full border border-line px-3 py-1 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
        {state === "copied" ? "Скопировано" : "Скопировать вопрос"}
      </button>
      {toMentor && !send.isSuccess && (
        <button
          onClick={() => send.mutate()}
          disabled={send.isPending}
          className="rounded-full bg-accent px-4 py-1 font-semibold text-black hover:bg-accent-hover disabled:opacity-50"
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
