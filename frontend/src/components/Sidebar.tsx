"use client";

// Левая колонка (редизайн 13.11, по мотивам онбординга Т-Банка; светлая, как career.avito.com: тёмная давала слишком резкий контраст): навигация — карточка профиля с прогрессом,
// разделы, внизу — демо-панель («Войти как», «Следующий день», «Сброс»), чтобы она не мешала самому продукту.
import { useCalendar, usePlan } from "@/lib/queries";
import { DEMO_USERS, ROLE_TITLES } from "@/lib/users";
import type { DemoUser } from "@/lib/types";

import type { Section } from "@/lib/store";

export type { Section };

export const SECTIONS: Record<Section, string> = { home: "Главная", plan: "Мой план", profile: "Мой профиль" };

type Props = {
  actor: DemoUser;
  section: Section;
  onSection: (s: Section) => void;
  onUser: (id: string) => void;
  onNextDay: () => void;
  onReset: () => void;
  scriptedMode: boolean;
  demoError: string | null;
};

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

/** «2026-11-11» → «ср, 11.11» (без сдвига часового пояса: дата демо-календаря, не время). */
export function demoDate(iso: string, weekday = true): string {
  const [y, m, d] = iso.split("-").map(Number);
  const short = `${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")}`;
  return weekday ? `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}, ${short}` : short;
}

export function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2);
}

/** Кольцо прогресса: доля закрытых пунктов недель 1–2. Цвет — зелёный «сделано». */
export function ProgressRing({ done, total, size = 56 }: { done: number; total: number; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const share = total ? done / total : 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Закрыто ${done} из ${total}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeOpacity={0.15} strokeWidth={6} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--brand-green)" strokeWidth={6} strokeLinecap="round"
        strokeDasharray={`${c * share} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" fontSize={size / 4} fontWeight={700} fill="currentColor">
        {Math.round(share * 100)}%
      </text>
    </svg>
  );
}

export function Sidebar({ actor, section, onSection, onUser, onNextDay, onReset, scriptedMode, demoError }: Props) {
  const intern = actor.role === "intern";
  const plan = usePlan(actor, intern ? actor.id : undefined);
  const work = plan.data?.items.filter((i) => i.stage === "week1" || i.stage === "week2") ?? [];
  const done = work.filter((i) => i.status === "done").length;
  const sections: Section[] = intern ? ["home", "plan", "profile"] : ["plan"];
  const calendar = useCalendar(actor).data;
  const mine = calendar?.interns.find((i) => i.id === actor.id);

  return (
    <aside aria-label="Навигация" className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto overscroll-contain border-r border-line bg-sidebar p-4 text-foreground">
      <div className="flex items-center gap-2 px-1">
        <span className="grid size-8 place-items-center rounded-full bg-accent text-sm font-bold text-black">AI</span>
        <span className="text-lg font-bold tracking-tight">AI-buddy</span>
      </div>

      {/* Карточка профиля: голубая, текст чёрный (контраст 8:1). */}
      <section aria-label="Профиль" className="rounded-[20px] bg-accent p-4 text-black">
        <div className="flex items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-full bg-white text-sm font-bold">{initials(actor.name)}</span>
          <div className="min-w-0">
            <div className="truncate font-semibold leading-tight">{actor.name}</div>
            <div className="truncate text-sm text-black/70">{ROLE_TITLES[actor.role]} · {actor.team}</div>
          </div>
        </div>
        {intern && plan.data && (
          <div className="mt-3 flex items-center gap-3 rounded-2xl bg-white/90 p-2.5">
            <ProgressRing done={done} total={work.length} size={48} />
            <div className="text-sm leading-tight">
              <div className="font-semibold">
                День {plan.data.current_day}
                {mine && <span className="font-normal text-black/60"> · с {demoDate(mine.start_date, false)}</span>}
              </div>
              <div className="text-black/60">закрыто {done} из {work.length} · недели 1–2</div>
            </div>
          </div>
        )}
      </section>

      <nav aria-label="Разделы" className="flex flex-col gap-1">
        {sections.map((s) => (
          <button
            key={s}
            aria-current={section === s ? "page" : undefined}
            onClick={() => onSection(s)}
            className={`rounded-xl px-3 py-2.5 text-left text-[15px] font-medium transition-colors ${
              section === s ? "bg-foreground text-background" : "text-[var(--muted)] hover:bg-surface-2 hover:text-foreground"
            }`}
          >
            {intern ? SECTIONS[s] : "План стажёров"}
          </button>
        ))}
      </nav>

      {/* Демо-панель: инструмент показа, не часть продукта — внизу и приглушённо. */}
      <section aria-label="Демо-панель" className="mt-auto space-y-2 rounded-2xl border border-dashed border-line p-3 text-sm">
        <div className="text-xs text-[var(--muted)]">
          Демо-панель{scriptedMode && " · сценарный режим (без ключа модели)"}
        </div>
        {/* Миша 14.11: «день скачет». Дата одна на всех и меняется только кнопкой; номер дня у стажёров разный —
            они вышли в разные даты, поэтому при «Войти как» он меняется, а дата — нет. */}
        <p className="text-sm" title="День меняется только кнопкой «Следующий день» — сразу у всех стажёров. «Сброс» возвращает среду 11.11.">
          Сегодня в демо: <b>{calendar?.today ? demoDate(calendar.today) : "…"}</b>
        </p>
        <label className="block">
          <span className="text-xs text-[var(--muted)]">Войти как</span>
          <select
            value={actor.id}
            onChange={(e) => onUser(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-line bg-surface px-2 py-1.5"
          >
            {DEMO_USERS.map((u) => (
              <option key={u.id} value={u.id}>{u.name} — {ROLE_TITLES[u.role]}</option>
            ))}
          </select>
        </label>
        <div className="flex gap-2 text-xs">
          <button onClick={onNextDay} className="flex-1 whitespace-nowrap rounded-full bg-surface-2 px-3 py-1.5 hover:bg-line">Следующий день</button>
          <button onClick={onReset} className="rounded-full px-3 py-1.5 text-[var(--muted)] hover:bg-surface-2 hover:text-foreground">Сброс</button>
        </div>
        {demoError && <p role="alert" className="text-xs text-red-700 dark:text-red-300">{demoError}</p>}
      </section>
    </aside>
  );
}
