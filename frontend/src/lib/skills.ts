// Карта навыков (SPEC раздел 4, спека 104): общие подписи для экрана наставника и страницы «Мой профиль».
import type { SkillLevel } from "./types";

export const TOPIC_TITLES: Record<string, string> = { git: "Git", sql: "SQL", ci: "CI и тесты" };

export const LEVELS: Array<{ id: SkillLevel; title: string }> = [
  { id: "novice", title: "новичок" },
  { id: "familiar", title: "знаком" },
  { id: "confident", title: "уверенно" },
];

export const topicTitle = (topic: string) => TOPIC_TITLES[topic] ?? topic;
export const levelTitle = (level: SkillLevel) => LEVELS.find((l) => l.id === level)!.title;
