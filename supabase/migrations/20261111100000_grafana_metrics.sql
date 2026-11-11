-- Обезличенные представления для локальной демонстрационной панели Grafana.
-- Идемпотентно: выполняется также init-контейнером на существующем Docker volume.
BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_buddy_grafana') THEN
        CREATE ROLE ai_buddy_grafana NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END $$;
ALTER ROLE ai_buddy_grafana SET default_transaction_read_only = on;
DO $$ BEGIN
    IF to_regclass('public.events') IS NOT NULL THEN
        CREATE OR REPLACE VIEW public.grafana_answers AS
        SELECT ts, coalesce(payload->>'topic', 'other') AS topic,
            coalesce(payload->'with_source' = 'true'::jsonb, false) AS with_source,
            coalesce(payload->'not_in_base' = 'true'::jsonb, false) AS not_in_base,
            (NOT coalesce(payload->'refused' = 'true'::jsonb, false)
             AND NOT coalesce(payload->'not_in_base' = 'true'::jsonb, false)
             AND coalesce(payload->>'topic', 'other') <> 'hr'
             AND (coalesce(payload->'with_source' = 'true'::jsonb, false)
                  OR (jsonb_typeof(payload->'tools') = 'array' AND payload->'tools' <> '[]'::jsonb))) IS TRUE AS closed_without_human,
            CASE WHEN jsonb_typeof(payload->'latency_ms') = 'number'
                 THEN (payload->>'latency_ms')::double precision ELSE 0::double precision END AS latency_ms
        FROM public.events WHERE type = 'question_answered' AND payload->>'intern_id' IS NOT NULL;
        CREATE OR REPLACE VIEW public.grafana_feedback AS
        SELECT ts, coalesce(payload->'useful' = 'true'::jsonb, false) AS useful
        FROM public.events WHERE type = 'answer_feedback' AND payload->>'intern_id' IS NOT NULL;
    ELSE
        CREATE OR REPLACE VIEW public.grafana_answers AS
        SELECT NULL::timestamptz AS ts, NULL::text AS topic, false AS with_source,
            false AS not_in_base, false AS closed_without_human, 0::double precision AS latency_ms WHERE false;
        CREATE OR REPLACE VIEW public.grafana_feedback AS
        SELECT NULL::timestamptz AS ts, false AS useful WHERE false;
    END IF;
    IF to_regclass('public.plan_items') IS NOT NULL THEN
        CREATE OR REPLACE VIEW public.grafana_plan_progress AS
        SELECT stage, status, count(*) AS items FROM public.plan_items GROUP BY stage, status;
    ELSE
        CREATE OR REPLACE VIEW public.grafana_plan_progress AS
        SELECT NULL::text AS stage, NULL::text AS status, 0::bigint AS items WHERE false;
    END IF;
END $$;
REVOKE ALL ON public.grafana_answers, public.grafana_feedback, public.grafana_plan_progress FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ai_buddy_grafana;
GRANT SELECT ON public.grafana_answers, public.grafana_feedback, public.grafana_plan_progress TO ai_buddy_grafana;
COMMIT;
