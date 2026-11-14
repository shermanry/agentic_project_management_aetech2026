"""Rhino .3dm -> structured description + rendered snapshots, without Rhino installed.

Reads the file with rhino3dm (McNeel's open-source openNURBS bindings):
  * text: units, extents, object counts by type, layer tree, blocks, materials,
    named views, document/object user text, annotation and text-dot content
  * images: shaded views (top, front, right, axonometric) rendered from the
    render meshes stored in the file, with edges and curves drawn over them,
    plus one "layer highlighted in context" view per major layer

If the file was saved without render meshes (e.g. "Save Small"), surfaces are
approximated from their untrimmed UV grid and a warning is recorded.
"""
from __future__ import annotations

import io
import math
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw

from ..core import Package
from ..engine import register, Context

IMG_W, IMG_H, SS = 1280, 960, 2      # output size, supersampling factor
MAX_TRIANGLES = 400_000
MAX_LAYER_VIEWS = 8
CURVE_SAMPLES = 48
BG = (250, 250, 248)
NEUTRAL = (196, 198, 204)
GHOST = (228, 229, 232)
ACCENT = (232, 112, 48)   # highlighted layer in per-layer views
UNIT_TO_M = {"Millimeters": 0.001, "Centimeters": 0.01, "Meters": 1.0, "Kilometers": 1000.0, "Inches": 0.0254,
             "Feet": 0.3048, "Yards": 0.9144, "Miles": 1609.344, "Decimeters": 0.1, "Microns": 1e-6}


# ----------------------------------------------------------------- geometry extraction
def _mesh_arrays(mesh) -> tuple[np.ndarray, np.ndarray] | None:
    """rhino3dm Mesh -> (vertices Nx3, triangles Mx3 int)."""
    if mesh is None or len(mesh.Vertices) == 0 or len(mesh.Faces) == 0:
        return None
    v = np.array([[p.X, p.Y, p.Z] for p in mesh.Vertices.ToPoint3dArray()])
    tris = []
    for i in range(len(mesh.Faces)):
        a, b, c, d = mesh.Faces[i]
        tris.append((a, b, c))
        if c != d:
            tris.append((a, c, d))
    return v, np.array(tris, dtype=np.int64)


def _surface_grid(face, n: int = 10) -> tuple[np.ndarray, np.ndarray] | None:
    """Untrimmed UV-grid approximation of a Brep face when no render mesh is stored."""
    try:
        du, dv = face.Domain(0), face.Domain(1)
        us = np.linspace(du.T0, du.T1, n)
        vs = np.linspace(dv.T0, dv.T1, n)
        pts = np.array([[(p := face.PointAt(u, w)).X, p.Y, p.Z] for u in us for w in vs])
        tris = []
        for i in range(n - 1):
            for j in range(n - 1):
                a, b, c, d = i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1
                tris += [(a, b, c), (a, c, d)]
        return pts, np.array(tris)
    except Exception:
        return None


def _curve_points(crv, n: int = CURVE_SAMPLES) -> np.ndarray | None:
    try:
        dom = crv.Domain
        if crv.IsLinear() if callable(getattr(crv, "IsLinear", None)) else False:
            ts = [dom.T0, dom.T1]
        else:
            ts = np.linspace(dom.T0, dom.T1, n)
        return np.array([[(p := crv.PointAt(t)).X, p.Y, p.Z] for t in ts])
    except Exception:
        return None


def _xform(points: np.ndarray, xf) -> np.ndarray:
    m = np.array([[getattr(xf, f"M{r}{c}") for c in range(4)] for r in range(4)])
    h = np.c_[points, np.ones(len(points))] @ m.T
    w = np.where(np.abs(h[:, 3:4]) < 1e-12, 1.0, h[:, 3:4])
    return h[:, :3] / w


