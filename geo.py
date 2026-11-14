"""Geocoding for itinerary stops.

Uses the Google Geocoding API when GOOGLE_MAPS_API_KEY is set (best for shop and
restaurant names), otherwise OpenStreetMap Nominatim (free, no key, max 1 request/second).
Results are biased to the destination so "Nishiki Market" never lands in another city.
"""

import re
import time

import requests

from search import get_secret

USER_AGENT = "TripPilot/1.0 (https://github.com/Shosei-Abe/Travel-Pilot)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
GOOGLE = "https://maps.googleapis.com/maps/api/geocode/json"

_cache: dict[str, tuple[float, float] | None] = {}
_last_osm_call = 0.0


def _osm(query: str, viewbox: str | None = None) -> tuple[float, float] | None:
    global _last_osm_call
    wait = 1.05 - (time.time() - _last_osm_call)  # Nominatim usage policy: max 1 req/s
    if wait > 0:
        time.sleep(wait)
    params = {"q": query, "format": "json", "limit": 1}
    if viewbox:
        params.update(viewbox=viewbox, bounded=1)
    r = requests.get(NOMINATIM, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
    _last_osm_call = time.time()
    r.raise_for_status()
    hits = r.json()
    return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None


def _google(query: str, key: str) -> tuple[float, float] | None:
    r = requests.get(GOOGLE, params={"address": query, "key": key}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        return None
    loc = data["results"][0]["geometry"]["location"]
    return (loc["lat"], loc["lng"])


def geocode(query: str, viewbox: str | None = None) -> tuple[float, float] | None:
    cache_key = f"{query}|{viewbox}"
    if cache_key in _cache:
        return _cache[cache_key]
    key = get_secret("GOOGLE_MAPS_API_KEY")
    try:
        result = _google(query, key) if key else _osm(query, viewbox)
    except requests.RequestException:
        result = None  # network trouble: leave the stop off the map, don't crash the app
    _cache[cache_key] = result
    return result


def destination_viewbox(destination: str, span_deg: float = 0.6) -> str | None:
    """A box around the destination (~60 km) to keep matches local (Nominatim only)."""
    center = geocode(destination)
    if not center:
        return None
    lat, lng = center
    return f"{lng - span_deg},{lat + span_deg},{lng + span_deg},{lat - span_deg}"


def _candidates(place: str, destination: str) -> list[str]:
    plain = re.sub(r"\s*\(.*?\)\s*", " ", place).strip()  # "Izuju (Gion)" -> "Izuju"
    paren = re.findall(r"\((.*?)\)", place)
    out = [f"{place}, {destination}"]
    if plain and plain != place:
        out.append(f"{plain}, {destination}")
        if paren:
            out.append(f"{plain}, {paren[0]}, {destination}")
    return out


def geocode_plan(plan: dict, destination: str, progress=lambda done, total: None) -> int:
    """Add lat/lng to every activity that lacks them. Returns how many were placed."""
    acts = [a for d in plan.get("days", []) for a in d.get("activities", [])]
    todo = [a for a in acts if a.get("lat") is None and not a.get("geo_failed")]
    if not todo:
        return 0
    viewbox = None if get_secret("GOOGLE_MAPS_API_KEY") else destination_viewbox(destination)
    placed = 0
    for i, a in enumerate(todo, 1):
        progress(i, len(todo))
        hit = None
        for q in _candidates(a.get("place", ""), destination):
            hit = geocode(q, viewbox)
            if hit:
                break
        if hit:
            a["lat"], a["lng"] = hit
            a.pop("geo_failed", None)
            placed += 1
        else:
            a["geo_failed"] = True  # don't retry on every rerun
    return placed
