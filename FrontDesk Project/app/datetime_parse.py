"""Strict booking date/time parser.

The weekday is ALWAYS derived from the validated calendar date (never guessed).
Anything unclear returns a clarification message instead of a silent default:
no fallback to "tomorrow", no default hour, no ambiguous 10/11 guessing.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MON = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
_ORD = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"

_log = logging.getLogger("frontdesk.booking")

DATE_HELP = "Please include the date, for example '10 November at 5pm' or '2026-11-10 17:00'."


def business_now(tz_name: str | None = None) -> datetime:
    """Current wall-clock time in the business timezone (naive)."""
    from app.config import settings

    name = tz_name or settings.business_timezone or "UTC"
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(name)).replace(tzinfo=None)
    except Exception:  # missing tzdata or bad name: fall back, but say so
        _log.warning("Timezone %r unavailable; using server local time", name)
        return datetime.now()


def _fmt(d: date) -> str:
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}"


def _make(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _explicit_date(text: str, today: date) -> Tuple[Optional[date], Optional[str], str]:
    """Return (date, error, text_without_date)."""
    def no_year(m: int, d: int, raw: str):
        cand = _make(today.year, m, d)
        if cand is None:
            # e.g. 29 February in a non-leap year: try next year only if valid there
            nxt = _make(today.year + 1, m, d)
            if nxt is None:
                return None, f"'{raw}' is not a valid calendar date."
            return nxt, None
        if cand < today:  # date already passed this year -> next occurrence
            cand = _make(today.year + 1, m, d)
            if cand is None:
                return None, f"'{raw}' is not a valid calendar date next year."
        return cand, None

    pats = [
        ("iso", rf"\b(\d{{4}})-(\d{{1,2}})-(\d{{1,2}})\b"),
        ("dmy", rf"\b{_ORD}\s+(?:of\s+)?{_MON}{_YEAR}\b"),
        ("mdy", rf"\b{_MON}\s+{_ORD}{_YEAR}\b"),
        ("num", r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?\b"),
    ]
    for kind, pat in pats:
        m = re.search(pat, text)
        if not m:
            continue
        raw = m.group(0).strip()
        rest = (text[:m.start()] + " " + text[m.end():])
        if kind == "iso":
            d = _make(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return (d, None if d else f"'{raw}' is not a valid calendar date.", rest)
        if kind in ("dmy", "mdy"):
            day_s, mon_s, year_s = (m.group(1), m.group(2), m.group(3)) if kind == "dmy" else (m.group(2), m.group(1), m.group(3))
            mon = _MONTHS[mon_s.rstrip(".")]
            if year_s:
                d = _make(int(year_s), mon, int(day_s))
                return (d, None if d else f"'{raw}' is not a valid calendar date.", rest)
            d, err = no_year(mon, int(day_s), raw)
            return d, err, rest
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a <= 12 and b <= 12 and a != b:
            return None, (f"'{raw}' is ambiguous (day/month order). Please write the month name, "
                          "e.g. '10 November' or '2026-11-10'."), rest
        day, mon = (a, b) if a > 12 or a == b else (b, a)
        if mon > 12:
            return None, f"'{raw}' is not a valid calendar date.", rest
        if y:
            year = int(y) + (2000 if len(y) == 2 else 0)
            d = _make(year, mon, day)
            return (d, None if d else f"'{raw}' is not a valid calendar date.", rest)
        d, err = no_year(mon, day, raw)
        return d, err, rest
    return None, None, text


def _time(text: str) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if re.search(r"\bnoon\b|\bmidday\b", text):
        return (12, 0), None
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", text)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)[0]
        if not 1 <= h <= 12 or mi > 59:
            return None, "Please give a valid time, for example '5pm' or '17:00'."
        if ap == "p" and h < 12:
            h += 12
        if ap == "a" and h == 12:
            h = 0
        return (h, mi), None
    m = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", text)
    if m:
        return (int(m.group(1)), int(m.group(2))), None
    if re.search(r"\bat\s+\d{1,2}\b", text):
        return None, "Please add AM/PM or use 24-hour time, for example '5pm' or '17:00'."
    return None, "Please include a time, for example '5pm' or '17:00'."


def parse_booking_datetime(text: str, now: datetime | None = None) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse a booking request. Returns (datetime, None) or (None, clarification)."""
    now = now or business_now()
    today = now.date()
    t = re.sub(r"\s+", " ", (text or "").lower()).strip()

    d, err, rest = _explicit_date(t, today)
    if err:
        return None, err
    relative = None
    if re.search(r"\bday after tomorrow\b", rest):
        relative = today + timedelta(days=2)
        rest = re.sub(r"\b(the )?day after tomorrow\b", " ", rest)
    elif re.search(r"\btomorrow\b", rest):
        relative = today + timedelta(days=1)
        rest = re.sub(r"\btomorrow\b", " ", rest)
    elif re.search(r"\btoday\b|\btonight\b", rest):
        relative = today
        rest = re.sub(r"\btoday\b|\btonight\b", " ", rest)

    weekday = next((i for i, n in enumerate(DAY_NAMES)
                    if re.search(rf"\b{n}\b|\b{n[:3]}\b", rest)), None)

    if d and relative and d != relative:
        return None, f"{_fmt(d)} does not match the relative day you wrote ({_fmt(relative)}). Which date did you mean?"
    d = d or relative
    if weekday is not None:
        if d is not None:
            if d.weekday() != weekday:
                return None, (f"{_fmt(d)} is a {d.strftime('%A')}, not a {DAY_NAMES[weekday].title()}. "
                              "Please confirm the date you want.")
        else:
            ahead = (weekday - today.weekday()) % 7 or 7
            d = today + timedelta(days=ahead)
    if d is None:
        return None, DATE_HELP

    hm, terr = _time(rest)
    if terr:
        return None, terr
    dt = datetime.combine(d, datetime.min.time()).replace(hour=hm[0], minute=hm[1])
    if dt <= now:
        return None, f"{_fmt(d)} at {dt.strftime('%I:%M %p').lstrip('0')} has already passed. Please choose a future time."
    return dt, None
