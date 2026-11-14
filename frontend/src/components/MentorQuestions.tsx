"use client";

// «Память» (PR #45 Codex + Claude 13.11): стажёр отправляет наставнику вопрос, которого нет в документах;
// наставник отвечает один раз и по желанию добавляет ответ в базу знаний команды — следующий стажёр получит его
// от бота сразу. Ответ наставника — в чате (14.11, DecisionCard); здесь — список «Мои вопросы» на «Главной» стажёра.
import { useMentorQuestions } from "@/lib/queries";
import type { DemoUser } from "@/lib/types";

const SECTION = "Вопросы наставнику"; // общий aria-label: к нему ведёт кнопка уведомления (notifications.ts)

export function MentorQuestions({ actor }: { actor: DemoUser }) {
  const questions = (useMentorQuestions(actor).data ?? []).slice(0, 3);
  if (actor.role === "mentor" || !questions.length) return null;
  return (
    <section aria-label={SECTION} className="card p-4 sm:p-5">
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
