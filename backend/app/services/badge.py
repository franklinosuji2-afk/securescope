"""The public score badge: a small flat SVG with a fixed layout. Every value is escaped; no script, no font
files, no external resources."""

from __future__ import annotations

from html import escape

from app.repositories.integrations import BadgeReading

GRADE_COLOURS = {
    "A": "#1d7a54",
    "B": "#4a7c1f",
    "C": "#8a6d0b",
    "D": "#b35c00",
    "E": "#b3261e",
    "F": "#b3261e",
}
NEUTRAL = "#5b6770"
LABEL = "SecureScope"


def _width(text: str) -> int:
    # Close enough to Verdana 11px for a fixed layout; the box only has to fit the text.
    return int(len(text) * 6.6) + 12


def render_badge(reading: BadgeReading | None, *, available: bool = True) -> str:
    if not available:
        value, colour, note = "unavailable", NEUTRAL, "This badge is not available."
    elif reading is None:
        value, colour, note = "not scanned yet", NEUTRAL, "No completed scan yet."
    else:
        value = f"{reading.score}/100 · {reading.grade}"
        colour = GRADE_COLOURS.get(reading.grade, NEUTRAL)
        when = reading.scanned_at.strftime("%d %b %Y") if reading.scanned_at else "date unknown"
        note = f"Latest passive scan, {when}. A heuristic score, not proof of security."
    left, right = _width(LABEL), _width(value)
    total = left + right
    label_x = left * 5
    value_x = (left + right / 2) * 10
    aria = f"{LABEL}: {value}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" '
        f'aria-label="{escape(aria)}">'
        f"<title>{escape(aria)}. {escape(note)}</title>"
        f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)"><rect width="{left}" height="20" fill="#24303a"/>'
        f'<rect x="{left}" width="{right}" height="20" fill="{colour}"/>'
        f'<rect width="{total}" height="20" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        f'font-size="110" text-rendering="geometricPrecision">'
        f'<text x="{label_x}" y="140" transform="scale(.1)" textLength="{(left - 12) * 10}">{escape(LABEL)}</text>'
        f'<text x="{value_x:.0f}" y="140" transform="scale(.1)" textLength="{(right - 12) * 10}">'
        f"{escape(value)}</text></g></svg>"
    )
