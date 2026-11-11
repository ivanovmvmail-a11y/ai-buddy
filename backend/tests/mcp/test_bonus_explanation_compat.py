"""Совместимость бонусного backend с объяснениями из обновлённого main.

Профиль может быть недоступен роли, а документ/практика — отсутствовать: ответ
не должен расширять права или придумывать отсутствующую инструкцию.
"""
from app import async_runner
from app.agent import explain
from app.agent.users import DEMO_USERS
run=async_runner.run
ANYA='intern-anya'
ITEM='anya.w1.notes'


def configure(edit, *, document=True, practice=None, level='novice'):
    def change(data):
        item=data.items[ITEM]
        item.doc_source_id='demo:02-code-review.md' if document else None
        item.practice=practice
        data.profiles[ANYA].skills['git']=level
    edit(change)


def test_lead_explains_without_permission_to_private_skill_profile(store,edit):
    configure(edit)
    result=run(explain.explain_item(DEMO_USERS['lead-olga'],ANYA,ITEM,'explain'))
    assert result['with_source'] and result['source']['title']=='Регламент учебного код-ревью'
    assert 'Разберём подробно' not in result['text'] and 'уверенно' not in result['text']
    assert 'Задание на практике' not in result['text']


def test_familiar_level_gets_short_document_explanation(store,edit):
    configure(edit,level='familiar')
    result=run(explain.explain_item(DEMO_USERS[ANYA],ANYA,ITEM,'explain'))
    assert result['with_source'] and 'Коротко по разделу' in result['text']


def test_missing_document_and_practice_do_not_invent_instructions(store,edit):
    configure(edit,document=False)
    result=run(explain.explain_item(DEMO_USERS[ANYA],ANYA,ITEM,'explain'))
    assert not result['with_source'] and result['source'] is None
    assert 'Из раздела' not in result['text'] and 'Задание на практике' not in result['text']
    steps=run(explain.explain_item(DEMO_USERS[ANYA],ANYA,ITEM,'steps'))
    assert not steps['with_source'] and 'выдумывать не буду' in steps['text']


def test_document_steps_without_practice_keep_only_document_steps(store,edit):
    configure(edit)
    result=run(explain.explain_item(DEMO_USERS[ANYA],ANYA,ITEM,'steps'))
    assert result['with_source'] and '\n1. ' in result['text']
    assert 'Проверь себя на практике' not in result['text']


def test_waiting_question_and_missing_route_document_use_own_mentor(store,snapshot,monkeypatch):
    item=next(i for i in snapshot().items.values() if i.intern_id=='intern-ivan' and i.status=='waiting')
    original=explain.load_doc
    monkeypatch.setattr(explain,'load_doc',lambda source: None if source==explain.WHO_DOC else original(source))
    result=run(explain.explain_item(DEMO_USERS['intern-ivan'],'intern-ivan',item.id,'who'))
    assert 'Сейчас пункт ждёт: Мария Орлова' in result['text'] and 'Пётр Волков' not in result['text']
    assert not result['with_source'] and result['source'] is None
