// Состояние сессии в браузере (Zustand): кто вошёл и чей план открыт. Данные — с сервера (TanStack Query).
import { create } from "zustand";

type Session = {
  userId: string;
  internPick: string | null; // выбранный стажёр для наставника/руководителя/куратора
  setUser: (id: string) => void;
  pickIntern: (id: string) => void;
};

export const useSession = create<Session>((set) => ({
  userId: "intern-anya",
  internPick: null,
  setUser: (userId) => set({ userId, internPick: null }),
  pickIntern: (internPick) => set({ internPick }),
}));
