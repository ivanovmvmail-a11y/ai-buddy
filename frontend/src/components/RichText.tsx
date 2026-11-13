import { Fragment, type ReactNode } from "react";

// Модель (GigaChat) отвечает с Markdown: ```bash-блоки, **жирный**, `код`. Без отрисовки стажёр видел звёздочки
// и обратные кавычки (проверка 13.11). Небольшой разбор без зависимостей и без dangerouslySetInnerHTML:
// только блоки кода, жирный и код в строке; остальное — обычный текст с переносами строк.
// Текст остаётся прямо внутри блока сообщения (без лишних обёрток) — как было до разметки.

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

function inline(text: string, key: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={`${key}-${i}`} className="rounded bg-black/[0.06] px-1 py-0.5 font-mono text-[0.9em] dark:bg-white/10">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

export function RichText({ text }: { text: string }) {
  // Нечётные части — содержимое закрытых ```-блоков (первая строка блока — язык, её не показываем).
  const parts = text.split("```");
  const last = parts.length - 1;
  return (
    <div className="whitespace-pre-wrap">
      {parts.map((part, i) => {
        if (i % 2 === 1 && i < last) {
          const body = part.replace(/^[\w+-]*\n/, "").replace(/\n$/, "");
          return (
            <pre
              key={i}
              className="my-1.5 overflow-x-auto rounded-lg bg-black/[0.06] px-3 py-2 font-mono text-[13px] leading-snug dark:bg-white/10"
            >
              {body}
            </pre>
          );
        }
        // Вокруг блока кода переносы строк дал бы сам <pre>; незакрытый ``` (обрезанный ответ) — просто текст.
        let plain = i % 2 === 1 ? part.replace(/^[\w+-]*\n/, "") : part;
        if (i > 0) plain = plain.replace(/^\n/, "");
        if (i < last) plain = plain.replace(/\n$/, "");
        return <Fragment key={i}>{inline(plain, String(i))}</Fragment>;
      })}
    </div>
  );
}
