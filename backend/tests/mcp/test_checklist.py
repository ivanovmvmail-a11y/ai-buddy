"""AC-1…AC-11: прикладная логика T1; сохранение после перезапуска — T3."""
import pytest
from pydantic import ValidationError

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock
from app.mcp_server.errors import Conflict, Forbidden, NotFound

run = async_runner.run
ANYA = DEMO_USERS["intern-anya"]
IVAN = DEMO_USERS["intern-ivan"]
PETR = DEMO_USERS["mentor-petr"]


def test_ac1_working_items_and_inert_outlines(store):
    plan = run(checklist.get_plan(ANYA, ANYA.id))
    working = [item for item in plan.items if item.stage in {"week1", "week2"}]
    assert len(working) == 10
    assert plan.current_day == 2
    assert plan.ladder[0].total == 10 and plan.ladder[0].done == 1
    assert plan.next_step.item.id == "anya.w1.access-base"
    assert [stage.title for stage in plan.ladder] == ["Недели 1–2", "Месяц 1", "Месяц 2", "После 3 месяцев"]
    assert [stage.state for stage in plan.ladder] == ["current", "ahead", "ahead", "ahead"]
    for item in plan.items:
        assert "демо-данные, не регламент Авито" in item.summary
        if item.stage not in {"week1", "week2"}:
            assert item.practice is None and item.resource_id is None
            with pytest.raises(Forbidden):
                run(checklist.set_item_status(ANYA, item.id, "done"))


def test_ac2_common_skeleton_and_team_items(store):
    anya = run(checklist.get_plan(ANYA, ANYA.id))
    ivan = run(checklist.get_plan(IVAN, IVAN.id))
    a = {item.id.split(".", 1)[1]: item for item in anya.items}
    b = {item.id.split(".", 1)[1]: item for item in ivan.items}
    assert a.keys() == b.keys()
    differing = {key for key in a if a[key].title != b[key].title}
    assert differing == {"w1.team-space", "w1.sandbox", "w2.docs"}
    assert a["w1.team-space"].resource_id == "bitbucket-platform"
    assert b["w1.team-space"].resource_id == "bitbucket-delivery"
    assert a["w1.notes"].practice == b["w1.notes"].practice


def test_ac3_overdue_is_next_and_computed(store, snapshot):
    plan = run(checklist.get_plan(IVAN, IVAN.id))
    assert plan.current_day == 8
    assert plan.next_step.item.id == "ivan.w1.notes"
    assert plan.next_step.item.overdue and plan.next_step.item.due_day == 5
    assert not snapshot().items["ivan.w1.notes"].overdue
    waiting = next(item for item in plan.next_step.waiting if item.id == "ivan.w1.team-space")
    assert waiting.waiting_for == "mentor-maria" and waiting.waiting_days == 3


def test_ac4_only_waiting_means_no_own_step(store, edit):
    def waiting(data):
        for item in data.items.values():
            if item.intern_id == ANYA.id and item.owner_role == "intern" and item.stage in {"week1", "week2"}:
                item.status = "waiting"
                item.waiting_for = PETR.id
    edit(waiting)
    plan = run(checklist.get_plan(ANYA, ANYA.id))
    assert plan.next_step.item is None
    assert plan.next_step.waiting and all(item.waiting_for == PETR.id for item in plan.next_step.waiting)
    assert all(item.waiting_days == 1 for item in plan.next_step.waiting)


def test_ac5_status_survives_service_calls_in_same_store(store, snapshot):
    result = run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    assert result.status == "done" and result.updated_by == ANYA.id
    assert snapshot().items[result.id].status == "done"
    assert next(item for item in run(checklist.get_plan(PETR, ANYA.id)).items if item.id == result.id).status == "done"
    # Возвращаемый объект не даёт изменить сохранённые данные в обход сервиса.
    result.status = "not_started"
    assert snapshot().items[result.id].status == "done"


@pytest.mark.parametrize("item_id", ["anya.w1.channels", "anya.w1.one-to-one", "anya.w1.goals", "anya.w1.access-base", "anya.w1.team-space"])
def test_ac6_intern_cannot_change_other_owner_or_service(store, snapshot, item_id):
    before = snapshot()
    with pytest.raises(Forbidden):
        run(checklist.set_item_status(ANYA, item_id, "done"))
    assert snapshot() == before


