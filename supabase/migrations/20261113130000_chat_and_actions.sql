-- SPEC §9: переписка с ботом и черновики действий переживают перезапуск backend (Claude, 13.11; задача из HANDOFF 11.11).
BEGIN;
CREATE TABLE IF NOT EXISTS public.chat_messages (
    seq bigserial PRIMARY KEY,
    id text NOT NULL UNIQUE,
    user_id text NOT NULL,
    role text NOT NULL CHECK (role IN ('user','assistant')),
    content text NOT NULL,
    sources jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(sources)='array'),
    answer_id text,
    scripted boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_user_idx ON public.chat_messages(user_id, seq);

CREATE TABLE IF NOT EXISTS public.agent_actions (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    tool text NOT NULL,
    title text NOT NULL,
    params jsonb NOT NULL CHECK (jsonb_typeof(params)='object'),
    status text NOT NULL CHECK (status IN ('pending','running','done','failed','cancelled')),
    result jsonb,
    error text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS agent_actions_user_idx ON public.agent_actions(user_id, created_at DESC);

-- Только backend: никаких прав у ролей публичного API Supabase (как у остальных таблиц онбординга).
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_actions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_messages, public.agent_actions FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.chat_messages_seq_seq FROM PUBLIC;
DO $$ DECLARE api_role text; BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
            EXECUTE format('REVOKE ALL ON public.chat_messages, public.agent_actions FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.chat_messages_seq_seq FROM %I', api_role);
        END IF;
    END LOOP;
END $$;
COMMIT;
