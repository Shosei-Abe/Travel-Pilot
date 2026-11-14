"""Tavily integration: build queries and run them in parallel."""

import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

MAX_RESULTS_PER_QUERY = 5
MAX_CONTENT_CHARS = 1200  # keep the LLM context small and fast
# Social posts are weak evidence; keep sources to articles and official sites.
EXCLUDED_DOMAINS = ["facebook.com", "instagram.com", "youtube.com", "tiktok.com", "x.com"]


def build_queries(destination: str, interests: list[str], preferences: str = "") -> list[str]:
    interest_text = ", ".join(interests) if interests else "sightseeing"
    queries = [
        f"best things to do in {destination} for {interest_text}",
        f"{destination} must-try local food and restaurants",
        f"{destination} attractions opening hours and admission fees",
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
            }
        )
    return results


def run_searches(queries: list[str]) -> tuple[list[dict], list[str]]:
    """Run all queries in parallel. Returns (deduplicated results, error messages)."""
    api_key = os.getenv("TAVILY_API_KEY")
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
    return unique, errors


if __name__ == "__main__":
    qs = build_queries("Kyoto", ["Culture", "Food"])
    res, errs = run_searches(qs)
    for r in res:
        print(f"- {r['title']}\n  {r['url']}")
    print(f"\n{len(res)} unique results, {len(errs)} errors")
    for e in errs:
        print("  error:", e)
