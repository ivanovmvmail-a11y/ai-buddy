"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatMessage, sendChat } from "@/lib/api";

const GREETING: ChatMessage = {
  role: "assistant",
  content: "Привет! Я AI-buddy — помогу освоиться в команде. Спроси что угодно о процессах, инструментах или первых задачах.",
};

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setError(null);
    setLoading(true);
    try {
      // приветствие не отправляем в LLM
      const { reply } = await sendChat(next.slice(1));
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Неизвестная ошибка");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex h-dvh max-w-2xl flex-col px-4">
      <header className="flex items-center gap-2 border-b border-black/10 py-4 dark:border-white/10">
        <span className="grid size-8 place-items-center rounded-full bg-[#00aaff] text-sm font-bold text-white">AI</span>
        <h1 className="text-lg font-semibold">AI-buddy</h1>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto py-4">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-[15px] leading-relaxed ${
                m.role === "user" ? "bg-[#00aaff] text-white" : "bg-black/5 dark:bg-white/10"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm opacity-60">AI-buddy печатает…</div>}
        {error && <div className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-600">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="flex gap-2 border-t border-black/10 py-3 dark:border-white/10">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Напиши вопрос…"
          className="min-w-0 flex-1 rounded-xl border border-black/15 bg-transparent px-4 py-3 text-base outline-none focus:border-[#00aaff] dark:border-white/20"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-xl bg-[#00aaff] px-5 font-medium text-white disabled:opacity-40"
        >
          Отправить
        </button>
      </form>
    </main>
  );
}
