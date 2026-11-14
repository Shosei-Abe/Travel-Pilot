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
        lines.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['content']}\n")
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
        "description": {"type": "string"},
        "duration_minutes": {"type": "integer"},
        "estimated_cost": {"type": ["number", "null"]},
        "cost_verified": {"type": "boolean"},
        "opening_hours": {"type": ["string", "null"]},
        "source_url": {"type": ["string", "null"]},
        "unverified": {"type": "boolean"},
    },
    "required": ["time", "place", "description", "source_url", "unverified"],
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
