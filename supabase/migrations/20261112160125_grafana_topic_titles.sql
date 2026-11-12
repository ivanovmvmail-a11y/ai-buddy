-- Русские названия тем; имена/типы колонок и формула метрик сохранены.
-- Повторное применение безопасно; исходные events и их payload не меняются.
BEGIN;
DO $$ BEGIN
    IF to_regclass('public.events') IS NOT NULL THEN
        CREATE OR REPLACE VIEW public.grafana_answers AS
        SELECT ts, CASE payload->>'topic'
                WHEN 'hr' THEN 'орг. вопросы (HR)'
                WHEN 'access' THEN 'доступы'
                WHEN 'git' THEN 'git и ревью'
                WHEN 'environment' THEN 'окружение и запуск'
                WHEN 'tasks' THEN 'задачи'
                WHEN 'plan' THEN 'план'
                WHEN 'people' THEN 'к кому идти'
                ELSE 'другое'
            END AS topic,
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
    ELSE
        CREATE OR REPLACE VIEW public.grafana_answers AS
        SELECT NULL::timestamptz AS ts, NULL::text AS topic, false AS with_source,
            false AS not_in_base, false AS closed_without_human, 0::double precision AS latency_ms WHERE false;
    END IF;
END $$;
COMMENT ON VIEW public.grafana_answers IS NULL;
REVOKE ALL ON public.grafana_answers FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.grafana_answers FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.grafana_answers FROM authenticated;
    END IF;
END $$;
GRANT SELECT ON public.grafana_answers TO ai_buddy_grafana;
COMMIT;
