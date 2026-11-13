// Состояние сессии в браузере (Zustand): кто вошёл и чей план открыт. Данные — с сервера (TanStack Query).
import { create } from "zustand";

export type Section = "home" | "plan" | "profile";

type Session = {
  userId: string;
  internPick: string | null; // выбранный стажёр для наставника/руководителя/куратора
  section: Section; // раздел в центре у стажёра (редизайн 13.11): «Главная», «Мой план», «Мой профиль»
  setSection: (s: Section) => void;
  setUser: (id: string) => void;
  pickIntern: (id: string) => void;
};

const SAVED_USER = "ai-buddy-user";

/** Кто входил последним — чтобы обновление страницы не выкидывало на Аню (аудит D7). Без хранилища — просто нет. */
export function savedUserId(): string | null {
  try {
    return localStorage.getItem(SAVED_USER);
  } catch {
    return null;
  }
}

export const useSession = create<Session>((set) => ({
  userId: "intern-anya",
  internPick: null,
  section: "home",
  setSection: (section) => set({ section }),
  setUser: (userId) => {
    try {
      localStorage.setItem(SAVED_USER, userId);
    } catch {
      /* приватное окно — запомнить не получится, это не ошибка */
    }
    set({ userId, internPick: null, section: "home" });
  },
  pickIntern: (internPick) => set({ internPick }),
}));
