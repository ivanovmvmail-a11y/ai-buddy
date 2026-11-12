// Данные поддельного сервера для тестов интерфейса (бывший макет T2). Настоящие данные — seed имитаций
// сервисов на backend. Всё синтетическое.
import { DEMO_USERS } from "@/lib/users";
import type { AbsenceRequest, Reminder, SkillSuggestion } from "@/lib/types";
import type { AccessRequest, AccessResource, DemoUser, OwnerRole, PlanItem, SkillProfile, Stage } from "@/lib/types";

export { DEMO_USERS };

export const RESOURCES: AccessResource[] = [
  { id: "base-access", title: "Jira и Confluence", kind: "base", team: null, approver: "auto" },
  { id: "bitbucket-platform", title: "Пространство команды в Bitbucket", kind: "team_space", team: "Платформа объявлений", approver: "mentor" },
  { id: "bitbucket-delivery", title: "Пространство команды в Bitbucket", kind: "team_space", team: "Авито Доставка", approver: "mentor" },
];

type ItemSeed = {
  key: string;
  stage: Stage;
  title: string;
  summary: string;
  owner: OwnerRole;
  due?: number;
  topic?: string;
  doc?: string;
  resource?: string;
  practice?: string;
};

const COMMON: ItemSeed[] = [
  { key: "w1.team", stage: "week1", owner: "intern", due: 2, doc: "demo:01-onboarding.md",
    title: "Познакомиться с командой", summary: "Коротко расскажи о себе на встрече команды и узнай, кто за что отвечает." },
  { key: "w1.access-base", stage: "week1", owner: "intern", due: 3, resource: "base-access",
    title: "Запросить базовые доступы: Jira и Confluence", summary: "Без них не видно задач и базы знаний. Выдаются автоматически." },
  { key: "w1.chats", stage: "week1", owner: "mentor", due: 2,
    title: "Добавить стажёра в чаты и каналы Mattermost", summary: "Наставник добавляет в рабочие каналы команды." },
  { key: "w1.one-on-one", stage: "week1", owner: "mentor", due: 5,
    title: "Назначить регулярные 1:1", summary: "Наставник ставит встречи в календарь, обычно раз в неделю." },
  { key: "w1.goals", stage: "week1", owner: "lead", due: 5,
    title: "Обсудить цели, план адаптации и критерии успеха", summary: "Руководитель рассказывает, что будет считаться успехом стажировки." },
  { key: "w1.notes", stage: "week1", owner: "intern", due: 5,
    title: "Завести конспект встреч с наставником", summary: "Один документ: вопросы до встречи, договорённости после." },
  { key: "w2.tracker", stage: "week2", owner: "intern", due: 8,
    title: "Получить у куратора инструмент отслеживания прогресса", summary: "Внести туда свои цели на испытательный срок." },
  { key: "w2.docs", stage: "week2", owner: "intern", due: 10, topic: "monitoring",
    title: "Изучить документы и мануалы команды", summary: "Как устроены сервисы команды и где смотреть их состояние.",
    practice: "Открой Grafana, найди два дашборда своей команды и посмотри время ответа сервиса." },
  { key: "m1.task", stage: "month1", owner: "intern", title: "Первая задача в рабочем репозитории", summary: "Небольшая задача с понятным результатом." },
  { key: "m1.review", stage: "month1", owner: "mentor", title: "Разбор первой задачи с наставником", summary: "Что получилось и что улучшить." },
  { key: "m2.feature", stage: "month2", owner: "intern", title: "Самостоятельная задача средней сложности", summary: "Задача, которую ведёшь сам от начала до релиза." },
  { key: "a3.results", stage: "after3m", owner: "lead", title: "Итоги испытательного срока", summary: "Встреча с руководителем и наставником." },
];

const TEAM: Record<string, ItemSeed[]> = {
  "Платформа объявлений": [
    { key: "w1.access-team", stage: "week1", owner: "intern", due: 5, topic: "git", resource: "bitbucket-platform",
      doc: "demo:13-team-space-access.md", title: "Запросить доступ в пространство команды и изучить его",
      summary: "Репозитории команды в Bitbucket. Доступ одобряет наставник.",
      practice: "Склонируй учебный репозиторий и найди, где описан запуск сервиса." },
    { key: "w1.sandbox", stage: "week1", owner: "intern", due: 5, topic: "ci", doc: "demo:17-platform-sandbox-setup.md",
      title: "Поднять песочницу Платформы объявлений", summary: "Локальный стенд с учебными объявлениями.",
      practice: "Создай в песочнице объявление «Картонный дирижабль» и найди его поиском." },
  ],
  "Авито Доставка": [
    { key: "w1.access-team", stage: "week1", owner: "intern", due: 5, topic: "git", resource: "bitbucket-delivery",
      doc: "demo:13-team-space-access.md", title: "Запросить доступ в пространство команды и изучить его",
      summary: "Репозитории команды в Bitbucket. Доступ одобряет наставник.",
      practice: "Склонируй учебный репозиторий и найди, где описаны статусы отправления." },
    { key: "w1.sandbox", stage: "week1", owner: "intern", due: 5, topic: "ci", doc: "demo:20-delivery-sandbox-setup.md",
      title: "Поднять учебный стенд Доставки", summary: "Стенд с вымышленными пунктами выдачи.",
      practice: "Создай отправление «Бирюзовый пакет» и проверь его статус." },
  ],
};

