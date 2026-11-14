# TripPilot

**Itineraries drawn from real sources, every stop accounted for.**

TripPilot is an AI travel agent. Give it a destination, number of days, budget and interests;
it searches the live web, plans the days with Claude, and checks every citation in code,
so you always know which stops, prices and opening hours are backed by a source.

`Search → Reason → Plan → Verify`

## Features

| | |
|---|---|
| **Live research** | Tavily runs 4–5 searches in parallel (sights, food, official hours and fees, transport). Social media is excluded. |
| **Official sources first** | Government, city and tourism-board sites and venues' own sites are tagged `[OFFICIAL]`, ranked first, and preferred by Claude for hours and prices. After planning, TripPilot looks up an official page for every stop that lacks one and shows it as **◆ Official**. |
| **Verified citations** | Every URL Claude cites is matched against what was actually retrieved. Anything else is removed and the stop is marked **Unverified**. Prices are labelled *from source* or *≈ estimate*. |
| **Refine by chat** | “Swap the Day 1 lunch for a ramen place” — the agent searches again if needed, changes only that stop, and re-verifies. Japanese works too. |
| **Edit by hand** | Per-day table: start / end time, place, category, cost, note. Add or remove stops. A place you type yourself is marked unverified until the agent finds a source. |
| **Map** | Every stop on an in-app map, coloured by category and numbered in visiting order, with each day's route. |
| **PDF** | *Download plan · PDF* — an A4 itinerary with links, readable on any phone (Japanese font embedded). |
| **Google Maps** | A Google Maps link on every stop, a CSV export for Google My Maps, and (on your own Mac) fully automatic My Maps creation. |
| **Honest fallback** | If an API fails, a sample plan is shown with a clear **DEMO DATA** banner. |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your keys
streamlit run app.py
```

### Keys (`.env` locally, **Secrets** on Streamlit Cloud)

| Name | Required | Used for |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Planning and chat edits (Claude) |
| `TAVILY_API_KEY` | yes | Web search |
| `GOOGLE_MAPS_API_KEY` | no | Better geocoding for the map (otherwise OpenStreetMap, ~1 stop/second) |
| `CLAUDE_MODEL` | no | Override the model (default `claude-sonnet-5-5`) |

On Streamlit Cloud, Secrets must be TOML with quoted values: `TAVILY_API_KEY = "tvly-..."`.

## Google My Maps automation (your Mac only)

Google offers no API for My Maps or for Saved lists in Google Maps, so this drives **your own
signed-in Chrome on your Mac** with Playwright. It never handles your Google password, and it is
**not** available on the public deployment (a server signed in to your Google account would be
usable by anyone with the URL, and Google blocks sign-ins from cloud servers).

```bash
pip install -r requirements-local.txt
playwright install chromium
python automation/mymaps_sync.py login               # sign in once in the window that opens
TRIPPILOT_LOCAL_AUTOMATION=1 streamlit run app.py    # adds "Send to Google My Maps · this Mac"
```

It creates the map, imports the stops, groups them by category, checks every stop was placed and
that the map was saved. The map then appears in the Google Maps app under **Saved → Maps**.
Each step leaves a screenshot in `~/.trippilot/logs/`.

Command line: `python automation/mymaps_sync.py import trippilot_mymaps.csv --title "Kyoto"`

### As an MCP server (Claude Desktop / Claude Code)

```bash
claude mcp add trippilot-mymaps -- "$PWD/.venv/bin/python" "$PWD/automation/mcp_server.py"
```

Tools: `mymaps_check_login`, `mymaps_login`, `send_csv_to_mymaps`, `send_plan_to_mymaps`.

## Project layout

| File | Role |
|---|---|
| `app.py` | Streamlit UI: form, itinerary, map, chat, editing, exports |
| `agent.py` | Pipeline (search → plan → official pages → verify), chat edit agent, CSV export |
| `search.py` | Tavily queries, official-source detection and lookup, secrets |
| `prompts.py` | Claude prompts and tool schemas (`submit_itinerary`, `search_web`) |
| `editing.py` | Manual per-day edits (times, places, costs) |
| `geo.py`, `map_view.py` | Geocoding and the pydeck map |
| `pdf_export.py` | PDF itinerary |
| `automation/` | Local My Maps automation and its MCP server |
| `assets/` | Logo and the embedded IPA Gothic font (IPA Font License in `assets/fonts/`) |
