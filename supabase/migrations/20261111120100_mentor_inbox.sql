BEGIN;
CREATE TABLE public.mentor_questions (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    intern_id text NOT NULL REFERENCES public.intern_state(intern_id),
    mentor_id text NOT NULL,
    team text NOT NULL,
    question text NOT NULL CHECK (length(btrim(question)) BETWEEN 1 AND 3000),
    created_day integer NOT NULL CHECK (created_day >= 1),
    status text NOT NULL CHECK (status IN ('pending','answered')),
    answer text CHECK (length(btrim(answer)) BETWEEN 1 AND 6000),
    answered_day integer CHECK (answered_day >= 1),
    answered_at timestamptz,
    publication_status text NOT NULL CHECK (publication_status IN ('not_requested','pending','published')),
    public_content text,
    source_id text UNIQUE,
    CHECK (status <> 'answered' OR (answer IS NOT NULL AND answered_day IS NOT NULL AND answered_at IS NOT NULL)),
    CHECK (publication_status = 'not_requested' OR (status='answered' AND public_content IS NOT NULL AND source_id IS NOT NULL))
);
CREATE INDEX mentor_questions_inbox_idx ON public.mentor_questions(mentor_id,status,seq);
ALTER TABLE public.reminders ADD COLUMN mentor_question_id text UNIQUE REFERENCES public.mentor_questions(id) ON DELETE CASCADE;
ALTER TABLE public.mentor_questions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.mentor_questions FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.mentor_questions_seq_seq FROM PUBLIC;
DO $$ DECLARE api_role text; BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
            EXECUTE format('REVOKE ALL ON public.mentor_questions FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.mentor_questions_seq_seq FROM %I', api_role);
        END IF;
    END LOOP;
END $$;
COMMIT;
