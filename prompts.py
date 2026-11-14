"""Prompts for the planning LLM."""

SYSTEM_PROMPT = """You are TripPilot AI, an autonomous, evidence-grounded travel planner.

Create a realistic itinerary using ONLY the numbered search results provided.

Rules:
1. Respect the user's budget. Estimate costs conservatively.
2. Group activities by geographic proximity and avoid unnecessary backtracking.
3. Use realistic visiting durations and travel time between stops.
4. Recommend only places that appear in the search results.
5. Never invent opening hours, prices, or addresses. If a price or hour is not stated
   in the sources, set the value to null and mark it unverified.
5b. Sources marked [OFFICIAL] are government, tourism-board or the venue's own site. Prefer them:
   when an official source covers a place, cite it, and take hours and prices from it over blogs.
6. Every activity must cite a source by copying a URL exactly from the search results.
   If no source supports it, set "source_url": null and "unverified": true.
7. Meals and transport may be rough estimates, but mark them "cost_verified": false.
8. Write in the same language as the user's preferences field if given, otherwise English.

Submit the itinerary by calling the submit_itinerary tool exactly once, with an object matching this schema:
{
  "destination": string,
  "summary": string,                       // 1-2 sentences
  "days": [
    {
      "day": integer,
      "theme": string,
      "activities": [
        {
          "time": "HH:MM",
          "place": string,
          "category": "food" | "cafe" | "sightseeing" | "nature" | "shopping" | "nightlife" | "other",
          "description": string,          // why it fits the user's interests
          "duration_minutes": integer,
          "estimated_cost": number | null, // in the user's currency
          "cost_verified": boolean,        // true only if the price is stated in a source
          "opening_hours": string | null,  // only if stated in a source
          "source_url": string | null,
          "unverified": boolean
        }
      ]
    }
  ],
  "budget": {
    "currency": string,
    "estimated_total": number,
    "breakdown": [{"category": string, "amount": number}],
    "notes": string
  },
  "tips": [string],
  "unverified_notes": [string]             // anything the user should double-check
}"""


def build_user_prompt(
    destination: str,
    days: int,
    budget: float,
    currency: str,
    interests: list[str],
    preferences: str,
    results: list[dict],
) -> str:
    lines = [
        "## Trip request",
        f"- Destination: {destination}",
        f"- Duration: {days} day(s)",
        f"- Total budget: {budget:,.0f} {currency} (excluding accommodation and travel to the destination)",
        f"- Interests: {', '.join(interests) if interests else 'general sightseeing'}",
        f"- Preferences: {preferences or 'none'}",
        "",
        "## Search results",
    ]
    for i, r in enumerate(results, 1):
        tag = " [OFFICIAL]" if r.get("kind") == "official" else ""
        lines.append(f"[{i}]{tag} {r['title']}\nURL: {r['url']}\n{r['content']}\n")
    lines.append(f"Plan exactly {days} day(s). Submit it with the submit_itinerary tool.")
    return "\n".join(lines)


REPAIR_PROMPT = (
    "Your previous reply was not valid JSON. Return the same itinerary as ONE valid JSON "
    "object that matches the schema. No markdown fences, no commentary."
)


CONCISE_NOTE = (
    "\n\nIMPORTANT: your previous answer was too long and got cut off. Keep each description "
    "under 20 words, at most 5 activities per day, and at most 3 tips."
)

_ACTIVITY = {
    "type": "object",
    "properties": {
        "time": {"type": "string"},
        "place": {"type": "string"},
        "category": {"type": "string", "enum": ["food", "cafe", "sightseeing", "nature", "shopping", "nightlife", "other"]},
        "description": {"type": "string"},
        "duration_minutes": {"type": "integer"},
        "estimated_cost": {"type": ["number", "null"]},
        "cost_verified": {"type": "boolean"},
        "opening_hours": {"type": ["string", "null"]},
        "source_url": {"type": ["string", "null"]},
        "unverified": {"type": "boolean"},
    },
    "required": ["time", "place", "category", "description", "source_url", "unverified"],
}

ITINERARY_TOOL = {
    "name": "submit_itinerary",
    "description": "Submit the final, source-grounded travel itinerary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {"type": "string"},
            "summary": {"type": "string"},
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "integer"},
                        "theme": {"type": "string"},
                        "activities": {"type": "array", "items": _ACTIVITY},
                    },
                    "required": ["day", "activities"],
                },
            },
            "budget": {
                "type": "object",
                "properties": {
                    "currency": {"type": "string"},
                    "estimated_total": {"type": "number"},
                    "breakdown": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"category": {"type": "string"}, "amount": {"type": "number"}},
                            "required": ["category", "amount"],
                        },
                    },
                    "notes": {"type": "string"},
                },
                "required": ["currency", "estimated_total"],
            },
            "tips": {"type": "array", "items": {"type": "string"}},
            "unverified_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["destination", "summary", "days", "budget"],
    },
}


SEARCH_TOOL = {
    "name": "search_web",
    "description": "Search the web (Tavily) for current information, e.g. alternative restaurants or attractions.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "One focused search query"}},
        "required": ["query"],
    },
}

EDIT_SYSTEM_PROMPT = SYSTEM_PROMPT + """

You are now EDITING an existing itinerary in a conversation with the traveller.
- Change only what the user asks for. Keep every other activity exactly as it is, including its source_url.
- If the change needs new places or facts, call search_web first (1-2 focused queries).
- New or changed activities must cite a URL from the search results you have been given.
- Re-check timing, proximity and the budget after the change.
- Finish by calling submit_itinerary with the FULL updated itinerary, and in the same reply write
  1-2 sentences telling the user what you changed. Write that message in the user's language.
- Keep the itinerary's existing language unless the user asks otherwise."""


def format_results(results: list[dict], start: int = 1) -> str:
    return "\n".join(
        f"[{i}]{' [OFFICIAL]' if r.get('kind') == 'official' else ''} {r['title']}\nURL: {r['url']}\n{r['content']}\n"
        for i, r in enumerate(results, start)
    )


def build_edit_prompt(plan: dict, sources: list[dict], instruction: str) -> str:
    import json
    clean = {k: v for k, v in plan.items() if k != "verification"}
    return (
        "## Current itinerary\n" + json.dumps(clean, ensure_ascii=False) +
        "\n\n## Sources already retrieved\n" + format_results(sources) +
        "\n## Traveller's request\n" + instruction
    )