class Scene:
    """Flat lists of triangles and polylines, each tagged with a layer index and colour."""

    def __init__(self):
        self.tri_chunks: list[tuple[np.ndarray, int, tuple]] = []   # (Tx3x3 coords, layer, colour)
        self.lines: list[tuple[np.ndarray, int, tuple]] = []        # (Px3 polyline, layer, colour)
        self.points: list[tuple[np.ndarray, int, tuple]] = []
        self.approximate_surfaces = 0

    def add_mesh(self, arrays, layer, colour, xf=None):
        if arrays is None:
            return
        v, t = arrays
        if xf is not None:
            v = _xform(v, xf)
        if len(t):
            self.tri_chunks.append((v[t], layer, colour))

    def add_line(self, pts, layer, colour, xf=None):
        if pts is not None and len(pts) >= 2:
            self.lines.append((_xform(pts, xf) if xf is not None else pts, layer, colour))

    def all_points(self) -> np.ndarray:
        parts = [t.reshape(-1, 3) for t, _, _ in self.tri_chunks] + [l for l, _, _ in self.lines] + [p for p, _, _ in self.points]
        return np.vstack(parts) if parts else np.zeros((0, 3))


def _add_geometry(scene: Scene, geom, layer: int, colour, xf=None, lookup=None, depth=0):
    import rhino3dm as r
    if isinstance(geom, r.Brep):
        for face in geom.Faces:
            mesh = face.GetMesh(r.MeshType.Any)
            arrays = _mesh_arrays(mesh)
            if arrays is None:
                arrays = _surface_grid(face)
                scene.approximate_surfaces += 1
            scene.add_mesh(arrays, layer, colour, xf)
        for edge in geom.Edges:
            scene.add_line(_curve_points(edge, 24), layer, colour, xf)
    elif isinstance(geom, r.Extrusion):
        arrays = _mesh_arrays(geom.GetMesh(r.MeshType.Any))
        if arrays is None:
            brep = geom.ToBrep(True) if hasattr(geom, "ToBrep") else None
            if brep is not None:
                return _add_geometry(scene, brep, layer, colour, xf, lookup, depth)
        scene.add_mesh(arrays, layer, colour, xf)
    elif isinstance(geom, r.Mesh):
        scene.add_mesh(_mesh_arrays(geom), layer, colour, xf)
    elif isinstance(geom, r.SubD):
        try:
            scene.add_mesh(_mesh_arrays(r.Mesh.CreateFromSubDControlNet(geom)), layer, colour, xf)
        except Exception:
            pass
    elif isinstance(geom, r.Curve):
        scene.add_line(_curve_points(geom), layer, colour, xf)
    elif isinstance(geom, r.Point):
        p = geom.Location
        scene.points.append((np.array([[p.X, p.Y, p.Z]]), layer, colour))
    elif isinstance(geom, r.PointCloud):
        pts = np.array([[p.X, p.Y, p.Z] for p in geom.GetPoints()][:20000])
        if len(pts):
            scene.points.append((pts if xf is None else _xform(pts, xf), layer, colour))
    elif isinstance(geom, r.InstanceReference) and lookup is not None and depth < 4:
        xform = geom.Xform
        for child_geom, child_layer in lookup.get(str(geom.ParentIdefId), []):
            # nested transform: apply instance xform after any outer xform
            if xf is not None:
                m = np.array([[getattr(xf, f"M{a}{b}") for b in range(4)] for a in range(4)]) @ \
                    np.array([[getattr(xform, f"M{a}{b}") for b in range(4)] for a in range(4)])
                combined = _MatrixXf(m)
            else:
                combined = xform
            _add_geometry(scene, child_geom, layer, colour, combined, lookup, depth + 1)


class _MatrixXf:
    """Duck-typed stand-in for rhino3dm.Transform built from a numpy 4x4."""

    def __init__(self, m):
        for a in range(4):
            for b in range(4):
                setattr(self, f"M{a}{b}", float(m[a, b]))


# ----------------------------------------------------------------- rendering
VIEWS = {
    # name: (right vector, up vector) ; view direction = cross(up, right)  (towards the viewer)
    "top": ((1, 0, 0), (0, 1, 0)),
    "front": ((1, 0, 0), (0, 0, 1)),
    "right": ((0, 1, 0), (0, 0, 1)),
    "axonometric": None,  # computed: looking from south-east, 35 deg elevation
}


