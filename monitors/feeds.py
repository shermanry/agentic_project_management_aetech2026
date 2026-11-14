"""The live-data monitors. Each one: fetch -> snapshot -> events for changes that matter.

See Ryan/data-sources.md for the source catalog.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from base import Event, Monitor, Site, daterange, distance_nm, geom_distance_nm, get_json

KMH_PER_MPH = 1.609344


# ---------------------------------------------------------------- weather forecast

class WeatherForecast(Monitor):
    """Hourly Open-Meteo forecast -> which days in (or near) the flight window are flyable.

    Emits when a day's flyability flips, or the number of flyable hours moves by 2+.
    """
    name = "weather_forecast"
    cadence_s = 3600
    near_flight_cadence_s = 900
    URL = "https://api.open-meteo.com/v1/forecast"

    def fetch(self) -> dict:
        alt = self.site.limits.flight_altitude_m
        wind_var = f"wind_speed_{alt}m" if alt in (10, 80, 120) else "wind_speed_120m"
        d = get_json(self.URL, {
            "latitude": self.site.lat, "longitude": self.site.lon,
            "hourly": f"{wind_var},wind_gusts_10m,precipitation_probability,visibility,cloud_cover,is_day",
            "daily": "sunrise,sunset",
            "wind_speed_unit": "mph", "timezone": "America/New_York", "forecast_days": 16,
        })
        d["_wind_var"] = wind_var
        return d

    def assess(self, d: dict) -> dict[str, dict]:
        L, h, wv = self.site.limits, d["hourly"], d["_wind_var"]
        days: dict[str, dict] = defaultdict(lambda: {"flyable_hours": [], "worst": {}, "reasons": defaultdict(int)})
        for i, t in enumerate(h["time"]):
            day = t[:10]
            if L.daylight_only and not h["is_day"][i]:
                continue
            reasons = []
            wind, gust = h[wv][i] or 0, h["wind_gusts_10m"][i] or 0
            rain, vis = h["precipitation_probability"][i], h["visibility"][i]
            if wind > L.max_wind_mph: reasons.append("wind")
            if gust > L.max_gust_mph: reasons.append("gusts")
            if rain is not None and rain > L.max_precip_prob: reasons.append("rain")
            if vis is not None and vis < L.min_visibility_m: reasons.append("visibility")
            rec = days[day]
            w = rec["worst"]
            w["wind_mph"] = max(w.get("wind_mph", 0), round(wind))
            w["gust_mph"] = max(w.get("gust_mph", 0), round(gust))
            if rain is not None:
                w["rain_pct"] = max(w.get("rain_pct", 0), rain)
            if reasons:
                for r in reasons:
                    rec["reasons"][r] += 1
            else:
                rec["flyable_hours"].append(t[11:16])
        out = {}
        for day, rec in sorted(days.items()):
            n = len(rec["flyable_hours"])
            out[day] = {
                "flyable": n >= 3,  # need a usable block for a facade mission
                "flyable_hours": n,
                "first_last": [rec["flyable_hours"][0], rec["flyable_hours"][-1]] if n else None,
                "worst": rec["worst"],
                "main_reasons": sorted(rec["reasons"], key=rec["reasons"].get, reverse=True)[:2],
            }
        return out

    def check(self, prev):
        d = self.fetch()
        days = self.assess(d)
        start, end = self.site.window()
        watch = {k for k in days if start and end and start - timedelta(days=2) <= date.fromisoformat(k) <= end + timedelta(days=2)}
        if not watch:  # no window set, or it's beyond the forecast: watch the next 7 days
            watch = set(sorted(days)[:7])
        events: list[Event] = []
        old = (prev or {}).get("days", {})
        for day in sorted(watch):
            now, before = days[day], old.get(day)
            in_window = bool(start and end and start <= date.fromisoformat(day) <= end)
            if before is None:
                if prev is None:
                    continue  # first run: baseline only, no flood of events
            elif before["flyable"] == now["flyable"] and abs(before["flyable_hours"] - now["flyable_hours"]) < 2:
                continue
            verb = "now flyable" if now["flyable"] else "no longer flyable"
            why = ", ".join(now["main_reasons"]) or "conditions"
            sev = "high" if in_window and not now["flyable"] else ("medium" if in_window else "low")
            events.append(self.event(
                kind="weather.flyability_changed",
                title=f"{day}: {verb} ({now['flyable_hours']} flyable daylight hours)",
                summary=(f"Worst: wind {now['worst'].get('wind_mph')} mph at {self.site.limits.flight_altitude_m} m, "
                         f"gusts {now['worst'].get('gust_mph')} mph, rain {now['worst'].get('rain_pct')}%. "
                         + ("" if now["flyable"] else f"Limited by {why}.")),
                severity_hint=sev, valid_from=day, valid_to=day,
                dedupe_key=f"flyability:{day}",
                data={"day": day, "in_flight_window": in_window, **now, "before": before},
                url="https://open-meteo.com/",
            ))
        if start and end:
            flyable = [k for k in sorted(days) if start <= date.fromisoformat(k) <= end and days[k]["flyable"]]
            covered = [k for k in days if start <= date.fromisoformat(k) <= end]
            summary_key = (tuple(flyable), len(covered))
            if prev is not None and tuple(prev.get("window_flyable", [])) != tuple(flyable) and covered:
                events.append(self.event(
                    kind="weather.window_summary",
                    title=f"Flight window {start}..{end}: {len(flyable)} of {len(covered)} forecast days flyable",
                    summary=("Flyable: " + ", ".join(flyable)) if flyable else "No flyable day in the window so far.",
                    severity_hint="high" if len(flyable) <= 1 else "medium",
                    valid_from=str(start), valid_to=str(end), dedupe_key=f"window:{start}:{end}",
                    data={"flyable_days": flyable, "forecast_days_in_window": covered},
                ))
        return {"days": days, "window_flyable": [k for k in sorted(days) if start and end and start <= date.fromisoformat(k) <= end and days[k]["flyable"]],
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, events


def flyable_odds(site: Site, month_day_from: str, month_day_to: str, years: int = 5) -> dict:
    """Historical odds a day in a calendar range is flyable (daily max gust + rain), for picking a permit date.

    month_day_*: "MM-DD". Uses the Open-Meteo archive (ERA5).
    """
    L = site.limits
    this_year = date.today().year
    good = total = 0
    per_year = {}
    for y in range(this_year - years, this_year):
        s, e = f"{y}-{month_day_from}", f"{y}-{month_day_to}"
        d = get_json("https://archive-api.open-meteo.com/v1/archive", {
            "latitude": site.lat, "longitude": site.lon, "start_date": s, "end_date": e,
            "daily": "wind_gusts_10m_max,wind_speed_10m_max,precipitation_sum", "wind_speed_unit": "mph",
            "timezone": "America/New_York"})
        dd = d["daily"]
        ok = sum(1 for g, w, p in zip(dd["wind_gusts_10m_max"], dd["wind_speed_10m_max"], dd["precipitation_sum"])
                 if g is not None and g <= L.max_gust_mph and w <= L.max_wind_mph and (p or 0) < 1.0)
        per_year[y] = f"{ok}/{len(dd['time'])}"
        good += ok
        total += len(dd["time"])
    return {"range": f"{month_day_from}..{month_day_to}", "flyable_share": round(good / total, 2) if total else None,
            "per_year": per_year, "note": "Daily max at 10 m, rain under 1 mm. A rough guide, stricter than hourly."}


# ---------------------------------------------------------------- NWS alerts

class WeatherAlerts(Monitor):
    name = "weather_alerts"
    cadence_s = 900

    def check(self, prev):
        d = get_json("https://api.weather.gov/alerts/active", {"point": f"{self.site.lat:.4f},{self.site.lon:.4f}"})
        alerts = {}
        for f in d.get("features", []):
            p = f["properties"]
            alerts[p["id"]] = {k: p.get(k) for k in ("event", "headline", "severity", "onset", "ends", "description", "areaDesc")}
        old = (prev or {}).get("alerts", {})
        events = []
        for aid, a in alerts.items():
            if aid in old:
                continue
            sev = {"Extreme": "high", "Severe": "high", "Moderate": "medium"}.get(a["severity"], "low")
            events.append(self.event(kind="weather.alert_new", title=f"NWS: {a['event']}", summary=a["headline"] or "",
                                     severity_hint=sev, valid_from=a["onset"], valid_to=a["ends"], dedupe_key=f"nws:{aid}",
                                     data=a, url="https://alerts.weather.gov/"))
        for aid in set(old) - set(alerts):
            events.append(self.event(kind="weather.alert_ended", title=f"NWS alert ended: {old[aid]['event']}",
                                     severity_hint="info", dedupe_key=f"nws:{aid}", data=old[aid]))
        return {"alerts": alerts}, events


# ---------------------------------------------------------------- METAR / TAF

class AviationWeather(Monitor):
    """Current observations at nearby airports. Emits when the nearest field crosses the site's wind/gust limits."""
    name = "aviation_weather"
    cadence_s = 1800

    def check(self, prev):
        ids = ",".join(self.site.airports)
        obs = get_json("https://aviationweather.gov/api/data/metar", {"ids": ids, "format": "json"}) or []
        L = self.site.limits
        now = {}
        for m in obs:
            kt_to_mph = 1.15078
            wspd, wgst = (m.get("wspd") or 0) * kt_to_mph, (m.get("wgst") or 0) * kt_to_mph
            dist = distance_nm(self.site.lat, self.site.lon, m["lat"], m["lon"])
            now[m["icaoId"]] = {"wind_mph": round(wspd), "gust_mph": round(wgst), "visib": m.get("visib"),
                                "flight_category": m.get("fltCat"), "raw": m.get("rawOb"), "distance_nm": round(dist, 1),
                                "over_limits": wspd > L.max_wind_mph or wgst > L.max_gust_mph}
        events = []
        if now:
            nearest = min(now, key=lambda k: now[k]["distance_nm"])
            was = ((prev or {}).get("obs", {}).get(nearest) or {}).get("over_limits")
            cur = now[nearest]
            if prev is not None and was is not None and was != cur["over_limits"]:
                events.append(self.event(
                    kind="weather.observed_limits", severity_hint="medium" if cur["over_limits"] else "low",
                    title=f"{nearest} now {'above' if cur['over_limits'] else 'within'} flight limits: "
                          f"wind {cur['wind_mph']} mph, gusts {cur['gust_mph']} mph",
                    summary=cur["raw"] or "", dedupe_key=f"metar:{nearest}", data=cur,
                    url=f"https://aviationweather.gov/data/metar/?ids={nearest}"))
        return {"obs": now}, events


