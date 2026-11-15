"""Markups: images where someone drew on a render/photo/drawing to ask for a change.

Two ways to find what was drawn, both local (OpenCV, no AI):
  1. diff against the original: if the library already holds the un-annotated image
     (perceptual hash match), whatever changed is the markup - precise.
  2. colour strokes: markups are thin, saturated red/magenta/yellow/green/blue
     strokes that are rare in the rest of the image - works on screenshots too.

Each marked area becomes its own image chunk whose text says who asked, what they
said, where on the image it is, and which original it refers to - so a search for
"canopy" or "north elevation" lands on the exact circle. The manifest records a plain
fact (`drawn_on`) about which original the strokes were drawn on.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .core import Package

ANALYSIS_SIDE = 1024
MAX_REGIONS = 12
HASH_MATCH_MAX = 14       # of 64 bits; markups change some pixels, re-saves change a few


# ------------------------------------------------------------------ perceptual hash
def dhash(img: Image.Image) -> str:
    g = np.asarray(img.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def dhash_file(path: Path) -> str:
    with Image.open(path) as im:
        return dhash(im)


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _is_markup_package(d: Path) -> bool:
    try:
        return json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("kind") == "markup"
    except (OSError, ValueError):
        return False


def find_original_by_features(pkg: Package, img: Image.Image) -> dict | None:
    """Fallback for screenshots (Teams/Slack UI around the picture, cropped, rescaled) where
    the hash can't match: try feature alignment against our own model views only."""
    a, _ = _to_cv(img)
    best = None
    for chunks in pkg.out_root.glob("uep_*/chunks.jsonl"):
        if chunks.parent.name == pkg.id:
            continue
        for line in chunks.read_text(encoding="utf-8").splitlines():
            if '"role": "snapshot"' not in line or '"layer"' in line:
                continue
            c = json.loads(line)
            try:
                with Image.open(chunks.parent / c["asset"]) as o:
                    al = _align(a, o)
                    if al is None or al[3] != "aligned-diff":
                        continue
                    cover = al[1].mean()
            except Exception:
                continue
            if cover > 0.3 and (best is None or cover > best["cover"]):
                m = json.loads((chunks.parent / "manifest.json").read_text(encoding="utf-8"))
                best = {"package_id": c["package_id"], "chunk_id": c["id"], "asset": c["asset"], "distance": None,
                        "caption": c["text"], "title": m["title"], "kind": m["kind"], "cover": round(cover, 2),
                        "matched_by": "features"}
    return best


def _pixel_distance(img: Image.Image, path: Path) -> float:
    """Mean grey-level difference at thumbnail size: separates near-identical views
    (e.g. the same model view with different layers highlighted) that dhash can't."""
    with Image.open(path) as o:
        if not same_framing(img, o):
            return 1.0
        a = np.asarray(img.convert("L").resize((96, 72)), dtype=float)
        b = np.asarray(o.convert("L").resize((96, 72)), dtype=float)
    return float(np.abs(a - b).mean() / 255)


def find_original(pkg: Package, h: str, img: Image.Image | None = None) -> dict | None:
    """Nearest image chunk in *other* packages of the library (excluding exact copies)."""
    candidates = []
    for chunks in pkg.out_root.glob("uep_*/chunks.jsonl"):
        if chunks.parent.name == pkg.id or _is_markup_package(chunks.parent):
            continue  # an original is never itself a markup (that gave titles like "Markup on Markup on …")
        try:
            lines = chunks.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"modality": "image"' not in line:
                continue
            c = json.loads(line)
            if c["role"] in ("markup", "markup_region") or not c.get("asset") or c["meta"].get("suggested_by"):
                continue  # only original content: no markups, no crops/figures the AI added
            ch = c["meta"].get("dhash")
            if not ch:  # packages converted before hashes existed
                try:
                    ch = dhash_file(chunks.parent / c["asset"])
                except Exception:
                    continue
            d = hamming(h, ch)
            if 0 < d <= HASH_MATCH_MAX:
                candidates.append({"package_id": c["package_id"], "chunk_id": c["id"], "asset": c["asset"],
                                   "distance": d, "caption": c["text"]})
    if not candidates:
        return None
    candidates.sort(key=lambda c: c["distance"])
    if img is not None and len(candidates) > 1:
        close = [c for c in candidates if c["distance"] <= candidates[0]["distance"] + 4][:20]
        best = min(close, key=lambda c: _pixel_distance(img, pkg.out_root / c["package_id"] / c["asset"]))
    else:
        best = candidates[0]
    if best:
        try:
            m = json.loads((pkg.out_root / best["package_id"] / "manifest.json").read_text(encoding="utf-8"))
            best["title"] = m["title"]
            best["kind"] = m["kind"]
        except Exception:
            pass
    return best


