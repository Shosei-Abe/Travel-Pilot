"""Tavily integration: build queries and run them in parallel."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def get_secret(name: str):
    """Env var / .env locally; falls back to st.secrets on Streamlit Cloud."""
    value = os.getenv(name)
    if value:
        return value.strip()
    try:
        import streamlit as st
        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None

MAX_RESULTS_PER_QUERY = 5
MAX_CONTENT_CHARS = 1200  # keep the LLM context small and fast
# Social posts are weak evidence; keep sources to articles and official sites.
EXCLUDED_DOMAINS = ["facebook.com", "instagram.com", "youtube.com", "tiktok.com", "x.com"]


# Government, municipal and tourism-board domains count as official.
OFFICIAL_TLD = re.compile(r"\.(go\.jp|lg\.jp|gov(\.[a-z]{2})?|gouv\.fr|gob\.[a-z]{2}|gv\.at|admin\.ch)$")
TOURISM_BOARDS = {"japan.travel", "kyoto.travel", "gotokyo.org", "osaka-info.jp", "visitsingapore.com",
                  "visitkorea.or.kr", "visitlondon.com", "parisjetaime.com", "nycgo.com", "vietnam.travel",
                  "tourismthailand.org", "visithungary.com", "budapestinfo.hu", "hongkongtourismboard.com",
                  "discoverhongkong.com", "taiwan.net.tw", "germany.travel", "myswitzerland.com"}
OFFICIAL_TITLE = re.compile(r"official|公式|オフィシャル|官方|공식", re.I)


def source_kind(url: str, title: str = "") -> str:
    """'official' for government / tourism-board / self-declared official sites, else 'guide'."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if OFFICIAL_TLD.search(host) or host in TOURISM_BOARDS or any(host.endswith("." + b) for b in TOURISM_BOARDS):
        return "official"
    if OFFICIAL_TITLE.search(title or ""):
        return "official"
    return "guide"


def build_queries(destination: str, interests: list[str], preferences: str = "") -> list[str]:
    interest_text = ", ".join(interests) if interests else "sightseeing"
    queries = [
        f"best things to do in {destination} for {interest_text}",
        f"{destination} must-try local food and restaurants",
        f"{destination} attractions official website opening hours admission fee",
        f"{destination} getting around public transport tourist guide",
    ]
    if preferences.strip():
        queries.append(f"{destination} travel tips {preferences.strip()[:80]}")
    return queries


def _search_one(client, query: str) -> list[dict]:
    response = client.search(
        query=query,
        max_results=MAX_RESULTS_PER_QUERY,
        search_depth="basic",
        exclude_domains=EXCLUDED_DOMAINS,
    )
    results = []
    for r in response.get("results", []):
        url = r.get("url")
        if not url:
            continue
        results.append(
            {
                "query": query,
                "title": r.get("title") or url,
                "url": url,
                "content": (r.get("content") or "")[:MAX_CONTENT_CHARS],
                "score": r.get("score"),
                "kind": source_kind(url, r.get("title") or ""),
            }
        )
    return results


def run_searches(queries: list[str]) -> tuple[list[dict], list[str]]:
    """Run all queries in parallel. Returns (deduplicated results, error messages)."""
    api_key = get_secret("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    results: list[dict] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = {pool.submit(_search_one, client, q): q for q in queries}
        for future, query in futures.items():
            try:
                results.extend(future.result(timeout=30))
            except Exception as e:  # one failing query should not kill the run
                errors.append(f"'{query}': {e}")

    seen, unique = set(), []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    if not unique:
        raise RuntimeError("Tavily returned no results. " + "; ".join(errors))
    unique.sort(key=lambda r: r["kind"] != "official")  # official sources first (stable sort)
    return unique, errors


def _mentions(place: str, text: str) -> bool:
    words = [w for w in re.findall(r"\w+", place.lower()) if len(w) > 3]
    return bool(words) and sum(w in text.lower() for w in words) >= max(1, len(words) // 2)


_official_cache: dict[tuple[str, str], dict | None] = {}


def find_official_pages(places: list[str], destination: str) -> dict[str, dict]:
    """For each place, look for its own official page. Returns {place: result} for hits only."""
    api_key = get_secret("TAVILY_API_KEY")
    cached = {p: _official_cache[(p, destination)] for p in places if (p, destination) in _official_cache}
    places = [p for p in places if (p, destination) not in _official_cache]
    if not api_key or not places:
        return {p: h for p, h in cached.items() if h}
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    found: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(places))) as pool:
        futures = {pool.submit(_search_one, client, f"{p} {destination} official website"): p for p in places}
        for future, place in futures.items():
            try:
                hits = future.result(timeout=30)
            except Exception:
                continue
            _official_cache[(place, destination)] = None
            for h in hits:
                if h["kind"] == "official" and _mentions(place, h["title"] + " " + h["content"]):
                    found[place] = _official_cache[(place, destination)] = h
                    break
    return {**{p: h for p, h in cached.items() if h}, **found}


if __name__ == "__main__":
    qs = build_queries("Kyoto", ["Culture", "Food"])
    res, errs = run_searches(qs)
    for r in res:
        print(f"- {r['title']}\n  {r['url']}")
    print(f"\n{len(res)} unique results, {len(errs)} errors")
    for e in errs:
        print("  error:", e)