# ---------------------------------------------------------------- TFRs

class TFR(Monitor):
    """FAA temporary flight restrictions. Emits when an active TFR appears/disappears within radius of the site."""
    name = "tfr"
    cadence_s = 1800
    near_flight_cadence_s = 900

    def check(self, prev):
        active = get_json("https://tfr.faa.gov/tfrapi/getTfrList")
        active_ids = {t["notam_id"]: t for t in active}
        geo = get_json("https://tfr.faa.gov/geoserver/TFR/ows", {
            "service": "WFS", "version": "1.1.0", "request": "GetFeature",
            "typeName": "TFR:V_TFR_LOC", "outputFormat": "application/json", "maxFeatures": 2000})
        near = {}
        for f in geo.get("features", []):
            p = f.get("properties", {})
            nid = (p.get("NOTAM_KEY") or "").split("-")[0]
            if nid not in active_ids or not f.get("geometry"):
                continue  # the shape layer keeps expired TFRs; only trust the active list
            dist = geom_distance_nm(self.site.lat, self.site.lon, f["geometry"])
            if dist <= self.site.radius_nm:
                t = active_ids[nid]
                cur = near.get(nid)
                if cur is None or dist < cur["distance_nm"]:
                    near[nid] = {"type": t.get("type"), "description": t.get("description"), "state": t.get("state"),
                                 "distance_nm": round(dist, 2), "title": p.get("TITLE"), "legal": p.get("LEGAL")}
        # Also catch NY/NJ TFRs whose shape isn't published yet (by state, as a lower-confidence hint)
        same_state = {nid: t for nid, t in active_ids.items() if t.get("state") in ("NY", "NJ") and nid not in near}
        old_near = (prev or {}).get("near", {})
        old_state = (prev or {}).get("same_state", {})
        events = []
        for nid, t in near.items():
            if nid in old_near:
                continue
            where = "covers the site" if t["distance_nm"] == 0 else f"{t['distance_nm']} NM from the site"
            events.append(self.event(
                kind="airspace.tfr_new", severity_hint="high",
                title=f"TFR {nid} {where}: {t['type']}",
                summary=t["description"] or "", dedupe_key=f"tfr:{nid}", data={"notam_id": nid, **t},
                url=f"https://tfr.faa.gov/tfr3/?page=detail_{nid.replace('/', '_')}"))
        for nid, t in same_state.items():
            if nid in old_state or nid in old_near:
                continue
            events.append(self.event(
                kind="airspace.tfr_regional", severity_hint="medium",
                title=f"New {t.get('state')} TFR {nid}: {t.get('type')} (location not yet matched to the site)",
                summary=t.get("description") or "", dedupe_key=f"tfr:{nid}", data={"notam_id": nid, **t},
                url=f"https://tfr.faa.gov/tfr3/?page=detail_{nid.replace('/', '_')}"))
        for nid in set(old_near) - set(active_ids):
            events.append(self.event(kind="airspace.tfr_ended", severity_hint="low",
                                     title=f"TFR {nid} near the site has ended", dedupe_key=f"tfr:{nid}", data=old_near[nid]))
        return {"near": near, "same_state": same_state, "active_count": len(active_ids)}, events


