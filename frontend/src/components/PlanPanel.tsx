"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { canMarkDone, canRequestAccess, isWorking, STAGE_TITLES, waitedFor } from "@/lib/plan-logic";
import { useCatalog, useInterns, usePlan, useProfile, useRefresh, useRequests } from "@/lib/queries";
import { useSession } from "@/lib/store";
import { InternCards } from "./InternCards";
import { ComparePlans, SkillSuggestions } from "./MentorTools";
import { AbsenceRequests } from "./AbsencePanel";
import { MentorQuestions } from "./MentorQuestions";
import { findUser } from "@/lib/users";
import type { DemoUser, ItemStatus, PlanItem, SkillLevel, Stage, StageInfo } from "@/lib/types";

const STATUS: Record<ItemStatus, { label: string; cls: string }> = {
  not_started: { label: "не начат", cls: "bg-surface-2 text-[var(--muted)]" },
  in_progress: { label: "в работе", cls: "bg-accent/15 text-accent-ink" },
  waiting: { label: "ждёт другого человека", cls: "bg-amber-500/15 text-amber-800 dark:text-amber-300" },
  done: { label: "сделано", cls: "bg-brand-green/20 text-emerald-800 dark:text-emerald-300" },
};
const OWNER: Record<PlanItem["owner_role"], string> = { intern: "стажёр", mentor: "наставник", lead: "руководитель" };
const STAGES: Stage[] = ["week1", "week2", "month1", "month2", "after3m"];

type Props = {
  actor: DemoUser;
  onExplain: (item: PlanItem) => void;
  onDo: (item: PlanItem) => void;
  onPractice: (item: PlanItem) => void; // «Сдать задание» — в чате (чекпоинт 2)
};

function Retry({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div role="alert" className="m-4 rounded-xl bg-red-500/10 p-3 text-sm text-red-800 dark:text-red-300">
      {text}{" "}
      <button onClick={onRetry} className="ml-1 rounded-full border border-current px-2.5 py-1">Повторить</button>
    </div>
  );
}

