// Типы повторяют контракт имитаций сервисов: docs/specs/101-plan-next-step/plan.md, раздел 3.1.
// Когда появится API (задача T4), те же типы придут с сервера.

export type Role = "intern" | "mentor" | "lead" | "hrbp" | "curator";
export type Stage = "week1" | "week2" | "month1" | "month2" | "after3m";
export type OwnerRole = "intern" | "mentor" | "lead";
export type ItemStatus = "not_started" | "in_progress" | "waiting" | "done";
export type SkillLevel = "novice" | "familiar" | "confident";
export type AccessLevel = "read" | "edit" | "admin";
export type RequestStatus = "created" | "pending_approval" | "granted" | "rejected";

export type DemoUser = {
  id: string;
  name: string;
  role: Role;
  team: string;
  mentor_id?: string | null;
};

export type PlanItem = {
  id: string;
  intern_id: string;
  stage: Stage;
  order: number;
  title: string;
  summary: string;
  owner_role: OwnerRole;
  topic: string | null;
  doc_source_id: string | null;
  resource_id: string | null;
  due_day: number | null;
  practice: string | null;
  status: ItemStatus;
  status_reason: string | null;
  updated_at: string;
  updated_by: string | null;
  overdue: boolean;
  waiting_for: string | null;
  waiting_days: number | null;
};

export type StageInfo = {
  stage: Stage;
  title: string;
  total: number;
  done: number;
  state: "passed" | "current" | "ahead";
};

export type NextStep = { item: PlanItem | null; waiting: PlanItem[] };

export type Plan = {
  intern_id: string;
  current_day: number;
  items: PlanItem[];
  ladder: StageInfo[];
  next_step: NextStep;
};

export type AccessResource = {
  id: string;
  title: string;
  kind: "base" | "team_space";
  team: string | null;
  approver: "auto" | "mentor";
};

export type AccessRequest = {
  id: string;
  intern_id: string;
  resource_id: string;
  level: AccessLevel;
  justification: string;
  status: RequestStatus;
  approver_id: string | null;
  reject_reason: string | null;
  plan_item_id: string | null;
  created_day: number;
};

export type SkillProfile = {
  intern_id: string;
  skills: Record<string, SkillLevel>;
  strengths: string[];
  growth: string[];
};

export type Reminder = {
  id: string;
  user_id: string;
  plan_item_id: string | null;
  request_id: string | null;
  text: string;
  status: "active" | "snoozed" | "done";
  created_day: number;
  snooze_until_day: number | null;
};