# ---------------------------------------------------------------- UAS facility map ceiling

class UASCeiling(Monitor):
    """LAANC grid ceilings around the site (0-400 ft AGL). Emits if the ceiling at the site changes."""
    name = "uas_ceiling"
    cadence_s = 86400
    URL = ("https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/"
           "FAA_UAS_FacilityMap_Data/FeatureServer/0/query")

    def check(self, prev):
        pad = 0.002  # ~200 m box: grid cells are 1/60 deg, so this hits the cell(s) at the site
        env = {"xmin": self.site.lon - pad, "ymin": self.site.lat - pad, "xmax": self.site.lon + pad,
               "ymax": self.site.lat + pad, "spatialReference": {"wkid": 4326}}
        import json as _json
        d = get_json(self.URL, {"geometry": _json.dumps(env), "geometryType": "esriGeometryEnvelope",
                                "spatialRel": "esriSpatialRelIntersects", "outFields": "CEILING,APT1_FAAID,APT1_NAME",
                                "returnGeometry": "false", "f": "json"})
        cells = [f["attributes"] for f in d.get("features", [])]
        if cells:
            ceiling = min(c["CEILING"] for c in cells)
            airport = cells[0].get("APT1_FAAID")
            snap = {"ceiling_ft": ceiling, "airport": airport, "cells": len(cells), "in_grid": True}
        else:
            snap = {"ceiling_ft": None, "airport": None, "cells": 0, "in_grid": False}
        events = []
        if prev is not None and (prev.get("ceiling_ft"), prev.get("in_grid")) != (snap["ceiling_ft"], snap["in_grid"]):
            events.append(self.event(
                kind="airspace.laanc_ceiling_changed", severity_hint="high",
                title=(f"LAANC ceiling at site changed: {prev.get('ceiling_ft')} -> {snap['ceiling_ft']} ft"
                       if snap["in_grid"] else "Site no longer inside a LAANC facility-map grid"),
                summary="Check the authorization and flight plan altitudes.", dedupe_key="laanc:ceiling", data=snap,
                url="https://faa.maps.arcgis.com/apps/webappviewer/index.html?id=9c2e4406710048e19806ebf6a06754ad"))
        return snap, events


