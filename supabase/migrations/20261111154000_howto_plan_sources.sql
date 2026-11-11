-- S2: исправить только известные ссылки демо-плана, не сбрасывая прогресс.
BEGIN;
DO $$ BEGIN
    IF to_regclass('public.plan_items') IS NOT NULL THEN
        UPDATE public.plan_items AS item
        SET doc_source_id = patch.new_source
        FROM (VALUES
            ('anya.w1.team-space', 'intern-anya', 'demo:05-platform-sandbox.md', 'demo:13-team-space-access.md'),
            ('ivan.w1.team-space', 'intern-ivan', 'demo:08-delivery-sandbox.md', 'demo:13-team-space-access.md'),
            ('anya.w1.sandbox', 'intern-anya', 'demo:05-platform-sandbox.md', 'demo:17-platform-sandbox-setup.md'),
            ('ivan.w1.sandbox', 'intern-ivan', 'demo:08-delivery-sandbox.md', 'demo:20-delivery-sandbox-setup.md')
        ) AS patch(item_id, intern_id, old_source, new_source)
        WHERE item.id = patch.item_id
          AND item.intern_id = patch.intern_id
          AND item.doc_source_id = patch.old_source;
    END IF;
END $$;
COMMIT;
