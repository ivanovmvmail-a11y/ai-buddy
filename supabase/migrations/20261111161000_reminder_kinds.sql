BEGIN;
ALTER TABLE public.reminders
    ADD COLUMN kind text,
    ADD COLUMN action jsonb,
    ADD COLUMN intern_id text REFERENCES public.intern_state(intern_id),
    ADD COLUMN absence_request_id text REFERENCES public.absence_requests(id),
    ADD COLUMN suggestion_id text;
UPDATE public.reminders SET kind = CASE WHEN request_id IS NOT NULL THEN 'access_request' ELSE 'plan_item' END;
ALTER TABLE public.reminders ALTER COLUMN kind SET NOT NULL;
ALTER TABLE public.reminders ALTER COLUMN kind SET DEFAULT 'plan_item';
ALTER TABLE public.reminders ADD CONSTRAINT reminders_kind_check CHECK (kind IN
    ('plan_item','access_request','skill_changed','personal_item_added','skill_suggestion',
     'absence_pending','absence_decided','absence_today','absence_new','absence_fact'));
ALTER TABLE public.reminders ADD CONSTRAINT reminders_action_check CHECK (action IS NULL OR jsonb_typeof(action)='object');
ALTER TABLE public.reminders DROP CONSTRAINT reminders_plan_item_id_key;
CREATE UNIQUE INDEX reminders_one_item_kind ON public.reminders(kind, plan_item_id) WHERE plan_item_id IS NOT NULL;
ALTER TABLE public.reminders ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reminders FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.reminders_seq_seq FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.reminders FROM %I',r);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.reminders_seq_seq FROM %I',r);
        END IF;
    END LOOP;
END $$;
COMMIT;
