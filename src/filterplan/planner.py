"""Plan air filter changes from run hours instead of a fixed calendar."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta

COLUMNS = ("unit_id", "location", "filter_size", "qty", "interval_hours", "run_hours_per_week", "last_changed")


@dataclass(frozen=True)
class Unit:
    unit_id: str
    location: str
    filter_size: str
    qty: int
    interval_hours: float
    run_hours_per_week: float
    last_changed: date

    def hours_used(self, asof: date) -> float:
        """Run hours since the last change, estimated from weekly run hours."""
        return max(0, (asof - self.last_changed).days) / 7 * self.run_hours_per_week

    def due_date(self) -> date:
        """The date the filter reaches its interval, at the current weekly run hours."""
        weeks = self.interval_hours / self.run_hours_per_week
        return self.last_changed + timedelta(days=round(weeks * 7))


@dataclass(frozen=True)
class Line:
    unit: Unit
    due: date
    days_left: int
    percent_used: float
    status: str


def load_units(path: str) -> tuple[list[Unit], list[str]]:
    """Read the units CSV. Returns (units, problems); bad rows are left out and described."""
    units, problems, seen = [], [], set()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("missing column(s): " + ", ".join(missing))
        for n, row in enumerate(reader, start=2):
            uid = (row["unit_id"] or "").strip()
            if not uid:
                problems.append(f"row {n}: unit_id is empty")
                continue
            if uid.lower() in seen:
                problems.append(f"row {n}: duplicate unit_id '{uid}'")
                continue
            try:
                qty = int(row["qty"])
                interval = float(row["interval_hours"])
                weekly = float(row["run_hours_per_week"])
                changed = datetime.strptime(row["last_changed"].strip(), "%Y-%m-%d").date()
                if qty < 1 or interval <= 0 or weekly <= 0:
                    raise ValueError("values must be above zero")
            except (TypeError, ValueError, AttributeError) as exc:
                bad = next((c for c in ("qty", "interval_hours", "run_hours_per_week", "last_changed")
                            if not _ok(c, row[c])), None)
                what = f"{bad} '{row[bad]}'" if bad else str(exc)
                problems.append(f"row {n}: {uid}: invalid {what}")
                continue
            seen.add(uid.lower())
            units.append(Unit(uid, (row["location"] or "").strip(), (row["filter_size"] or "").strip(),
                              qty, interval, weekly, changed))
    return units, problems


def _ok(col: str, raw) -> bool:
    try:
        if col == "qty":
            return int(raw) >= 1
        if col == "last_changed":
            datetime.strptime(raw.strip(), "%Y-%m-%d")
            return True
        return float(raw) > 0
    except (TypeError, ValueError, AttributeError):
        return False


def plan(units: list[Unit], asof: date, soon_days: int = 30) -> list[Line]:
    """Return one line per unit sorted by due date. Status is OVERDUE, SOON (within soon_days) or ok."""
    lines = []
    for u in units:
        due = u.due_date()
        left = (due - asof).days
        status = "OVERDUE" if left < 0 else "SOON" if left <= soon_days else "ok"
        lines.append(Line(u, due, left, 100 * u.hours_used(asof) / u.interval_hours, status))
    return sorted(lines, key=lambda l: (l.due, l.unit.unit_id))


def order_list(units: list[Unit], asof: date, within_days: int = 60) -> dict[str, int]:
    """Filters to buy: total quantity per filter size for units due within `within_days` (overdue included)."""
    totals: dict[str, int] = {}
    for line in plan(units, asof, within_days):
        if line.days_left <= within_days:
            totals[line.unit.filter_size] = totals.get(line.unit.filter_size, 0) + line.unit.qty
    return dict(sorted(totals.items()))
