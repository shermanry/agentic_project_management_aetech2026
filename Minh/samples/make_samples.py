"""Generates one synthetic test file per supported family into samples/generated/.

    python samples/make_samples.py
"""
from __future__ import annotations

import io
import math
import subprocess
from email.message import EmailMessage
from pathlib import Path

OUT = Path(__file__).parent / "generated"


def rhino():
    import rhino3dm as r
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Meters
    def layer(name, rgb):
        L = r.Layer(); L.Name = name; L.Color = (*rgb, 255)
        return m.Layers.Add(L)
    site, struct, facade, flight = layer("Site", (120, 160, 110)), layer("Structure", (190, 190, 200)), \
        layer("Facade", (90, 140, 210)), layer("Flight_Path", (230, 80, 60))

    def attrs(li, name=None, **user):
        a = r.ObjectAttributes(); a.LayerIndex = li
        if name: a.Name = name
        for k, v in user.items(): a.SetUserString(k, v)
        return a

    def box_mesh(x0, y0, z0, x1, y1, z1):
        mesh = r.Mesh()
        for x, y, z in [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]:
            mesh.Vertices.Add(x, y, z)
        for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            mesh.Faces.AddFace(*f)
        mesh.Normals.ComputeNormals() if hasattr(mesh.Normals, "ComputeNormals") else None
        return mesh

    ground = box_mesh(-20, -20, -0.2, 60, 50, 0)
    m.Objects.AddMesh(ground, attrs(site, "Ground plane"))
    m.Objects.AddMesh(box_mesh(0, 0, 0, 30, 20, 24), attrs(struct, "Tower A", program="office", floors="6"))
    m.Objects.AddMesh(box_mesh(34, 4, 0, 46, 28, 12), attrs(struct, "Podium B", program="retail"))
    for i in range(7):  # facade fins
        x = i * 5
        m.Objects.AddMesh(box_mesh(x - 0.2, -1.2, 0, x + 0.2, 0, 24), attrs(facade, f"Fin {i + 1}"))
    sphere = r.Brep.CreateFromSphere(r.Sphere(r.Point3d(40, 16, 16), 4))
    m.Objects.AddBrep(sphere, attrs(struct, "Dome"))
    pts = [r.Point3d(-10 + 70 * t / 20, -10 + 8 * math.sin(t / 3), 40) for t in range(21)]
    m.Objects.AddCurve(r.Curve.CreateControlPointCurve(pts, 3), attrs(flight, "Survey pass 1", altitude_m="40"))
    m.Objects.AddTextDot("Takeoff point", r.Point3d(-10, -10, 0), attrs(flight))
    m.Objects.AddPoint(r.Point3d(-10, -10, 0), attrs(flight, "Home"))
    m.Strings["Project"] = "Hackathon tower survey"
    m.Strings["Client"] = "Example Developer"
    m.Write(str(OUT / "tower_site.3dm"), 8)


def pdf():
    import pymupdf
    doc = pymupdf.open()
    for i, txt in enumerate(["Flight Operations Plan\n\nSite: example tower, Manhattan. Airspace class B; LAANC authorization needed below 100 ft AGL.",
                             "Weather limits\n\nMax sustained wind 20 mph, gusts 25 mph. No rain. Visibility 3 statute miles.",
                             "Schedule\n\nMonitoring flights every 2 weeks during construction. Please confirm the first flight date."]):
        p = doc.new_page()
        p.insert_text((72, 90), txt, fontsize=13)
        p.draw_rect(pymupdf.Rect(72, 300, 520, 700), color=(0.2, 0.3, 0.7), width=2)
    doc.set_metadata({"title": "Flight Operations Plan", "author": "Drone team"})
    doc.save(OUT / "flight_plan.pdf")


def image_with_gps(path: Path):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1600, 1000), (140, 170, 200))
    d = ImageDraw.Draw(img)
    d.rectangle([500, 300, 1100, 1000], fill=(180, 180, 175))
    for x in range(520, 1100, 60):
        d.rectangle([x, 330, x + 30, 980], fill=(110, 140, 170))
    exif = Image.Exif()
    exif[0x010F] = "DJI"; exif[0x0110] = "FC3582"; exif[0x0132] = "2026:11:10 10:22:00"
    gps = exif.get_ifd(0x8825)
    gps.update({1: "N", 2: (40.0, 44.0, 54.36), 3: "W", 4: (73.0, 59.0, 8.5), 6: 52.3})
    xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description drone-dji:RelativeAltitude="+40.10" '
           b'drone-dji:GimbalPitchDegree="-30.0" drone-dji:FlightYawDegree="+112.5"/></rdf:RDF></x:xmpmeta>')
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif, xmp=xmp)
    path.write_bytes(buf.getvalue())


