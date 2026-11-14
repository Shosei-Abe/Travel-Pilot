"""Manual edits to an itinerary: times, places, costs. Pure functions, no Streamlit."""

import copy
import math
import re

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
CATEGORIES = ["food", "cafe", "sightseeing", "nature", "shopping", "nightlife", "other"]


def _minutes(t) -> int | None:
    m = TIME_RE.match(str(t or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def end_time(a: dict) -> str:
    start, dur = _minutes(a.get("time")), a.get("duration_minutes")
    return _hhmm(start + int(dur)) if start is not None and dur else ""


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() == ""


def _editable(a: dict) -> tuple:
    """The fields a user can change in the table, normalised the same way the table shows them."""
    return (a.get("place", ""), a.get("time", ""), end_time(a), a.get("category") or "other",
            a.get("description") or "", a.get("estimated_cost"))


def day_rows(day: dict) -> list[dict]:
    """Editable table rows for one day. `id` links a row back to its original activity."""
    return [
        {"id": i, "Start": a.get("time", ""), "End": end_time(a), "Place": a.get("place", ""),
         "Category": a.get("category", "other"),
         "Cost": a.get("estimated_cost"), "Note": a.get("description", "")}
        for i, a in enumerate(day.get("activities", []))
    ]


def apply_day_edits(plan: dict, day_index: int, rows: list[dict]) -> tuple[dict, list[str]]:
    """Return (new plan, errors). On any error the plan is returned unchanged."""
    errors = []
    old_acts = plan["days"][day_index].get("activities", [])
    new_acts = []

    for n, row in enumerate(rows, 1):
        place = "" if _blank(row.get("Place")) else str(row["Place"]).strip()
        if not place:
            continue  # empty row = deleted / never filled
        start, end = _minutes(row.get("Start")), _minutes(row.get("End"))
        if start is None:
            errors.append(f"Row {n} ({place}): start time must be HH:MM")
            continue
        if not _blank(row.get("End")) and end is None:
            errors.append(f"Row {n} ({place}): end time must be HH:MM")
            continue
        if end is not None and end <= start:
            errors.append(f"Row {n} ({place}): end time must be after start time")
            continue

        rid = row.get("id")
        orig = None if _blank(rid) else old_acts[int(rid)] if 0 <= int(rid) < len(old_acts) else None
        a = copy.deepcopy(orig) if orig else {
            "source_url": None, "unverified": True, "cost_verified": False, "opening_hours": None,
        }
        changed_place = orig is None or place != orig.get("place")
        a["place"] = place
        a["time"] = _hhmm(start)
        a["duration_minutes"] = (end - start) if end is not None else a.get("duration_minutes")
        cat = str(row.get("Category") or "other")
        a["category"] = cat if cat in CATEGORIES else "other"
        a["description"] = "" if _blank(row.get("Note")) else str(row["Note"])

        cost = None if _blank(row.get("Cost")) else float(row["Cost"])
        if orig is None or cost != orig.get("estimated_cost"):
            a["cost_verified"] = False  # a price the user typed is not from a source
        a["estimated_cost"] = cost

        if changed_place:
            # The old citation described a different place; never carry it over.
            a.update(source_url=None, unverified=True, opening_hours=None, cost_verified=False)
        if orig is None or changed_place or _editable(a) != _editable(orig):
            a["user_edited"] = True
        new_acts.append(a)

    if errors:
        return plan, errors

    new_acts.sort(key=lambda a: _minutes(a["time"]))
    new_plan = copy.deepcopy(plan)
    new_plan["days"][day_index]["activities"] = new_acts

    # Shift the total by the change in this day's activity costs (other budget lines are untouched).
    old_cost = sum(a.get("estimated_cost") or 0 for a in old_acts)
    new_cost = sum(a.get("estimated_cost") or 0 for a in new_acts)
    budget = new_plan.setdefault("budget", {})
    budget["estimated_total"] = max(0, (budget.get("estimated_total") or 0) + new_cost - old_cost)
    return new_plan, []