# ---------------------------------------------------------------- Federal Register (rule changes)

class Regulations(Monitor):
    """New FAA / DHS / TSA documents about drones. Each becomes a candidate 'discovery' for the embedding match."""
    name = "regulations"
    cadence_s = 6 * 3600
    TERMS = ["unmanned aircraft", "UAS", "drone", "remote pilot", "Part 107", "flight restriction"]
    AGENCIES = ["federal-aviation-administration", "homeland-security-department", "transportation-security-administration"]

    def check(self, prev):
        since = (date.today() - timedelta(days=30)).isoformat()
        params = {"per_page": 50, "order": "newest", "conditions[publication_date][gte]": since,
                  "conditions[agencies][]": self.AGENCIES, "conditions[term]": " | ".join(f'"{t}"' for t in self.TERMS),
                  "fields[]": ["document_number", "title", "type", "abstract", "html_url", "publication_date", "agencies"]}
        d = get_json("https://www.federalregister.gov/api/v1/documents.json", params)
        docs = {r["document_number"]: r for r in d.get("results", [])}
        relevant = re.compile(r"unmanned|drone|\bUAS\b|remote pilot|part 107|flight restriction|airspace|"
                              r"special security instructions|national defense airspace", re.I)
        docs = {k: r for k, r in docs.items() if relevant.search(f"{r.get('title') or ''} {r.get('abstract') or ''}")}
        seen = set((prev or {}).get("seen", []))
        events = []
        for num, r in docs.items():
            if prev is None or num in seen:
                continue
            title = r.get("title") or ""
            is_rule = r.get("type") in ("Rule", "Proposed Rule")
            boring = re.search(r"Petition for Exemption|Summary of Petition|Airworthiness Directive", title, re.I)
            events.append(self.event(
                kind="rules.document_new",
                severity_hint="medium" if is_rule and not boring else "low",
                title=f"{r.get('type')}: {title[:140]}",
                summary=(r.get("abstract") or "")[:600], valid_from=r.get("publication_date"),
                dedupe_key=f"fr:{num}", url=r.get("html_url"),
                data={"document_number": num, "type": r.get("type"), "agencies": [a.get("name") for a in r.get("agencies", [])],
                      "embed_text": f"{title}\n{r.get('abstract') or ''}"}))
        return {"seen": sorted(seen | set(docs))[-500:]}, events


