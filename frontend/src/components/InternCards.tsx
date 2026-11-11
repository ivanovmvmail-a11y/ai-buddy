"use client";

// Экран наставника (спека 201): карточки стажёров без рейтинга и сравнения. Порядок — как в списке
// стажёров, без сортировки по прогрессу; только факты: что закрыто, что зависло, итоги недели.
import { useState } from "react";
import { isWorking, waitedFor } from "@/lib/plan-logic";
import { useInterns, usePlan, useProfile, useSummary } from "@/lib/queries";
import { useSession } from "@/lib/store";
import { findUser } from "@/lib/users";
import type { DemoUser } from "@/lib/types";

type Intern = { id: string; name: string; team: string };

export function InternCards({ actor }: { actor: DemoUser }) {
  const interns = useInterns(actor);
  const internPick = useSession((s) => s.internPick);
  const pickIntern = useSession((s) => s.pickIntern);
  const list = interns.data ?? [];
  if (!list.length) {
    return interns.isSuccess ? <p className="text-sm text-black/55 dark:text-white/55">Стажёров пока нет.</p> : null;
  }
  const selected = list.find((u) => u.id === internPick)?.id ?? list[0].id;

  return (
    <section aria-label={actor.role === "mentor" ? "Мои стажёры" : "Стажёры"} className="space-y-2">
      <h2 className="text-lg font-semibold">{actor.role === "mentor" ? "Мои стажёры" : "Стажёры"}</h2>
      <ul className="grid gap-2 sm:grid-cols-2">
        {list.map((intern) => (
          <InternCard key={intern.id} actor={actor} intern={intern} selected={intern.id === selected} onSelect={() => pickIntern(intern.id)} />
        ))}
      </ul>
    </section>
  );
}

function InternCard({ actor, intern, selected, onSelect }: { actor: DemoUser; intern: Intern; selected: boolean; onSelect: () => void }) {
  const plan = usePlan(actor, intern.id);
  const profile = useProfile(actor, intern.id); // запрос только у наставника — см. useProfile
  const [open, setOpen] = useState(false);
  const week = Math.max(1, Math.ceil((plan.data?.current_day ?? 1) / 7));
  const summary = useSummary(actor, intern.id, week, open && !!plan.data);

  const work = plan.data?.items.filter((i) => isWorking(i.stage)) ?? [];
  const done = work.filter((i) => i.status === "done").length;
  const stuck = work.filter((i) => i.status !== "done" && (i.status === "waiting" || i.overdue));

  return (
    <li
      className={`rounded-xl border p-3 text-sm transition-colors ${selected ? "border-[#00aaff] bg-[#00aaff]/5" : "border-black/10 dark:border-white/10"}`}
    >
      <button onClick={onSelect} aria-pressed={selected} className="w-full text-left">
        <span className="block text-[15px] font-medium">{intern.name}</span>
        <span className="block text-black/55 dark:text-white/55">
          {intern.team}{plan.data ? ` · день ${plan.data.current_day}` : ""}
        </span>
      </button>

      {plan.isError && (
        <p role="alert" className="mt-2 text-red-800 dark:text-red-300">
          Не получилось загрузить.{" "}
          <button onClick={() => plan.refetch()} className="rounded-full border border-current px-2.5 py-1">Повторить</button>
        </p>
      )}

      {plan.data && (
        <>
          <div className="mt-2">
            <div className="text-black/70 dark:text-white/70">Недели 1–2: закрыто {done} из {work.length}</div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10" aria-hidden>
              <div className="h-full rounded-full bg-[#00aaff]" style={{ width: `${work.length ? (done / work.length) * 100 : 0}%` }} />
            </div>
          </div>
          <div className="mt-2">
            <div className="font-medium">Что зависло</div>
            {stuck.length ? (
              <ul className="mt-0.5 space-y-0.5 text-black/70 dark:text-white/70">
                {stuck.map((i) => (
                  <li key={i.id}>
                    «{i.title}» —{" "}
                    {i.status === "waiting"
                      ? `ждёт: ${findUser(i.waiting_for)?.name ?? "согласующий"}, ${waitedFor(i.waiting_days ?? 0)}`
                      : "срок прошёл"}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-black/55 dark:text-white/55">Ничего не зависло.</p>
            )}
          </div>
        </>
      )}

      {profile.data && (
        <div className="mt-2 grid gap-1">
          <div><span className="font-medium">Сильные стороны:</span> {profile.data.strengths.join(", ") || "—"}</div>
          <div><span className="font-medium">Темы для роста:</span> {profile.data.growth.join(", ") || "—"}</div>
        </div>
      )}

      {plan.data && (
        <div className="mt-2">
          <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="rounded-lg border border-black/15 px-2.5 py-1 dark:border-white/20">
            Итоги недели {week}
          </button>
          {open && summary.isError && <p role="alert" className="mt-1 text-red-800 dark:text-red-300">{summary.error.message}</p>}
          {open && summary.data && (
            <div className="mt-2 space-y-1 text-black/70 dark:text-white/70">
              <div>
                Закрыто: {summary.data.closed.length ? summary.data.closed.map((c) => `«${c.title}»`).join(", ") : "пока ничего"}
              </div>
              <div>Получено доступов: {summary.data.access_granted.length}</div>
              <div>
                Переходит дальше: {summary.data.carry_over.length ? summary.data.carry_over.map((c) => `«${c.title}»`).join(", ") : "ничего"}
              </div>
              <div className="text-xs text-black/45 dark:text-white/45">Только факты из плана — основа для встречи 1:1, без оценок.</div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
