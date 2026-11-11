BEGIN;
CREATE TABLE public.service_drafts (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    id text PRIMARY KEY,
    owner_id text NOT NULL,
    action text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status text NOT NULL CHECK (status IN ('pending','confirmed','cancelled')),
    result_id text,
    CHECK (status <> 'confirmed' OR result_id IS NOT NULL)
);
ALTER TABLE public.service_drafts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.service_drafts FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.service_drafts_seq_seq FROM PUBLIC;
DO $$ DECLARE api_role text; BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
            EXECUTE format('REVOKE ALL ON public.service_drafts FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.service_drafts_seq_seq FROM %I', api_role);
        END IF;
    END LOOP;
END $$;
COMMIT;
