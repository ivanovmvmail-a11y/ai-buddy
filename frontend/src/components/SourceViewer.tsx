"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ApiError } from "@/lib/api";
import { useDocument } from "@/lib/queries";
import type { DemoUser } from "@/lib/types";

/** Название источника — кнопка: по клику документ открывается в окне (проверка 12.11: ссылки вели в никуда). */
export function SourceLink({ actor, title, className = "" }: { actor: DemoUser; title: string; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`underline decoration-current/40 underline-offset-2 hover:text-[#00aaff] hover:decoration-[#00aaff] active:scale-100 ${className}`}
      >
        {title}
      </button>
      {/* В body: панель чата на телефоне сдвинута, и fixed внутри неё считался бы от панели, а не от экрана. */}
      {open && createPortal(<DocumentDialog actor={actor} title={title} onClose={() => setOpen(false)} />, document.body)}
    </>
  );
}

function DocumentDialog({ actor, title, onClose }: { actor: DemoUser; title: string; onClose: () => void }) {
  const doc = useDocument(actor, title);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      back?.focus();
    };
  }, [onClose]);

  const hidden = doc.error instanceof ApiError && doc.error.status === 404;
  return (
    <div className="doc-backdrop fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Документ: ${title}`}
        onClick={(e) => e.stopPropagation()}
        className="doc-dialog flex max-h-[min(80vh,40rem)] w-[min(40rem,100%)] flex-col rounded-2xl border border-transparent bg-white text-left text-sm text-black shadow-xl ring-1 ring-black/10 dark:bg-neutral-900 dark:text-white dark:ring-white/10"
      >
        <div className="flex items-start gap-3 border-b border-black/10 px-5 py-4 dark:border-white/10">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-balance">{title}</h2>
            <p className="mt-0.5 text-xs text-black/55 dark:text-white/55">
              {doc.data ? (doc.data.team ? `Документ команды «${doc.data.team}»` : "Общий документ для всех команд") : "Документ"}
              {" "}· демо-данные, не регламент Авито
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="-mr-1.5 grid size-8 shrink-0 place-items-center rounded-full text-black/60 hover:bg-black/5 dark:text-white/65 dark:hover:bg-white/10"
          >
            <svg aria-hidden viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto overscroll-contain px-5 py-4 leading-relaxed">
          {doc.isPending && <p className="text-black/55 dark:text-white/55">Открываю документ…</p>}
          {hidden && <p>Документ недоступен: он не найден или относится к другой команде.</p>}
          {doc.isError && !hidden && <p>Не получилось открыть документ. Попробуй ещё раз чуть позже.</p>}
          {/* Первый заголовок «# …» повторяет название в шапке окна — не дублируем. */}
          {doc.data && <DocumentText text={doc.data.content.replace(/^\s*#\s[^\n]*\n/, "")} />}
        </div>
        <p className="border-t border-black/10 px-5 py-3 text-xs text-black/55 dark:border-white/10 dark:text-white/55">
          При внедрении здесь будет страница базы знаний команды (Confluence) — с её правами доступа.
        </p>
      </div>
    </div>
  );
}

/** Простой markdown демо-документов: заголовки «#», пункты «- », **жирный**; остальное — абзацы. */
export function DocumentText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`l${blocks.length}`} className="my-2 list-disc space-y-1 pl-5">
          {list.map((item, i) => <li key={i}>{bold(item)}</li>)}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of text.split(/\n\s*\n/)) {
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
    let paragraph: string[] = [];
    const endParagraph = () => {
      if (paragraph.length) blocks.push(<p key={`p${blocks.length}`} className="my-2">{bold(paragraph.join(" "))}</p>);
      paragraph = [];
    };
    for (const line of lines) {
      const heading = /^(#{1,3})\s+(.*)$/.exec(line);
      const item = /^(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
      if (heading) {
        endParagraph();
        flush();
        const Tag = heading[1].length === 1 ? "h3" : "h4";
        blocks.push(<Tag key={`h${blocks.length}`} className="mb-1 mt-4 font-semibold first:mt-0">{heading[2]}</Tag>);
      } else if (item) {
        endParagraph();
        list.push(item[1]);
      } else {
        flush();
        paragraph.push(line);
      }
    }
    endParagraph();
    flush();
  }
  return <>{blocks}</>;
}

function bold(text: string): ReactNode[] {
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : part));
}
