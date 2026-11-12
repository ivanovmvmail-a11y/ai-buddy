"use client";

// Отгул на один день (SPEC 3.8). Руководитель решает заявки своей команды; стажёр видит свои;
// наставник — только «отсутствует <дата>» без причины. Кнопка руководителя и есть решение человека.
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAbsenceFacts, useAbsenceRequests, useRefresh } from "@/lib/queries";
import type { AbsenceRequest, DemoUser } from "@/lib/types";

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

/** «2026-11-12» → «12.11 (чт)» — без часового пояса браузера: дата демо-часов, а не момент времени. */
export function dayText(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")} (${weekday})`;
}

const STATUS: Record<AbsenceRequest["status"], { label: string; cls: string }> = {
  pending: { label: "ждёт решения", cls: "bg-amber-500/15 text-amber-800 dark:text-amber-300" },
  approved: { label: "согласован", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
  rejected: { label: "отклонён", cls: "bg-black/5 text-black/60 dark:bg-white/10 dark:text-white/60" },
};

export function AbsenceRequests({ actor }: { actor: DemoUser }) {
  const requests = useAbsenceRequests(actor);
  const refresh = useRefresh();
  const decide = useMutation({
    mutationFn: (v: { id: string; approve: boolean }) => api.decideAbsence(actor.id, v.id, v.approve),
    onSuccess: refresh,
  });
  const lead = actor.role === "lead";
  // Руководителю — всё, что ждёт решения; стажёру — три последние свои заявки (сервер отдаёт новые сверху).
  const all = requests.data ?? [];
  const shown = lead ? all.filter((r) => r.status === "pending") : all.slice(0, 3);
  if (!shown.length) return null;

  return (
    <section aria-label="Заявки на отгул" className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-3">
      <h3 className="mb-2 text-sm font-semibold">{lead ? "Заявки на отгул ждут твоего решения" : "Мои заявки на отгул"}</h3>
      {decide.isError && <p role="alert" className="mb-2 text-sm text-red-700 dark:text-red-300">{decide.error.message}</p>}
      <ul className="space-y-2">
        {shown.map((r) => (
          <li key={r.id} className="text-sm">
            <div className="flex flex-wrap items-center gap-1.5">
              {lead && <b>{r.intern_name}</b>}
              <span>{lead ? "· " : ""}{dayText(r.day)} · {r.reason_title.toLowerCase()}</span>
              {!lead && <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS[r.status].cls}`}>{STATUS[r.status].label}</span>}
            </div>
            {lead && (
              <div className="mt-1.5 flex gap-2">
                <button
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: r.id, approve: true })}
                  className="rounded-lg bg-[#00aaff] px-2.5 py-1 font-medium text-white disabled:opacity-50"
                >
                  Согласовать
                </button>
                <button
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: r.id, approve: false })}
                  className="rounded-lg border border-black/15 px-2.5 py-1 disabled:opacity-50 dark:border-white/20"
                >
                  Отклонить
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Строка в карточке стажёра у наставника: только даты, без причины (SPEC 3.8, 7). */
export function AbsenceFacts({ actor, internId }: { actor: DemoUser; internId: string }) {
  const facts = useAbsenceFacts(actor, internId).data ?? [];
  if (!facts.length) return null;
  return (
    <div className="mt-2">
      <span className="font-medium">Отсутствует:</span> {facts.map((f) => dayText(f.day)).join(", ")}
    </div>
  );
}
