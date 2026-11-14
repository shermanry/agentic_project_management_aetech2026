"""Images: normalized copy for embedding + EXIF/GPS + drone XMP (DJI altitude,
gimbal, yaw) so drone photos can be placed on a map/site node."""
from __future__ import annotations

import io
import re

from PIL import Image, ExifTags, ImageOps

from ..core import Package
from ..engine import register, Context
from ..markup import analyze

MAX_SIDE = 2048
_XMP_FIELDS = ["RelativeAltitude", "AbsoluteAltitude", "GimbalPitchDegree", "GimbalYawDegree", "GimbalRollDegree",
               "FlightYawDegree", "FlightPitchDegree", "FlightRollDegree", "GpsLatitude", "GpsLongitude",
               "GpsLongtitude", "CamReverse", "Make", "Model"]


def _gps_to_deg(v, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in v)
        deg = d + m / 60 + s / 3600
        return -deg if ref in ("S", "W") else deg
    except Exception:
        return None


def read_exif(img: Image.Image) -> dict:
    out: dict = {}
    exif = img.getexif()
    if not exif:
        return out
    for k, v in exif.items():
        name = ExifTags.TAGS.get(k, str(k))
        if name in ("Make", "Model", "DateTime", "Software", "Artist", "ImageDescription", "Orientation"):
            out[name] = str(v).strip("\x00 ")
    try:
        sub = exif.get_ifd(ExifTags.IFD.Exif)
        for k, v in sub.items():
            name = ExifTags.TAGS.get(k, str(k))
            if name in ("DateTimeOriginal", "FocalLength", "FNumber", "ExposureTime", "ISOSpeedRatings", "LensModel"):
                out[name] = float(v) if hasattr(v, "numerator") else str(v).strip("\x00 ")
    except Exception:
        pass
    try:
        gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in exif.get_ifd(ExifTags.IFD.GPSInfo).items()}
        lat = _gps_to_deg(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
        lon = _gps_to_deg(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
        if lat is not None and lon is not None:
            out["gps"] = {"lat": round(lat, 7), "lon": round(lon, 7)}
            if "GPSAltitude" in gps:
                out["gps"]["alt_m"] = round(float(gps["GPSAltitude"]), 2)
    except Exception:
        pass
    return out


def read_drone_xmp(raw: bytes) -> dict:
    """DJI and others write flight attitude into XMP as drone-dji:Field="value"."""
    start = raw.find(b"<x:xmpmeta")
    if start < 0:
        return {}
    end = raw.find(b"</x:xmpmeta>", start)
    xmp = raw[start:end if end > 0 else start + 65536].decode("utf-8", "ignore")
    out = {}
    for f in _XMP_FIELDS:
        m = re.search(rf'[\w-]+:{f}="([^"]*)"', xmp) or re.search(rf"<[\w-]+:{f}>([^<]*)<", xmp)
        if m:
            v = m.group(1)
            try:
                v = float(v)
            except ValueError:
                pass
            out[f.replace("Longtitude", "Longitude")] = v
    return out


def save_normalized(img: Image.Image, max_side: int = MAX_SIDE) -> tuple[bytes, str]:
    img = ImageOps.exif_transpose(img)
    img.thumbnail((max_side, max_side))
    if img.mode in ("RGBA", "LA", "P"):
        buf = io.BytesIO(); img.convert("RGBA").save(buf, "PNG"); return buf.getvalue(), "png"
    buf = io.BytesIO(); img.convert("RGB").save(buf, "JPEG", quality=90); return buf.getvalue(), "jpg"


@register("image", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
def convert_image(pkg: Package, ctx: Context) -> None:
    raw = pkg.source.read_bytes()
    img = Image.open(io.BytesIO(raw))
    frames = getattr(img, "n_frames", 1)
    pkg.metadata.update(width=img.width, height=img.height, mode=img.mode, format=img.format, frames=frames)
    exif = read_exif(img)
    drone = read_drone_xmp(raw)
    if exif:
        pkg.metadata["exif"] = exif
    if drone:
        pkg.metadata["drone"] = drone
        pkg.tags.update({"flight", "drone-capture"})
    if "gps" in exif:
        pkg.metadata["location"] = exif["gps"]
        pkg.tags.add("geolocated")
    data, ext = save_normalized(img)
    rel = pkg.add_asset_bytes(f"image.{ext}", data)

    parts = [f"Image '{pkg.original_name}', {img.width}x{img.height}px"]
    cam = " ".join(str(exif[k]) for k in ("Make", "Model") if k in exif)
    if cam:
        parts.append(f"taken with {cam}")
    if exif.get("DateTimeOriginal") or exif.get("DateTime"):
        parts.append(f"on {exif.get('DateTimeOriginal') or exif.get('DateTime')}")
    if "gps" in exif:
        g = exif["gps"]
        parts.append(f"at lat {g['lat']}, lon {g['lon']}" + (f", altitude {g['alt_m']} m" if "alt_m" in g else ""))
    if "RelativeAltitude" in drone:
        parts.append(f"drone {drone['RelativeAltitude']} m above takeoff")
    if "GimbalPitchDegree" in drone:
        parts.append(f"gimbal pitch {drone['GimbalPitchDegree']} deg")
    caption = ", ".join(parts) + "."
    if pkg.context_line():
        caption += " " + pkg.context_line()
    chunk = pkg.add_image(rel, caption, role="image")
    if exif.get("ImageDescription"):
        pkg.add_text(exif["ImageDescription"], role="caption")

    # markup? (someone drew on a render/photo to request a change)
    if pkg.context.get("intent") != "reference":
        normalized = Image.open(io.BytesIO(data))
        summary = analyze(pkg, normalized, rel, label=", ".join(parts) + ".",
                          force=pkg.context.get("intent") == "markup", chunk=chunk)
        if summary:
            pkg.kind = "markup"
            pkg.metadata["markup"] = summary
            pkg.tags.update({"markup", "change-request"})
            if summary.get("drawn_on"):
                pkg.title = f"Markup on {summary['drawn_on'].get('title', 'image')} - {pkg.title}"
            caption = chunk.text
    pkg.description = caption
