"use client";

// Решения наставника и руководителя — карточками в чате, а не блоками посреди плана (Миша, 14.11, по замечанию
// эксперта на чекпоинте: «большинство вещей в чате, а какие-то почему-то посреди плана»). Карточка читает живые
// данные по id: если решение уже принято (здесь или в другой вкладке), показывает итог вместо кнопок.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { useChat, type Decision } from "@/lib/chat";
import { useAbsenceRequests, useMentorQuestions, useRefresh, useRequests, useSuggestions } from "@/lib/queries";
import { levelTitle } from "@/lib/skills";
import { findUser } from "@/lib/users";
import { dayText } from "./AbsencePanel";
import type { DemoUser, MentorQuestion } from "@/lib/types";

const box = "mt-2 rounded-xl border border-black/10 bg-[var(--background)] p-3 text-sm dark:border-white/15";
const primary = "rounded-full bg-accent px-4 py-1.5 font-semibold text-black hover:bg-accent-hover disabled:opacity-50";
const secondary = "rounded-full border border-line px-3.5 py-1.5 disabled:opacity-50 dark:border-white/20";
const muted = "text-black/55 dark:text-white/55";
const LEVELS: Record<string, string> = { read: "чтение", edit: "редактирование", admin: "администрирование" };

export function DecisionCard({ d, actor }: { d: Decision; actor: DemoUser }) {
  if (d.kind === "access") return <AccessCard id={d.id} actor={actor} />;
  if (d.kind === "suggestion") return <SuggestionCard id={d.id} actor={actor} />;
  if (d.kind === "absence") return <AbsenceCard id={d.id} actor={actor} />;
  return <QuestionCard id={d.id} actor={actor} />;
}

function Done({ text }: { text: string }) {
  return <div className={`mt-2 ${muted}`}>{text}</div>;
}

function Failed({ error }: { error: Error | null }) {
  return error ? <p role="alert" className="mt-2 text-red-700 dark:text-red-300">{error.message}</p> : null;
}

function AccessCard({ id, actor }: { id: string; actor: DemoUser }) {
  const requests = useRequests(actor);
  const refresh = useRefresh();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const decide = useMutation({
    mutationFn: (v: { approve: boolean; reason?: string }) => api.decide(actor.id, id, v.approve, v.reason),
    onSuccess: refresh,
  });
  const r = requests.data?.find((x) => x.id === id);
  if (!r) return null;
  const open = r.status === "pending_approval" && r.approver_id === actor.id;
  return (
    <div role="group" className={box} aria-label={`Заявка ${r.id}`}>
      <div className="mb-1.5 font-semibold">Заявка на доступ · {r.id}</div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className={muted}>Стажёр</dt><dd>{findUser(r.intern_id)?.name ?? r.intern_id}</dd>
        <dt className={muted}>Ресурс</dt><dd>{r.resource_title ?? r.resource_id}</dd>
        <dt className={muted}>Права</dt><dd>{LEVELS[r.level] ?? r.level}</dd>
        <dt className={muted}>Обоснование</dt><dd>{r.justification}</dd>
      </dl>
      <Failed error={decide.error} />
      {!open ? (
        <Done text={r.status === "granted" ? "Одобрено — доступ выдан." : r.status === "rejected" ? `Отклонено${r.reject_reason ? `: ${r.reject_reason}` : ""}.` : "Решено."} />
      ) : rejecting ? (
        <div className="mt-3 flex gap-2">
          <input
            aria-label="Причина отказа"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Причина отказа"
            className="min-w-0 flex-1 rounded-full border border-black/15 bg-transparent px-3 py-1.5 dark:border-white/20"
          />
          <button disabled={!reason.trim() || decide.isPending} onClick={() => decide.mutate({ approve: false, reason: reason.trim() })} className={secondary}>
            Отклонить
          </button>
        </div>
      ) : (
        <div className="mt-3 flex gap-2">
          <button disabled={decide.isPending} onClick={() => decide.mutate({ approve: true })} className={primary}>Одобрить</button>
          <button onClick={() => setRejecting(true)} className={secondary}>Отклонить…</button>
        </div>
      )}
    </div>
  );
}

function SuggestionCard({ id, actor }: { id: string; actor: DemoUser }) {
  const suggestions = useSuggestions(actor);
  const refresh = useRefresh();
  const decide = useMutation({ mutationFn: (accept: boolean) => api.decideSuggestion(actor.id, id, accept), onSuccess: refresh });
  // Сервер отдаёт только ждущие: нет в списке — решение уже принято.
  const s = suggestions.data?.find((x) => x.id === id);
  const outcome = decide.data
    ? (decide.data.status === "accepted" ? "Уровень поднят — стажёр увидит изменение." : "Оставили как есть — стажёру отказ не показывается.")
    : null;
  if (!s) return outcome || suggestions.data ? <Done text={outcome ?? "Решено."} /> : null;
  return (
    <div role="group" className={box} aria-label={`Предложение: ${s.intern_name}, ${s.topic_title}`}>
      <div className="mb-1.5 font-semibold">{s.intern_name}, {s.topic_title}: {levelTitle(s.from_level)} → {levelTitle(s.to_level)}</div>
      <div className={muted}>Основание: {s.basis}</div>
      <div className={`mt-1 text-xs ${muted}`}>Решаешь ты. Стажёр увидит только результат, отказ ему не показывается.</div>
      <Failed error={decide.error} />
      <div className="mt-3 flex gap-2">
        <button disabled={decide.isPending} onClick={() => decide.mutate(true)} className={primary}>Поднять уровень</button>
        <button disabled={decide.isPending} onClick={() => decide.mutate(false)} className={secondary}>Оставить</button>
      </div>
    </div>
  );
}

