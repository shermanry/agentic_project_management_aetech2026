"""Word, PowerPoint, Excel. Text keeps its structure (headings -> sections,
slides -> slides, sheets -> tables); embedded media is pulled out as images."""
from __future__ import annotations

import zipfile
from pathlib import PurePosixPath

from ..core import Package
from ..engine import register, Context
from .text import add_table

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
MAX_MEDIA = 40


def _core_props(pkg: Package, props) -> None:
    for k in ("title", "author", "subject", "keywords", "last_modified_by", "created", "modified", "category"):
        v = getattr(props, k, None)
        if v:
            pkg.metadata[k] = v
    if getattr(props, "title", None):
        pkg.title = props.title


def _media(pkg: Package, prefix: str, label: str) -> int:
    """Extract images stored in the OOXML zip under e.g. word/media/."""
    n = 0
    with zipfile.ZipFile(pkg.source) as z:
        for name in z.namelist():
            p = PurePosixPath(name)
            if name.startswith(prefix) and p.suffix.lower() in IMAGE_EXT and n < MAX_MEDIA:
                data = z.read(name)
                if len(data) < 4_000:  # icons, bullets
                    continue
                rel = pkg.add_asset_bytes(p.name, data)
                pkg.add_image(rel, f"Image '{p.name}' embedded in {label} '{pkg.title}'.", role="figure")
                n += 1
    return n


@register("document", ".docx")
def convert_docx(pkg: Package, ctx: Context) -> None:
    import docx

    d = docx.Document(pkg.source)
    _core_props(pkg, d.core_properties)
    heading, buf, sections = None, [], 0

    def flush():
        nonlocal sections
        if buf:
            pkg.add_text("\n".join(buf), locator={"section": heading} if heading else None)
            sections += 1

    for para in d.paragraphs:
        style = (para.style.name or "").lower() if para.style is not None else ""
        if style.startswith("heading") or style == "title":
            flush()
            heading, buf = para.text.strip(), [para.text.strip()]
        elif para.text.strip():
            buf.append(para.text)
    flush()
    for ti, table in enumerate(d.tables):
        rows = [[c.text.strip() for c in r.cells] for r in table.rows]
        add_table(pkg, rows, locator={"table": ti + 1})
    imgs = _media(pkg, "word/media/", "document")
    pkg.metadata.update(sections=sections, tables=len(d.tables), images=imgs)


@register("presentation", ".pptx")
def convert_pptx(pkg: Package, ctx: Context) -> None:
    from pptx import Presentation

    prs = Presentation(pkg.source)
    _core_props(pkg, prs.core_properties)
    for i, slide in enumerate(prs.slides, 1):
        lines = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for r in shape.table.rows:
                    lines.append(" | ".join(c.text for c in r.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            lines.append("Speaker notes: " + slide.notes_slide.notes_text_frame.text.strip())
        if lines:
            pkg.add_text(f"Slide {i}\n" + "\n".join(lines), role="slide", locator={"slide": i})
    imgs = _media(pkg, "ppt/media/", "presentation")
    pkg.metadata.update(slides=len(prs.slides), images=imgs)
    pkg.warnings.append("slides are not rendered to images (needs PowerPoint/LibreOffice); embedded media extracted instead")


@register("spreadsheet", ".xlsx", ".xlsm")
def convert_xlsx(pkg: Package, ctx: Context) -> None:
    import openpyxl

    wb = openpyxl.load_workbook(pkg.source, read_only=True, data_only=True)
    _core_props(pkg, wb.properties)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append(list(r))
            if len(rows) >= 2000:
                pkg.warnings.append(f"sheet '{ws.title}' truncated at 2000 rows")
                break
        sheets.append({"name": ws.title, "rows": len(rows)})
        add_table(pkg, rows, locator={"sheet": ws.title})
    wb.close()
    pkg.metadata["sheets"] = sheets
