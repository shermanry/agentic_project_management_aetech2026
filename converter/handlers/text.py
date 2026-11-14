"""Plain text, markdown, csv, json, html, xml."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ..core import Package
from ..engine import register, Context


def read_text(path: Path) -> str:
    return decode_bytes(path.read_bytes())


def decode_bytes(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


@register("text", ".txt", ".md", ".markdown", ".log", ".rst", ".ini", ".yaml", ".yml", ".srt", ".vtt")
def convert_text(pkg: Package, ctx: Context) -> None:
    text = read_text(pkg.source)
    if pkg.source.suffix.lower() in (".md", ".markdown"):
        _markdown_sections(pkg, text)
    else:
        pkg.add_text(text)
    pkg.metadata["characters"] = len(text)
    pkg.metadata["lines"] = text.count("\n") + 1


def _markdown_sections(pkg: Package, text: str) -> None:
    """Split markdown on headings so each section can become its own suggested node."""
    section, heading = [], None
    for line in text.splitlines():
        if line.startswith("#"):
            if section:
                pkg.add_text("\n".join(section), locator={"section": heading} if heading else None)
            heading, section = line.lstrip("#").strip(), [line]
        else:
            section.append(line)
    if section:
        pkg.add_text("\n".join(section), locator={"section": heading} if heading else None)
    first_h1 = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), None)
    if first_h1:
        pkg.title = first_h1


@register("table", ".csv", ".tsv")
def convert_csv(pkg: Package, ctx: Context) -> None:
    text = read_text(pkg.source)
    delim = "\t" if pkg.source.suffix.lower() == ".tsv" else (csv.Sniffer().sniff(text[:4096]).delimiter if text else ",")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    pkg.metadata.update(rows=len(rows), columns=(rows[0] if rows else []))
    add_table(pkg, rows)


def add_table(pkg: Package, rows: list[list], locator: dict | None = None, rows_per_chunk: int = 40) -> None:
    """Tables become 'header + N rows' chunks so each chunk is self-describing."""
    rows = [[("" if c is None else str(c)) for c in r] for r in rows if any(c not in (None, "") for c in r)]
    if not rows:
        return
    header, body = rows[0], rows[1:]
    head_line = " | ".join(header)
    if not body:
        pkg.add_text(head_line, role="table", locator=locator)
        return
    for i in range(0, len(body), rows_per_chunk):
        block = body[i:i + rows_per_chunk]
        lines = [head_line, " | ".join("---" for _ in header)] + [" | ".join(r) for r in block]
        loc = dict(locator or {}, rows=f"{i + 2}-{i + 1 + len(block)}")
        pkg.add_text("\n".join(lines), role="table", locator=loc)


@register("data", ".json", ".geojson")
def convert_json(pkg: Package, ctx: Context) -> None:
    text = read_text(pkg.source)
    try:
        data = json.loads(text)
        pkg.metadata["json_top_level"] = type(data).__name__
        if isinstance(data, dict):
            pkg.metadata["json_keys"] = list(data)[:50]
        elif isinstance(data, list):
            pkg.metadata["json_items"] = len(data)
        text = json.dumps(data, indent=1, ensure_ascii=False)
    except json.JSONDecodeError as e:
        pkg.warnings.append(f"invalid JSON: {e}")
    pkg.add_text(text)


@register("web", ".html", ".htm", ".xml")
def convert_html(pkg: Package, ctx: Context) -> None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(read_text(pkg.source), "html.parser")  # stdlib parser handles xml well enough
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    if soup.title and soup.title.string:
        pkg.title = soup.title.string.strip()
    links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
    if links:
        pkg.metadata["links"] = links[:100]
    pkg.add_text(soup.get_text("\n"))
