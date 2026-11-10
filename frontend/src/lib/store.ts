// Состояние макета (Zustand). Действия повторяют функции имитаций сервисов из контракта спеки 101:
// set_item_status, create_request, decide_request, advance_day, reset_demo. В задаче T4 они станут вызовами API.
import { create } from "zustand";
import { initialState, RESOURCES, type DemoState } from "./mock-data";
import type { AccessLevel, AccessRequest } from "./types";

type Store = DemoState & {
  userId: string;
  setUser: (id: string) => void;
  markDone: (itemId: string, by: string) => void;
  returnItem: (itemId: string, by: string, reason: string) => void;
  createRequest: (itemId: string, level: AccessLevel, justification: string) => AccessRequest | null;
  decideRequest: (requestId: string, approve: boolean, reason?: string) => void;
  nextDay: () => void;
  dismissReminder: (id: string) => void;
  reset: () => void;
};

let reqCounter = 1003;

export const useDemo = create<Store>((set, get) => ({
  ...initialState(),
  userId: "intern-anya",
  setUser: (id) => set({ userId: id }),

  markDone: (itemId, by) =>
    set((s) => ({
      items: s.items.map((i) => (i.id === itemId ? { ...i, status: "done", status_reason: null, updated_by: by } : i)),
    })),

  returnItem: (itemId, by, reason) =>
    set((s) => ({
      items: s.items.map((i) => (i.id === itemId ? { ...i, status: "in_progress", status_reason: reason, updated_by: by } : i)),
    })),

  createRequest: (itemId, level, justification) => {
    const s = get();
    const item = s.items.find((i) => i.id === itemId);
    const resource = RESOURCES.find((r) => r.id === item?.resource_id);
    if (!item || !resource) return null;
    const auto = resource.approver === "auto";
    const mentorId = item.intern_id === "intern-anya" ? "mentor-petr" : "mentor-maria";
    const req: AccessRequest = {
      id: `REQ-${reqCounter++}`,
      intern_id: item.intern_id,
      resource_id: resource.id,
      level,
      justification,
      status: auto ? "granted" : "pending_approval",
      approver_id: auto ? null : mentorId,
      reject_reason: null,
      plan_item_id: item.id,
      created_day: s.days[item.intern_id] ?? 1,
    };
    set({
      requests: [req, ...s.requests],
      items: s.items.map((i) => (i.id === itemId ? { ...i, status: auto ? "done" : "waiting", status_reason: null } : i)),
    });
    return req;
  },

  decideRequest: (requestId, approve, reason) =>
    set((s) => {
      const req = s.requests.find((r) => r.id === requestId);
      if (!req) return {};
      return {
        requests: s.requests.map((r) =>
          r.id === requestId ? { ...r, status: approve ? "granted" : "rejected", reject_reason: approve ? null : reason ?? null } : r,
        ),
        items: s.items.map((i) =>
          i.id === req.plan_item_id
            ? { ...i, status: approve ? "done" : "in_progress", status_reason: approve ? null : reason ?? null }
            : i,
        ),
      };
    }),

  nextDay: () =>
    set((s) => ({ days: Object.fromEntries(Object.entries(s.days).map(([k, v]) => [k, v + 1])) })),

  dismissReminder: (id) => set((s) => ({ dismissedReminders: [...s.dismissedReminders, id] })),

  reset: () => {
    reqCounter = 1003;
    set({ ...initialState() });
  },
}));
