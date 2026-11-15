"""Turn a Rhino model into linework the browser can draw: every edge as a line segment.

    python rhino_linework.py model.3dm out_dir [name]

Writes <name>.bin (Int16 x,y,z per point, two points per segment, Rhino's Z-up kept) and <name>.json
(scale back to metres, centre, and how many segments belong to each group). Groups, in file order:
  "main"    layers under "Simple Reference Facade" (walls, roof slabs, window recesses)
  "context" the surrounding buildings (layer "OSM_Buildings")
Needs rhino3dm (in src/converter/requirements.txt).
"""
import json
import sys
from pathlib import Path

import numpy as np
import rhino3dm as r

src, out = Path(sys.argv[1]), Path(sys.argv[2])
name = sys.argv[3] if len(sys.argv) > 3 else src.stem.lower().replace(" ", "_")
m = r.File3dm.Read(str(src))
layers = [l.FullPath for l in m.Layers]


def group(path: str) -> str | None:
    if path.startswith("Simple Reference Facade"):
        return "main"
    if path.endswith("OSM_Buildings"):
        return "context"
    return None


def edge_points(e) -> list:
    if e.IsLinear():
        return [e.PointAtStart, e.PointAtEnd]
    d = e.Domain
    return [e.PointAt(d.T0 + (d.T1 - d.T0) * i / 8) for i in range(9)]   # curved edge: 8 short segments


segs = {"main": set(), "context": set()}
for o in m.Objects:
    g = group(layers[o.Attributes.LayerIndex])
    if not g:
        continue
    geo = o.Geometry
    if isinstance(geo, r.Extrusion):
        geo = geo.ToBrep(False)
    if not isinstance(geo, r.Brep):
        continue
    for e in geo.Edges:
        pts = [(round(p.X, 2), round(p.Y, 2), round(p.Z, 2)) for p in edge_points(e)]
        for a, b in zip(pts, pts[1:]):
            if a != b:
                segs[g].add((a, b) if a <= b else (b, a))   # shared edges are drawn once

main = np.array(sorted(segs["main"]), dtype=np.float64).reshape(-1, 3)
ctx = np.array(sorted(segs["context"]), dtype=np.float64).reshape(-1, 3)
lo, hi = main.min(axis=0), main.max(axis=0)
centre = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])          # centre of the footprint, at the ground
allp = np.vstack([main, ctx]) - centre
scale = float(np.abs(allp).max()) / 32000
(out / f"{name}.bin").write_bytes(np.round(allp / scale).astype("<i2").tobytes())
meta = {"source": src.name, "units": "m", "scale": scale, "size": [float(x) for x in hi - lo],
        "groups": [{"name": "main", "segments": len(main) // 2}, {"name": "context", "segments": len(ctx) // 2}]}
(out / f"{name}.json").write_text(json.dumps(meta, indent=1))
print(meta, (out / f"{name}.bin").stat().st_size, "bytes")
