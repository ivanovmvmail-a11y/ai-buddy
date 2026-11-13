"use client";

// «Память» (PR #45 Codex + Claude 13.11): стажёр отправляет наставнику вопрос, которого нет в документах;
// наставник отвечает один раз и по желанию добавляет ответ в базу знаний команды — следующий стажёр получит его
// от бота сразу. Имена и контакты из опубликованного ответа сервер вычищает; полный ответ видит только автор вопроса.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { useMentorQuestions, useRefresh } from "@/lib/queries";
import type { DemoUser, MentorQuestion } from "@/lib/types";

const SECTION = "Вопросы наставнику"; // общий aria-label: к нему ведёт кнопка уведомления (notifications.ts)

export function MentorQuestions({ actor }: { actor: DemoUser }) {
  return actor.role === "mentor" ? <Inbox actor={actor} /> : <MyQuestions actor={actor} />;
}

function MyQuestions({ actor }: { actor: DemoUser }) {
  const questions = (useMentorQuestions(actor).data ?? []).slice(0, 3);
  if (!questions.length) return null;
  return (
    <section aria-label={SECTION} className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-3">
      <h3 className="mb-2 text-sm font-semibold">Мои вопросы наставнику</h3>
      <ul className="space-y-3">
        {questions.map((q) => (
          <li key={q.id} className="text-sm">
            <p className="text-black/70 dark:text-white/70">«{q.question}»</p>
            {q.status === "pending" ? (
              <p className="mt-1 text-xs text-black/55 dark:text-white/55">Ждёт ответа наставника</p>
            ) : (
              <p className="mt-1 rounded-lg bg-white/70 px-2.5 py-1.5 dark:bg-white/5"><b>Ответ:</b> {q.answer}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Inbox({ actor }: { actor: DemoUser }) {
  const all = useMentorQuestions(actor).data ?? [];
  const pending = all.filter((q) => q.status === "pending");
  const unpublished = all.filter((q) => q.status === "answered" && q.publication_status === "not_requested").slice(0, 3);
  if (!pending.length && !unpublished.length) return null;
  return (
    <section aria-label={SECTION} className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-3">
      <h3 className="text-sm font-semibold">Вопросы стажёров</h3>
      <p className="mb-2 text-xs text-black/55 dark:text-white/55">
        Этого нет в документах. Ответь один раз — с галочкой бот запомнит ответ и следующему стажёру ответит сам.
      </p>
      <ul className="space-y-3">
        {pending.map((q) => <AnswerForm key={q.id} actor={actor} q={q} />)}
        {unpublished.map((q) => <PublishLater key={q.id} actor={actor} q={q} />)}
      </ul>
    </section>
  );
}

function AnswerForm({ actor, q }: { actor: DemoUser; q: MentorQuestion }) {
  const [text, setText] = useState("");
  const [publish, setPublish] = useState(true);
  const [topic, setTopic] = useState(q.question);
  const refresh = useRefresh();
  const answer = useMutation({
    mutationFn: () => api.answerMentor(actor.id, q.id, text.trim(), publish, publish ? topic.trim() || undefined : undefined),
    onSuccess: refresh,
  });
  const id = `answer-${q.id}`;
  return (
    <li className="text-sm">
      <p><b>{q.intern_name}</b>: «{q.question}»</p>
      <form
        className="mt-1.5 space-y-1.5"
        onSubmit={(e) => { e.preventDefault(); if (text.trim()) answer.mutate(); }}
      >
        <label htmlFor={id} className="sr-only">Ответ стажёру</label>
        <textarea
          id={id}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          maxLength={6000}
          placeholder="Ответ стажёру"
          className="w-full rounded-lg border border-black/15 bg-white px-2.5 py-1.5 dark:border-white/20 dark:bg-white/5"
        />
        <label className="flex items-start gap-2 text-xs">
          <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} className="mt-0.5" />
          <span>Добавить ответ в базу знаний команды — имена и контакты бот уберёт сам</span>
        </label>
        {publish && <TopicField id={`topic-${q.id}`} value={topic} onChange={setTopic} />}
        {answer.isError && <p role="alert" className="text-xs text-red-700 dark:text-red-300">{answer.error.message}</p>}
        <button
          type="submit"
          disabled={!text.trim() || answer.isPending}
          className="rounded-lg bg-[#00aaff] px-2.5 py-1 font-medium text-white disabled:opacity-50"
        >
          Ответить
        </button>
      </form>
    </li>
  );
}

/** Тема в базе знаний: по ней другие стажёры найдут ответ, даже если он написан другими словами. Наставник видит
 *  и может переписать то, что будет опубликовано; по умолчанию — вопрос стажёра (имена и контакты сервер уберёт). */
function TopicField({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-0.5">
      <label htmlFor={id} className="text-xs text-black/60 dark:text-white/60">Тема в базе знаний — по ней ответ найдут другие стажёры</label>
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

function PublishLater({ actor, q }: { actor: DemoUser; q: MentorQuestion }) {
  const [topic, setTopic] = useState(q.question);
  const refresh = useRefresh();
  const publish = useMutation({ mutationFn: () => api.publishMentor(actor.id, q.id, topic.trim() || undefined), onSuccess: refresh });
  return (
    <li className="text-sm">
      <p className="text-black/70 dark:text-white/70"><b>{q.intern_name}</b>: «{q.question}» — ответ дан</p>
      <div className="mt-1"><TopicField id={`topic-later-${q.id}`} value={topic} onChange={setTopic} /></div>
      {publish.isError && <p role="alert" className="text-xs text-red-700 dark:text-red-300">{publish.error.message}</p>}
      <button
        onClick={() => publish.mutate()}
        disabled={publish.isPending}
        className="mt-1 rounded-lg border border-black/15 px-2.5 py-1 text-xs disabled:opacity-50 dark:border-white/20"
      >
        Добавить ответ в базу знаний
      </button>
    </li>
  );
}
