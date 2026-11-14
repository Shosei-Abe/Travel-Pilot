"""Itinerary map: one coloured dot per stop, numbered in visiting order, with each day's route."""

import pydeck as pdk

# Muted, print-like colours that sit on the paper theme. RGB.
CATEGORY_COLORS = {
    "food": (138, 75, 20),
    "cafe": (176, 124, 64),
    "sightseeing": (28, 27, 25),
    "nature": (74, 107, 58),
    "shopping": (78, 86, 128),
    "nightlife": (122, 62, 107),
    "other": (140, 134, 122),
}
CATEGORY_LABELS = {"food": "Food", "cafe": "Café", "sightseeing": "Sight", "nature": "Nature",
                   "shopping": "Shop", "nightlife": "Night", "other": "Other"}


def map_points(plan: dict, day: int | None = None) -> list[dict]:
    points, n = [], 0
    for d in plan.get("days", []):
        if day is not None and d.get("day") != day:
            continue
        for a in d.get("activities", []):
            if a.get("lat") is None:
                continue
            n += 1
            cat = a.get("category") if a.get("category") in CATEGORY_COLORS else "other"
            points.append({
                "n": str(n), "day": d.get("day"), "lat": a["lat"], "lng": a["lng"],
                "place": a.get("place", ""), "time": a.get("time", ""),
                "category": CATEGORY_LABELS[cat], "color": list(CATEGORY_COLORS[cat]),
            })
    return points


def routes(points: list[dict]) -> list[dict]:
    by_day: dict = {}
    for p in points:
        by_day.setdefault(p["day"], []).append([p["lng"], p["lat"]])
    return [{"day": d, "path": path} for d, path in by_day.items() if len(path) > 1]


def build_deck(plan: dict, day: int | None = None) -> pdk.Deck | None:
    points = map_points(plan, day)
    if not points:
        return None
    lats, lngs = [p["lat"] for p in points], [p["lng"] for p in points]
    span = max(max(lats) - min(lats), max(lngs) - min(lngs), 0.005)
    zoom = 14 if span < 0.02 else 13 if span < 0.05 else 12 if span < 0.1 else 11 if span < 0.25 else 9
    view = pdk.ViewState(latitude=(max(lats) + min(lats)) / 2, longitude=(max(lngs) + min(lngs)) / 2, zoom=zoom)
    layers = [
        pdk.Layer("PathLayer", routes(points), get_path="path", get_color=[28, 27, 25, 110],
                  width_min_pixels=2, get_width=2),
        pdk.Layer("ScatterplotLayer", points, get_position=["lng", "lat"], get_fill_color="color",
                  get_line_color=[246, 244, 238], line_width_min_pixels=2, stroked=True,
                  radius_min_pixels=11, radius_max_pixels=11, pickable=True),
        pdk.Layer("TextLayer", points, get_position=["lng", "lat"], get_text="n", get_size=12,
                  get_color=[246, 244, 238], font_weight=700, get_alignment_baseline="'center'"),
    ]
    return pdk.Deck(layers=layers, initial_view_state=view, map_style="light",
                    tooltip={"text": "{n}. {place}\n{time} · {category}"})