# ------------------------------------------------------------------ region detection
def _to_cv(img: Image.Image, side: int = ANALYSIS_SIDE):
    im = img.convert("RGB")
    s = side / max(im.size)
    if s < 1:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    return np.asarray(im), min(s, 1.0)


def _boxes_from_mask(mask: np.ndarray, min_area_frac: float, max_fill: float | None):
    import cv2
    h, w = mask.shape
    k = max(3, int(round(max(h, w) / 120)))
    grown = cv2.dilate(mask, np.ones((k, k), np.uint8), iterations=2)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(grown, 8)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw * bh < min_area_frac * w * h:
            continue
        stroke = mask[y:y + bh, x:x + bw].mean() / 255
        if max_fill is not None and stroke > max_fill:   # solid blob = a red object in the photo, not a pen stroke
            continue
        boxes.append([x, y, x + bw, y + bh, float(stroke)])
    return _merge(boxes, pad=k * 2)


def _merge(boxes, pad):
    boxes = sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    merged = []
    for b in boxes:
        for m in merged:
            if b[0] < m[2] + pad and b[2] > m[0] - pad and b[1] < m[3] + pad and b[3] > m[1] - pad:
                m[0], m[1], m[2], m[3] = min(m[0], b[0]), min(m[1], b[1]), max(m[2], b[2]), max(m[3], b[3])
                break
        else:
            merged.append(list(b))
    return merged[:MAX_REGIONS]


def detect_by_colour(img: Image.Image) -> tuple[list[dict], float]:
    """Saturated pen-like strokes in a colour that is rare in the image."""
    import cv2
    rgb, s = _to_cv(img)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hch, sat, val = hsv[..., 0].astype(int), hsv[..., 1], hsv[..., 2]
    vivid = (sat > 140) & (val > 110)
    total = vivid.size
    regions = []
    # Markup pens are overwhelmingly red / magenta. Greens and blues are too common in renders
    # (ground, glass, sky) to be told apart without the original; use diff mode for those.
    for lo, hi, name in [(0, 8, "red"), (168, 180, "red"), (140, 168, "magenta")]:
        m = vivid & (hch >= lo) & (hch < hi)
        frac = m.sum() / total
        if frac < 0.0004 or frac > 0.08:
            continue
        for x0, y0, x1, y1, stroke in _boxes_from_mask(m.astype(np.uint8) * 255, 0.0015, max_fill=0.45):
            regions.append({"bbox": [round(x0 / s), round(y0 / s), round(x1 / s), round(y1 / s)], "colour": name,
                            "method": "colour"})
    out = regions[:MAX_REGIONS]
    score = sum(((r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1])) for r in out) / (img.width * img.height)
    return out, score


def colour_name(rgb_pixels: np.ndarray) -> str:
    """Name of the dominant stroke colour (mean of vivid pixels; avoids hue wrap-around at red)."""
    import colorsys
    px = rgb_pixels.reshape(-1, 3).astype(float) / 255
    if not len(px):
        return "?"
    sat = px.max(1) - px.min(1)
    for t in (0.5, 0.3, 0.0):  # the pen colour itself, not anti-aliased edges blended with the background
        vivid = px[sat > t]
        if len(vivid) > 10:
            break
    r, g, b = np.median(vivid, axis=0)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.2:
        return "black" if l < 0.3 else ("white" if l > 0.85 else "grey")
    deg = h * 360
    for limit, name in [(15, "red"), (40, "orange"), (70, "yellow"), (160, "green"), (200, "cyan"), (255, "blue"),
                        (330, "magenta"), (361, "red")]:
        if deg < limit:
            return name
    return "red"


def same_framing(img: Image.Image, original: Image.Image) -> bool:
    ra, rb = img.width / img.height, original.width / original.height
    return abs(ra - rb) / rb < 0.02


