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
