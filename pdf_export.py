"""Printable / phone-friendly PDF of a TripPilot plan (A4, paper & ink style, Japanese-safe)."""

import io
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from editing import end_time

INK, MUTED, FAINT, UMBER, PAPER = (colors.HexColor(c) for c in ("#1c1b19", "#6f6a60", "#d9d4c7", "#8a4b14", "#f6f4ee"))
# IPA P Gothic is embedded (subset) so Japanese renders on every phone and viewer. License: assets/fonts.
SERIF = SANS = "IPAPGothic"
pdfmetrics.registerFont(TTFont(SANS, str(Path(__file__).parent / "assets" / "fonts" / "ipagp.ttf")))

LOGO = Path(__file__).parent / "assets" / "logo.png"
CAT = {"food": "Food", "cafe": "Café", "sightseeing": "Sight", "nature": "Nature",
       "shopping": "Shop", "nightlife": "Night", "other": "Other"}

S = {
    "title": ParagraphStyle("title", fontName=SERIF, fontSize=24, leading=28, textColor=INK),
    "summary": ParagraphStyle("summary", fontName=SERIF, fontSize=10.5, leading=15, textColor=MUTED),
    "label": ParagraphStyle("label", fontName="Helvetica", fontSize=7, leading=9, textColor=MUTED),
    "value": ParagraphStyle("value", fontName="Helvetica", fontSize=14, leading=17, textColor=INK),
    "h2": ParagraphStyle("h2", fontName=SERIF, fontSize=14, leading=18, textColor=INK, spaceBefore=10),
    "place": ParagraphStyle("place", fontName=SERIF, fontSize=11, leading=14, textColor=INK),
    "body": ParagraphStyle("body", fontName=SERIF, fontSize=8.5, leading=12, textColor=INK),
    "small": ParagraphStyle("small", fontName=SANS, fontSize=7, leading=10, textColor=MUTED),
    "time": ParagraphStyle("time", fontName="Helvetica", fontSize=9, leading=12, textColor=INK),
}


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text or "")), S[style])


def _domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def _link(url: str, label: str) -> str:
    return f'<link href="{escape(url)}" color="#1c1b19"><u>{escape(label)}</u></link>'


def _money(x) -> str:
    return f"{x:,.0f}" if isinstance(x, (int, float)) else "–"


def build_pdf(result: dict, destination: str, budget_limit: float, currency: str) -> bytes:
    plan = result["plan"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"TripPilot · {plan.get('destination', destination)}", author="TripPilot")
    W = doc.width
    story = []

    # Masthead
    head = [[Image(str(LOGO), 14 * mm, 14 * mm) if LOGO.exists() else "",
             [_p("TRIPPILOT · ITINERARY", "label"), _p(plan.get("destination") or destination, "title")]]]
    t = Table(head, colWidths=[18 * mm, W - 18 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 4 * mm), _p(plan.get("summary", ""), "summary"), Spacer(1, 5 * mm)]
    if result.get("mode") != "live":
        story += [_p("DEMO DATA — NOT LIVE SEARCH", "label"), Spacer(1, 3 * mm)]

    # Ledger
    b, v = plan.get("budget", {}), plan.get("verification", {})
    total = b.get("estimated_total") or 0
    official = sum(1 for s in result.get("sources", []) if s.get("kind") == "official")
    cells = [
        ("ESTIMATED SPEND", f"{_money(total)} {b.get('currency', currency)}"),
        ("BUDGET", f"{_money(budget_limit)} {currency}"),
        ("SOURCES READ", f"{len(result.get('sources', []))}  ({official} official)"),
        ("STOPS SOURCED", f"{v.get('grounded', 0)}/{v.get('activities', 0)}"),
    ]
    ledger = Table([[[_p(k, "label"), _p(val, "value")] for k, val in cells]], colWidths=[W / 4] * 4)
    ledger.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBEFORE", (1, 0), (-1, 0), 0.4, FAINT), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (0, 0), 0)]))
    story += [ledger, Spacer(1, 4 * mm)]

    # Days
    for d in plan.get("days", []):
        story.append(_p(f"Day {d.get('day')}" + (f" — {d['theme']}" if d.get("theme") else ""), "h2"))
        rows = []
        for a in d.get("activities", []):
            meta = [CAT.get(a.get("category"), "Other")]
            if a.get("duration_minutes"):
                meta.append(f"{a['duration_minutes']} min")
            if a.get("opening_hours"):
                meta.append(f"Hours {a['opening_hours']}")
            if a.get("user_edited"):
                meta.append("Edited by you")
            stop = [Paragraph(f"<b>{escape(a.get('place', ''))}</b>", S["place"]),
                    _p(a.get("description", ""), "body"), _p(" · ".join(meta), "small")]
            src = []
            if a.get("official_url"):
                src.append(Paragraph("Official: " + _link(a["official_url"], _domain(a["official_url"])), S["small"]))
            if a.get("source_url") and a.get("source_url") != a.get("official_url"):
                src.append(Paragraph(_link(a["source_url"], _domain(a["source_url"])), S["small"]))
            if not src:
                src.append(Paragraph('<font color="#8a4b14">Unverified — check before going</font>', S["small"]))
            cost = a.get("estimated_cost")
            cost_txt = "not stated" if cost is None else (
                f"{_money(cost)} (source)" if a.get("cost_verified") else f"≈ {_money(cost)}")
            rows.append([_p(a.get("time", "") + (f"\n– {end_time(a)}" if end_time(a) else ""), "time"),
                         stop, _p(cost_txt, "small"), src])
        if rows:
            tbl = Table(rows, colWidths=[20 * mm, W - 20 * mm - 24 * mm - 40 * mm, 24 * mm, 40 * mm])
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, FAINT),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (0, -1), 0)]))
            story.append(tbl)

    # Budget, notes, checks
    def section(title, items):
        if items:
            story.append(KeepTogether([_p(title, "h2")] + [_p("• " + i, "body") for i in items]))

    breakdown = [f"{i.get('category')}: {_money(i.get('amount'))}" for i in b.get("breakdown", [])]
    section("Budget", breakdown + ([b["notes"]] if b.get("notes") else []))
    section("Check before you go", plan.get("unverified_notes", []))
    section("Notes", plan.get("tips", []))

    # Sources
    src = result.get("sources", [])
    if src:
        story.append(_p(f"Sources ({len(src)})", "h2"))
        for i, s in enumerate(src, 1):
            tag = "OFFICIAL · " if s.get("kind") == "official" else ""
            story.append(Paragraph(f"{i}. {tag}{_link(s['url'], s.get('title') or s['url'])}"
                                   f' <font color="#6f6a60">{escape(_domain(s["url"]))}</font>', S["small"]))

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9 * mm, "TripPilot — itineraries drawn from real sources")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, str(_doc.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
