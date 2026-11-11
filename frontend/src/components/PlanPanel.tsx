"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { canMarkDone, canRequestAccess, isWorking, STAGE_TITLES, waitedFor } from "@/lib/plan-logic";
import { useInterns, usePlan, useProfile, useRefresh, useRequests } from "@/lib/queries";
import { useSession } from "@/lib/store";
import { InternCards } from "./InternCards";
import { ComparePlans, SkillSuggestions } from "./MentorTools";
import { findUser } from "@/lib/users";
import type { DemoUser, ItemStatus, PlanItem, SkillLevel, Stage, StageInfo } from "@/lib/types";

const STATUS: Record<ItemStatus, { label: string; cls: string }> = {
  not_started: { label: "не начат", cls: "bg-black/5 text-black/60 dark:bg-white/10 dark:text-white/60" },
  in_progress: { label: "в работе", cls: "bg-sky-500/10 text-sky-700 dark:text-sky-300" },
  waiting: { label: "ждёт другого человека", cls: "bg-amber-500/15 text-amber-800 dark:text-amber-300" },
  done: { label: "сделано", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
};
const OWNER: Record<PlanItem["owner_role"], string> = { intern: "стажёр", mentor: "наставник", lead: "руководитель" };
const STAGES: Stage[] = ["week1", "week2", "month1", "month2", "after3m"];

type Props = {
  actor: DemoUser;
  onExplain: (item: PlanItem) => void;
  onDo: (item: PlanItem) => void;
};

function Retry({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div role="alert" className="m-4 rounded-xl bg-red-500/10 p-3 text-sm text-red-800 dark:text-red-300">
      {text}{" "}
      <button onClick={onRetry} className="ml-1 rounded-full border border-current px-2.5 py-1">Повторить</button>
    </div>
  );
}

export function PlanPanel({ actor, onExplain, onDo }: Props) {
  const internPick = useSession((s) => s.internPick);
  const pickIntern = useSession((s) => s.pickIntern);
  const interns = useInterns(actor);
  const list = actor.role === "intern" ? [{ id: actor.id, name: actor.name, team: actor.team }] : interns.data ?? [];
  const internId = list.find((u) => u.id === internPick)?.id ?? list[0]?.id;
  const plan = usePlan(actor, internId);
  const profile = useProfile(actor, internId);

  if (actor.role === "hrbp") {
    return (
      <div className="p-6 text-sm text-black/60 dark:text-white/60">
        Планы и профили стажёров для твоей роли недоступны. Чат справа отвечает по общим документам.
      </div>
    );
  }
  if (interns.isError) return <Retry text={interns.error.message} onRetry={() => interns.refetch()} />;
  if (plan.isError) return <Retry text={plan.error.message} onRetry={() => plan.refetch()} />;
  if (!plan.data) return <p className="p-6 text-sm text-black/55 dark:text-white/55">Загружаю план…</p>;

  const p = plan.data;
  const intern = findUser(p.intern_id);

  return (
    <div className="space-y-5 p-4 sm:p-5">
      {actor.role !== "intern" && <InternCards actor={actor} />}

      {actor.role === "mentor" && <Approvals actor={actor} />}
      {actor.role === "mentor" && <SkillSuggestions actor={actor} />}
      {actor.role === "mentor" && <ComparePlans actor={actor} />}

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{actor.id === p.intern_id ? "Мой план" : `План: ${intern?.name}`}</h2>
          <p className="text-sm text-black/55 dark:text-white/55">
            {intern?.team} · день {p.current_day}
          </p>
        </div>
        {list.length > 1 && (
          <select
            aria-label="Стажёр"
            value={internId}
            onChange={(e) => pickIntern(e.target.value)}
            className="rounded-lg border border-black/15 bg-transparent px-2 py-1 text-sm dark:border-white/20"
          >
            {list.map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        )}
      </div>

      <Ladder ladder={p.ladder} />

      {STAGES.map((stage) => {
        const items = p.items.filter((i) => i.stage === stage);
        if (!items.length) return null;
        return (
          <section key={stage} aria-label={STAGE_TITLES[stage]}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-black/45 dark:text-white/45">
              {STAGE_TITLES[stage]} {!isWorking(stage) && "· впереди"}
            </h3>
            <ul className="space-y-2">
              {items.map((item) => (
                <PlanRow
                  key={item.id}
                  item={item}
                  actor={actor}
                  isNext={p.next_step.item?.id === item.id}
                  level={item.topic ? profile.data?.skills[item.topic] : undefined}
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
      {ladder.map((s) => (
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
            {s.state === "passed" ? "пройдено" : s.state === "current" ? `осталось ${s.total - s.done}` : "впереди"}
          </div>
        </li>
      ))}
    </ol>
  );
}

const HINT: Partial<Record<SkillLevel, string>> = { novice: "здесь помогу подробно" };

function PlanRow({
  item, actor, isNext, level, onExplain, onDo,
}: { item: PlanItem; actor: DemoUser; isNext: boolean; level?: SkillLevel; onExplain: Props["onExplain"]; onDo: Props["onDo"] }) {
  const refresh = useRefresh();
  const mark = useMutation({ mutationFn: () => api.setStatus(actor.id, item.id, "done"), onSuccess: refresh });
  const working = isWorking(item.stage);
  const st = STATUS[item.status];
  const self = actor.id === item.intern_id;
  // Карту навыков видят только сам стажёр и наставник (SPEC 7) — от неё зависят «почему» и «коротко».
  const seesSkills = self || actor.role === "mentor";
  const lvl = item.skill_level ?? level;
  const hint = lvl && self ? HINT[lvl] : undefined;
  const personal = item.kind === "personal";
  const short = seesSkills && !personal && lvl === "confident";

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
      {isNext && <div className="mb-0.5 text-xs font-semibold text-[#0088cc]">Следующий шаг</div>}
      <div className="text-[15px] font-medium leading-snug">{item.title}</div>
      {working && (
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
          <span
            className={`rounded-full px-2 py-0.5 ${
              personal
                ? "bg-violet-500/12 font-medium text-violet-700 dark:text-violet-300"
                : "border border-black/10 text-black/50 dark:border-white/15 dark:text-white/50"
            }`}
          >
            {personal ? (self ? "для тебя" : "персональный") : "для всех"}
          </span>
          {short && (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">
              {self ? "ты это умеешь — коротко" : "умеет — коротко"}
            </span>
          )}
          <span className={`rounded-full px-2 py-0.5 ${st.cls}`}>{st.label}</span>
          {item.overdue && item.status !== "waiting" && <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-orange-800 dark:text-orange-300">срок прошёл</span>}
          <span className="text-black/50 dark:text-white/50">
            {OWNER[item.owner_role]}
            {item.due_day ? ` · до дня ${item.due_day}` : ""}
          </span>
          {hint && <span className="text-black/50 dark:text-white/50">· {hint}</span>}
        </div>
      )}
      {personal && item.reason && seesSkills && (
        <p className="mt-1 text-xs text-black/55 dark:text-white/55">Почему: {item.reason}</p>
      )}
      {item.status === "waiting" && item.waiting_for && (
        <p className="mt-1 text-xs text-black/55 dark:text-white/55">
          Ждём: {findUser(item.waiting_for)?.name}, {waitedFor(item.waiting_days ?? 0)}
        </p>
      )}
      {item.status_reason && <p className="mt-1 text-xs text-orange-800 dark:text-orange-300">Причина: {item.status_reason}</p>}
      {mark.isError && <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-300">{mark.error.message}</p>}
      {working && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button onClick={() => onExplain(item)} className="rounded-lg border border-black/15 px-2.5 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10">
            Объяснить
          </button>
          {canRequestAccess(actor, item) && (
            <button onClick={() => onDo(item)} className="rounded-lg bg-[#00aaff] px-2.5 py-1 text-sm font-medium text-white hover:bg-[#0099e6]">
              Сделать за меня
            </button>
          )}
          {canMarkDone(actor, item) && (
            <button
              disabled={mark.isPending}
              onClick={() => mark.mutate()}
              className="rounded-lg border border-emerald-600/40 px-2.5 py-1 text-sm text-emerald-700 hover:bg-emerald-500/10 disabled:opacity-50 dark:text-emerald-300"
            >
              Готово
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function Approvals({ actor }: { actor: DemoUser }) {
  const requests = useRequests(actor);
  const refresh = useRefresh();
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const decide = useMutation({
    mutationFn: (v: { id: string; approve: boolean; reason?: string }) => api.decide(actor.id, v.id, v.approve, v.reason),
    onSuccess: () => {
      setRejecting(null);
      setReason("");
      return refresh();
    },
  });
  const pending = (requests.data ?? []).filter((r) => r.approver_id === actor.id && r.status === "pending_approval");
  if (!pending.length) return null;

  return (
    <section aria-label="Ждут одобрения" className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-3">
      <h3 className="mb-2 text-sm font-semibold">Ждут твоего одобрения</h3>
      {decide.isError && <p role="alert" className="mb-2 text-sm text-red-700 dark:text-red-300">{decide.error.message}</p>}
      <ul className="space-y-2">
        {pending.map((r) => (
          <li key={r.id} className="text-sm">
            <div>
              <b>{r.id}</b> · {findUser(r.intern_id)?.name} · {r.resource_title ?? r.resource_id} · права: {r.level === "read" ? "чтение" : r.level}
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
                  disabled={!reason.trim() || decide.isPending}
                  onClick={() => decide.mutate({ id: r.id, approve: false, reason: reason.trim() })}
                  className="rounded-lg border border-black/15 px-2.5 py-1 disabled:opacity-40 dark:border-white/20"
                >
                  Отклонить
                </button>
              </div>
            ) : (
              <div className="mt-1.5 flex gap-2">
                <button disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, approve: true })} className="rounded-lg bg-[#00aaff] px-2.5 py-1 font-medium text-white disabled:opacity-50">
                  Одобрить
                </button>
                <button onClick={() => setRejecting(r.id)} className="rounded-lg border border-black/15 px-2.5 py-1 dark:border-white/20">Отклонить…</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
