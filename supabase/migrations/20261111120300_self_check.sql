-- Личный разбор самопроверки; результаты не используются для оценки стажёра.
BEGIN;
CREATE TABLE public.self_check_attempts (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    intern_id text NOT NULL REFERENCES public.intern_state(intern_id),
    team text NOT NULL,
    topic text NOT NULL CHECK (topic IN ('git','sql','ci')),
    completed_day integer NOT NULL CHECK (completed_day>=1),
    review jsonb NOT NULL CHECK (jsonb_typeof(review)='array' AND jsonb_array_length(review) BETWEEN 2 AND 3)
);
ALTER TABLE public.self_check_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.self_check_attempts FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.self_check_attempts_seq_seq FROM PUBLIC;
DO $$ DECLARE api_role text; BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
            EXECUTE format('REVOKE ALL ON public.self_check_attempts FROM %I',api_role);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.self_check_attempts_seq_seq FROM %I',api_role);
        END IF;
    END LOOP;
END $$;
COMMIT;
