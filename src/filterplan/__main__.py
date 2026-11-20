"""Command line: python -m filterplan plan|order|check UNITS.csv"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from .planner import load_units, order_list, plan


def _date(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a YYYY-MM-DD date")


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 when rows are invalid (check) or units are overdue (--fail-overdue), 2 on a bad file."""
    parser = argparse.ArgumentParser(prog="filterplan", description="Air filter change planner from run hours")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("plan", "schedule sorted by due date"), ("order", "filters to buy for units due soon"),
                       ("check", "list rows that cannot be used")):
        p = sub.add_parser(name, help=text)
        p.add_argument("file")
        if name != "check":
            p.add_argument("--asof", type=_date, default=date.today(), help="date to plan from (default today)")
        if name == "plan":
            p.add_argument("--soon", type=int, default=30, help="days ahead that count as SOON (default 30)")
            p.add_argument("--fail-overdue", action="store_true", help="exit 1 when any unit is overdue")
        if name == "order":
            p.add_argument("--within", type=int, default=60, help="days ahead to buy for (default 60)")
    args = parser.parse_args(argv)
    try:
        units, problems = load_units(args.file)
    except FileNotFoundError:
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    if args.command == "check":
        for p in problems:
            print(p)
        print(f"{len(units)} usable unit(s), {len(problems)} problem(s)")
        return 1 if problems else 0
    for p in problems:
        print(f"skipped {p}", file=sys.stderr)
    if args.command == "order":
        totals = order_list(units, args.asof, args.within)
        if not totals:
            print(f"Nothing due within {args.within} days of {args.asof}")
        for size, qty in totals.items():
            print(f"{size:<10} {qty:>3}")
        return 0
    lines = plan(units, args.asof, args.soon)
    print(f"{'unit':<8} {'location':<13} {'filter':<9} {'qty':>3} {'used':>5}  {'due':<10} {'days':>5}  status")
    for l in lines:
        u = l.unit
        print(f"{u.unit_id:<8} {u.location:<13} {u.filter_size:<9} {u.qty:>3} {l.percent_used:>4.0f}%  {l.due.isoformat():<10} {l.days_left:>5}  {l.status}")
    overdue = sum(1 for l in lines if l.status == "OVERDUE")
    print(f"{len(lines)} units, {overdue} overdue, {sum(1 for l in lines if l.status == 'SOON')} due soon")
    return 1 if (args.fail_overdue and overdue) else 0


if __name__ == "__main__":
    sys.exit(main())
