"""Таблица 3.2: каждая роль/оба стажёра, прямые вызовы без агента и API."""
import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock, events, hiring
from app.mcp_server.errors import Forbidden, NotFound
from app.mcp_server.models import Reminder

run = async_runner.run


@pytest.mark.parametrize("actor_id", DEMO_USERS)
@pytest.mark.parametrize("target", ["intern-anya", "intern-ivan"])
def test_plan_and_summary_read_matrix(store, actor_id, target):
    allowed = {"intern-anya": {"intern-anya", "mentor-petr", "lead-olga", "curator-dmitry"},
               "intern-ivan": {"intern-ivan", "mentor-maria", "lead-sergey", "curator-dmitry"}}
    actor = DEMO_USERS[actor_id]
    for operation in (lambda: checklist.get_plan(actor, target), lambda: checklist.weekly_summary(actor, target, 1)):
        if actor_id in allowed[target]:
            result = run(operation())
            if hasattr(result, "next_step") and result.next_step.item:
                assert result.next_step.item.owner_role == actor.role
        else:
            with pytest.raises(NotFound):
                run(operation())


@pytest.mark.parametrize("actor_id", DEMO_USERS)
@pytest.mark.parametrize("target", ["intern-anya", "intern-ivan"])
def test_private_read_and_profile_write_matrix(store, actor_id, target):
    mentor = {"intern-anya": "mentor-petr", "intern-ivan": "mentor-maria"}[target]
    actor = DEMO_USERS[actor_id]
    for operation in (lambda: hiring.get_skill_profile(actor, target), lambda: access.list_requests(actor, target)):
        if actor_id in {target, mentor}:
            run(operation())
        else:
            with pytest.raises(NotFound):
                run(operation())
    if actor_id == mentor:
        assert run(hiring.set_skill_level(actor, target, "git", "familiar")).updated_by == actor.id
    else:
        with pytest.raises(Forbidden if actor_id == target else NotFound):
            run(hiring.set_skill_level(actor, target, "git", "familiar"))


@pytest.mark.parametrize("actor_id", DEMO_USERS)
@pytest.mark.parametrize("item,owner", [("w1.notes", "intern-anya"), ("w1.channels", "mentor-petr"), ("w1.goals", "lead-olga")])
def test_manual_status_owner_matrix(store, actor_id, item, owner):
    actor = DEMO_USERS[actor_id]
    visible = {"intern-anya", "mentor-petr", "lead-olga", "curator-dmitry"}
    if actor_id == owner:
        assert run(checklist.set_item_status(actor, f"anya.{item}", "done")).status == "done"
    else:
        # Наставник может только вернуть уже закрытый пункт стажёра, не выполнить его.
        from app.mcp_server.errors import Conflict
        error = Conflict if actor_id == "mentor-petr" and item == "w1.notes" else (Forbidden if actor_id in visible else NotFound)
        with pytest.raises(error):
            run(checklist.set_item_status(actor, f"anya.{item}", "done"))


@pytest.mark.parametrize("actor_id", DEMO_USERS)
def test_resource_create_and_list_matrix(store, actor_id):
    actor = DEMO_USERS[actor_id]
    if actor.role == "intern":
        resources = run(access.list_resources(actor))
        own = "bitbucket-platform" if actor.team == "Платформа объявлений" else "bitbucket-delivery"
        assert {resource.id for resource in resources} == {"jira", "confluence", own}
        resource = "confluence" if actor.team == "Платформа объявлений" else "bitbucket-platform"
        if actor.team == "Платформа объявлений":
            assert run(access.create_request(actor, resource, "read", "Учебная задача")).intern_id == actor_id
        else:
            with pytest.raises(NotFound):
                run(access.create_request(actor, resource, "read", "Учебная задача"))
    else:
        for operation in (lambda: access.list_resources(actor), lambda: access.create_request(actor, "jira", "read", "Учебная задача")):
            with pytest.raises(Forbidden):
                run(operation())


@pytest.mark.parametrize("actor_id", DEMO_USERS)
def test_only_actual_approver_decides(store, actor_id):
    actor = DEMO_USERS[actor_id]
    if actor_id == "mentor-maria":
        assert run(access.decide_request(actor, "REQ-1001", True)).status == "granted"
    else:
        with pytest.raises(Forbidden if actor_id == "intern-ivan" else NotFound):
            run(access.decide_request(actor, "REQ-1001", True))


@pytest.mark.parametrize("actor_id", DEMO_USERS)
def test_demo_clock_all_roles_and_system_only_operations(store, actor_id):
    actor = DEMO_USERS[actor_id]
    assert run(clock.get_day(actor, "intern-anya")) == 2
    assert run(clock.advance_day(actor, "intern-anya")) == {"intern-anya": 3}
    run(clock.reset_demo(actor))
    assert run(clock.get_day(actor, "intern-anya")) == 2
    for operation in (lambda: clock.cron_tick(actor, 10), lambda: events.log_event(actor, "forged", {}), lambda: events.list_events(actor)):
        with pytest.raises(Forbidden):
            run(operation())


@pytest.mark.parametrize("actor_id", DEMO_USERS)
def test_reminders_are_owner_only(store, edit, actor_id):
    actor = DEMO_USERS[actor_id]
    edit(lambda data: data.reminders.update({"own": Reminder(id="own", user_id=actor.id, text="Учебное напоминание", created_day=1),
        "foreign": Reminder(id="foreign", user_id="intern-ivan" if actor_id != "intern-ivan" else "intern-anya", text="Чужой текст", created_day=1)}))
    assert {reminder.id for reminder in run(clock.list_reminders(actor))} == {"own"}
    assert run(clock.snooze_reminder(actor, "own")).status == "snoozed"
    assert run(clock.done_reminder(actor, "own")).status == "done"
    for id in ("foreign", "missing"):
        for operation in (lambda: clock.snooze_reminder(actor, id), lambda: clock.done_reminder(actor, id)):
            with pytest.raises(NotFound) as error:
                run(operation())
            assert str(error.value) == "Не найдено"


def test_forged_actor_is_not_accepted(store):
    actor = DEMO_USERS["intern-anya"].model_copy(update={"role": "curator"})
    for operation in (lambda: checklist.get_plan(actor, "intern-ivan"), lambda: access.list_resources(actor),
                      lambda: clock.advance_day(actor), lambda: clock.reset_demo(actor)):
        with pytest.raises(NotFound):
            run(operation())