export function PlanPanel({ actor, onExplain, onDo, onPractice }: Props) {
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
      {/* Наставнику сначала то, что ждёт решения, и сравнение планов (главная идея), потом карточки (проверка 12.11). */}
      {actor.role === "mentor" && <Approvals actor={actor} />}
      {actor.role === "mentor" && <MentorQuestions actor={actor} />}
      {actor.role === "mentor" && <SkillSuggestions actor={actor} />}
      {actor.role === "mentor" && <ComparePlans actor={actor} />}

      {actor.role !== "intern" && <InternCards actor={actor} />}
      {/* Стажёру «Мои вопросы наставнику» и «Мои заявки на отгул» — на «Главной» (редизайн 13.11). */}
      {actor.role === "lead" && <AbsenceRequests actor={actor} />}

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-[22px] font-bold tracking-[-0.01em]">{actor.id === p.intern_id ? "Мой план" : `План: ${intern?.name}`}</h2>
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

      {actor.role === "mentor" && <CatalogPicker actor={actor} internId={p.intern_id} name={intern?.name.split(" ")[0] ?? ""} />}

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
                  onPractice={onPractice}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

/** Наставник добавляет стажёру пункт из каталога команды (SPEC 3.1): только то, чего ещё нет в плане. */
function CatalogPicker({ actor, internId, name }: { actor: DemoUser; internId: string; name: string }) {
  const catalog = useCatalog(actor, internId);
  const refresh = useRefresh();
  const add = useMutation({ mutationFn: (key: string) => api.addPersonal(actor.id, internId, key), onSuccess: refresh });
  const free = (catalog.data ?? []).filter((c) => !c.in_plan);
  if (!free.length) return null;
  return (
    <section aria-label="Каталог пунктов" className="rounded-[20px] border border-dashed border-brand-violet/50 p-4 text-sm">
      <h3 className="font-semibold">Добавить пункт в план{name ? `: ${name}` : ""}</h3>
      <p className="mb-2 text-xs text-black/50 dark:text-white/50">Из каталога команды. Общие пункты не меняются.</p>
      {add.isError && <p role="alert" className="mb-2 text-red-700 dark:text-red-300">{add.error.message}</p>}
      <ul className="flex flex-wrap gap-2">
        {free.map((c) => (
          <li key={c.key}>
            <button
              disabled={add.isPending}
              onClick={() => add.mutate(c.key)}
              // Имя кнопки для программ чтения с экрана — название пункта, а не подсказка (проверка 12.11)
              aria-label={`Добавить в план: ${c.title}`}
              title={c.summary}
              className="rounded-lg border border-violet-500/40 px-2.5 py-1 text-violet-700 hover:bg-violet-500/10 disabled:opacity-50 dark:text-violet-300"
            >
              + {c.title}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Ladder({ ladder }: { ladder: StageInfo[] }) {
  return (
    <ol aria-label="Этапы стажировки" className="grid grid-cols-4 gap-1.5">
      {ladder.map((s) => (
        <li
          key={s.title}
          aria-current={s.state === "current" ? "step" : undefined}
          className={`rounded-2xl px-3 py-2 text-xs leading-tight ${
            s.state === "current"
              ? "bg-accent/15 shadow-[inset_0_0_0_1.5px_var(--accent)]"
              : s.state === "passed"
                ? "bg-brand-green/20"
                : "bg-surface-2 text-[var(--muted)]"
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
  item, actor, isNext, level, onExplain, onDo, onPractice,
}: { item: PlanItem; actor: DemoUser; isNext: boolean; level?: SkillLevel; onExplain: Props["onExplain"]; onDo: Props["onDo"]; onPractice: Props["onPractice"] }) {
  const refresh = useRefresh();
  const mark = useMutation({ mutationFn: () => api.setStatus(actor.id, item.id, "done"), onSuccess: refresh });
  // SPEC 4: «это я уже знаю» — повод для предложения наставнику; пункт не закрывается, уровень решает наставник.
  const know = useMutation({ mutationFn: (known: boolean) => api.markKnown(actor.id, item.id, known), onSuccess: refresh });
  // SPEC 3.1: наставник убирает персональный пункт своего стажёра (общие и закрытые — нельзя).
  const remove = useMutation({ mutationFn: () => api.removePersonal(actor.id, item.id), onSuccess: refresh });
  const working = isWorking(item.stage);
  const st = STATUS[item.status];
  const self = actor.id === item.intern_id;
  // Карту навыков видят только сам стажёр и наставник (SPEC 7) — от неё зависят «почему» и «коротко».
  const seesSkills = self || actor.role === "mentor";
  const lvl = item.skill_level ?? level;
  const hint = lvl && self ? HINT[lvl] : undefined;
  const personal = item.kind === "personal";
  const short = seesSkills && !personal && lvl === "confident";
  // Спека 107: задание на практике, которое бот проверит по документу пункта (только сам стажёр).
  const canPractice = self && working && item.practice_check && item.status !== "done";
  const canKnow = self && working && item.owner_role === "intern" && !!item.topic && item.status !== "done" && lvl !== "confident";

  // Иерархия (Миша, 13.11: «слишком много кнопок, главные сливаются»): одна главная кнопка-таблетка справа —
  // то, что нужно сделать стажёру; остальное — тихими ссылками под пунктом. У закрытого пункта — ничего лишнего.
  const primary: { label: string; run: () => void; pending?: boolean } | null =
    canRequestAccess(actor, item) ? { label: "Сделать за меня", run: () => onDo(item) }
      : canPractice ? { label: "Сдать задание", run: () => onPractice(item) }
        : canMarkDone(actor, item) ? { label: "Готово", run: () => mark.mutate(), pending: mark.isPending }
          : null;
  const done = item.status === "done";
  const link = "rounded-md text-sm text-[var(--muted)] underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50";

  return (
    <li
      className={`rounded-[20px] p-4 ${
        !working
          ? "border border-dashed border-line text-[var(--muted)]"
          : isNext
            ? "card shadow-[0_0_0_2px_var(--accent)]"
            : done ? "bg-surface/60" : "card"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          {isNext && <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-accent-ink">Следующий шаг</div>}
          <div className={`text-[15px] font-semibold leading-snug ${done ? "text-[var(--muted)] line-through decoration-1" : ""}`}>{item.title}</div>
          {working && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
              <span className={`rounded-full px-2 py-0.5 font-medium ${st.cls}`}>{st.label}</span>
              {personal ? (
                <span className="rounded-full bg-brand-violet/15 px-2 py-0.5 font-medium text-violet-700 dark:text-violet-300">
                  {self ? "для тебя" : "персональный"}
                </span>
              ) : (
                <span className="text-[var(--muted)]">для всех</span>
              )}
              {short && (
                <span className="rounded-full bg-brand-green/20 px-2 py-0.5 text-emerald-800 dark:text-emerald-300">{self ? "ты это умеешь — коротко" : "умеет — коротко"}</span>
              )}
              {item.overdue && item.status !== "waiting" && !done && (
                <span className="rounded-full bg-brand-red/15 px-2 py-0.5 font-medium text-red-700 dark:text-red-300">срок прошёл</span>
              )}
              <span className="text-[var(--muted)]">
                · {OWNER[item.owner_role]}
                {item.due_day ? ` · до дня ${item.due_day}` : ""}
                {hint ? ` · ${hint}` : ""}
              </span>
            </div>
          )}
        </div>
        {working && primary && (
          <button
            disabled={primary.pending}
            onClick={primary.run}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold disabled:opacity-50 ${
              isNext ? "bg-accent text-black hover:bg-accent-hover" : "border border-foreground/25 hover:bg-surface-2"
            }`}
          >
            {primary.label}
          </button>
        )}
      </div>
      {personal && item.reason && seesSkills && !done && (
        <p className="mt-1.5 text-xs text-[var(--muted)]">Почему: {item.reason}</p>
      )}
      {item.status === "waiting" && item.waiting_for && (
        <p className="mt-1.5 text-xs text-amber-800 dark:text-amber-300">
          Ждём: {findUser(item.waiting_for)?.name}, {waitedFor(item.waiting_days ?? 0)}
        </p>
      )}
      {item.status_reason && <p className="mt-1.5 text-xs text-red-700 dark:text-red-300">Причина: {item.status_reason}</p>}
      {item.known_marked && self && !done && (
        <p className="mt-1.5 text-xs text-[var(--muted)]">
          Отмечено: это я уже знаю. Наставник решит, поднять ли уровень.{" "}
          <button disabled={know.isPending} onClick={() => know.mutate(false)} className="underline underline-offset-2 disabled:opacity-50">
            Убрать отметку
          </button>
        </p>
      )}
      {mark.isError && <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-300">{mark.error.message}</p>}
      {know.isError && <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-300">{know.error.message}</p>}
      {remove.isError && <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-300">{remove.error.message}</p>}
      {working && !done && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          <button onClick={() => onExplain(item)} className={link}>Объяснить</button>
          {canKnow && !item.known_marked && (
            <button disabled={know.isPending} onClick={() => know.mutate(true)} className={link}>Это я уже знаю</button>
          )}
          {actor.role === "mentor" && personal && (
            <button disabled={remove.isPending} onClick={() => remove.mutate()} className={link}>Убрать из плана</button>
          )}
        </div>
      )}
      {working && done && (
        <button onClick={() => onExplain(item)} className={`${link} mt-1.5`}>Объяснить</button>
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
    <section aria-label="Ждут одобрения" className="card p-4 sm:p-5 shadow-[inset_4px_0_0_rgb(245_158_11),0_0_0_1px_var(--line)]">
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
                  className="rounded-full border border-line px-3 py-1 disabled:opacity-40 dark:border-white/20"
                >
                  Отклонить
                </button>
              </div>
            ) : (
              <div className="mt-1.5 flex gap-2">
                <button disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, approve: true })} className="rounded-full bg-accent px-4 py-1 font-semibold text-black hover:bg-accent-hover disabled:opacity-50">
                  Одобрить
                </button>
                <button onClick={() => setRejecting(r.id)} className="rounded-full border border-line px-3 py-1 dark:border-white/20">Отклонить…</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
