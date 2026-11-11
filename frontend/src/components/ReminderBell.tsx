"use client";

// Колокольчик напоминаний (спека 301, SPEC 3.6): число активных напоминаний и список с действиями.
// Само напоминание по-прежнему приходит сообщением бота; колокольчик — чтобы не потерять его в чате.
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useReminders, useRefresh } from "@/lib/queries";
import type { DemoUser, Reminder } from "@/lib/types";

type Props = { actor: DemoUser; onOpen: (r: Reminder) => void };

export function ReminderBell({ actor, onOpen }: Props) {
  const reminders = useReminders(actor);
  const refresh = useRefresh();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const list = reminders.data ?? [];

  const act = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "snooze" | "done" }) =>
      kind === "snooze" ? api.snooze(actor.id, id) : api.doneReminder(actor.id, id),
    onSuccess: refresh,
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  useEffect(() => setOpen(false), [actor.id]);

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={list.length ? `Напоминания: ${list.length}` : "Напоминаний нет"}
        className="relative grid size-9 place-items-center rounded-full text-black/70 hover:bg-black/5 dark:text-white/75 dark:hover:bg-white/10"
      >
        <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 9a6 6 0 1 1 12 0c0 4.5 1.5 6.5 2.5 7.5h-17C4.5 15.5 6 13.5 6 9Z" />
          <path d="M10 19.5a2 2 0 0 0 4 0" />
        </svg>
        {list.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full bg-[#ff4053] px-1 text-[11px] font-semibold leading-[18px] tabular-nums text-white">
            {list.length}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Напоминания"
          className="absolute right-0 z-20 mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-y-auto overscroll-contain rounded-xl border border-black/10 bg-white p-2 text-sm shadow-lg dark:border-white/10 dark:bg-neutral-900"
          style={{ maxHeight: "60vh" }}
        >
          {list.length === 0 ? (
            <p className="px-2 py-3 text-black/55 dark:text-white/55">Напоминаний нет — всё по плану.</p>
          ) : (
            <ul className="space-y-1">
              {list.map((r) => (
                <li key={r.id} className="rounded-lg p-2 hover:bg-black/[0.03] dark:hover:bg-white/[0.04]">
                  <p>{r.text}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <button
                      onClick={() => { setOpen(false); onOpen(r); }}
                      className="rounded-full bg-[#00aaff] px-2.5 py-1 text-white"
                    >
                      Открыть в чате
                    </button>
                    <button
                      disabled={act.isPending}
                      onClick={() => act.mutate({ id: r.id, kind: "snooze" })}
                      className="rounded-full border border-black/15 px-2.5 py-1 disabled:opacity-50 dark:border-white/20"
                    >
                      Напомнить завтра
                    </button>
                    <button
                      disabled={act.isPending}
                      onClick={() => act.mutate({ id: r.id, kind: "done" })}
                      className="rounded-full px-2.5 py-1 text-black/60 disabled:opacity-50 dark:text-white/60"
                    >
                      Готово
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {act.isError && <p role="alert" className="px-2 pt-1 text-red-800 dark:text-red-300">{act.error.message}</p>}
        </div>
      )}
    </div>
  );
}
