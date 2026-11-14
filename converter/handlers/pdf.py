"""PDF: text per page, a rendered image of every page (drawings are mostly visual),
and embedded raster images above a size threshold."""
from __future__ import annotations

from ..core import Chunk, Package
from ..engine import register, Context

MAX_PAGE_RENDERS = 60
PAGE_DPI = 110
MIN_EMBEDDED_IMAGE_PX = 300
MAX_EMBEDDED_IMAGES = 40


SKIP_ANNOTS = {"Link", "Widget", "Popup"}


def _annotations(pkg: Package, doc) -> None:
    """Bluebeam / Acrobat markups are structured: exact author, comment text, type and
    position. Each becomes a markup_region chunk (cropped image + text), with replies
    folded into the comment they answer."""
    from ..markup import position_words
    found = []
    for page in doc:
        annots = [a for a in page.annots() if a.type[1] not in SKIP_ANNOTS]
        by_xref = {a.xref: a for a in annots}
        replies: dict[int, list[str]] = {}
        for a in annots:
            irt = getattr(a, "irt_xref", 0)
            if irt and irt in by_xref:
                i = a.info
                replies.setdefault(irt, []).append(f"{i.get('title') or 'someone'}: {i.get('content', '').strip()}")
        for a in annots:
            if getattr(a, "irt_xref", 0) in by_xref:
                continue  # shown as a reply under its parent
            info = a.info
            author = (info.get("title") or "").strip()
            content = (info.get("content") or "").strip()
            subject = (info.get("subject") or a.type[1]).strip()
            date = _pdf_date(info.get("modDate") or info.get("creationDate") or "")
            rect = a.rect
            where = position_words((rect.x0, rect.y0, rect.x1, rect.y1), page.rect.width, page.rect.height)
            n = page.number + 1
            pad = 0.04 * max(page.rect.width, page.rect.height)
            clip = (rect + (-pad, -pad, pad, pad)) & page.rect
            rel = None
            if clip.width > 4 and clip.height > 4:
                rel = pkg.add_asset_bytes(f"annot_p{n:03d}_{a.xref}.png", page.get_pixmap(clip=clip, dpi=150).tobytes("png"))
            text = (f"{subject} markup on page {n} of '{pkg.title}' ({where})" + (f" by {author}" if author else "") +
                    (f" on {date}" if date else "") + (f": \"{content}\"" if content else "") +
                    ("".join(f" Reply from {r}" for r in replies.get(a.xref, []))) + ".")
            loc = {"page": n, "position": where, "bbox": [round(v, 1) for v in rect]}
            meta = {"annotation_type": a.type[1], "subject": subject, "author": author, "date": date}
            if rel:
                pkg.add_image(rel, text, role="markup_region", locator=loc, **meta)
            else:
                pkg.add(Chunk("text", text=text, role="markup_region", locator=loc, meta=meta))
            found.append({"page": n, "type": a.type[1], "subject": subject, "author": author, "date": date,
                          "content": content, "replies": replies.get(a.xref, [])})
    if found:
        pkg.metadata["annotations"] = found
        pkg.metadata["markup"] = {"regions": len(found), "method": "pdf-annotations",
                                  "authors": sorted({f["author"] for f in found if f["author"]})}
        pkg.tags.update({"markup", "change-request"})
        comments = [f for f in found if f["content"]]
        if comments:  # one chunk with every comment: the "what did reviewers say" vector
            pkg.add_text(f"Review comments on '{pkg.title}':\n" + "\n".join(
                f"p.{f['page']} {f['subject']} ({f['author'] or 'unknown'}): {f['content']}" for f in comments),
                role="markup")


def _pdf_date(s: str) -> str:
    s = s.removeprefix("D:")
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s[:8].isdigit() else ""


@register("document", ".pdf")
def convert_pdf(pkg: Package, ctx: Context) -> None:
    import pymupdf

    with pymupdf.open(pkg.source) as doc:
        _convert(pkg, doc)


def _convert(pkg: Package, doc) -> None:
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    pkg.metadata.update(pages=doc.page_count, **{f"pdf_{k}": v for k, v in meta.items()})
    if meta.get("title"):
        pkg.title = meta["title"]
    toc = doc.get_toc(simple=True)
    if toc:
        pkg.metadata["outline"] = [{"level": l, "title": t, "page": p} for l, t, p in toc[:200]]
        pkg.add_text("Table of contents:\n" + "\n".join(f"{'  ' * (l - 1)}{t} (p.{p})" for l, t, p in toc[:200]),
                     role="header")

    seen_xrefs: set[int] = set()
    embedded = 0
    text_pages = 0
    for i, page in enumerate(doc):
        n = i + 1
        text = page.get_text("text")
        if text.strip():
            text_pages += 1
            pkg.add_text(text, role="page", locator={"page": n})
        if i < MAX_PAGE_RENDERS:
            pix = page.get_pixmap(dpi=PAGE_DPI)
            rel = pkg.add_asset_bytes(f"page_{n:03d}.png", pix.tobytes("png"))
            hint = (text.strip().split("\n")[0][:120]) if text.strip() else "no extractable text (drawing or scan)"
            pkg.add_image(rel, f"Page {n} of {doc.page_count} of '{pkg.title}'. {hint}", role="page", locator={"page": n})
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen_xrefs or embedded >= MAX_EMBEDDED_IMAGES:
                continue
            seen_xrefs.add(xref)
            try:
                info = doc.extract_image(xref)
            except Exception:
                continue
            if min(info.get("width", 0), info.get("height", 0)) < MIN_EMBEDDED_IMAGE_PX:
                continue
            rel = pkg.add_asset_bytes(f"page_{n:03d}_img_{xref}.{info.get('ext', 'png')}", info["image"])
            pkg.add_image(rel, f"Image embedded on page {n} of '{pkg.title}'.", role="figure", locator={"page": n},
                          width=info.get("width"), height=info.get("height"))
            embedded += 1
    _annotations(pkg, doc)
    if doc.page_count > MAX_PAGE_RENDERS:
        pkg.warnings.append(f"only the first {MAX_PAGE_RENDERS} of {doc.page_count} pages were rendered as images")
    if text_pages == 0:
        pkg.warnings.append("no text layer found (scanned or vector drawing); page images included, OCR not run")
    pkg.metadata["pages_with_text"] = text_pages
    from ..engine import excerpt
    pkg.description = (f"PDF '{pkg.title}', {doc.page_count} page(s), {text_pages} with text, "
                       f"{embedded} embedded image(s). {excerpt(pkg)}").strip()
