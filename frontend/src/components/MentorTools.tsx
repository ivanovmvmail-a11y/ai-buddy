"use client";

// Экран наставника, правка 11.11 (SPEC 4, 5): предложения бота поднять уровень и сравнение двух планов.
// Бот только предлагает — решает наставник. Сравнение показывает, как план подстраивается под человека,
// а не кто лучше: без процентов, баллов и сортировки по успехам.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { useCompare, useInterns, useRefresh, useSuggestions } from "@/lib/queries";
import { levelTitle } from "@/lib/skills";
import type { DemoUser, ItemStatus } from "@/lib/types";

export function SkillSuggestions({ actor }: { actor: DemoUser }) {
  const suggestions = useSuggestions(actor);
  const refresh = useRefresh();
  const decide = useMutation({
    mutationFn: (v: { id: string; accept: boolean }) => api.decideSuggestion(actor.id, v.id, v.accept),
    onSuccess: refresh,
  });
  const pending = (suggestions.data ?? []).filter((s) => s.status === "pending");
  if (!pending.length) return null;

  return (
    <section aria-label="Предложения бота" className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-3">
      <h3 className="text-sm font-semibold">Бот предлагает поднять уровень</h3>
      <p className="mb-2 text-xs text-black/50 dark:text-white/50">Решаешь ты. Стажёр увидит только результат, отказ ему не показывается.</p>
      {decide.isError && <p role="alert" className="mb-2 text-sm text-red-700 dark:text-red-300">{decide.error.message}</p>}
      <ul className="space-y-2">
        {pending.map((s) => (
          <li key={s.id} className="text-sm">
            <div>
              <b>{s.intern_name}</b>, {s.topic_title}: {levelTitle(s.from_level)} → {levelTitle(s.to_level)}
            </div>
            <div className="text-black/55 dark:text-white/55">Основание: {s.basis}</div>
            <div className="mt-1.5 flex gap-2">
              <button
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: s.id, accept: true })}
                className="rounded-lg bg-[#00aaff] px-2.5 py-1 font-medium text-white disabled:opacity-50"
              >
                Поднять уровень
              </button>
              <button
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: s.id, accept: false })}
                className="rounded-lg border border-black/15 px-2.5 py-1 disabled:opacity-50 dark:border-white/20"
              >
                Оставить
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

const STATUS_SHORT: Record<ItemStatus, string> = {
  not_started: "не начат", in_progress: "в работе", waiting: "ждёт", done: "сделано",
};

export function ComparePlans({ actor }: { actor: DemoUser }) {
  const interns = useInterns(actor).data ?? [];
  const [open, setOpen] = useState(false);
  const [a, b] = [interns[0]?.id ?? "", interns[1]?.id ?? ""];
  const compare = useCompare(actor, a, b, open);
  if (actor.role !== "mentor" || interns.length < 2) return null;

  return (
    <section aria-label="Сравнение планов" className="space-y-2">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="rounded-lg border border-black/15 px-2.5 py-1 text-sm dark:border-white/20">
        Сравнить планы: {interns[0].name.split(" ")[0]} и {interns[1].name.split(" ")[0]}
      </button>
      {open && compare.isError && (
        <p role="alert" className="text-sm text-red-800 dark:text-red-300">
          {compare.error.message}{" "}
          <button onClick={() => compare.refetch()} className="rounded-full border border-current px-2.5 py-1">Повторить</button>
        </p>
      )}
      {open && compare.isSuccess && !compare.data && (
        <p className="text-sm text-black/55 dark:text-white/55">Сравнение планов пока недоступно на сервере.</p>
      )}
      {open && compare.data && (
        <div className="rounded-xl border border-black/10 p-3 text-sm dark:border-white/10">
          <p className="mb-2 text-xs text-black/50 dark:text-white/50">
            Общие пункты у всех одинаковые, персональные подобраны по карте навыков. Это не рейтинг.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {compare.data.interns.map((intern) => {
              const personal = compare.data!.personal[intern.id] ?? [];
              return (
                <div key={intern.id} aria-label={`План: ${intern.name}`} role="group">
                  <div className="font-medium">{intern.name}</div>
                  <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-black/45 dark:text-white/45">Для тебя</div>
                  {personal.length ? (
                    <ul className="mt-0.5 space-y-1">
                      {personal.map((i) => (
                        <li key={i.id}>
                          {i.title}
                          {i.reason && <span className="block text-xs text-black/55 dark:text-white/55">Почему: {i.reason}</span>}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-black/55 dark:text-white/55">Персональных пунктов нет.</p>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-black/45 dark:text-white/45">
            Для всех · {compare.data.common.length}
          </div>
          <ul className="mt-1 divide-y divide-black/5 dark:divide-white/10">
            {compare.data.common.map((c) => (
              <li key={c.key} className="flex flex-wrap items-baseline justify-between gap-x-3 py-1">
                <span>{c.title}</span>
                <span className="text-xs text-black/55 dark:text-white/55">
                  {compare.data!.interns
                    .map((i) => {
                      const st = c.by_intern[i.id];
                      const short = st?.skill_level === "confident" ? ", коротко" : "";
                      return `${i.name.split(" ")[0]}: ${st ? STATUS_SHORT[st.status] : "—"}${short}`;
                    })
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
