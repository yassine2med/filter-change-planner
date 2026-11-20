from datetime import date
from pathlib import Path

import pytest

from filterplan.__main__ import main
from filterplan.planner import Unit, load_units, order_list, plan

EX = Path(__file__).resolve().parent.parent / "examples"
GOOD = str(EX / "units.csv")
BAD = str(EX / "units_with_errors.csv")
ASOF = date(2026, 11, 20)


def unit(**kw):
    base = dict(unit_id="U", location="L", filter_size="20x20x2", qty=2, interval_hours=1000,
                run_hours_per_week=50, last_changed=date(2026, 1, 1))
    base.update(kw)
    return Unit(**base)


def test_load_sample():
    units, problems = load_units(GOOD)
    assert len(units) == 10 and problems == []


def test_load_reports_each_problem():
    units, problems = load_units(BAD)
    assert len(units) == 1
    assert any("duplicate unit_id 'AHU-01'" in p for p in problems)
    assert any("qty 'two'" in p for p in problems)
    assert any("run_hours_per_week '0'" in p for p in problems)
    assert any("last_changed '12/10/2026'" in p for p in problems)
    assert any("unit_id is empty" in p for p in problems)


def test_missing_column(tmp_path):
    f = tmp_path / "u.csv"
    f.write_text("unit_id,location\nA,b\n")
    with pytest.raises(ValueError, match="filter_size"):
        load_units(str(f))


def test_due_date_from_run_hours():
    # 1000 h at 50 h/week is 20 weeks = 140 days
    assert unit().due_date() == date(2026, 5, 21)


def test_more_run_hours_means_sooner():
    assert unit(run_hours_per_week=100).due_date() < unit(run_hours_per_week=50).due_date()


def test_hours_used_is_linear_and_never_negative():
    u = unit()
    assert u.hours_used(date(2026, 1, 8)) == 50
    assert u.hours_used(date(2025, 12, 1)) == 0


def test_status_overdue_soon_ok():
    u = unit()
    due = u.due_date()
    assert plan([u], due.replace(day=due.day + 1))[0].status == "OVERDUE"
    assert plan([u], date(2026, 5, 1))[0].status == "SOON"
    assert plan([u], date(2026, 3, 1))[0].status == "ok"


def test_percent_used_at_interval_is_100():
    u = unit()
    assert round(plan([u], u.due_date())[0].percent_used) == 100


def test_plan_sorted_by_due_date():
    units, _ = load_units(GOOD)
    dues = [l.due for l in plan(units, ASOF)]
    assert dues == sorted(dues)


def test_sample_has_overdue_and_soon():
    units, _ = load_units(GOOD)
    statuses = [l.status for l in plan(units, ASOF)]
    assert statuses.count("OVERDUE") == 3 and statuses.count("SOON") == 3


def test_order_list_sums_quantities():
    us = [unit(unit_id="A", qty=2), unit(unit_id="B", qty=3), unit(unit_id="C", filter_size="16x20x1", qty=1)]
    assert order_list(us, date(2026, 6, 1), 60) == {"16x20x1": 1, "20x20x2": 5}


def test_order_list_window_excludes_far_units():
    us = [unit(last_changed=date(2026, 11, 1))]
    assert order_list(us, ASOF, 30) == {}
    assert order_list(us, ASOF, 400) == {"20x20x2": 2}


def test_cli_plan_and_fail_overdue(capsys):
    assert main(["plan", GOOD, "--asof", "2026-11-20"]) == 0
    assert "OVERDUE" in capsys.readouterr().out
    assert main(["plan", GOOD, "--asof", "2026-11-20", "--fail-overdue"]) == 1


def test_cli_order_and_check(capsys):
    assert main(["order", GOOD, "--asof", "2026-11-20", "--within", "30"]) == 0
    assert "24x24x4" in capsys.readouterr().out
    assert main(["check", GOOD]) == 0
    assert main(["check", BAD]) == 1


def test_cli_errors():
    assert main(["plan", "nope.csv"]) == 2
    with pytest.raises(SystemExit):
        main(["plan", GOOD, "--asof", "20/11/2026"])