// Персональные пункты из каталога (SPEC 3.1): тема в карте навыков «новичок» → учебный пункт «для тебя».
const PERSONAL: Record<string, Array<ItemSeed & { reason: string }>> = {
  "intern-anya": [
    { key: "p.git", stage: "week1", owner: "intern", due: 6, topic: "git", doc: "demo:11-git-workflow.md",
      title: "Практикум: ветки и pull request", summary: "Учебный pull request в песочнице команды.",
      reason: "в карте навыков Git — новичок" },
  ],
  "intern-kirill": [
    { key: "p.sql", stage: "week2", owner: "intern", due: 10, topic: "sql", doc: "demo:06-platform-lifecycle.md",
      title: "Практикум: запросы к учебной базе объявлений", summary: "Три запроса к вымышленным объявлениям.",
      reason: "в карте навыков SQL — новичок" },
  ],
  "intern-ivan": [
    { key: "p.sql", stage: "week2", owner: "intern", due: 10, topic: "sql", doc: "demo:09-delivery-statuses.md",
      title: "Практикум: запросы к учебной базе доставок", summary: "Три запроса к вымышленным отправлениям.",
      reason: "в карте навыков SQL — новичок" },
  ],
};

const STAGE_ORDER: Stage[] = ["week1", "week2", "month1", "month2", "after3m"];

function buildItems(intern: DemoUser): PlanItem[] {
  const personal = PERSONAL[intern.id] ?? [];
  const seeds: Array<ItemSeed & { reason?: string }> = [...COMMON, ...(TEAM[intern.team] ?? []), ...personal];
  const short = intern.id.replace("intern-", "");
  return seeds
    .sort((a, b) => STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage))
    .map((s, i) => ({
      kind: s.reason ? ("personal" as const) : ("common" as const),
      reason: s.reason ?? null,
      known_marked: false,
      catalog_key: s.reason ? `${short}.${s.key}` : null,
      id: `${short}.${s.key}`,
      intern_id: intern.id,
      stage: s.stage,
      order: i,
      title: s.title,
      summary: s.summary,
      owner_role: s.owner,
      topic: s.topic ?? null,
      doc_source_id: s.doc ?? null,
      resource_id: s.resource ?? null,
      due_day: s.due ?? null,
      practice: s.practice ?? null,
      status: "not_started",
      status_reason: null,
      updated_at: "2026-11-11T09:00:00Z",
      updated_by: null,
      overdue: false,
      waiting_for: null,
      waiting_days: null,
    }));
}

export type DemoState = {
  days: Record<string, number>;
  items: PlanItem[];
  requests: AccessRequest[];
  profiles: SkillProfile[];
  dismissedReminders: string[];
  suggestions: SkillSuggestion[];
  absences: AbsenceRequest[];
  notifications: Reminder[];
};

/** Второй стажёр Петра (SPEC 3.1). В поддельном сервере подключается только в тестах сравнения (`srv.addKirill()`),
 * чтобы старые тесты «у Петра одна Аня» не менялись. */
export const KIRILL: DemoUser = DEMO_USERS.find((u) => u.id === "intern-kirill")!;
export const EXTRA_INTERNS = new Set(["intern-kirill", "intern-liza"]);

export function addKirill(s: DemoState) {
  s.days[KIRILL.id] = 3;
  s.items.push(...buildItems(KIRILL));
  s.profiles.push({ intern_id: KIRILL.id, skills: { git: "confident", sql: "novice", ci: "familiar", monitoring: "familiar" },
    strengths: ["Уверенно работает с Git"], growth: ["SQL"] });
}

export function initialState(): DemoState {
  const anya = DEMO_USERS[0];
  const ivan = DEMO_USERS[1];
  const items = [...buildItems(anya), ...buildItems(ivan)];
  const set = (id: string, patch: Partial<PlanItem>) => {
    const it = items.find((x) => x.id === id);
    if (it) Object.assign(it, patch);
  };
  // Аня — день 2: познакомилась с командой.
  set("anya.w1.team", { status: "done" });
  // Иван — день 8: базовые доступы есть, заявка в пространство команды ждёт 3 дня, конспект просрочен.
  for (const k of ["w1.team", "w1.access-base", "w1.chats", "w1.one-on-one", "w1.sandbox"]) set(`ivan.${k}`, { status: "done" });
  set("ivan.w1.access-team", { status: "waiting" });

  return {
    days: { "intern-anya": 2, "intern-ivan": 8 },
    items,
    requests: [
      { id: "REQ-1001", intern_id: "intern-ivan", resource_id: "base-access", level: "read", justification: "Работа с задачами команды",
        status: "granted", approver_id: null, reject_reason: null, plan_item_id: "ivan.w1.access-base", created_day: 2 },
      { id: "REQ-1002", intern_id: "intern-ivan", resource_id: "bitbucket-delivery", level: "read", justification: "Изучить репозитории команды",
        status: "pending_approval", approver_id: "mentor-maria", reject_reason: null, plan_item_id: "ivan.w1.access-team", created_day: 5 },
    ],
    profiles: [
      { intern_id: "intern-anya", skills: { git: "novice", sql: "confident", ci: "familiar", monitoring: "novice" },
        strengths: ["Хорошо пишет SQL-запросы", "Аккуратно описывает задачи"], growth: ["Работа с Git и ревью", "Мониторинг сервисов"] },
      { intern_id: "intern-ivan", skills: { git: "confident", sql: "novice", ci: "confident", monitoring: "familiar" },
        strengths: ["Уверенно работает с Git", "Быстро поднимает окружение"], growth: ["SQL и аналитика данных"] },
    ],
    dismissedReminders: [],
    suggestions: [],
    absences: [],
    notifications: [],
  };
}
