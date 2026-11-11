"""Золотой набор в CI: сценарный режим без ключей должен проходить весь набор и не давать утечек."""
from golden.run import check, report, run_cases, summary


def test_golden_set_scenario_mode():
    results = run_cases("scenario")
    s = summary(results)
    failed = [(r.case["id"], r.notes) for r in results if not r.passed]
    assert s["leaks"] == 0
    assert not failed, failed
    assert "Отчёт золотого набора" in report(results, "scenario")


def test_checker_catches_failures():
    leak = check({"expect": {"no_leak": ["Сосна"]}}, "Маршрут через Сосна", [], [], 0)
    assert leak == (False, True, ["утечка: «Сосна»"])
    ok, _, notes = check({"expect": {"source": "Глоссарий"}}, "В документах команды этого нет", ["Другое"], [], 0)
    assert not ok and len(notes) == 2
    ok, _, notes = check({"expect": {"draft": {"tool": "create_access_request", "resource_id": "jira"}}}, "", [], [], 1)
    assert not ok and "заявка создана без подтверждения" in notes
    ok, _, _ = check({"expect": {"no_draft": True}}, "", [], [{"tool": "x"}], 0)
    assert not ok
    ok, _, notes = check({"expect": {"refusal": True, "hr": True, "not_in_base": True, "contains": ["x"],
                                     "contains_any": ["y"], "no_refusal": False}}, "ответ", [], [], 0)
    assert not ok and len(notes) == 6