def email_with_attachments():
    msg = EmailMessage()
    msg["Subject"] = "RE: Flight date moved - TFR over Midtown"
    msg["From"] = "Pilot <pilot@example.com>"
    msg["To"] = "PM <pm@example.com>"
    msg["Date"] = "Tue, 10 Nov 2026 09:15:00 -0500"
    msg.set_content("Hi,\n\nThe FAA issued a TFR for Thursday, so we need to reschedule the facade inspection flight.\n"
                    "Friday looks good for wind (8 mph). Can you confirm Friday 9am with the client?\n\nThanks\n\n"
                    "On Mon, 9 Nov 2026, PM wrote:\n> Are we still on for Thursday?\n")
    msg.add_attachment((OUT / "drone_photo.jpg").read_bytes(), maintype="image", subtype="jpeg", filename="site_photo.jpg")
    msg.add_attachment((OUT / "flight_plan.pdf").read_bytes(), maintype="application", subtype="pdf", filename="flight_plan_v2.pdf")
    (OUT / "flight_reschedule.eml").write_bytes(bytes(msg))


def office():
    import docx, openpyxl
    d = docx.Document()
    d.core_properties.title = "Facade Inspection Scope"; d.core_properties.author = "Design team"
    d.add_heading("Facade Inspection Scope", 0)
    d.add_heading("Objectives", 1); d.add_paragraph("Inspect the curtain wall for cracks and sealant failure on levels 10-24.")
    d.add_heading("Constraints", 1); d.add_paragraph("No flights over the street during rush hour. Pilot must hold Part 107.")
    t = d.add_table(rows=3, cols=3)
    for i, row in enumerate([["Elevation", "Area m2", "Priority"], ["North", "1200", "High"], ["East", "800", "Medium"]]):
        for j, v in enumerate(row): t.cell(i, j).text = v
    d.save(OUT / "inspection_scope.docx")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Flights"
    ws.append(["Date", "Type", "Wind mph", "Status"])
    for r in [("2026-11-12", "Monitoring", 12, "Done"), ("2026-11-26", "Monitoring", None, "Planned"), ("2026-12-10", "Inspection", None, "Planned")]:
        ws.append(r)
    wb.save(OUT / "flight_log.xlsx")
    (OUT / "notes.md").write_text("# Site notes\n\nCrane on the north side until December.\n\n## Risks\n\nBird nesting on roof; RF interference near antenna.\n", encoding="utf-8")


def media():
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=45",
                    str(OUT / "voice_memo.m4a")], check=True)
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=40",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=40", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-metadata", "location=+40.7484-073.9857/", str(OUT / "flyover.mp4")], check=True)


def archive():
    import zipfile
    with zipfile.ZipFile(OUT / "rfi_bundle.zip", "w") as z:
        z.writestr("RFI-012.txt", "RFI-012: Contractor asks whether the drone survey will cover the roof mechanical area. Need decision by Nov 20?")
        z.writestr("folder/RFI-013.txt", "RFI-013: Confirm GCP (ground control point) locations for photogrammetry.")


def _draw_markup(base_png: Path, out: Path, screenshot: bool = False):
    """Simulates a client/lead marking up a render: red cloud, arrow, handwritten-ish note."""
    from PIL import Image, ImageDraw
    img = Image.open(base_png).convert("RGB")
    W, H = img.size
    d = ImageDraw.Draw(img)
    # red ellipse around the upper-left part of the tower
    d.ellipse([W * .20, H * .12, W * .42, H * .40], outline=(225, 30, 35), width=6)
    # arrow towards the podium
    d.line([W * .78, H * .18, W * .66, H * .40], fill=(225, 30, 35), width=6)
    d.polygon([(W * .66, H * .40), (W * .655, H * .35), (W * .69, H * .37)], fill=(225, 30, 35))
    d.text((W * .70, H * .10), "lighter canopy here?", fill=(225, 30, 35))
    if screenshot:  # Teams screenshot: cropped + rescaled, so no pixel diff possible
        img = img.crop((int(W * .05), int(H * .05), int(W * .95), int(H * .92))).resize((900, 640))
    img.save(out)


def markups():
    """Needs a converted Rhino model first for the 'same framing' case (python -m converter convert ...)."""
    import pymupdf
    base = Path(__file__).parents[1] / "converter_output"
    axo = next(base.glob("uep_*/assets/view_axonometric.png"), None)
    if axo:
        _draw_markup(axo, OUT / "client_markup_on_render.png")
        _draw_markup(axo, OUT / "teams_screenshot_markup.png", screenshot=True)
    # Bluebeam-style PDF review: cloud + callout + sticky note with a reply
    doc = pymupdf.open(OUT / "flight_plan.pdf")
    p = doc[0]
    a = p.add_rect_annot(pymupdf.Rect(70, 70, 420, 110))
    a.set_colors(stroke=(1, 0, 0)); a.set_info(title="Project Lead - A. Chen", subject="Cloud+",
                                              content="Airspace note is wrong: site is under the class B shelf, check LAANC grid ceiling for level 30 roof.")
    a.update()
    t = p.add_text_annot((480, 320), "Add the north elevation crane exclusion zone to this map (see RFI-012).")
    t.set_info(title="Client - J. Smith", subject="Note"); t.update()
    r = p.add_text_annot((490, 330), "Agreed, will add by Nov 20.", icon="Comment")
    r.set_info(title="Drone pilot - M. Ngo", subject="Reply"); r.update()
    try:
        r.set_irt_xref(t.xref)
    except Exception:
        pass
    doc.save(OUT / "flight_plan_reviewed.pdf")


