"use client";

import { useState } from "react";
import { RESOURCES } from "@/lib/mock-data";
import { buildPlan, canMarkDone, findUser, isWorking, STAGE_TITLES, waitedFor, visibleInterns } from "@/lib/plan-logic";
import { useDemo } from "@/lib/store";
import type { DemoUser, ItemStatus, PlanItem, SkillLevel, Stage, StageInfo } from "@/lib/types";

const STATUS: Record<ItemStatus, { label: string; cls: string }> = {
  not_started: { label: "не начат", cls: "bg-black/5 text-black/60 dark:bg-white/10 dark:text-white/60" },
  in_progress: { label: "в работе", cls: "bg-sky-500/10 text-sky-700 dark:text-sky-300" },
  waiting: { label: "ждёт другого человека", cls: "bg-amber-500/15 text-amber-800 dark:text-amber-300" },
  done: { label: "сделано", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
};
const OWNER: Record<PlanItem["owner_role"], string> = { intern: "стажёр", mentor: "наставник", lead: "руководитель" };

type Props = {
  actor: DemoUser;
  onExplain: (item: PlanItem) => void;
  onDo: (item: PlanItem) => void;
};

export function PlanPanel({ actor, onExplain, onDo }: Props) {
  const state = useDemo();
  const interns = visibleInterns(actor);
  const [picked, setPicked] = useState<string | null>(null);
  const internId = interns.find((u) => u.id === picked)?.id ?? interns[0]?.id;

  if (!internId) {
    return (
      <div className="p-6 text-sm text-black/60 dark:text-white/60">
        Планы и профили стажёров для твоей роли недоступны. Чат справа отвечает по общим документам.
      </div>
    );
  }

  const plan = buildPlan(state, internId, actor);
  const intern = findUser(internId)!;
  const profile = state.profiles.find((p) => p.intern_id === internId);
  const showSkills = actor.role === "intern" || actor.role === "mentor";
  const stages: Stage[] = ["week1", "week2", "month1", "month2", "after3m"];
  const pending = state.requests.filter((r) => r.approver_id === actor.id && r.status === "pending_approval");

  return (
    <div className="space-y-5 p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{actor.id === internId ? "Мой план" : `План: ${intern.name}`}</h2>
          <p className="text-sm text-black/55 dark:text-white/55">
            {intern.team} · день {plan.current_day}
          </p>
        </div>
        {interns.length > 1 && (
          <select
            aria-label="Стажёр"
            value={internId}
            onChange={(e) => setPicked(e.target.value)}
            className="rounded-lg border border-black/15 bg-transparent px-2 py-1 text-sm dark:border-white/20"
          >
            {interns.map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        )}
      </div>

      {pending.length > 0 && <Approvals actor={actor} />}

      <Ladder ladder={plan.ladder} />

      {stages.map((stage) => {
        const items = plan.items.filter((i) => i.stage === stage);
        if (!items.length) return null;
        const working = isWorking(stage);
        return (
          <section key={stage} aria-label={STAGE_TITLES[stage]}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-black/45 dark:text-white/45">
              {STAGE_TITLES[stage]} {!working && "· впереди"}
            </h3>
            <ul className="space-y-2">
              {items.map((item) => (
                <PlanRow
                  key={item.id}
                  item={item}
                  actor={actor}
                  isNext={plan.next_step.item?.id === item.id}
                  level={showSkills && item.topic ? profile?.skills[item.topic] : undefined}
                  onExplain={onExplain}
                  onDo={onDo}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function Ladder({ ladder }: { ladder: StageInfo[] }) {
  return (
    <ol aria-label="Этапы стажировки" className="grid grid-cols-4 gap-1.5">
      {ladder.map((s) => {
        const left = s.total - s.done;
        return (
          <li
            key={s.title}
            aria-current={s.state === "current" ? "step" : undefined}
            className={`rounded-lg border px-2 py-2 text-xs leading-tight ${
              s.state === "current"
                ? "border-[#00aaff] bg-[#00aaff]/10"
                : s.state === "passed"
                  ? "border-emerald-500/40 bg-emerald-500/10"
                  : "border-dashed border-black/20 text-black/45 dark:border-white/20 dark:text-white/45"
            }`}
          >
            <div className="font-medium">{s.title}</div>
            <div className="mt-0.5 opacity-75">
              {s.state === "passed" ? "пройдено" : s.state === "current" ? `осталось ${left}` : "впереди"}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const HINT: Partial<Record<SkillLevel, string>> = { novice: "здесь помогу подробно", confident: "ты это знаешь" };

function PlanRow({
  item, actor, isNext, level, onExplain, onDo,
}: { item: PlanItem; actor: DemoUser; isNext: boolean; level?: SkillLevel; onExplain: Props["onExplain"]; onDo: Props["onDo"] }) {
  const markDone = useDemo((s) => s.markDone);
  const working = isWorking(item.stage);
  const st = STATUS[item.status];
  const isOwnIntern = actor.role === "intern" && actor.id === item.intern_id;
  const canDo = isOwnIntern && working && item.resource_id && (item.status === "not_started" || item.status === "in_progress");

  return (
    <li
      className={`rounded-xl border p-3 transition-colors ${
        !working
          ? "border-dashed border-black/15 text-black/45 dark:border-white/15 dark:text-white/45"
          : isNext
            ? "border-[#00aaff] shadow-[0_0_0_3px_rgba(0,170,255,0.12)]"
            : "border-black/10 dark:border-white/10"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {isNext && <div className="mb-0.5 text-xs font-semibold text-[#0088cc]">Следующий шаг</div>}
          <div className="text-[15px] font-medium leading-snug">{item.title}</div>
          {working && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
              <span className={`rounded-full px-2 py-0.5 ${st.cls}`}>{st.label}</span>
              {item.overdue && <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-orange-800 dark:text-orange-300">срок прошёл</span>}
              <span className="text-black/50 dark:text-white/50">
                {OWNER[item.owner_role]}
                {item.due_day ? ` · до дня ${item.due_day}` : ""}
              </span>
              {level && HINT[level] && <span className="text-black/50 dark:text-white/50">· {HINT[level]}</span>}
            </div>
          )}
          {item.status === "waiting" && item.waiting_for && (
            <p className="mt-1 text-xs text-black/55 dark:text-white/55">
              Ждём: {findUser(item.waiting_for)?.name}, {waitedFor(item.waiting_days ?? 0)}
            </p>
          )}
          {item.status_reason && <p className="mt-1 text-xs text-orange-800 dark:text-orange-300">Причина: {item.status_reason}</p>}
        </div>
      </div>
      {working && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button onClick={() => onExplain(item)} className="rounded-lg border border-black/15 px-2.5 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
            Объяснить
          </button>
          {canDo && (
            <button onClick={() => onDo(item)} className="rounded-lg bg-[#00aaff] px-2.5 py-1 text-sm font-medium text-white hover:bg-[#0099e6]">
              Сделать за меня
            </button>
          )}
          {canMarkDone(actor, item) && (
            <button onClick={() => markDone(item.id, actor.id)} className="rounded-lg border border-emerald-600/40 px-2.5 py-1 text-sm text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300">
              Готово
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function Approvals({ actor }: { actor: DemoUser }) {
  const requests = useDemo((s) => s.requests);
  const decide = useDemo((s) => s.decideRequest);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const pending = requests.filter((r) => r.approver_id === actor.id && r.status === "pending_approval");

  return (
    <section aria-label="Ждут одобрения" className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-3">
      <h3 className="mb-2 text-sm font-semibold">Ждут твоего одобрения</h3>
      <ul className="space-y-2">
        {pending.map((r) => (
          <li key={r.id} className="text-sm">
            <div>
              <b>{r.id}</b> · {findUser(r.intern_id)?.name} · {RESOURCES.find((x) => x.id === r.resource_id)?.title} · права: чтение
            </div>
            <div className="text-black/55 dark:text-white/55">{r.justification}</div>
            {rejecting === r.id ? (
              <div className="mt-1.5 flex gap-2">
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Причина отказа"
                  className="min-w-0 flex-1 rounded-lg border border-black/15 bg-transparent px-2 py-1 dark:border-white/20"
                />
                <button
                  disabled={!reason.trim()}
                  onClick={() => { decide(r.id, false, reason.trim()); setRejecting(null); setReason(""); }}
                  className="rounded-lg border border-black/15 px-2.5 py-1 disabled:opacity-40 dark:border-white/20"
                >
                  Отклонить
                </button>
              </div>
            ) : (
              <div className="mt-1.5 flex gap-2">
                <button onClick={() => decide(r.id, true)} className="rounded-lg bg-[#00aaff] px-2.5 py-1 font-medium text-white">Одобрить</button>
                <button onClick={() => setRejecting(r.id)} className="rounded-lg border border-black/15 px-2.5 py-1 dark:border-white/20">Отклонить…</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
