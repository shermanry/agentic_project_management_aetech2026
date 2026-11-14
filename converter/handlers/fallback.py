"""Unknown formats: keep the file referenced, extract text if it is mostly printable."""
from __future__ import annotations

from ..core import Package
from ..engine import Context
from .text import decode_bytes


def convert_unknown(pkg: Package, ctx: Context) -> None:
    raw = pkg.source.read_bytes()[:2_000_000]
    sample = raw[:8192]
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in sample) / max(len(sample), 1)
    if sample and printable > 0.9:
        pkg.kind = "text"
        pkg.add_text(decode_bytes(raw))
    else:
        pkg.warnings.append(f"no converter for '{pkg.source.suffix or 'no extension'}'; stored metadata only")
        pkg.description = f"Binary file {pkg.original_name} ({len(raw):,} bytes sampled). No converter available yet."