def _view_basis(name):
    if name == "axonometric":
        az, el = math.radians(-45), math.radians(35)
        to_cam = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
        right = np.cross([0, 0, 1], to_cam); right /= np.linalg.norm(right)
        up = np.cross(to_cam, right)
        return right, up, to_cam
    r_, u_ = (np.array(v, float) for v in VIEWS[name])
    return r_, u_, np.cross(r_, u_)


def _subdivide(tris: np.ndarray, max_edge: float, budget: int) -> np.ndarray:
    """Split large triangles 1->4 until edges are short, so painter's-algorithm depth
    sorting (per triangle centroid) stays correct where big faces meet small ones."""
    for _ in range(8):
        e = np.max(np.linalg.norm(tris - np.roll(tris, 1, axis=1), axis=2), axis=1)
        big = e > max_edge
        if not big.any() or len(tris) + 3 * big.sum() > budget:
            break
        t = tris[big]
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        new = np.concatenate([np.stack(s, axis=1) for s in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])
        tris = np.concatenate([tris[~big], new])
    return tris


def _split_polyline(pts: np.ndarray, max_edge: float) -> np.ndarray:
    out = [pts[0]]
    for p0, p1 in zip(pts[:-1], pts[1:]):
        n = int(np.linalg.norm(p1 - p0) // max_edge) + 1
        out += [p0 + (p1 - p0) * k / n for k in range(1, n + 1)]
    return np.array(out)


def _shade(colour, normals_dot):
    k = 0.42 + 0.58 * normals_dot
    return [tuple(int(min(255, c * kk)) for c in colour) for kk in k]


def render(scene: Scene, view: str, highlight_layer: int | None = None, bbox=None) -> bytes:
    right, up, to_cam = _view_basis(view)
    light = to_cam * 0.6 + up * 0.5 + right * 0.3
    light /= np.linalg.norm(light)
    W, H = IMG_W * SS, IMG_H * SS
    lo, hi = bbox
    pts_all = scene.all_points()
    if len(pts_all) > 200_000:
        pts_all = pts_all[:: len(pts_all) // 200_000 + 1]
    sx, sy = pts_all @ right, pts_all @ up
    span = max((sx.max() - sx.min()) / W, (sy.max() - sy.min()) / H, 1e-9) * 1.1
    max_edge = float(np.linalg.norm(hi - lo)) / 40 or 1.0
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2

    def to_px(p):
        return np.c_[W / 2 + (p @ right - cx) / span, H / 2 - (p @ up - cy) / span]

    def colour_for(layer, colour, faded):
        if highlight_layer is None:
            return colour
        return ACCENT if layer == highlight_layer else faded

    items = []  # (depth, kind, coords, fill)
    total = sum(len(t) for t, _, _ in scene.tri_chunks)
    step = max(1, math.ceil(total / MAX_TRIANGLES))
    for tris, layer, colour in scene.tri_chunks:
        tris = _subdivide(tris[::step], max_edge, budget=max(len(tris) // step * 4, 20_000))
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        ln = np.linalg.norm(n, axis=1)
        keep = ln > 1e-12
        tris, n = tris[keep], n[keep] / ln[keep][:, None]
        if not len(tris):
            continue
        base = colour_for(layer, colour, GHOST)
        fills = _shade(base, np.abs(n @ light))
        depth = (tris.mean(axis=1) @ to_cam)
        px = to_px(tris.reshape(-1, 3)).reshape(-1, 3, 2)
        items += [(d, 0, p, f) for d, p, f in zip(depth, px, fills)]
    for pts, layer, colour in scene.lines:
        edge = tuple(int(c * 0.45) for c in colour_for(layer, colour, (200, 200, 205)))
        pts = _split_polyline(pts, max_edge)
        d = pts @ to_cam
        px = to_px(pts)
        for i in range(len(pts) - 1):
            items.append(((d[i] + d[i + 1]) / 2 + span * 2, 1, px[i:i + 2], edge))  # bias: edges sit on faces
    for pts, layer, colour in scene.points:
        dot = tuple(int(c * 0.5) for c in colour_for(layer, colour, (200, 200, 205)))
        for p, d in zip(to_px(pts), pts @ to_cam):
            items.append((d, 2, p, dot))
    items.sort(key=lambda it: it[0])

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    lw = max(1, SS)
    for _, kind, coords, fill in items:
        if kind == 0:
            draw.polygon([tuple(c) for c in coords], fill=fill)
        elif kind == 1:
            draw.line([tuple(c) for c in coords], fill=fill, width=lw)
        else:
            x, y = coords
            draw.ellipse([x - 2 * SS, y - 2 * SS, x + 2 * SS, y + 2 * SS], fill=fill)
    img = img.resize((IMG_W, IMG_H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ----------------------------------------------------------------- description helpers
def _colour(c) -> tuple[int, int, int]:
    try:
        rgb = (c[0], c[1], c[2]) if isinstance(c, tuple) else (c.R, c.G, c.B)
    except Exception:
        return NEUTRAL
    # very dark / very light layer colours shade badly: use neutral grey
    return NEUTRAL if sum(rgb) < 90 or sum(rgb) > 720 else tuple(int(x) for x in rgb)


def _type_name(geom) -> str:
    import rhino3dm as r
    if isinstance(geom, r.Brep):
        return "Closed polysurface" if geom.IsSolid else ("Surface" if len(geom.Faces) == 1 else "Polysurface")
    if isinstance(geom, r.Extrusion):
        return "Extrusion"
    if isinstance(geom, r.InstanceReference):
        return "Block instance"
    name = type(geom).__name__
    return {"NurbsCurve": "Curve", "PolylineCurve": "Polyline", "LineCurve": "Line", "ArcCurve": "Arc",
            "PolyCurve": "Polycurve", "TextDot": "Text dot"}.get(name, name)


def _plural(t: str, n: int) -> str:
    if n == 1:
        return t
    return t + ("es" if t.endswith(("sh", "ch", "s", "x")) else "s")


def _fmt(x: float) -> str:
    return f"{x:,.3f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:,.0f}"


def _user_strings(obj) -> dict:
    try:
        return {k: v for k, v in obj.GetUserStrings()}
    except Exception:
        try:
            return dict(obj.GetUserStrings2())
        except Exception:
            return {}


def _text_of(geom) -> str | None:
    for attr in ("PlainText", "Text", "RichText"):
        v = getattr(geom, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ----------------------------------------------------------------- handler
@register("rhino_model", ".3dm")
def convert_3dm(pkg: Package, ctx: Context) -> None:
    import rhino3dm as r

    model = r.File3dm.Read(str(pkg.source))
    if model is None:
        raise RuntimeError("rhino3dm could not read this file (corrupt or newer than supported)")

    settings = model.Settings
    units = str(settings.ModelUnitSystem).split(".")[-1]
    to_m = UNIT_TO_M.get(units)
    meta = {"units": units, "rhino_archive_version": getattr(model, "ArchiveVersion", None),
            "created_by": model.CreatedBy, "last_edited_by": model.LastEditedBy,
            "created": str(model.Created), "last_edited": str(model.LastEdited), "revision": model.Revision,
            "application": model.ApplicationName, "tolerance": settings.ModelAbsoluteTolerance}
    try:
        notes = r.File3dm.ReadNotes(str(pkg.source))
        if notes and notes.strip():
            meta["notes"] = notes.strip()
    except Exception:
        pass
    try:
        ea = settings.EarthAnchorPoint
        lat, lon = ea.EarthBasepointLatitude, ea.EarthBasepointLongitude
        if (lat, lon) != (0.0, 0.0) and abs(lat) <= 90:
            meta["location"] = {"lat": lat, "lon": lon, "elevation": ea.EarthBasepointElevation}
            pkg.tags.add("geolocated")
    except Exception:
        pass

    # layers
    layers = {}
    for i in range(len(model.Layers)):
        L = model.Layers[i]
        layers[L.Index] = {"name": L.Name, "path": L.FullPath, "colour": _colour(L.Color), "visible": L.Visible,
                           "locked": L.Locked, "user_text": _user_strings(L)}

    # block definitions: geometry belonging to each definition
    obj_by_id = {}
    for obj in model.Objects:
        obj_by_id[str(obj.Attributes.Id)] = obj
    block_lookup: dict[str, list] = {}
    blocks = []
    for idef in model.InstanceDefinitions:
        ids = [str(g) for g in idef.GetObjectIds()]
        block_lookup[str(idef.Id)] = [(obj_by_id[g].Geometry, obj_by_id[g].Attributes.LayerIndex) for g in ids if g in obj_by_id]
        blocks.append({"name": idef.Name, "description": idef.Description, "objects": len(ids), "id": str(idef.Id)})

    scene = Scene()
    type_counts = Counter()
    per_layer = defaultdict(Counter)
    named, texts, obj_user_text = [], [], []
    instance_counts = Counter()
    for obj in model.Objects:
        a, g = obj.Attributes, obj.Geometry
        if a.IsInstanceDefinitionObject:
            continue  # drawn through its instances
        tname = _type_name(g)
        type_counts[tname] += 1
        li = a.LayerIndex
        per_layer[li][tname] += 1
        if a.Name:
            named.append(f"{a.Name} ({tname}, layer {layers.get(li, {}).get('path', li)})")
        if (t := _text_of(g)):
            texts.append(f"[{layers.get(li, {}).get('path', li)}] {t}")
        if (us := _user_strings(a)):
            obj_user_text.append({"object": a.Name or str(a.Id), "layer": layers.get(li, {}).get("path"), "user_text": us})
        if isinstance(g, r.InstanceReference):
            instance_counts[str(g.ParentIdefId)] += 1
        colour = _colour(a.ObjectColor) if str(a.ColorSource).endswith("ColorFromObject") else layers.get(li, {}).get("colour", NEUTRAL)
        if layers.get(li, {}).get("visible", True) and a.Visible:
            try:
                _add_geometry(scene, g, li, colour, lookup=block_lookup)
            except Exception as e:
                pkg.warnings.append(f"could not draw {tname}: {e}")
    for b in blocks:
        b["instances"] = instance_counts.get(b["id"], 0)

    pts = scene.all_points()
    bbox = None
    if len(pts):
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        bbox = (lo, hi)
        dims = hi - lo
        meta["bounding_box"] = {"min": lo.round(4).tolist(), "max": hi.round(4).tolist(), "size": dims.round(4).tolist()}
        if to_m:
            meta["size_m"] = (dims * to_m).round(3).tolist()

    doc_strings = {}
    try:
        for i in range(len(model.Strings)):
            item = model.Strings[i]
            if isinstance(item, (tuple, list)) and len(item) == 2 and item[0]:
                doc_strings[str(item[0])] = str(item[1])
    except Exception as e:
        pkg.warnings.append(f"could not read document user text: {e}")
    materials = sorted({m.Name for m in model.Materials if m.Name})
    named_views = [v.Name for v in model.NamedViews if v.Name]
    total_objects = sum(type_counts.values())
    meta.update(object_count=total_objects, object_types=dict(type_counts), layer_count=len(layers),
                layers=[{**v, "colour": list(v["colour"]), "objects": dict(per_layer.get(i, {}))} for i, v in layers.items()],
                blocks=blocks, materials=materials, named_views=named_views, document_user_text=doc_strings,
                object_user_text=obj_user_text[:200], named_objects=len(named))
    pkg.metadata.update(meta)
    pkg.tags.update({"geometry", "rhino"})

    # ---- text: overview
    size_txt = ""
    if bbox is not None:
        d = bbox[1] - bbox[0]
        size_txt = f"Overall extents {_fmt(d[0])} x {_fmt(d[1])} x {_fmt(d[2])} {units.lower()}"
        if to_m and units != "Meters":
            m = d * to_m
            size_txt += f" ({_fmt(m[0])} x {_fmt(m[1])} x {_fmt(m[2])} m)"
        size_txt += " (width x depth x height)."
    types_txt = ", ".join(f"{n} {_plural(t, n)}" for t, n in type_counts.most_common())
    used_layers = sorted(per_layer, key=lambda i: -sum(per_layer[i].values()))
    overview = [
        f"Rhino 3D model '{pkg.original_name}' in {units.lower()}.",
        f"{total_objects} objects on {len(used_layers)} of {len(layers)} layers: {types_txt}." if total_objects else "The model is empty.",
        size_txt,
        f"Created by {meta['created_by']} ({meta['created']}), last edited by {meta['last_edited_by']} ({meta['last_edited']}), revision {meta['revision']}." if meta.get("created_by") else "",
        "Main layers: " + "; ".join(f"{layers[i]['path']} ({sum(per_layer[i].values())})" for i in used_layers[:12] if i in layers) + "." if used_layers else "",
        f"Blocks: " + ", ".join(f"{b['name']} x{b['instances']}" for b in blocks) + "." if blocks else "",
        f"Materials: {', '.join(materials[:20])}." if materials else "",
        f"Named views: {', '.join(named_views)}." if named_views else "",
        f"Geolocated at lat {meta['location']['lat']}, lon {meta['location']['lon']}." if meta.get("location") else "",
        f"Notes: {meta['notes']}" if meta.get("notes") else "",
    ]
    pkg.description = " ".join(s for s in overview if s)
    pkg.add_text(pkg.description, role="summary")

    # ---- text: layer tree (one chunk per layer, so a layer can become its own node)
    for i in used_layers:
        L = layers.get(i)
        if not L:
            continue
        counts = ", ".join(f"{n} {t}" for t, n in per_layer[i].most_common())
        extra = f" Layer user text: {L['user_text']}." if L["user_text"] else ""
        pkg.add_text(f"Layer '{L['path']}' in model '{pkg.title}': {counts}.{extra}", role="layer",
                     locator={"layer": L["path"]})
    if named:
        pkg.add_text("Named objects:\n" + "\n".join(named[:500]), role="body")
    if texts:
        pkg.add_text("Text and annotations in the model:\n" + "\n".join(texts[:500]), role="annotation")
    if doc_strings:
        pkg.add_text("Document user text:\n" + "\n".join(f"{k}: {v}" for k, v in doc_strings.items()), role="metadata")
    if obj_user_text:
        pkg.add_text("Object user text:\n" + "\n".join(f"{o['object']} [{o['layer']}]: " + ", ".join(f"{k}={v}" for k, v in o['user_text'].items())
                                                       for o in obj_user_text[:300]), role="metadata")

    # ---- snapshots
    if bbox is None:
        pkg.warnings.append("no drawable geometry; no snapshots rendered")
        return
    if scene.approximate_surfaces:
        pkg.warnings.append(f"{scene.approximate_surfaces} surface(s) had no stored render mesh; drawn as untrimmed "
                            "approximations (save from Rhino with render meshes for accurate snapshots)")
    for view in ("axonometric", "top", "front", "right"):
        rel = pkg.add_asset_bytes(f"view_{view}.png", render(scene, view, bbox=bbox))
        pkg.add_image(rel, f"{view.capitalize()} view of Rhino model '{pkg.title}'. {size_txt}", role="snapshot",
                      locator={"view": view})
    if len(used_layers) > 1:
        for i in used_layers[:MAX_LAYER_VIEWS]:
            L = layers.get(i)
            if not L or not any(l == i for _, l, _ in scene.tri_chunks + scene.lines):
                continue
            rel = pkg.add_asset_bytes(f"layer_{L['name']}.png", render(scene, "axonometric", highlight_layer=i, bbox=bbox))
            counts = ", ".join(f"{n} {t}" for t, n in per_layer[i].most_common())
            pkg.add_image(rel, f"Axonometric view of model '{pkg.title}' with layer '{L['path']}' highlighted ({counts}).",
                          role="snapshot", locator={"view": "axonometric", "layer": L["path"]})
