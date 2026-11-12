-- Дополняем каталог существующего демо, не сбрасывая планы, заявки и события.
-- На пустой БД ничего не вставляем: полный seed заполняет её при старте.
-- RLS/ACL существующей access_resources остаются прежними.
BEGIN;
INSERT INTO public.access_resources (id, title, kind, team, approver, fields)
SELECT resource.id, resource.title, 'base', NULL, 'auto', jira.fields
FROM (VALUES ('redash', 'Учебный Redash'), ('grafana', 'Учебная Grafana')) AS resource(id, title)
CROSS JOIN public.access_resources AS jira
WHERE jira.id = 'jira' AND EXISTS (SELECT 1 FROM public.intern_state)
ON CONFLICT (id) DO NOTHING;
COMMIT;