def _tts(text: str, wav: Path) -> bool:
    """Windows built-in speech synthesis (System.Speech). Returns False elsewhere."""
    import platform
    if platform.system() != "Windows":
        return False
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.Rate = 0; $s.SetOutputToWaveFile('{wav}'); $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], input=text, text=True, capture_output=True)
    return r.returncode == 0 and wav.exists()


def media_ai():
    """Speech, narrated site video and a scanned drawing: things only the AI media pass can read."""
    import imageio_ffmpeg
    import pymupdf
    from PIL import Image, ImageDraw, ImageFont
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    memo = ("Site visit voice note, Pier 54, November fourteenth. Wind on the pier end was gusting about twenty two "
            "miles per hour at two p.m., stronger than the forecast. The crane on the north side is still up and the "
            "operator says it stays until December twelfth. Two G C P targets near the south entrance were moved by "
            "the contractor, we need to re-survey them before the next flight. Battery swap took six minutes.")
    wav = OUT / "_memo.wav"
    if _tts(memo, wav):
        subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), str(OUT / "site_voice_note.m4a")], check=True)
        narration = ("Starting the north facade pass. You can see the crane on the left. Moving east now along the pier deck.")
        wav2 = OUT / "_narr.wav"
        _tts(narration, wav2)
        base = Path(__file__).parents[1] / "converter_output"
        view = next(base.glob("uep_*/assets/view_axonometric.png"), None) or next(base.glob("uep_*/assets/*.png"))
        subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", str(view), "-i", str(wav2),
                        "-vf", "scale=1600:-2,zoompan=z='1.0+0.0015*on':x='iw*0.1+on*2':y='ih/4':d=1:s=1280x720:fps=25",
                        "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        str(OUT / "drone_flyover_narrated.mp4")], check=True)
        for f in (wav, wav2):
            f.unlink(missing_ok=True)
    else:
        print("  (no Windows speech synthesis: skipped voice note and narrated video)")
    # scanned drawing: text exists only as pixels
    img = Image.new("RGB", (2200, 1550), (246, 244, 236))
    d = ImageDraw.Draw(img)
    try:
        f_big, f_med = ImageFont.truetype("arial.ttf", 44), ImageFont.truetype("arial.ttf", 30)
    except OSError:
        f_big = f_med = ImageFont.load_default()
    d.rectangle([80, 120, 1500, 1150], outline=(40, 40, 40), width=5)            # elevation outline
    for i in range(7):
        y = 1150 - i * 140
        d.line([80, y, 1500, y], fill=(120, 120, 120), width=2)
        d.text((1520, y - 18), f"L{i + 1}  +{3.6 * i:.1f}m", fill=(30, 30, 30), font=f_med)
    d.rectangle([600, 120, 900, 260], outline=(200, 30, 30), width=4)
    d.text((620, 280), "PARAPET HT. 1100 MIN - VERIFY ON SITE", fill=(200, 30, 30), font=f_med)
    d.text((100, 60), "NORTH ELEVATION - FACADE SURVEY ZONES", fill=(20, 20, 20), font=f_big)
    d.text((120, 1180), "Zone N1: levels 1-3, scaffold until Dec 12. Zone N2: levels 4-7, drone pass OK.", fill=(20, 20, 20), font=f_med)
    d.rectangle([1700, 1250, 2150, 1520], outline=(20, 20, 20), width=3)          # title block
    for i, t in enumerate(["PROJECT: PIER 54", "DWG No: A-201", "REV: C   DATE: 2026-11-10", "SCALE 1:200   DRAWN: MN"]):
        d.text((1720, 1270 + i * 60), t, fill=(20, 20, 20), font=f_med)
    img = img.rotate(0.6, expand=True, fillcolor=(250, 250, 250))                  # a slightly crooked scan
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=80)
    doc = pymupdf.open()
    page = doc.new_page(width=img.width * 0.36, height=img.height * 0.36)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(OUT / "scanned_north_elevation.pdf")


if __name__ == "__main__":
    import sys
    OUT.mkdir(parents=True, exist_ok=True)
    if "--markups" in sys.argv:
        markups()
        raise SystemExit
    if "--media-ai" in sys.argv:
        media_ai()
        for n in ("site_voice_note.m4a", "drone_flyover_narrated.mp4", "scanned_north_elevation.pdf"):
            p = OUT / n
            print(f"{p.stat().st_size if p.exists() else 0:>10,}  {n}")
        raise SystemExit
    rhino(); pdf(); image_with_gps(OUT / "drone_photo.jpg"); email_with_attachments(); office(); media(); archive()
    for p in sorted(OUT.iterdir()):
        print(f"{p.stat().st_size:>10,}  {p.name}")
