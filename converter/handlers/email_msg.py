"""Email (.eml, Outlook .msg): headers become metadata, the body becomes text,
inline images become image chunks, and attachments become child packages
(so a PDF attached to an email gets its own node, linked to the email)."""
from __future__ import annotations

import email
import email.policy
import email.utils
import mimetypes
import re

from ..core import Package
from ..engine import register, Context
from ..markup import analyze

_QUOTE_SPLIT = re.compile(r"^(On .+ wrote:|-----Original Message-----|From: .+\nSent: .+)$", re.M)
IMAGE_MIME = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp")


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return soup.get_text("\n")


def _body_chunks(pkg: Package, body: str) -> None:
    """Latest message first, quoted thread history as separate chunks."""
    m = _QUOTE_SPLIT.search(body)
    if m and m.start() > 20:
        pkg.add_text(body[:m.start()], role="body", locator={"thread": "latest"})
        pkg.add_text(body[m.start():], role="quoted", locator={"thread": "history"})
    else:
        pkg.add_text(body, role="body")


def _finish(pkg: Package, h: dict, ctx: Context, attachments: list[tuple[str, bytes, str | None]]) -> None:
    pkg.title = h.get("subject") or pkg.title
    pkg.metadata.update({k: v for k, v in h.items() if v})
    header_text = "\n".join(f"{k.capitalize()}: {v}" for k, v in h.items() if v and k != "message_id")
    pkg.add_text(header_text, role="header")
    # the sender is the author of anything drawn on attached images
    pkg.context.setdefault("author", h.get("from"))
    pkg.context.setdefault("channel", "email")
    if h.get("date_iso") or h.get("date"):
        pkg.context.setdefault("date", (h.get("date_iso") or h.get("date"))[:10])
    message = next((c.text for c in pkg.chunks if c.role == "body"), "") or ""
    message = " ".join(message.split())[:500]
    markups = []
    for fname, data, mime in attachments:
        mime = mime or mimetypes.guess_type(fname)[0] or ""
        if mime.startswith("image/") and len(data) < 15_000_000:
            # images stay inside the email package: they are usually part of the message
            rel = pkg.add_asset_bytes(fname, data)
            label = f"Image '{fname}' attached to email '{pkg.title}' from {h.get('from', '?')}."
            chunk = pkg.add_image(rel, f"{label} Message: \"{message[:300]}\"" if message else label,
                                  role="attachment", filename=fname)
            try:
                from PIL import Image
                import io
                with Image.open(io.BytesIO(data)) as im:
                    im.load()
                    s = analyze(pkg, im, rel, label=label, message=message, chunk=chunk)
                if s:
                    markups.append({"file": fname, **s})
            except Exception as e:
                pkg.warnings.append(f"markup check failed for {fname}: {e}")
        else:
            ctx.convert_child(data, fname, pkg)
    if markups:
        pkg.metadata["markup"] = markups
        pkg.tags.update({"markup", "change-request"})
    pkg.metadata["attachments"] = [a[0] for a in attachments]
    pkg.description = (f"Email '{pkg.title}' from {h.get('from', '?')} to {h.get('to', '?')} on {h.get('date', '?')}, "
                       f"{len(attachments)} attachment(s).")


@register("email", ".eml")
def convert_eml(pkg: Package, ctx: Context) -> None:
    msg = email.message_from_bytes(pkg.source.read_bytes(), policy=email.policy.default)
    h = {
        "subject": str(msg.get("subject", "")), "from": str(msg.get("from", "")), "to": str(msg.get("to", "")),
        "cc": str(msg.get("cc", "")), "date": str(msg.get("date", "")), "message_id": str(msg.get("message-id", "")),
        "in_reply_to": str(msg.get("in-reply-to", "")),
    }
    try:
        dt = email.utils.parsedate_to_datetime(h["date"])
        h["date_iso"] = dt.isoformat()
    except Exception:
        pass
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is not None:
        content = body.get_content()
        _body_chunks(pkg, _html_to_text(content) if body.get_content_type() == "text/html" else content)
    attachments = []
    for part in msg.walk():
        if part.is_multipart() or part is body:
            continue
        disp = part.get_content_disposition()
        ctype = part.get_content_type()
        if disp in ("attachment", "inline") or ctype in IMAGE_MIME:
            data = part.get_payload(decode=True)
            if data:
                ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif"}.get(ctype, ".bin")
                attachments.append((part.get_filename() or f"part_{len(attachments) + 1}{ext}", data, ctype))
    _finish(pkg, h, ctx, attachments)


@register("email", ".msg")
def convert_msg(pkg: Package, ctx: Context) -> None:
    import extract_msg

    m = extract_msg.openMsg(str(pkg.source))
    try:
        h = {"subject": m.subject or "", "from": m.sender or "", "to": m.to or "", "cc": m.cc or "",
             "date": str(m.date or ""), "message_id": getattr(m, "messageId", "") or ""}
        if m.date is not None and hasattr(m.date, "isoformat"):
            h["date_iso"] = m.date.isoformat()
        body = m.body or ""
        if not body.strip() and m.htmlBody:
            raw = m.htmlBody
            body = _html_to_text(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
        _body_chunks(pkg, body)
        attachments = []
        for a in m.attachments:
            data = getattr(a, "data", None)
            if isinstance(data, (bytes, bytearray)):
                fname = a.longFilename or a.shortFilename or f"attachment_{len(attachments) + 1}.bin"
                attachments.append((fname, bytes(data), getattr(a, "mimetype", None)))
            else:  # embedded .msg (a forwarded email): save it and convert as a child
                try:
                    attachments.append((f"embedded_{len(attachments) + 1}.msg", a.data.exportBytes(), None))
                except Exception:
                    pkg.warnings.append("skipped an embedded item that could not be exported")
    finally:
        m.close()
    _finish(pkg, h, ctx, attachments)
