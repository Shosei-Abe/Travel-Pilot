# TripPilot AI ✈️

Autonomous, evidence-grounded travel planner: **Search → Reason → Plan → Verify**.

- **Search**: Tavily runs 4–5 queries in parallel (attractions, food, hours/fees, transport)
- **Reason & Plan**: Claude builds a day-by-day itinerary from the retrieved sources only
- **Verify**: code checks every cited URL against the retrieved sources; made-up URLs are stripped and the activity is flagged as unverified
- **Fallback**: if an API fails, a clearly labelled demo plan is shown

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY and TAVILY_API_KEY
streamlit run app.py
```

## Check each stage on its own
```bash
python search.py   # Tavily only
python agent.py    # full pipeline, prints JSON
```

| File | Role |
|---|---|
| app.py | Streamlit UI |
| agent.py | Pipeline, JSON parsing/repair, citation verification, fallback |
| search.py | Tavily queries |
| prompts.py | Claude prompts and output schema |

## Map
Every stop is placed on an in-app map, coloured by category and numbered in visiting order.
Geocoding uses `GOOGLE_MAPS_API_KEY` if set (Geocoding API, best for shops and restaurants),
otherwise OpenStreetMap Nominatim (free, no key, about 1 stop per second).

## Send trips to Google My Maps automatically (your Mac only)
Google My Maps has no public API, so this drives **your own signed-in Chrome on your Mac** with Playwright.
It never handles your Google password and is never enabled on the public deployment.

```bash
pip install -r requirements-local.txt
playwright install chromium
python automation/mymaps_sync.py login          # sign in once in the window that opens
TRIPPILOT_LOCAL_AUTOMATION=1 streamlit run app.py   # adds "Send to Google My Maps · this Mac"
```

Or from the command line: `python automation/mymaps_sync.py import trippilot_mymaps.csv --title "Kyoto"`.
Each step saves a screenshot under `~/.trippilot/logs/` so a broken step is easy to spot.

### As an MCP server (Claude Desktop / Claude Code)
```bash
claude mcp add trippilot-mymaps -- "$PWD/.venv/bin/python" "$PWD/automation/mcp_server.py"
```
Tools: `mymaps_check_login`, `mymaps_login`, `send_csv_to_mymaps`, `send_plan_to_mymaps`.
