"use client";

// «Главная» стажёра (редизайн 13.11, по мотивам «Рабочего пространства» онбординга Т-Банка и виджетов Сферы X5):
// карточки вместо длинного списка. Одна главная кнопка на экране — у «Следующего шага» (Миша: «слишком много кнопок,
// главные сливаются»). Остальные карточки — справочные: прогресс, кого ждём, напоминания, моя команда.
import { canMarkDone, canRequestAccess, isWorking, STAGE_TITLES, waitedFor } from "@/lib/plan-logic";
import { actionLabel } from "@/lib/notifications";
import { usePlan, useReminders } from "@/lib/queries";
import { DEMO_USERS, findUser } from "@/lib/users";
import type { DemoUser, PlanItem, Reminder } from "@/lib/types";
import { AbsenceRequests } from "./AbsencePanel";
import { MentorQuestions } from "./MentorQuestions";
import { initials, ProgressRing } from "./Sidebar";

type Props = {
  actor: DemoUser;
  onExplain: (item: PlanItem) => void;
  onDo: (item: PlanItem) => void;
  onPractice: (item: PlanItem) => void;
  onDone: (item: PlanItem) => void;
  onReminder: (r: Reminder) => void;
  onPlan: () => void;
};

const title = "text-sm font-semibold uppercase tracking-wide text-[var(--muted)]";

export function HomePanel({ actor, onExplain, onDo, onPractice, onDone, onReminder, onPlan }: Props) {
  const plan = usePlan(actor, actor.id);
  const reminders = useReminders(actor);
  if (plan.isError) return <p role="alert" className="p-6 text-sm text-red-700 dark:text-red-300">{plan.error.message}</p>;
  if (!plan.data) return <p className="p-6 text-sm text-[var(--muted)]">Загружаю…</p>;

  const p = plan.data;
  const work = p.items.filter((i) => isWorking(i.stage));
  const done = work.filter((i) => i.status === "done").length;
  const next = p.next_step.item;
  const mentor = findUser(actor.mentor_id);
  const lead = findUser(actor.lead_id);
  const hr = DEMO_USERS.find((u) => u.role === "hrbp");
  const notes = (reminders.data ?? []).slice(0, 3);

  const primary = next && (
    canRequestAccess(actor, next) ? { label: "Сделать за меня", run: () => onDo(next) }
      : next.practice_check ? { label: "Сдать задание", run: () => onPractice(next) }
        : canMarkDone(actor, next) ? { label: "Готово", run: () => onDone(next) }
          : { label: "Объяснить", run: () => onExplain(next) }
  );

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <header>
        <h1 className="text-[28px] font-bold leading-tight tracking-[-0.02em]">Привет, {actor.name.split(" ")[0]}!</h1>
        <p className="mt-1 text-[var(--muted)]">День {p.current_day} · {actor.team}</p>
      </header>

      {/* Главное на экране — один шаг и одна яркая кнопка. */}
      <section aria-label="Следующий шаг" className="card p-5 sm:p-6">
        {next ? (
          <>
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-ink">
              Следующий шаг{next.overdue ? " · срок уже прошёл" : next.due_day ? ` · до дня ${next.due_day}` : ""}
            </div>
            <h2 className="mt-1.5 text-[22px] font-bold leading-snug tracking-[-0.01em]">{next.title}</h2>
            <p className="mt-1.5 max-w-prose text-[var(--muted)]">{next.summary.replace(/^демо-данные, не регламент Авито\.?\s*/i, "")}</p>
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
              {primary && (
                <button onClick={primary.run} className="rounded-full bg-accent px-6 py-3 text-base font-semibold text-black hover:bg-accent-hover">
                  {primary.label}
                </button>
              )}
              {primary?.label !== "Объяснить" && (
                <button onClick={() => onExplain(next)} className="text-[15px] font-medium text-accent-ink underline-offset-4 hover:underline">
                  Объяснить, что делать
                </button>
              )}
            </div>
          </>
        ) : (
          <p className="text-lg font-semibold">Недели 1–2 закрыты — дальше «Месяц 1». 🎉</p>
        )}
        {p.next_step.waiting.length > 0 && (
          <ul className="mt-4 space-y-1 border-t border-line pt-3 text-sm">
            {p.next_step.waiting.map((w) => (
              <li key={w.id} className="text-amber-800 dark:text-amber-300">
                Ждём ответа ({findUser(w.waiting_for)?.name ?? "согласующий"}): «{w.title}», {waitedFor(w.waiting_days ?? 0)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section aria-label="Прогресс адаптации" className="card p-5">
          <h3 className={title}>Прогресс адаптации</h3>
          <div className="mt-3 flex items-center gap-4">
            <ProgressRing done={done} total={work.length} size={72} />
            <div className="text-sm">
              <div className="text-base font-semibold">Закрыто {done} из {work.length}</div>
              <div className="text-[var(--muted)]">пунктов недель 1–2</div>
            </div>
          </div>
          <ol className="mt-4 grid grid-cols-4 gap-1.5 text-xs" aria-label="Этапы стажировки">
            {p.ladder.map((s) => (
              <li
                key={s.stage}
                aria-current={s.state === "current" ? "step" : undefined}
                className={`rounded-xl px-2 py-1.5 leading-tight ${
                  s.state === "current" ? "bg-accent/15 font-semibold" : s.state === "passed" ? "bg-brand-green/20" : "bg-surface-2 text-[var(--muted)]"
                }`}
              >
                {s.title ?? STAGE_TITLES[s.stage]}
              </li>
            ))}
          </ol>
          <button onClick={onPlan} className="mt-3 text-sm font-medium text-accent-ink underline-offset-4 hover:underline">
            Весь план →
          </button>
        </section>

        <section aria-label="Моя команда" className="card p-5">
          <h3 className={title}>Моя команда</h3>
          <ul className="mt-3 space-y-3">
            {[
              mentor && { u: mentor, role: "Наставник", about: "задачи, доступы, всё, что блокирует" },
              lead && { u: lead, role: "Руководитель", about: "цели стажировки, отгулы" },
              hr && { u: hr, role: "HR BP", about: "отпуск, больничный, документы" },
            ].filter(Boolean).map((x) => x && (
              <li key={x.u.id} className="flex items-center gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-2 text-sm font-semibold">{initials(x.u.name)}</span>
                <div className="min-w-0 text-sm leading-tight">
                  <div className="font-semibold">{x.u.name}</div>
                  <div className="text-[var(--muted)]">{x.role} · {x.about}</div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {notes.length > 0 && (
        <section aria-label="Напоминания на главной" className="card p-5">
          <h3 className={title}>Напоминания</h3>
          <ul className="mt-2 divide-y divide-line">
            {notes.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="min-w-0">🔔 {r.text}</span>
                <button onClick={() => onReminder(r)} className="shrink-0 font-medium text-accent-ink underline-offset-4 hover:underline">
                  {actionLabel(r)}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <MentorQuestions actor={actor} />
      <AbsenceRequests actor={actor} />
    </div>
  );
}
