-- Совместимо с чистым PostgreSQL + pgvector; роли Supabase не используются.
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
-- У уже созданного расширения в Supabase схема может быть extensions.
SET LOCAL search_path = public, extensions;

CREATE TABLE public.rag_documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id text NOT NULL UNIQUE CHECK (btrim(source_id) <> ''),
    title text NOT NULL CHECK (btrim(title) <> ''),
    url text,
    content text NOT NULL CHECK (btrim(content) <> ''),
    team text CHECK (team IS NULL OR btrim(team) <> '')
);

CREATE TABLE public.rag_chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES public.rag_documents(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL CHECK (btrim(content) <> ''),
    embedding vector(1024) NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX rag_documents_team_idx ON public.rag_documents (team);
-- Точный cosine-поиск по доступным фрагментам: без ANN-потерь после фильтра команды.

ALTER TABLE public.rag_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY rag_documents_read ON public.rag_documents FOR SELECT
    USING (team IS NULL OR team = nullif(current_setting('app.rag_team', true), ''));

CREATE POLICY rag_chunks_read ON public.rag_chunks FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM public.rag_documents AS d
        WHERE d.id = document_id
          AND (d.team IS NULL OR d.team = nullif(current_setting('app.rag_team', true), ''))
    ));

-- Загрузчик — владелец таблиц. Для отдельного читателя DBA выдаёт SELECT;
-- без контекста команды RLS даёт ему только общие документы, запись запрещена.
-- Владелец и суперпользователь обходят RLS: retrieve всегда добавляет явный WHERE.
COMMIT;