# ---------------------------------------------------------------- NYC permitted events

class NYCEvents(Monitor):
    """Permitted street events in the site's borough during (and around) the flight window."""
    name = "nyc_events"
    cadence_s = 6 * 3600
    BIG = re.compile(r"parade|marathon|festival|street fair|rally|march|plaza|block party", re.I)

    def check(self, prev):
        start, end = self.site.window()
        start = start or date.today()
        end = end or start + timedelta(days=14)
        lo, hi = (start - timedelta(days=1)).isoformat(), (end + timedelta(days=1)).isoformat()
        where = f"start_date_time <= '{hi}T23:59:59' AND end_date_time >= '{lo}T00:00:00'"
        if self.site.borough:
            where += f" AND event_borough = '{self.site.borough}'"
        rows, page = [], 1000
        while len(rows) < 20000:  # Socrata pages at 1000 rows; a busy Manhattan week has several thousand
            batch = get_json("https://data.cityofnewyork.us/resource/tvpp-9vvx.json",
                             {"$where": where, "$limit": page, "$offset": len(rows), "$order": "event_id"})
            rows.extend(batch)
            if len(batch) < page:
                break
        street_words = self._street_words()
        hits = {}
        for r in rows:
            loc = (r.get("event_location") or "")
            precincts = {p.strip() for p in (r.get("police_precinct") or "").split(",") if p.strip()}
            if self.site.police_precinct:
                near = self.site.police_precinct in precincts
            else:  # fallback: same street name (loose: Broadway is 13 miles long)
                near = bool(street_words) and any(w in loc.upper() for w in street_words)
            big = bool(self.BIG.search(f"{r.get('event_type','')} {r.get('event_name','')}"))
            if near or big:
                hits[r["event_id"]] = {k: r.get(k) for k in ("event_name", "event_type", "start_date_time", "end_date_time",
                                                            "event_location", "street_closure_type", "event_borough",
                                                            "police_precinct")} | {"near_site": near}
        seen = set((prev or {}).get("seen", []))
        events = []
        for eid, r in hits.items():
            if prev is None or eid in seen:
                continue
            events.append(self.event(
                kind="city.event_permitted",
                severity_hint="medium" if r["near_site"] else "low",
                title=f"{r['event_type']}: {r['event_name']} ({r['start_date_time'][:10]})",
                summary=f"{r['event_location'][:200]}. Closure: {r.get('street_closure_type') or 'n/a'}",
                valid_from=r["start_date_time"], valid_to=r["end_date_time"], dedupe_key=f"nycevent:{eid}", data=r,
                url="https://data.cityofnewyork.us/City-Government/NYC-Permitted-Event-Information/tvpp-9vvx"))
        return {"seen": sorted(seen | set(hits))[-2000:], "matched": len(hits), "scanned": len(rows)}, events

    def _street_words(self) -> list[str]:
        # "120 Broadway, New York" -> ["BROADWAY"]; good enough to match event_location strings
        a = (self.site.address or "").split(",")[0].upper()
        a = re.sub(r"^\d+[A-Z]?\s+", "", a).strip()
        return [a] if a else []


