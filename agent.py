"""Agent pipeline: Search -> Reason -> Plan -> Verify."""

import json
import os
import re
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from urllib.parse import quote_plus

from prompts import (CONCISE_NOTE, EDIT_SYSTEM_PROMPT, ITINERARY_TOOL, SEARCH_TOOL, SYSTEM_PROMPT,
                     build_edit_prompt, build_user_prompt, format_results)
from search import build_queries, run_searches

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
FALLBACK_PATH = Path(__file__).parent / "sample_data" / "fallback_plan.json"

Progress = Callable[[str, str], None]  # (step, message)


def _noop(step: str, message: str) -> None:
    pass


# ---------- JSON handling ----------

def parse_json(text: str) -> dict:
    """Parse LLM output, tolerating code fences and leading/trailing prose."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _call_claude(user_prompt, system: str = SYSTEM_PROMPT, tools: list | None = None):
    """user_prompt is a string, or a full messages list for multi-turn agent loops."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    return client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=system,
        messages=user_prompt if isinstance(user_prompt, list) else [{"role": "user", "content": user_prompt}],
        tools=tools or [ITINERARY_TOOL],
    )


def _extract_plan(response) -> dict:
    for block in response.content:
        if block.type == "tool_use" and isinstance(block.input, dict) and block.input.get("days"):
            return block.input
    text = "".join(getattr(b, "text", "") for b in response.content)
    try:
        return parse_json(text)  # in case the model answered in plain text
    except (json.JSONDecodeError, ValueError):
        raise RuntimeError(
            f"No usable itinerary (stop_reason={response.stop_reason}, "
            f"blocks={[b.type for b in response.content]}, text={text[:150]!r})"
        )


def generate_plan(user_prompt: str) -> dict:
    """Structured output via the submit_itinerary tool. One retry, asking for a shorter plan."""
    last_error = None
    for attempt in range(2):
        prompt = user_prompt if attempt == 0 else user_prompt + CONCISE_NOTE
        response = _call_claude(prompt)
        try:
            return _extract_plan(response)
        except RuntimeError as e:
            last_error = e
    raise last_error


# ---------- Verification ----------

def verify_plan(plan: dict, results: list[dict], budget: float) -> dict:
    """Enforce grounding rules in code, not just in the prompt."""
    allowed = {r["url"] for r in results}
    stats = {"activities": 0, "grounded": 0, "removed_sources": 0, "unverified": 0}

    for day in plan.get("days", []):
        for act in day.get("activities", []):
            stats["activities"] += 1
            url = act.get("source_url")
            if url and url not in allowed:
                act["source_url"] = None  # hallucinated URL
                act["unverified"] = True
                stats["removed_sources"] += 1
            if act.get("source_url"):
                stats["grounded"] += 1
            else:
                act["unverified"] = True
            if not act.get("cost_verified"):
                act["cost_verified"] = False
            if act.get("unverified"):
                stats["unverified"] += 1

    b = plan.setdefault("budget", {})
    total = b.get("estimated_total")
    if not isinstance(total, (int, float)):
        total = sum(
            a.get("estimated_cost") or 0
            for d in plan.get("days", [])
            for a in d.get("activities", [])
        )
        b["estimated_total"] = total
    b["within_budget"] = total <= budget
    plan["verification"] = stats
    return plan


# ---------- Pipeline ----------

def load_fallback() -> dict:
    return json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))


