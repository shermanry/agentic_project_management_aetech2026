"""Entity extraction for graph linking.

Embeddings link things that *mean* similar things; entities link things that
*name the same thing*. A Teams markup saying "north elevation, level 12" and a
PDF page about "North Elevation L12" share entities even if their vectors drift.
Values are normalised (lower-case, canonical spelling) so the graph can join on
exact matches: same entity value in two packages = candidate edge.
"""
from __future__ import annotations

import re

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_MONTH_FULL = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

PATTERNS: dict[str, re.Pattern] = {
    "rfi": re.compile(r"\bRFI[\s#-]*(\d{1,5})\b", re.I),
    "level": re.compile(r"\b(?:level|lvl|floor|storey|story)s?\s*(\d{1,3})(?:\s*(?:-|to|–)\s*(\d{1,3}))?\b|\bL(\d{1,3})\b", re.I),
    "elevation": re.compile(r"\b(north|south|east|west|n|s|e|w)[\s-]*(?:elevation|facade|façade|side|face)\b", re.I),
    "grid": re.compile(r"\bgrid(?:line)?\s*([A-Z]{1,2})\s*[-/]?\s*(\d{1,3})\b", re.I),
    # drawing sheets: discipline prefix + number (A-101, S201, AR-2001, FP-301)
    "sheet": re.compile(r"\b(A|AR|AD|S|ST|M|ME|E|EL|P|PL|C|CV|L|LA|FP|G|I|T)[-\s.]?(\d{3,4})\b"),
    "date": re.compile(rf"\b(\d{{4}}-\d{{2}}-\d{{2}})\b|\b(\d{{1,2}})\s+({_MONTH_FULL})\b|\b({_MONTH_FULL})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "regulation": re.compile(r"\b(part\s*107|laanc|tfr|notam|class\s*[a-g]\s*airspace)\b", re.I),
    "element": re.compile(r"\b(canopy|roof|parapet|facade|façade|curtain wall|mullion|fin|louvre|louver|cladding|balcony|"
                          r"entrance|lobby|podium|tower|dome|stair|core|column|beam|slab|window|door|atrium|terrace|"
                          r"crane|scaffold|antenna)s?\b", re.I),
}
_DIR = {"n": "north", "s": "south", "e": "east", "w": "west"}
_SHEET_STOP = {"RFI", "PDF", "MP", "ID", "AM", "PM"}


def _norm_month(m: str) -> str:
    return m[:3].lower()


def extract(text: str) -> dict[str, list[str]]:
    out: dict[str, set[str]] = {}

    def add(kind, value):
        out.setdefault(kind, set()).add(value)

    for m in PATTERNS["rfi"].finditer(text):
        add("rfi", f"rfi-{int(m[1]):03d}")
    for m in PATTERNS["level"].finditer(text):
        if m[3]:
            add("level", f"level-{int(m[3])}")
        elif m[2]:
            lo, hi = int(m[1]), int(m[2])
            for n in range(lo, min(hi, lo + 60) + 1):
                add("level", f"level-{n}")
        else:
            add("level", f"level-{int(m[1])}")
    for m in PATTERNS["elevation"].finditer(text):
        add("elevation", f"{_DIR.get(m[1].lower(), m[1].lower())}-elevation")
    for m in PATTERNS["grid"].finditer(text):
        add("grid", f"grid-{m[1].upper()}{m[2]}")
    for m in PATTERNS["sheet"].finditer(text):
        if m[1].upper() not in _SHEET_STOP:
            add("sheet", f"{m[1].upper()}-{m[2]}")
    for m in PATTERNS["date"].finditer(text):
        if m[1]:
            add("date", m[1])
        elif m[2]:
            add("date", f"{_norm_month(m[3])}-{int(m[2]):02d}")
        else:
            add("date", f"{_norm_month(m[4])}-{int(m[5]):02d}")
    for m in PATTERNS["email"].finditer(text):
        add("person", m[0].lower())
    for m in PATTERNS["regulation"].finditer(text):
        add("regulation", re.sub(r"\s+", " ", m[1].lower()))
    for m in PATTERNS["element"].finditer(text):
        add("element", m[1].lower().replace("façade", "facade").replace("louvre", "louver"))
    return {k: sorted(v) for k, v in sorted(out.items())}
