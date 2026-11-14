"""Zip archives: every member becomes a child package; the zip itself becomes a
'folder' node that lists its contents."""
from __future__ import annotations

import zipfile
from pathlib import PurePosixPath

from ..core import Package
from ..engine import register, Context

MAX_MEMBERS = 200
MAX_MEMBER_BYTES = 500_000_000


@register("archive", ".zip")
def convert_zip(pkg: Package, ctx: Context) -> None:
    listing = []
    with zipfile.ZipFile(pkg.source) as z:
        members = [i for i in z.infolist() if not i.is_dir()
                   and not any(part.startswith(("__MACOSX", ".")) for part in PurePosixPath(i.filename).parts)]
        for info in members[:MAX_MEMBERS]:
            listing.append(f"{info.filename} ({info.file_size:,} bytes)")
            if info.file_size > MAX_MEMBER_BYTES:
                pkg.warnings.append(f"skipped {info.filename}: too large")
                continue
            ctx.convert_child(z.read(info), info.filename, pkg)  # keeps the folder path as the filename
        if len(members) > MAX_MEMBERS:
            pkg.warnings.append(f"only the first {MAX_MEMBERS} of {len(members)} files were converted")
    pkg.metadata["members"] = len(members)
    pkg.add_text(f"Archive '{pkg.original_name}' containing {len(members)} file(s):\n" + "\n".join(listing), role="header")
    pkg.description = f"Archive with {len(members)} file(s), each converted as a linked child package."
