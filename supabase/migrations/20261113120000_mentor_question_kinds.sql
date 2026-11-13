-- «Память» (PR #45 + Claude 13.11): уведомления о вопросе наставнику и об ответе стажёру.
BEGIN;
ALTER TABLE public.reminders DROP CONSTRAINT reminders_kind_check;
ALTER TABLE public.reminders ADD CONSTRAINT reminders_kind_check CHECK (kind IN
    ('plan_item','access_request','skill_changed','personal_item_added','skill_suggestion',
     'absence_pending','absence_decided','absence_today','absence_new','absence_fact',
     'mentor_question','mentor_answer'));
COMMIT;
