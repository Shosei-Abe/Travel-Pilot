"""TripPilot — Streamlit frontend."""

import base64
import json
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
from PIL import Image

from agent import edit_plan, maps_url, plan_trip, to_mymaps_csv, verify_plan
from editing import CATEGORIES, apply_day_edits, day_rows, end_time

ASSETS = Path(__file__).parent / "assets"
LOGO_B64 = base64.b64encode((ASSETS / "logo.png").read_bytes()).decode()

st.set_page_config(page_title="TripPilot", page_icon=Image.open(ASSETS / "favicon.png"), layout="wide")

st.html(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root { --ink:#1c1b19; --muted:#6f6a60; --rule:#1c1b19; --paper:#f6f4ee; --faint:#d9d4c7; --warn:#8a4b14; }
html, body, [class*="css"], .stMarkdown, input, textarea, button, label {
  font-family: 'Newsreader', Georgia, serif !important; }
.block-container { max-width: 980px; padding-top: 2.2rem; padding-bottom: 4rem; }
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"] { display:none !important; }

.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace !important; }
.label { font-family:'IBM Plex Mono',monospace; font-size:.68rem; letter-spacing:.14em;
         text-transform:uppercase; color:var(--muted); }

/* masthead */
.mast { display:flex; align-items:center; gap:1.1rem; padding-bottom:1rem;
        border-bottom:1px solid var(--rule); }
.mast img { width:64px; height:64px; }
.mast h1 { font-size:2.6rem; font-weight:400; margin:0; line-height:1; letter-spacing:-.01em; }
.mast .sub { font-style:italic; color:var(--muted); margin-top:.25rem; }
.mast .right { margin-left:auto; text-align:right; }
.rule2 { border-top:1px solid var(--rule); margin-top:3px; margin-bottom:1.8rem; }

/* form */
[data-testid="stForm"] { border:none; padding:0; }
[data-testid="stWidgetLabel"] p { font-family:'IBM Plex Mono',monospace !important; font-size:.68rem !important;
  letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="base-input"] {
  background:transparent !important; border-radius:0 !important; border-color:var(--ink) !important; }
input { font-size:1.05rem !important; }
span[data-baseweb="tag"] { background:transparent !important; border:1px solid var(--ink); border-radius:0 !important; color:var(--ink) !important; }
span[data-baseweb="tag"] span { color:var(--ink) !important; }
[data-testid="stFormSubmitButton"] button, .stDownloadButton button {
  background:var(--ink) !important; color:var(--paper) !important; border-radius:0 !important; border:none;
  font-family:'IBM Plex Mono',monospace !important; letter-spacing:.16em; text-transform:uppercase; padding:.7rem 0; }
[data-testid="stFormSubmitButton"] button p, .stDownloadButton button p { font-family:'IBM Plex Mono',monospace !important; font-size:.8rem; }
[data-testid="stExpander"] [data-testid="stFormSubmitButton"] button { padding:.55rem 1.4rem; }
.stDownloadButton button { background:transparent !important; color:var(--ink) !important; border:1px solid var(--ink) !important; padding:.5rem 1.2rem; }

/* status box */
[data-testid="stExpander"] details, [data-testid="stStatusWidget"] { border-radius:0 !important; border-color:var(--faint) !important; }

/* result header */
.dest { font-size:2.2rem; font-weight:400; margin:2.2rem 0 .2rem; }
.summary { font-style:italic; font-size:1.12rem; color:#3b3832; max-width:46rem; }

/* ledger */
.ledger { display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid var(--rule);
          border-bottom:1px solid var(--rule); margin:1.6rem 0 2rem; }
.ledger > div { padding:.8rem 1rem; border-left:1px solid var(--faint); }
.ledger > div:first-child { border-left:none; padding-left:0; }
.ledger .v { font-family:'IBM Plex Mono',monospace; font-size:1.35rem; margin-top:.2rem; }
.ledger .n { font-family:'IBM Plex Mono',monospace; font-size:.72rem; color:var(--muted); }
.over { color:var(--warn); }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap:2rem; border-bottom:1px solid var(--faint); }
.stTabs [data-baseweb="tab"] { padding:0 0 .5rem; background:transparent; }
.stTabs [data-baseweb="tab"] p { font-family:'IBM Plex Mono',monospace !important; letter-spacing:.12em; font-size:.8rem; text-transform:uppercase; }
.stTabs [data-baseweb="tab-highlight"] { background:var(--ink); height:2px; }
.theme { font-style:italic; color:var(--muted); margin:.6rem 0 1.2rem; }

/* itinerary */
.stop { display:grid; grid-template-columns:4.2rem 1.4rem 1fr; }
.stop .t { font-family:'IBM Plex Mono',monospace; font-size:.9rem; padding-top:.22rem; }
.stop .t-end { font-size:.75rem; color:var(--muted); margin-top:.15rem; }
.meta .edit { color:var(--ink); font-style:italic; }
.stop .axis { position:relative; }
.stop .axis:before { content:""; position:absolute; left:50%; top:0; bottom:0; border-left:1px solid var(--faint); }
.stop .axis:after { content:""; position:absolute; left:calc(50% - 4px); top:.55rem; width:7px; height:7px;
                    background:var(--paper); border:1px solid var(--ink); transform:rotate(45deg); }
.stop .body { padding:0 0 1.5rem .6rem; }
.stop .place { font-size:1.25rem; font-weight:500; }
.stop .cat { font-family:'IBM Plex Mono',monospace; font-size:.66rem; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }
[data-testid="stChatMessage"] { background:transparent; }
[data-testid="stChatMessageAvatarUser"] { background:var(--ink) !important; color:var(--paper) !important; border-radius:0 !important; }
.stop .desc { margin:.2rem 0 .45rem; color:#3b3832; line-height:1.5; }
.meta { font-family:'IBM Plex Mono',monospace; font-size:.7rem; letter-spacing:.06em; color:var(--muted); }
.meta span { margin-right:1.1rem; }
.meta .ok { color:var(--ink); }
.meta .bad { color:var(--warn); }
.meta a { color:var(--ink); text-decoration:underline; text-underline-offset:2px; }

/* lists */
h4.sec { font-family:'IBM Plex Mono',monospace; font-weight:500; font-size:.72rem; letter-spacing:.14em;
         text-transform:uppercase; border-bottom:1px solid var(--rule); padding-bottom:.4rem; margin:2rem 0 .8rem; }
.row { display:flex; font-size:1rem; margin:.25rem 0; }
.row .dots { flex:1; border-bottom:1px dotted var(--muted); margin:0 .4rem .3rem; }
.row .amt { font-family:'IBM Plex Mono',monospace; }
.note { color:var(--muted); font-style:italic; font-size:.92rem; margin-top:.6rem; }
ul.plain { padding-left:1.1rem; margin:0; } ul.plain li { margin:.3rem 0; }
ol.src { padding-left:1.4rem; } ol.src li { margin:.35rem 0; }
ol.src .d { font-family:'IBM Plex Mono',monospace; font-size:.72rem; color:var(--muted); margin-left:.4rem; }
ol.src a { color:var(--ink); }
.banner { border:1px solid var(--warn); color:var(--warn); padding:.7rem 1rem; margin:1.5rem 0 0;
          font-family:'IBM Plex Mono',monospace; font-size:.78rem; letter-spacing:.06em; }
.qs { font-family:'IBM Plex Mono',monospace; font-size:.78rem; color:var(--muted); }
</style>
"""
)

st.markdown(
    f"""
<div class="mast">
  <img src="data:image/png;base64,{LOGO_B64}" alt="TripPilot logo">
  <div><h1>TripPilot</h1><div class="sub">Itineraries drawn from real sources, every stop accounted for.</div></div>
  <div class="right label">Search · Reason<br>Plan · Verify</div>
</div><div class="rule2"></div>
""",
    unsafe_allow_html=True,
)

# ---------- Input form ----------
with st.form("trip"):
    c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
    destination = c1.text_input("Destination", "Kyoto, Japan")
    days = c2.number_input("Days", 1, 7, 2)
    budget = c3.number_input("Budget, excl. lodging", 0, 10_000_000, 30000, step=1000)
    currency = c4.selectbox("Currency", ["JPY", "USD", "EUR", "HUF", "SGD"])
    interests = st.multiselect(
        "Interests",
        ["Culture", "Food", "Nature", "History", "Shopping", "Art", "Nightlife", "Photography"],
        default=["Culture", "Food", "Nature"],
    )
    preferences = st.text_input(
        "Preferences",
        placeholder="slow pace, avoid crowds, vegetarian, travelling with kids…",
    )
    submitted = st.form_submit_button("Plan the trip", use_container_width=True)


def domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def money(x) -> str:
    return f"{x:,.0f}"


CATEGORY_MARK = {"food": "● Food", "cafe": "◐ Café", "sightseeing": "◆ Sight", "nature": "▲ Nature",
                 "shopping": "■ Shop", "nightlife": "★ Night", "other": "○ Other"}


def stop_html(a: dict, destination: str) -> str:
    meta = []
    url = a.get("source_url")
    if url:
        meta.append(f'<span class="ok">✓ Sourced — <a href="{escape(url)}" target="_blank">{escape(domain(url))} ↗</a></span>')
    else:
        meta.append('<span class="bad">Unverified — check before going</span>')
    if a.get("user_edited"):
        meta.insert(0, '<span class="edit">✎ Edited by you</span>')
    if a.get("duration_minutes"):
        meta.append(f'<span>{a["duration_minutes"]} min</span>')
    cost = a.get("estimated_cost")
    if cost is None:
        meta.append("<span>Cost: not stated</span>")
    elif a.get("cost_verified"):
        meta.append(f'<span class="ok">{money(cost)} · price from source</span>')
    else:
        meta.append(f"<span>≈ {money(cost)} · estimate</span>")
    if a.get("opening_hours"):
        meta.append(f'<span class="ok">Hours {escape(str(a["opening_hours"]))}</span>')
    meta.append(f'<span><a href="{escape(maps_url(a.get("place", ""), destination))}" target="_blank">Google Maps ↗</a></span>')
    cat = CATEGORY_MARK.get(a.get("category", "other"), CATEGORY_MARK["other"])
    return (
        f'<div class="stop"><div class="t">{escape(str(a.get("time", "")))}'
        f'<div class="t-end">{"– " + end_time(a) if end_time(a) else ""}</div></div><div class="axis"></div>'
        f'<div class="body"><div class="cat">{cat}</div><div class="place">{escape(str(a.get("place", "")))}</div>'
        f'<div class="desc">{escape(str(a.get("description", "")))}</div>'
        f'<div class="meta">{"".join(meta)}</div></div></div>'
    )


def day_editor(result: dict, day_index: int, day: dict, budget_limit: float) -> None:
    """Spreadsheet-style manual editing of one day's stops."""
    if result["mode"] != "live":
        return
    with st.expander("Edit this day: times, places, costs"):
        st.caption("Change start/end (HH:MM), swap a place, add a row or clear a place to remove it. "
                   "A place you type yourself is shown as unverified until the agent finds a source for it.")
        version = st.session_state.get("plan_version", 0)
        with st.form(f"edit_form_{day_index}_{version}", border=False):
            edited = st.data_editor(
                day_rows(day), num_rows="dynamic", use_container_width=True, hide_index=True,
                key=f"editor_{day_index}_{version}",
                column_config={
                    "id": None,
                    "Start": st.column_config.TextColumn("Start", width="small", help="HH:MM"),
                    "End": st.column_config.TextColumn("End", width="small", help="HH:MM"),
                    "Place": st.column_config.TextColumn("Place", width="medium"),
                    "Category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, width="small"),
                    "Cost": st.column_config.NumberColumn("Cost", min_value=0, step=100, format="%d"),
                    "Note": st.column_config.TextColumn("Note", width="large"),
                },
            )
            if st.form_submit_button("Apply changes"):
                rows = edited.to_dict("records") if hasattr(edited, "to_dict") else edited
                new_plan, errors = apply_day_edits(result["plan"], day_index, rows)
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    removed = result["plan"].get("verification", {}).get("removed_sources", 0)
                    new_plan = verify_plan(new_plan, result["sources"], budget_limit)
                    new_plan["verification"]["removed_sources"] = removed
                    st.session_state["result"] = {**result, "plan": new_plan}
                    st.session_state["plan_version"] = version + 1
                    st.rerun()


def render_result(result: dict, budget_limit: float, currency: str, destination: str) -> None:
    plan = result["plan"]
    if result["mode"] == "fallback":
        st.markdown('<div class="banner">DEMO DATA — NOT LIVE SEARCH. The live pipeline failed, so a sample plan is shown.</div>',
                    unsafe_allow_html=True)
    for w in result["warnings"]:
        st.caption(w)

    st.markdown(f'<div class="dest">{escape(plan.get("destination", ""))}</div>'
                f'<div class="summary">{escape(plan.get("summary", ""))}</div>', unsafe_allow_html=True)

    b, v = plan.get("budget", {}), plan.get("verification", {})
    total = b.get("estimated_total") or 0
    cur = b.get("currency", currency)
    diff = budget_limit - total
    diff_html = (f'<div class="n">{money(diff)} remaining</div>' if diff >= 0
                 else f'<div class="n over">{money(-diff)} over budget</div>')
    st.markdown(
        f"""<div class="ledger">
<div><div class="label">Estimated spend</div><div class="v">{money(total)}</div><div class="n">{escape(cur)}</div></div>
<div><div class="label">Budget</div><div class="v">{money(budget_limit)}</div>{diff_html}</div>
<div><div class="label">Sources read</div><div class="v">{len(result["sources"])}</div><div class="n">via Tavily</div></div>
<div><div class="label">Stops sourced</div><div class="v">{v.get("grounded", 0)}/{v.get("activities", 0)}</div>
<div class="n">{v.get("removed_sources", 0)} citation(s) rejected</div></div>
</div>""",
        unsafe_allow_html=True,
    )

    day_list = plan.get("days", [])
    if day_list:
        tabs = st.tabs([f"Day {d.get('day', i + 1)}" for i, d in enumerate(day_list)])
        for i, (tab, d) in enumerate(zip(tabs, day_list)):
            with tab:
                html = f'<div class="theme">{escape(d.get("theme", ""))}</div>' if d.get("theme") else ""
                html += "".join(stop_html(a, destination) for a in d.get("activities", []))
                st.markdown(html, unsafe_allow_html=True)
                day_editor(result, i, d, budget_limit)

    left, right = st.columns(2, gap="large")
    with left:
        rows = "".join(
            f'<div class="row"><span>{escape(str(i.get("category", "")))}</span><span class="dots"></span>'
            f'<span class="amt">{money(i.get("amount") or 0)}</span></div>'
            for i in b.get("breakdown", [])
        )
        note = f'<div class="note">{escape(b["notes"])}</div>' if b.get("notes") else ""
        st.markdown(f'<h4 class="sec">Budget</h4>{rows}{note}', unsafe_allow_html=True)
    with right:
        html = ""
        if plan.get("tips"):
            html += '<h4 class="sec">Notes</h4><ul class="plain">' + "".join(
                f"<li>{escape(t)}</li>" for t in plan["tips"]) + "</ul>"
        if plan.get("unverified_notes"):
            html += '<h4 class="sec">Check before you go</h4><ul class="plain">' + "".join(
                f"<li>{escape(n)}</li>" for n in plan["unverified_notes"]) + "</ul>"
        st.markdown(html, unsafe_allow_html=True)

    if result["sources"]:
        items = "".join(
            f'<li><a href="{escape(s["url"])}" target="_blank">{escape(s["title"])}</a>'
            f'<span class="d">{escape(domain(s["url"]))}</span></li>'
            for s in result["sources"]
        )
        st.markdown(f'<h4 class="sec">Sources · {len(result["sources"])}</h4><ol class="src">{items}</ol>',
                    unsafe_allow_html=True)
    qs = "<br>".join(f"→ {escape(q)}" for q in result["queries"])
    st.markdown(f'<h4 class="sec">Queries the agent ran</h4><div class="qs">{qs}</div>', unsafe_allow_html=True)

    st.write("")
    st.download_button("Download plan · JSON", json.dumps(plan, ensure_ascii=False, indent=2),
                       file_name="trippilot_plan.json", mime="application/json")
    st.download_button("Export to Google My Maps · CSV", to_mymaps_csv(plan, destination),
                       file_name="trippilot_mymaps.csv", mime="text/csv")
    with st.expander("How to add these places to Google Maps"):
        st.markdown(
            "1. Open **mymaps.google.com** → *Create a new map*\n"
            "2. In the layer, click **Import** and choose `trippilot_mymaps.csv`\n"
            "3. Location column: **Address** · Title column: **Name**\n"
            "4. Click *Uniform style* → **Style by data column: Category** to give each category its own colour and icon\n"
            "5. The map then appears in the Google Maps app under **Saved → Maps**"
        )


# ---------- Run ----------
if submitted:
    if not destination.strip():
        st.error("Please enter a destination.")
        st.stop()
    labels = {"search": "Search", "plan": "Reason & plan", "verify": "Verify"}
    with st.status("Working…", expanded=True) as status:
        def progress(step: str, msg: str) -> None:
            st.markdown(f'<span class="label">{labels.get(step, step)}</span>&nbsp; {escape(msg)}',
                        unsafe_allow_html=True)

        result = plan_trip(destination, int(days), float(budget), currency,
                           interests, preferences, progress=progress)
        status.update(
            label="Plan ready" if result["mode"] == "live" else "Showing demo fallback",
            state="complete" if result["mode"] == "live" else "error",
            expanded=False,
        )
    st.session_state["result"] = result
    st.session_state["budget"] = float(budget)
    st.session_state["currency"] = currency
    st.session_state["destination"] = destination
    st.session_state["chat"] = []
    st.session_state["plan_version"] = st.session_state.get("plan_version", 0) + 1

if "result" in st.session_state:
    render_result(st.session_state["result"], st.session_state["budget"],
                  st.session_state["currency"], st.session_state["destination"])

    st.markdown('<h4 class="sec">Refine with the agent</h4>', unsafe_allow_html=True)
    if st.session_state["result"]["mode"] != "live":
        st.caption("Editing needs a live plan.")
    else:
        for msg in st.session_state["chat"]:
            avatar = str(ASSETS / "logo.png") if msg["role"] == "assistant" else ":material/person:"
            with st.chat_message(msg["role"], avatar=avatar):
                st.write(msg["content"])
        request = st.chat_input("e.g. Swap the Day 1 lunch for a ramen place / 2日目の午後をカフェ巡りに変えて")
        if request:
            st.session_state["chat"].append({"role": "user", "content": request})
            with st.status("Updating the plan…", expanded=True) as status:
                def progress(step: str, msg: str) -> None:
                    st.markdown(f'<span class="label">{escape(step)}</span>&nbsp; {escape(msg)}',
                                unsafe_allow_html=True)
                try:
                    new = edit_plan(st.session_state["result"], request, st.session_state["destination"],
                                    st.session_state["budget"], progress=progress)
                    st.session_state["result"] = new
                    st.session_state["plan_version"] = st.session_state.get("plan_version", 0) + 1
                    st.session_state["chat"].append({"role": "assistant", "content": new["reply"]})
                    status.update(label="Plan updated", state="complete")
                except Exception as e:
                    st.session_state["chat"].append(
                        {"role": "assistant", "content": f"Sorry, I couldn't apply that change ({e}). The plan is unchanged."})
                    status.update(label="Edit failed", state="error")
            st.rerun()
