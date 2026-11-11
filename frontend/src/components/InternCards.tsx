"use client";

// Экран наставника (спека 201): карточки стажёров без рейтинга и сравнения. Порядок — как в списке
// стажёров, без сортировки по прогрессу; только факты: что закрыто, что зависло, итоги недели.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isWorking, waitedFor } from "@/lib/plan-logic";
import { useInterns, useMetrics, usePlan, useProfile, useRefresh, useSummary } from "@/lib/queries";
import { useSession } from "@/lib/store";
import { findUser } from "@/lib/users";
import type { DemoUser, Metrics, SkillLevel, SkillProfile } from "@/lib/types";
import { LEVELS, TOPIC_TITLES } from "@/lib/skills";

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
      <MetricsLine actor={actor} />
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

      <TopicsLine actor={actor} internId={intern.id} />

      {profile.data && (
        <div className="mt-2 grid gap-1">
          <div><span className="font-medium">Сильные стороны:</span> {profile.data.strengths.join(", ") || "—"}</div>
          <div><span className="font-medium">Темы для роста:</span> {profile.data.growth.join(", ") || "—"}</div>
          {actor.role === "mentor" && (
            <SkillLevels actor={actor} profile={profile.data} topics={(plan.data?.items ?? []).map((i) => i.topic)} />
          )}
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

/** «0.0 с» читается как «не работает» — быстрые ответы подписываем честно (аудит, мелочи). */
export function latencyText(ms: number): string {
  return ms < 100 ? "быстрее 0,1 с" : `за ${(ms / 1000).toFixed(1).replace(".", ",")} с`;
}

/** Сводка по всем видимым стажёрам (спека 302): метрики «видим вживую» из SPEC 10. */
function MetricsLine({ actor }: { actor: DemoUser }) {
  const m = useMetrics(actor).data;
  if (!m) return null;
  const rated = m.feedback.useful + m.feedback.not_useful;
  return (
    <p className="text-sm text-black/60 dark:text-white/60" aria-label="Метрики">
      Вопросов боту: {m.questions} · закрыто без человека: {m.closed_without_human} · с источником:{" "}
      {Math.round(m.with_source_share * 100)}% · полезно: {m.feedback.useful} из {rated}
      {m.questions ? ` · ответ в среднем ${latencyText(m.avg_latency_ms)}` : ""}
    </p>
  );
}

/** Частые темы и темы без ответа в документах — без текстов вопросов (SPEC 5). */
function TopicsLine({ actor, internId }: { actor: DemoUser; internId: string }) {
  const m = useMetrics(actor, internId).data;
  if (!m || !m.questions) return null;
  const list = (items: Metrics["topics"]) => items.map((t) => `${t.title} — ${t.count}`).join(", ");
  return (
    <div className="mt-2 grid gap-1">
      <div><span className="font-medium">Частые темы:</span> {list(m.topics)}</div>
      {m.conflict_topics.length > 0 && (
        <div>
          <span className="font-medium">Документы расходятся:</span> {list(m.conflict_topics)}
          <span className="text-black/50 dark:text-white/50"> — стоит обновить документ</span>
        </div>
      )}
      {m.unanswered_topics.length > 0 && (
        <div>
          <span className="font-medium">Нет ответа в документах:</span> {list(m.unanswered_topics)}
          <span className="text-black/50 dark:text-white/50"> — стоит дописать документ</span>
        </div>
      )}
    </div>
  );
}


/** Спека 104: уровень по теме меняет только наставник; по нему бот выбирает глубину объяснений. */
function SkillLevels({ actor, profile, topics }: { actor: DemoUser; profile: SkillProfile; topics: Array<string | null> }) {
  const refresh = useRefresh();
  const save = useMutation({
    mutationFn: ({ topic, level }: { topic: string; level: SkillLevel }) => api.setSkill(actor.id, profile.intern_id, topic, level),
    onSuccess: refresh,
  });
  const all = [...new Set([...Object.keys(profile.skills), ...topics.filter((t): t is string => !!t)])].sort();
  if (!all.length) return null;
  return (
    <fieldset className="mt-1" disabled={save.isPending}>
      <legend className="font-medium">Уровень по темам</legend>
      <div className="mt-1 grid gap-1">
        {all.map((topic) => {
          const name = TOPIC_TITLES[topic] ?? topic;
          return (
            <label key={topic} className="flex items-center justify-between gap-2">
              <span>{name}</span>
              <select
                aria-label={`Уровень: ${name}`}
                value={profile.skills[topic] ?? ""}
                onChange={(e) => save.mutate({ topic, level: e.target.value as SkillLevel })}
                className="rounded-lg border border-black/15 bg-transparent px-2 py-1 dark:border-white/20"
              >
                {!profile.skills[topic] && <option value="" disabled>не указан</option>}
                {LEVELS.map((l) => <option key={l.id} value={l.id}>{l.title}</option>)}
              </select>
            </label>
          );
        })}
      </div>
      {save.isError && <p role="alert" className="mt-1 text-red-800 dark:text-red-300">{save.error.message}</p>}
      <p className="mt-1 text-xs text-black/45 dark:text-white/45">Ставит только наставник. Бот подстраивает глубину объяснений, стажёра не оценивает.</p>
    </fieldset>
  );
}
