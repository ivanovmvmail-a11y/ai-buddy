"use client";

// «Мой профиль» (SPEC раздел 4): стажёр видит всё, что бот о нём знает, но не правит.
import { usePlan, useProfile } from "@/lib/queries";
import { levelTitle, topicTitle } from "@/lib/skills";
import { DEMO_USERS, findUser, ROLE_TITLES } from "@/lib/users";
import type { DemoUser } from "@/lib/types";

const LEVEL_DOT: Record<string, string> = {
  novice: "bg-sky-500/15 text-sky-800 dark:text-sky-300",
  familiar: "bg-black/5 text-black/70 dark:bg-white/10 dark:text-white/70",
  confident: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
};

export function ProfilePanel({ actor }: { actor: DemoUser }) {
  const profile = useProfile(actor, actor.id);
  const plan = usePlan(actor, actor.id);
  const mentor = findUser(actor.mentor_id);
  const lead = DEMO_USERS.find((u) => u.role === "lead" && u.team === actor.team);

  if (profile.isError) {
    return (
      <div role="alert" className="m-4 rounded-xl bg-red-500/10 p-3 text-sm text-red-800 dark:text-red-300">
        {profile.error.message}{" "}
        <button onClick={() => profile.refetch()} className="ml-1 rounded-full border border-current px-2.5 py-1">Повторить</button>
      </div>
    );
  }
  if (!profile.data) return <p className="p-6 text-sm text-black/55 dark:text-white/55">Загружаю профиль…</p>;
  const p = profile.data;
  const topics = Object.keys(p.skills).sort();

  return (
    <div className="space-y-5 p-4 sm:p-5">
      <div>
        <h2 className="text-lg font-semibold">Мой профиль</h2>
        <p className="text-sm text-black/55 dark:text-white/55">Всё, что бот о тебе знает. Менять данные может только наставник.</p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-black/55 dark:text-white/55">Имя</dt><dd>{actor.name}, {ROLE_TITLES[actor.role]}</dd>
        <dt className="text-black/55 dark:text-white/55">Команда</dt><dd>{actor.team}</dd>
        <dt className="text-black/55 dark:text-white/55">Наставник</dt><dd>{mentor?.name ?? "—"}</dd>
        <dt className="text-black/55 dark:text-white/55">Руководитель</dt><dd>{lead?.name ?? "—"}</dd>
        {plan.data && <><dt className="text-black/55 dark:text-white/55">Стажировка</dt><dd>{plan.data.current_day}-й день</dd></>}
      </dl>

      <section aria-labelledby="skills-title" className="rounded-xl border border-black/10 p-3 dark:border-white/15">
        <h3 id="skills-title" className="font-medium">Уровень по темам</h3>
        {topics.length ? (
          <ul className="mt-2 flex flex-wrap gap-2">
            {topics.map((t) => (
              <li key={t} className={`rounded-full px-2.5 py-1 text-sm ${LEVEL_DOT[p.skills[t]]}`}>
                {topicTitle(t)} — {levelTitle(p.skills[t])}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-black/55 dark:text-white/55">Уровни пока не указаны.</p>
        )}
        <div className="mt-3 grid gap-1 text-sm">
          <div><span className="font-medium">Сильные стороны:</span> {p.strengths.join(", ") || "—"}</div>
          <div><span className="font-medium">Темы для роста:</span> {p.growth.join(", ") || "—"}</div>
        </div>
        {p.updated_by && (
          <p className="mt-2 text-xs text-black/45 dark:text-white/45">Последнее изменение: {findUser(p.updated_by)?.name ?? "наставник"}</p>
        )}
      </section>

      <section aria-labelledby="usage-title" className="text-sm">
        <h3 id="usage-title" className="font-medium">Как бот это использует</h3>
        <ul className="mt-1.5 list-disc space-y-1 pl-5 text-black/70 dark:text-white/70">
          <li>Подбирает глубину объяснений: где тема новая — подробно по шагам, где уверенно — коротко.</li>
          <li>Ставит в плане пометки «здесь помогу подробно» и «ты это знаешь». Порядок пунктов не меняется.</li>
          <li>Не влияет на права, доступы и решения о тебе. Бот не оценивает и не сравнивает стажёров.</li>
          <li>Баллы отбора, видео и тексты твоих вопросов не хранятся — в аналитику попадают только темы.</li>
        </ul>
      </section>
    </div>
  );
}
