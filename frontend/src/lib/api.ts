// Клиент к backend. Контракт — docs/API.md.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatMessage = { role: "user" | "assistant"; content: string };
export type Source = { title: string; url: string | null };
export type ChatResponse = { reply: string; sources: Source[] };

export async function sendChat(messages: ChatMessage[]): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Ошибка сервера: ${res.status}`);
  }
  return res.json();
}
