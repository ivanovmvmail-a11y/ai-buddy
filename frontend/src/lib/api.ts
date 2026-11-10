// Клиент к backend. Контракт — docs/API.md.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatMessage = { role: "user" | "assistant"; content: string };
export type Source = { title: string; url: string | null };
export type ChatResponse = { reply: string; sources: Source[] };

export async function sendChat(messages: ChatMessage[], userId?: string): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (userId) headers["X-User-Id"] = userId; // имитация входа, см. docs/API.md
  const res = await fetch(`${API_URL}/chat`, { method: "POST", headers, body: JSON.stringify({ messages }) });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Ошибка сервера: ${res.status}`);
  }
  return res.json();
}
