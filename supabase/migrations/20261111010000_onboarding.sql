-- Обычный PostgreSQL. Пользователи/права приложения проверяются сервисами backend;
-- доступ через публичные API БД запрещён. Никакие роли Supabase не создаются.
BEGIN;

CREATE TABLE public.intern_state (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    intern_id text PRIMARY KEY,
    start_date date NOT NULL,
    current_day integer NOT NULL CHECK (current_day >= 1)
);
CREATE TABLE public.access_resources (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    title text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('base', 'team_space')),
    team text,
    approver text NOT NULL CHECK (approver IN ('auto', 'mentor')),
    fields jsonb NOT NULL CHECK (jsonb_typeof(fields) = 'array')
);
CREATE TABLE public.plan_items (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    intern_id text NOT NULL REFERENCES public.intern_state(intern_id),
    stage text NOT NULL CHECK (stage IN ('week1','week2','month1','month2','after3m')),
    "order" integer NOT NULL CHECK ("order" >= 0),
    title text NOT NULL,
    summary text NOT NULL,
    owner_role text NOT NULL CHECK (owner_role IN ('intern','mentor','lead')),
    topic text,
    doc_source_id text,
    resource_id text REFERENCES public.access_resources(id),
    due_day integer CHECK (due_day >= 1),
    practice text,
    status text NOT NULL CHECK (status IN ('not_started','in_progress','waiting','done')),
    status_reason text,
    updated_at timestamptz NOT NULL,
    updated_by text,
    waiting_for text
);
CREATE INDEX plan_items_intern_idx ON public.plan_items(intern_id, stage, "order");
CREATE TABLE public.access_requests (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    intern_id text NOT NULL REFERENCES public.intern_state(intern_id),
    resource_id text NOT NULL REFERENCES public.access_resources(id),
    level text NOT NULL CHECK (level IN ('read','edit','admin')),
    justification text NOT NULL CHECK (btrim(justification) <> ''),
    status text NOT NULL CHECK (status IN ('created','pending_approval','granted','rejected')),
    approver_id text,
    reject_reason text,
    plan_item_id text REFERENCES public.plan_items(id),
    created_day integer NOT NULL CHECK (created_day >= 1),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX access_requests_one_active ON public.access_requests(intern_id, resource_id)
    WHERE status <> 'rejected';
CREATE TABLE public.skill_profiles (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    intern_id text PRIMARY KEY REFERENCES public.intern_state(intern_id),
    skills jsonb NOT NULL CHECK (jsonb_typeof(skills) = 'object'),
    strengths jsonb NOT NULL CHECK (jsonb_typeof(strengths) = 'array'),
    growth jsonb NOT NULL CHECK (jsonb_typeof(growth) = 'array'),
    updated_by text,
    updated_at timestamptz NOT NULL
);
CREATE TABLE public.reminders (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    user_id text NOT NULL,
    plan_item_id text UNIQUE REFERENCES public.plan_items(id),
    request_id text REFERENCES public.access_requests(id),
    text text NOT NULL,
    status text NOT NULL CHECK (status IN ('active','snoozed','done')),
    created_day integer NOT NULL CHECK (created_day >= 1),
    snooze_until_day integer CHECK (snooze_until_day >= 1)
);
CREATE INDEX reminders_user_idx ON public.reminders(user_id, status);
CREATE TABLE public.events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts timestamptz NOT NULL,
    user_id text NOT NULL,
    role text NOT NULL CHECK (role IN ('intern','mentor','lead','hrbp','curator','system')),
    team text NOT NULL,
    type text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object')
);
CREATE INDEX events_intern_order_idx ON public.events ((payload->>'intern_id'), id);

-- Даже случайный GRANT непривилегированному клиенту не открывает строки.
-- Владелец/доверенное backend-подключение обходит RLS; конечные пользователи SQL-доступа не имеют.
DO $$
DECLARE
    table_name text;
    api_role text;
    sequence_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['intern_state','access_resources','plan_items','access_requests','skill_profiles','reminders','events'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', table_name);
        sequence_name := pg_get_serial_sequence(format('public.%I', table_name), CASE WHEN table_name = 'events' THEN 'id' ELSE 'seq' END);
        EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC', sequence_name);
        FOREACH api_role IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', table_name, api_role);
                EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM %I', sequence_name, api_role);
            END IF;
        END LOOP;
    END LOOP;

END;
$$;
COMMIT;
