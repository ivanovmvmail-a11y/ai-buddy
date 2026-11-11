-- Каталог и персональные пункты. Применяет владелец БД, не публичный клиент.
BEGIN;
CREATE TABLE public.personal_catalog (
    seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    key text PRIMARY KEY,
    team text NOT NULL,
    topic text NOT NULL,
    topic_title text NOT NULL,
    level text NOT NULL CHECK (level = 'novice'),
    title text NOT NULL,
    summary text NOT NULL,
    doc_source_id text NOT NULL,
    practice text NOT NULL,
    stage text NOT NULL CHECK (stage IN ('week1','week2')),
    due_offset integer NOT NULL CHECK (due_offset >= 1),
    UNIQUE(team, topic)
);
INSERT INTO public.personal_catalog (key, team, topic, topic_title, level, title, summary, doc_source_id, practice, stage, due_offset) VALUES
('platform.git', 'Платформа объявлений', 'git', 'Git', 'novice', 'Практикум: Git', 'демо-данные, не регламент Авито. Разбери учебный пример по теме Git.', 'demo:11-git-workflow.md', 'Создай учебную ветку, коммит и pull request.', 'week1', 7),
('platform.sql', 'Платформа объявлений', 'sql', 'SQL', 'novice', 'Практикум: SQL', 'демо-данные, не регламент Авито. Разбери учебный пример по теме SQL.', 'demo:06-platform-lifecycle.md', 'Составь запрос для подсчёта объектов по состояниям на синтетических данных.', 'week2', 14),
('platform.ci', 'Платформа объявлений', 'ci', 'CI', 'novice', 'Практикум: CI', 'демо-данные, не регламент Авито. Разбери учебный пример по теме CI.', 'demo:12-red-pipeline.md', 'Найди упавший шаг учебного пайплайна и опиши проверку исправления.', 'week1', 7),
('platform.testing', 'Платформа объявлений', 'testing', 'Тестирование', 'novice', 'Практикум: Тестирование', 'демо-данные, не регламент Авито. Разбери учебный пример по теме Тестирование.', 'demo:17-platform-sandbox-setup.md', 'Выполни smoke-тест песочницы и запиши ожидаемый результат.', 'week2', 14),
('delivery.git', 'Авито Доставка', 'git', 'Git', 'novice', 'Практикум: Git', 'демо-данные, не регламент Авито. Разбери учебный пример по теме Git.', 'demo:11-git-workflow.md', 'Создай учебную ветку, коммит и pull request.', 'week1', 7),
('delivery.sql', 'Авито Доставка', 'sql', 'SQL', 'novice', 'Практикум: SQL', 'демо-данные, не регламент Авито. Разбери учебный пример по теме SQL.', 'demo:09-delivery-statuses.md', 'Составь запрос для подсчёта объектов по состояниям на синтетических данных.', 'week2', 14),
('delivery.ci', 'Авито Доставка', 'ci', 'CI', 'novice', 'Практикум: CI', 'демо-данные, не регламент Авито. Разбери учебный пример по теме CI.', 'demo:12-red-pipeline.md', 'Найди упавший шаг учебного пайплайна и опиши проверку исправления.', 'week1', 7),
('delivery.testing', 'Авито Доставка', 'testing', 'Тестирование', 'novice', 'Практикум: Тестирование', 'демо-данные, не регламент Авито. Разбери учебный пример по теме Тестирование.', 'demo:20-delivery-sandbox-setup.md', 'Выполни smoke-тест песочницы и запиши ожидаемый результат.', 'week2', 14);
ALTER TABLE public.plan_items
    ADD COLUMN kind text NOT NULL DEFAULT 'common' CHECK (kind IN ('common','personal')),
    ADD COLUMN reason text,
    ADD COLUMN known_marked boolean NOT NULL DEFAULT false,
    ADD COLUMN catalog_key text REFERENCES public.personal_catalog(key);
ALTER TABLE public.reminders DROP CONSTRAINT reminders_plan_item_id_fkey;
ALTER TABLE public.reminders ADD CONSTRAINT reminders_plan_item_id_fkey
    FOREIGN KEY (plan_item_id) REFERENCES public.plan_items(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX plan_personal_catalog_once ON public.plan_items(intern_id, catalog_key)
    WHERE catalog_key IS NOT NULL;
-- Существующие общие пункты/статусы не меняются. Известные демо-профили
-- получают недостающие персональные пункты без reset; новых пользователей добавляет seed.
INSERT INTO public.plan_items (id, intern_id, kind, reason, catalog_key, topic, title,
    summary, doc_source_id, practice, stage, "order", owner_role, due_day, status, updated_at)
SELECT replace(p.intern_id, 'intern-', '') || '.p.' || c.topic, p.intern_id, 'personal',
    'в карте навыков ' || c.topic_title || ' — новичок', c.key, c.topic, c.title,
    c.summary, c.doc_source_id, c.practice, c.stage, 100, 'intern', c.due_offset,
    'not_started', p.updated_at
FROM public.skill_profiles p
JOIN public.personal_catalog c ON c.team = CASE
    WHEN p.intern_id IN ('intern-anya','intern-kirill') THEN 'Платформа объявлений'
    WHEN p.intern_id IN ('intern-ivan','intern-liza') THEN 'Авито Доставка' END
WHERE p.skills->>c.topic = c.level
ON CONFLICT DO NOTHING;
ALTER TABLE public.personal_catalog ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.personal_catalog FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.personal_catalog_seq_seq FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON public.personal_catalog, public.plan_items FROM %I', r);
            EXECUTE format('REVOKE ALL ON SEQUENCE public.personal_catalog_seq_seq FROM %I', r);
        END IF;
    END LOOP;
END $$;
COMMIT;
