// Демо-пользователи для экрана «Войти как…» — те же, что в backend/app/agent/users.py.
// Имитация входа: в Авито список и роли приходят из корпоративного SSO.
import type { DemoUser, Role } from "./types";

export const DEMO_USERS: DemoUser[] = [
  { id: "intern-anya", name: "Аня Смирнова", role: "intern", team: "Платформа объявлений", mentor_id: "mentor-petr", lead_id: "lead-olga" },
  { id: "intern-ivan", name: "Иван Кузнецов", role: "intern", team: "Авито Доставка", mentor_id: "mentor-maria", lead_id: "lead-sergey" },
  { id: "mentor-petr", name: "Пётр Волков", role: "mentor", team: "Платформа объявлений" },
  { id: "mentor-maria", name: "Мария Орлова", role: "mentor", team: "Авито Доставка" },
  { id: "lead-olga", name: "Ольга Новикова", role: "lead", team: "Платформа объявлений" },
  { id: "lead-sergey", name: "Сергей Лебедев", role: "lead", team: "Авито Доставка" },
  { id: "hrbp-elena", name: "Елена Морозова", role: "hrbp", team: "HR" },
  { id: "curator-dmitry", name: "Дмитрий Соколов", role: "curator", team: "Avito Start" },
];

export const ROLE_TITLES: Record<Role, string> = {
  intern: "стажёр",
  mentor: "наставник",
  lead: "руководитель",
  hrbp: "HR BP",
  curator: "куратор",
};

export function findUser(id: string | null | undefined): DemoUser | undefined {
  return DEMO_USERS.find((u) => u.id === id);
}

export const firstName = (id: string | null | undefined) => findUser(id)?.name.split(" ")[0] ?? "";
