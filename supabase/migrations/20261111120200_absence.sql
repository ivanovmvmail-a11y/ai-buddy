-- Имитация отгула на один день, не кадровая система и не медицинские данные.
BEGIN;
CREATE TABLE public.absence_requests (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    intern_id text NOT NULL REFERENCES public.intern_state(intern_id),
    lead_id text NOT NULL,
    team text NOT NULL,
    day date NOT NULL,
    reason text NOT NULL CHECK (reason IN ('personal','family','study')),
    created_day integer NOT NULL CHECK (created_day>=1),
    status text NOT NULL CHECK (status IN ('pending','approved','rejected')),
    decided_day integer CHECK (decided_day>=1),
    CHECK (status='pending' OR decided_day IS NOT NULL)
);
CREATE UNIQUE INDEX absence_one_day_idx ON public.absence_requests(intern_id,day) WHERE status<>'rejected';
ALTER TABLE public.absence_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.absence_requests FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.absence_requests_seq_seq FROM PUBLIC;
DO $$ DECLARE api_role text; BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
            EXECUTE format('REVOKE ALL ON public.absence_requests FROM %I',api_role);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.absence_requests_seq_seq FROM %I',api_role);
        END IF;
    END LOOP;
END $$;
COMMIT;