# ---------------------------------------------------------------- Space weather

class SpaceWeather(Monitor):
    """NOAA planetary K index forecast. Kp >= 5 (geomagnetic storm) can degrade GPS."""
    name = "space_weather"
    cadence_s = 3 * 3600
    THRESHOLD = 5.0

    def check(self, prev):
        rows = get_json("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json")
        if rows and isinstance(rows[0], list):  # older format: header row + lists
            hdr = rows[0]
            rows = [dict(zip(hdr, r)) for r in rows[1:]]
        storm_days = defaultdict(float)
        for r in rows:
            if r.get("observed") in ("predicted", "estimated"):
                kp = float(r.get("kp") or 0)
                if kp >= self.THRESHOLD:
                    day = r["time_tag"][:10]
                    storm_days[day] = max(storm_days[day], kp)
        old = (prev or {}).get("storm_days", {})
        events = []
        if prev is not None:
            for day, kp in storm_days.items():
                if day not in old:
                    events.append(self.event(kind="space.geomagnetic_storm", severity_hint="medium",
                                             title=f"Geomagnetic storm forecast {day} (Kp {kp:.1f}): GPS may be degraded",
                                             valid_from=day, valid_to=day, dedupe_key=f"kp:{day}", data={"kp": kp},
                                             url="https://www.swpc.noaa.gov/products/planetary-k-index"))
        return {"storm_days": dict(storm_days)}, events


# ---------------------------------------------------------------- Site context (one-off)

def site_context(address: str) -> dict:
    """NYC address -> coordinates, building id (BIN), roof height and year built. Free, no key."""
    g = get_json("https://geosearch.planninglabs.nyc/v2/search", {"text": address, "size": 1})
    if not g.get("features"):
        raise ValueError(f"No NYC match for {address!r}")
    f = g["features"][0]
    lon, lat = f["geometry"]["coordinates"]
    pad = f["properties"].get("addendum", {}).get("pad", {})
    out = {"label": f["properties"].get("label"), "lat": lat, "lon": lon, "bin": pad.get("bin"), "bbl": pad.get("bbl"),
           "borough": (f["properties"].get("borough") or "").title()}
    if pad.get("bin"):
        b = get_json("https://data.cityofnewyork.us/resource/5zhs-2jue.json",
                     {"bin": pad["bin"], "$select": "height_roof,ground_elevation,construction_year"})
        if b:
            out.update({"roof_height_ft": float(b[0]["height_roof"]) if b[0].get("height_roof") else None,
                        "ground_elevation_ft": b[0].get("ground_elevation"),
                        "year_built": b[0].get("construction_year")})
    return out


ALL = [WeatherForecast, WeatherAlerts, AviationWeather, TFR, UASCeiling, Regulations, NYCEvents, SpaceWeather]
