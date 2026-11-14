"use client";

// Экран наставника (SPEC 5): сравнение двух планов. Предложения поднять уровень — карточками в чате (14.11, DecisionCard).
// Сравнение показывает, как план подстраивается под человека, а не кто лучше: без процентов, баллов и сортировки.
import { useState } from "react";
import { useCompare, useInterns } from "@/lib/queries";
import type { DemoUser, ItemStatus, PlanCompare } from "@/lib/types";

const STATUS_SHORT: Record<ItemStatus, string> = {
  not_started: "не начат", in_progress: "в работе", waiting: "ждёт", done: "сделано",
};

const first = (name: string) => name.split(" ")[0];
const COMMON_PREVIEW = 4;

/** Статус общего пункта у обоих в одну строку: «оба: не начат» или «Аня: сделано · Кирилл: не начат». */
function commonStatus(c: PlanCompare["common"][number], cols: { id: string; name: string }[]): string {
  const parts = cols.map((i) => {
    const st = c.by_intern[i.id];
    return `${st ? STATUS_SHORT[st.status] : "—"}${st?.skill_level === "confident" ? ", коротко" : ""}`;
  });
  return parts.every((p) => p === parts[0]) ? `оба: ${parts[0]}` : cols.map((i, k) => `${first(i.name)}: ${parts[k]}`).join(" · ");
}

// Проверка 12.11: сравнение должно читаться за три секунды — два столбца рядом, разные (персональные) пункты
// цветом, общие приглушены и выровнены строками. Открыто сразу и стоит над карточками стажёров.
export function ComparePlans({ actor }: { actor: DemoUser }) {
  const interns = useInterns(actor).data ?? [];
  const [open, setOpen] = useState(true);
  const [allCommon, setAllCommon] = useState(false);
  const [a, b] = [interns[0]?.id ?? "", interns[1]?.id ?? ""];
  const compare = useCompare(actor, a, b, open);
  if (actor.role !== "mentor" || interns.length < 2) return null;
  const data = compare.data;
  const cols = data?.interns ?? [];
  const personalRows = Math.max(0, ...cols.map((i) => data?.personal[i.id]?.length ?? 0));

  return (
    <section aria-label="Сравнение планов" className="card p-4 sm:p-5 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          Сравнить планы: {first(interns[0].name)} и {first(interns[1].name)}
        </h3>
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="rounded-lg px-2 py-0.5 text-xs text-black/55 transition-[background-color] duration-150 hover:bg-black/5 dark:text-white/55 dark:hover:bg-white/10"
        >
          {open ? "Свернуть" : "Развернуть"}
        </button>
      </div>
      {open && compare.isError && (
        <p role="alert" className="mt-2 text-sm text-red-800 dark:text-red-300">
          {compare.error.message}{" "}
          <button onClick={() => compare.refetch()} className="rounded-full border border-current px-2.5 py-1">Повторить</button>
        </p>
      )}
      {open && compare.isSuccess && !data && (
        <p className="mt-2 text-sm text-black/55 dark:text-white/55">Сравнение планов пока недоступно на сервере.</p>
      )}
      {open && data && (
        <>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-black/55 dark:text-white/55">
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-sm bg-violet-500/70" /> разные — подобраны по карте навыков
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-sm bg-black/15 dark:bg-white/20" /> общие — одинаковые у всех
            </span>
            <span>Это не рейтинг.</span>
          </p>

          <div className="mt-3 grid grid-cols-2 gap-x-2 gap-y-1.5">
            {cols.map((intern) => (
              <div key={intern.id} className="font-medium">{intern.name}</div>
            ))}

            <div className="col-span-2 mt-1 text-xs font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
              Персональные
            </div>
            {cols.map((intern) => {
              const personal = data.personal[intern.id] ?? [];
              return (
                <ul
                  key={intern.id}
                  role="group"
                  aria-label={`План: ${intern.name}`}
                  className="grid gap-y-1.5"
                  // subgrid: строки обоих столбцов общие — пункты Ани и Кирилла стоят друг напротив друга
                  style={{ gridRow: `span ${Math.max(personalRows, 1)}`, gridTemplateRows: "subgrid" }}
                >
                  {personal.length ? (
                    personal.map((i) => (
                      <li key={i.id} className="rounded-lg bg-violet-500/12 px-2 py-1.5 text-violet-950 dark:text-violet-100">
                        <span className="font-medium">{i.title}</span>
                        {i.reason && (
                          <span className="block text-xs text-violet-800/80 dark:text-violet-200/75">Почему: {i.reason}</span>
                        )}
                      </li>
                    ))
                  ) : (
                    <li className="px-2 py-1.5 text-black/55 dark:text-white/55">Персональных пунктов нет.</li>
                  )}
                </ul>
              );
            })}

            <div className="col-span-2 mt-2 text-xs font-semibold uppercase tracking-wide text-black/45 dark:text-white/45">
              Для всех · {data.common.length}
            </div>
            <ul className="col-span-2 divide-y divide-black/5 dark:divide-white/10" aria-label="Общие пункты">
              {(allCommon ? data.common : data.common.slice(0, COMMON_PREVIEW)).map((c) => (
                <li key={c.key} className="flex items-baseline justify-between gap-3 py-1 text-black/50 dark:text-white/50">
                  <span className="min-w-0 text-[13px]">{c.title}</span>
                  <span className="max-w-[45%] shrink-0 text-right text-xs text-black/40 dark:text-white/40">{commonStatus(c, cols)}</span>
                </li>
              ))}
            </ul>
            {data.common.length > COMMON_PREVIEW && (
              <button
                onClick={() => setAllCommon((v) => !v)}
                aria-expanded={allCommon}
                className="col-span-2 justify-self-start rounded-lg px-2 py-0.5 text-xs text-black/55 transition-[background-color] duration-150 hover:bg-black/5 dark:text-white/55 dark:hover:bg-white/10"
              >
                {allCommon ? "Скрыть общие" : `Показать все общие (${data.common.length})`}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
