"""Agent pipeline: Search -> Reason -> Plan -> Verify."""

import json
import os
import re
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from prompts import CONCISE_NOTE, ITINERARY_TOOL, SYSTEM_PROMPT, build_user_prompt
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


def _call_claude(user_prompt: str):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    return client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[ITINERARY_TOOL],
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
    """Structured output via forced tool use. One retry, asking for a shorter plan."""
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


if __name__ == "__main__":
    out = plan_trip("Kyoto", 2, 30000, "JPY", ["Culture", "Food"],
                    progress=lambda s, m: print(f"[{s}] {m}"))
    print("mode:", out["mode"])
    for w in out["warnings"]:
        print("warning:", w)
    print(json.dumps(out["plan"], ensure_ascii=False, indent=2)[:3000])
