-- Default privileges Supabase могут выдавать прямые grants на public-представления.
-- REVOKE FROM PUBLIC их не снимает; права выделенного datasource сохраняются.
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE public.grafana_answers, public.grafana_feedback,
            public.grafana_plan_progress FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE public.grafana_answers, public.grafana_feedback,
            public.grafana_plan_progress FROM authenticated;
    END IF;
END;
$$;
COMMIT;