def _align(a: np.ndarray, original: Image.Image):
    """Warp the original into the frame of the (possibly cropped / rescaled / screenshotted)
    markup image. Returns (warped original, valid-pixel mask, 3x3 map markup->original px) or None."""
    import cv2
    ow, oh = original.size
    h, w = a.shape[:2]
    if same_framing(Image.new("1", (w, h)), original):
        b = np.asarray(original.convert("RGB").resize((w, h), Image.LANCZOS))
        changed = (np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 48).mean()
        if changed < 0.12:  # same aspect AND the pixels line up -> plain diff
            return b, np.ones((h, w), bool), np.diag([ow / w, oh / h, 1.0]), "diff"
    o, so = _to_cv(original)
    g1, g2 = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(o, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(5000)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < 30 or len(k2) < 30:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d2, d1, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 25:
        return None
    src = np.float32([k2[m.queryIdx].pt for m in good])
    dst = np.float32([k1[m.trainIdx].pt for m in good])
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is None or inl.sum() < 20:
        return None
    b = cv2.warpPerspective(o, H, (w, h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    valid = cv2.warpPerspective(np.ones(o.shape[:2], np.uint8), H, (w, h)) > 0
    valid = cv2.erode(valid.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    # markup px -> original analysis px -> original full-res px
    to_orig = np.diag([1 / so, 1 / so, 1.0]) @ np.linalg.inv(H)
    return b, valid, to_orig, "aligned-diff"


def detect_by_diff(img: Image.Image, original: Image.Image) -> list[dict]:
    """Pixels that differ from the (aligned) original = what was drawn."""
    import cv2
    a, s = _to_cv(img)
    al = _align(a, original)
    if al is None:
        return []
    b, valid, to_orig, method = al
    if valid.mean() < 0.3:
        return []
    d = cv2.absdiff(a, b).max(axis=2)
    if method == "aligned-diff":  # resampling blur: compare slightly blurred versions
        d = cv2.absdiff(cv2.GaussianBlur(a, (5, 5), 0), cv2.GaussianBlur(b, (5, 5), 0)).max(axis=2)
    d = cv2.GaussianBlur(d, (3, 3), 0)
    if method == "aligned-diff":
        # Only trust differences inside areas that otherwise agree with the original. A screenshot
        # usually shows a crop, so the warped original overhangs the picture edge into chat UI:
        # that whole band differs, while real pen strokes are thin lines in agreeing surroundings.
        agree = (d < 30).astype(np.float32)
        k = max(15, (max(a.shape[:2]) // 25) | 1)
        valid = valid & (cv2.blur(agree, (k, k)) > 0.6)
    mask = ((d > (48 if method == "diff" else 64)) & valid).astype(np.uint8) * 255
    # anything whose centre sits on the edge of the matched area is a crop/registration artefact
    inner = cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0 if method == "aligned-diff" else None
    if mask[valid].mean() / 255 > 0.12:   # most pixels changed: a different image, not a markup layer
        return []
    out = []
    for x0, y0, x1, y1, _ in _boxes_from_mask(mask, 0.0008, max_fill=None):
        pm = mask[int(y0):int(y1), int(x0):int(x1)] > 0
        if inner is not None and pm.any():
            ys, xs = np.nonzero(pm)
            if (~inner[int(y0) + ys, int(x0) + xs]).mean() > 0.3:
                continue
        patch = a[int(y0):int(y1), int(x0):int(x1)]
        colour = colour_name(patch[pm]) if pm.any() else "?"
        corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], float).T
        oc = to_orig @ corners
        oc = oc[:2] / oc[2]
        out.append({"bbox": [round(x0 / s), round(y0 / s), round(x1 / s), round(y1 / s)], "colour": colour,
                    "method": method,
                    "bbox_original": [round(float(oc[0].min())), round(float(oc[1].min())),
                                      round(float(oc[0].max())), round(float(oc[1].max()))]})
    return out


def position_words(bbox, w, h) -> str:
    cx, cy = (bbox[0] + bbox[2]) / 2 / w, (bbox[1] + bbox[3]) / 2 / h
    v = "top" if cy < 1 / 3 else ("bottom" if cy > 2 / 3 else "middle")
    hz = "left" if cx < 1 / 3 else ("right" if cx > 2 / 3 else "centre")
    return "centre" if (v, hz) == ("middle", "centre") else f"{v}-{hz}"


# ------------------------------------------------------------------ main entry
def analyze(pkg: Package, img: Image.Image, rel_asset: str, label: str, message: str = "",
            force: bool = False, chunk=None) -> dict | None:
    """Detect markup on `img` (already stored at rel_asset). Adds region chunks to pkg and
    enriches the full-image chunk caption. Returns a summary dict, or None if no markup."""
    h = dhash(img)
    original = None
    ref = pkg.context.get("refers_to")
    if ref and ref != pkg.id:
        original = _load_ref(pkg, ref)
    if original is None:
        original = find_original(pkg, h, img)

    if original is None:
        original = find_original_by_features(pkg, img)

    regions = []
    aligned = False
    orig_size = img.size
    if original:
        try:
            with Image.open(pkg.out_root / original["package_id"] / original["asset"]) as base:
                orig_size = base.size
                regions = detect_by_diff(img, base)
                aligned = bool(regions)
        except Exception as e:
            pkg.warnings.append(f"diff against original failed: {e}")
            regions = []
    if not regions:
        regions, score = detect_by_colour(img)
        if score > 0.6:          # "markup" covering most of the picture = it's just a colourful image
            regions = []
    if not regions and not force:
        return None

    who = pkg.who()
    said = message or pkg.context.get("note", "")
    base_txt = f" on {original.get('title', original['package_id'])}" if original else ""
    if original and "view" in original.get("caption", "").lower():
        first = original["caption"].split(". ")[0]
        base_txt = f" on {first[0].lower()}{first[1:]}"
    # markup drawn exactly on one of our Rhino views: which model layers sit under each mark?
    layer_maps = _layer_maps(pkg, original) if (original and aligned) else {}
    for r in regions:
        r["layers"] = _layers_under(layer_maps, r.get("bbox_original", r["bbox"]), orig_size)
    places = [f"{position_words(r['bbox'], img.width, img.height)} ({r['colour']})" for r in regions]
    head = (f"Marked-up image{base_txt}" + (f" from {who}" if who else "") +
            (f". They wrote: \"{said}\"" if said else "") +
            (f". {len(regions)} marked area(s): {', '.join(places)}." if regions else "."))
    if chunk is not None:
        chunk.role = "markup"
        chunk.text = f"{head} {label}"

    for i, r in enumerate(regions, 1):
        x0, y0, x1, y1 = r["bbox"]
        pad = int(0.06 * max(img.width, img.height))
        box = (max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad))
        crop = img.convert("RGB").crop(box)
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=90)
        rel = pkg.add_asset_bytes(f"markup_region_{i:02d}.jpg", buf.getvalue())
        where = position_words(r["bbox"], img.width, img.height)
        layers_txt = f", covering model layer(s) {', '.join(r['layers'])}" if r.get("layers") else ""
        txt = (f"Markup area {i} of {len(regions)}, {where} of the image{base_txt}{layers_txt}, drawn in {r['colour']}" +
               (f", by {who}" if who else "") + (f". Request: \"{said}\"" if said else "") + ".")
        loc = {"region": i, "bbox": r["bbox"], "position": where, "source_asset": rel_asset}
        if r.get("layers"):
            loc["layers"] = r["layers"]
        pkg.add_image(rel, txt, role="markup_region", locator=loc, colour=r["colour"], method=r["method"])

    summary = {"regions": len(regions), "positions": [position_words(r["bbox"], img.width, img.height) for r in regions],
               "colours": sorted({r["colour"] for r in regions}), "method": regions[0]["method"] if regions else "manual",
               "markup_text": "pending: handwriting/typed notes need OCR or a vision model downstream"}
    layers = sorted({l for r in regions for l in r.get("layers", [])})
    if layers:
        summary["layers"] = layers
    if original:
        # a fact about this image (what it was drawn on), used to cut out the pen strokes precisely; not a graph link
        summary["drawn_on"] = {k: original[k] for k in ("package_id", "chunk_id", "title") if k in original}
    return summary


def _layer_maps(pkg: Package, original: dict) -> dict[str, np.ndarray]:
    """For a Rhino axonometric view: {layer path: boolean mask of where that layer is drawn},
    read from the per-layer highlight renders (accent colour = the layer)."""
    if original.get("kind") != "rhino_model" or not original["asset"].endswith("view_axonometric.png"):
        return {}
    from .handlers.rhino import ACCENT
    maps = {}
    for line in (pkg.out_root / original["package_id"] / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        layer = c.get("locator", {}).get("layer")
        if c["modality"] == "image" and layer and c["locator"].get("view") == "axonometric":
            with Image.open(pkg.out_root / original["package_id"] / c["asset"]) as im:
                a = np.asarray(im.convert("RGB").resize((320, 240)), dtype=int)
            # accent pixels, shaded: hue close to the accent, clearly saturated
            r, g, b = a[..., 0], a[..., 1], a[..., 2]
            maps[layer] = (r > g + 40) & (g > b + 15) & (r > 90)
    return maps


def _layers_under(maps: dict, bbox, size) -> list[str]:
    if not maps:
        return []
    W, H = size
    x0, y0, x1, y1 = (int(bbox[0] / W * 320), int(bbox[1] / H * 240), int(bbox[2] / W * 320) + 1, int(bbox[3] / H * 240) + 1)
    hits = []
    for layer, m in maps.items():
        share = m[y0:y1, x0:x1].mean() if (y1 > y0 and x1 > x0) else 0
        if share > 0.02:
            hits.append((share, layer.split("::")[-1]))
    return [l for _, l in sorted(hits, reverse=True)[:5]]


def _load_ref(pkg: Package, ref: str) -> dict | None:
    """User picked the original explicitly: use that package's first image."""
    p = pkg.out_root / ref / "chunks.jsonl"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["modality"] == "image":
            m = json.loads((pkg.out_root / ref / "manifest.json").read_text(encoding="utf-8"))
            return {"package_id": ref, "chunk_id": c["id"], "asset": c["asset"], "distance": None,
                    "title": m["title"], "caption": c["text"], "kind": m["kind"]}
    return None
