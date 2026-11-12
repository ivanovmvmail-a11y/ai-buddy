BEGIN;
ALTER TABLE public.reminders ADD CONSTRAINT reminders_suggestion_id_fkey
    FOREIGN KEY (suggestion_id) REFERENCES public.skill_suggestions(id) ON DELETE SET NULL;
-- У старых напоминаний появляются действие и контекст дня стажёра.
UPDATE public.reminders r SET
    action = jsonb_build_object('label','Открыть','target',CASE WHEN r.request_id IS NOT NULL THEN 'access_request' ELSE 'plan_item' END),
    intern_id = COALESCE((SELECT i.intern_id FROM public.plan_items i WHERE i.id=r.plan_item_id),
                         (SELECT a.intern_id FROM public.access_requests a WHERE a.id=r.request_id))
WHERE r.action IS NULL AND r.kind IN ('plan_item','access_request');
COMMIT;