@pytest.mark.parametrize("reason", [None, "", " \n "])
def test_ac7_mentor_return_requires_reason(store, snapshot, reason):
    before = snapshot()
    with pytest.raises(ValidationError):
        run(checklist.set_item_status(PETR, "anya.w1.meet-team", "in_progress", reason))
    assert snapshot() == before


def test_ac7_mentor_returns_with_visible_reason(store):
    result = run(checklist.set_item_status(PETR, "anya.w1.meet-team", "in_progress", "  Уточни, кто поможет с доступами  "))
    assert result.status_reason == "Уточни, кто поможет с доступами"
    seen = run(checklist.get_plan(ANYA, ANYA.id)).items[0]
    assert seen.status == "in_progress" and seen.status_reason == result.status_reason


@pytest.mark.parametrize("viewer", ["intern-ivan", "mentor-maria", "lead-sergey", "hrbp-elena"])
def test_ac8_foreign_plan_looks_missing(store, snapshot, viewer):
    before = snapshot()
    messages = []
    for target in (ANYA.id, "intern-missing"):
        with pytest.raises(NotFound) as error:
            run(checklist.get_plan(DEMO_USERS[viewer], target))
        messages.append(str(error.value))
    assert messages == ["Не найдено", "Не найдено"]
    assert snapshot() == before


def test_ac9_curator_read_only(store):
    actor = DEMO_USERS["curator-dmitry"]
    for target in (ANYA.id, IVAN.id):
        plan = run(checklist.get_plan(actor, target))
        assert plan.next_step.item is None
        with pytest.raises(Forbidden):
            run(checklist.set_item_status(actor, plan.items[0].id, "done"))


def test_ac10_ladder_progress_and_remaining_count(store, edit):
    edit(lambda data: [setattr(item, "status", "done") for item in data.items.values()
                       if item.intern_id == ANYA.id and item.stage in {"week1", "week2"}])
    plan = run(checklist.get_plan(ANYA, ANYA.id))
    assert plan.ladder[0].state == "passed"
    assert plan.ladder[0].total - plan.ladder[0].done == 0
    assert plan.ladder[1].state == "current"
    assert plan.ladder[1].total - plan.ladder[1].done == 2
    assert plan.next_step.item is None


def test_ac11_advance_and_reset_restore_initial_states(store, snapshot):
    initial = snapshot()
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    assert run(clock.advance_day(ANYA)) == {ANYA.id: 3, IVAN.id: 9}
    assert run(clock.advance_day(ANYA, ANYA.id)) == {ANYA.id: 4}
    plan = run(checklist.get_plan(ANYA, ANYA.id))
    assert next(item for item in plan.items if item.id == "anya.w1.access-base").overdue
    assert snapshot().reminders
    run(clock.reset_demo(ANYA))
    restored = snapshot()
    assert restored.interns == initial.interns
    assert restored.items == initial.items and restored.requests == initial.requests
    assert restored.profiles == initial.profiles and restored.reminders == {}
    assert restored.events[-1].type == "demo_reset"


def test_weekly_summary_uses_events_without_ratings(store):
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    request = run(access.create_request(ANYA, "jira", "read", "Для учебной задачи"))
    summary = run(checklist.weekly_summary(PETR, ANYA.id, 1))
    assert "anya.w1.notes" in {fact["item_id"] for fact in summary["closed"]}
    assert request.id in {fact["request_id"] for fact in summary["access_granted"]}
    assert all(item.stage == "week1" and item.status != "done" for item in summary["carry_over"])
    assert "rating" not in summary and "score" not in summary
    assert all(fact["intern_id"] == ANYA.id for fact in summary["closed"])
    with pytest.raises(ValidationError):
        run(checklist.weekly_summary(ANYA, ANYA.id, 0))


def test_status_validation_and_conflicts_are_atomic(store, snapshot):
    before = snapshot()
    for status, error in [("unknown", ValidationError), ("waiting", Conflict), ("not_started", Conflict)]:
        with pytest.raises(error):
            run(checklist.set_item_status(PETR, "anya.w1.meet-team", status, "причина"))
        assert snapshot() == before
    with pytest.raises(Conflict):
        run(checklist.set_item_status(PETR, "anya.w1.notes", "in_progress", "причина"))
    result = run(checklist.set_item_status(ANYA, "anya.w1.notes", "waiting"))
    assert result.waiting_for == PETR.id and result.waiting_days == 0
    current = snapshot()
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "waiting"))
    assert snapshot() == current
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "in_progress"))
    assert snapshot().items["anya.w1.notes"].waiting_for is None
