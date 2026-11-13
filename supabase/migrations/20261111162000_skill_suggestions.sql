BEGIN;
CREATE TABLE public.skill_suggestions (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    intern_id text NOT NULL REFERENCES public.intern_state(intern_id),
    mentor_id text NOT NULL,
    topic text NOT NULL,
    from_level text NOT NULL,
    to_level text NOT NULL,
    CHECK ((from_level='novice' AND to_level='familiar') OR (from_level='familiar' AND to_level='confident')),
    basis text NOT NULL,
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence)='array'),
    created_day integer NOT NULL CHECK (created_day>=1),
    status text NOT NULL CHECK (status IN ('pending','accepted','dismissed')),
    decided_day integer CHECK (decided_day>=1),
    CHECK ((status='pending') = (decided_day IS NULL))
);
CREATE UNIQUE INDEX skill_suggestions_one_pending ON public.skill_suggestions(intern_id,topic) WHERE status='pending';
ALTER TABLE public.skill_suggestions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.skill_suggestions FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.skill_suggestions_seq_seq FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.skill_suggestions FROM %I',r);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.skill_suggestions_seq_seq FROM %I',r);
        END IF;
    END LOOP;
END $$;
COMMIT;