def plan_trip(
    destination: str,
    days: int,
    budget: float,
    currency: str,
    interests: list[str],
    preferences: str = "",
    progress: Progress = _noop,
) -> dict:
    """Returns {"mode": "live"|"fallback", "plan", "sources", "queries", "warnings"}."""
    warnings: list[str] = []

    progress("search", "Building search queries")
    queries = build_queries(destination, interests, preferences)
    try:
        progress("search", f"Searching the web with Tavily ({len(queries)} queries)")
        results, errors = run_searches(queries)
        warnings += [f"Search failed for {e}" for e in errors]
        progress("search", f"Found {len(results)} unique sources")
    except Exception as e:
        warnings.append(f"Live search unavailable: {e}")
        return {"mode": "fallback", "plan": load_fallback(), "sources": [],
                "queries": queries, "warnings": warnings}

    try:
        progress("plan", f"Reasoning over sources with Claude ({MODEL})")
        prompt = build_user_prompt(destination, days, budget, currency,
                                   interests, preferences, results)
        plan = generate_plan(prompt)
    except Exception as e:
        warnings.append(f"Plan generation failed: {e}")
        return {"mode": "fallback", "plan": load_fallback(), "sources": results,
                "queries": queries, "warnings": warnings}

    progress("verify", "Checking every citation against retrieved sources")
    plan = verify_plan(plan, results, budget)
    return {"mode": "live", "plan": plan, "sources": results,
            "queries": queries, "warnings": warnings}


# ---------- Conversational editing ----------

def edit_plan(result: dict, instruction: str, destination: str, budget: float,
              progress: Progress = _noop, max_steps: int = 4) -> dict:
    """Agent loop: Claude may call search_web, then must call submit_itinerary.
    Returns a new result dict plus "reply" (Claude's message to the user)."""
    sources = list(result["sources"])
    queries = list(result["queries"])
    messages = [{"role": "user", "content": build_edit_prompt(result["plan"], sources, instruction)}]

    for _ in range(max_steps):
        progress("plan", "Claude is reading your request")
        response = _call_claude(messages, system=EDIT_SYSTEM_PROMPT, tools=[SEARCH_TOOL, ITINERARY_TOOL])
        tool_results, new_plan = [], None
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_itinerary" and isinstance(block.input, dict) and block.input.get("days"):
                new_plan = block.input
            elif block.name == "search_web":
                query = str(block.input.get("query", ""))[:200]
                progress("search", f"Searching: {query}")
                queries.append(query)
                try:
                    found, _ = run_searches([query])
                    content = format_results(found)
                except Exception as e:
                    found, content = [], f"Search failed: {e}"
                known = {s["url"] for s in sources}
                sources += [r for r in found if r["url"] not in known]
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

        if new_plan:
            progress("verify", "Checking every citation against retrieved sources")
            reply = " ".join(getattr(b, "text", "") for b in response.content if b.type == "text").strip()
            return {"mode": "live", "plan": verify_plan(new_plan, sources, budget), "sources": sources,
                    "queries": queries, "warnings": [], "reply": reply or "Updated the itinerary."}
        if not tool_results:
            raise RuntimeError(f"Edit failed (stop_reason={response.stop_reason})")
        messages += [{"role": "assistant", "content": response.content},
                     {"role": "user", "content": tool_results}]
    raise RuntimeError("Edit failed: too many steps")


# ---------- Google My Maps export ----------

def maps_url(place: str, destination: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{place}, {destination}")


def to_mymaps_csv(plan: dict, destination: str) -> str:
    """CSV for Google My Maps import: location column = Address, style by Category."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Category", "Day", "Time", "Address", "Description", "Source", "Google Maps"])
    for d in plan.get("days", []):
        for a in d.get("activities", []):
            place = a.get("place", "")
            w.writerow([place, a.get("category", "other"), f"Day {d.get('day')}", a.get("time", ""),
                        f"{place}, {destination}", a.get("description", ""), a.get("source_url") or "",
                        maps_url(place, destination)])
    return buf.getvalue()


if __name__ == "__main__":
    out = plan_trip("Kyoto", 2, 30000, "JPY", ["Culture", "Food"],
                    progress=lambda s, m: print(f"[{s}] {m}"))
    print("mode:", out["mode"])
    for w in out["warnings"]:
        print("warning:", w)
    print(json.dumps(out["plan"], ensure_ascii=False, indent=2)[:3000])