function AbsenceCard({ id, actor }: { id: string; actor: DemoUser }) {
  const requests = useAbsenceRequests(actor);
  const refresh = useRefresh();
  const decide = useMutation({ mutationFn: (approve: boolean) => api.decideAbsence(actor.id, id, approve), onSuccess: refresh });
  const r = requests.data?.find((x) => x.id === id);
  if (!r) return null;
  return (
    <div role="group" className={box} aria-label={`Отгул: ${r.intern_name}`}>
      <div className="mb-1.5 font-semibold">Заявление на отгул</div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className={muted}>Стажёр</dt><dd>{r.intern_name}</dd>
        <dt className={muted}>Дата</dt><dd>{dayText(r.day)}, один день</dd>
        <dt className={muted}>Причина</dt><dd>{r.reason_title.toLowerCase()}</dd>
      </dl>
      <Failed error={decide.error} />
      {r.status === "pending" ? (
        <div className="mt-3 flex gap-2">
          <button disabled={decide.isPending} onClick={() => decide.mutate(true)} className={primary}>Согласовать</button>
          <button disabled={decide.isPending} onClick={() => decide.mutate(false)} className={secondary}>Отклонить</button>
        </div>
      ) : (
        <Done text={r.status === "approved" ? "Согласовано — стажёр получит уведомление." : "Отклонено — стажёр получит уведомление."} />
      )}
    </div>
  );
}

/** Вопрос стажёра, которого нет в документах: ответ — обычным сообщением чата; с галочкой бот запомнит ответ. */
function QuestionCard({ id, actor }: { id: string; actor: DemoUser }) {
  const q = useMentorQuestions(actor).data?.find((x) => x.id === id);
  if (!q) return null;
  return (
    <div role="group" className={box} aria-label={`Вопрос: ${q.intern_name}`}>
      <div className="font-semibold">{q.intern_name}: «{q.question}»</div>
      {q.status === "pending" ? <AnswerControls q={q} /> : <PublishControls q={q} actor={actor} />}
    </div>
  );
}

function AnswerControls({ q }: { q: MentorQuestion }) {
  const reply = useChat((s) => s.reply);
  const setReply = useChat((s) => s.setReply);
  const active = reply?.questionId === q.id ? reply : null;
  if (!active) {
    return (
      <>
        <div className={`mt-1 text-xs ${muted}`}>Этого нет в документах. Ответь один раз — бот может запомнить ответ для следующих стажёров.</div>
        <div className="mt-3">
          <button
            onClick={() => setReply({ questionId: q.id, internName: q.intern_name, question: q.question, publish: true, topic: q.question })}
            className={primary}
          >
            Ответить
          </button>
        </div>
      </>
    );
  }
  return (
    <div className="mt-2 space-y-1.5">
      <div className={muted}>Напиши ответ в поле внизу — он уйдёт стажёру.</div>
      <label className="flex items-start gap-2 text-xs">
        <input type="checkbox" checked={active.publish} onChange={(e) => setReply({ ...active, publish: e.target.checked })} className="mt-0.5" />
        <span>Добавить ответ в базу знаний команды — имена и контакты бот уберёт сам</span>
      </label>
      {active.publish && <TopicField id={`topic-${q.id}`} value={active.topic} onChange={(topic) => setReply({ ...active, topic })} />}
    </div>
  );
}

function PublishControls({ q, actor }: { q: MentorQuestion; actor: DemoUser }) {
  const [topic, setTopic] = useState(q.question);
  const refresh = useRefresh();
  const publish = useMutation({ mutationFn: () => api.publishMentor(actor.id, q.id, topic.trim() || undefined), onSuccess: refresh });
  if (q.publication_status !== "not_requested") {
    return <Done text={`Ответ дан${q.publication_status === "published" ? " и добавлен в базу знаний" : ""}.`} />;
  }
  return (
    <div className="mt-2 space-y-1.5">
      <div className={muted}>Ответ дан. Можно добавить его в базу знаний — следующему стажёру бот ответит сам.</div>
      <TopicField id={`topic-later-${q.id}`} value={topic} onChange={setTopic} />
      <Failed error={publish.error} />
      <button onClick={() => publish.mutate()} disabled={publish.isPending} className={secondary}>Добавить ответ в базу знаний</button>
    </div>
  );
}

/** Тема в базе знаний: по ней другие стажёры найдут ответ, даже если он написан другими словами. */
function TopicField({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-0.5">
      <label htmlFor={id} className={`text-xs ${muted}`}>Тема в базе знаний — по ней ответ найдут другие стажёры</label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={200}
        className="w-full rounded-lg border border-black/15 bg-white px-2.5 py-1 text-sm dark:border-white/20 dark:bg-white/5"
      />
    </div>
  );
}
