# Live-data monitors

Watches the outside world for a drone site and writes an **event** whenever something changes that could affect the flight. Sources and reasoning: [Ryan/data-sources.md](../Ryan/data-sources.md). Free feeds only, no keys, Python 3.9+ standard library.

```bash
python3 monitors/run.py --once          # run every monitor once
python3 monitors/run.py                 # keep running, each on its cadence
python3 monitors/run.py --once --only tfr,weather_forecast
python3 monitors/run.py --context "120 Broadway, New York"   # coordinates, BIN, roof height
python3 monitors/run.py --odds 12-08 12-12                   # historical share of flyable days
```

The first run of each monitor records a baseline and emits nothing; later runs emit only changes. Events are appended to `monitors/data/events.jsonl`; snapshots live in `monitors/data/state/`. Both are git-ignored.

**In the app:** the north star app runs these monitors itself and turns their events into graph changes; see [Ryan/northstar/README.md](../Ryan/northstar/README.md#live-data-feeds).

## Monitors

| Monitor | Source | Cadence (near flight) | Emits |
| --- | --- | --- | --- |
| `weather_forecast` | Open-Meteo, hourly, wind at flight altitude | 1 h (15 min) | `weather.flyability_changed` per day; `weather.window_summary` when the set of flyable days in the window changes |
| `weather_alerts` | NWS active alerts at the site | 15 min | `weather.alert_new`, `weather.alert_ended` |
| `aviation_weather` | METAR at KLGA, KJFK, KEWR | 30 min | `weather.observed_limits` when the nearest airport crosses the wind/gust limits |
| `tfr` | FAA TFR list + shapes | 30 min (15 min) | `airspace.tfr_new` within `radius_nm` (or covering the site), `airspace.tfr_regional` for new NY/NJ TFRs without a shape yet, `airspace.tfr_ended` |
| `uas_ceiling` | FAA UAS Facility Map (LAANC grid) | daily | `airspace.laanc_ceiling_changed` |
| `regulations` | Federal Register: FAA, DHS, TSA, drone and airspace terms | 6 h | `rules.document_new`, with `data.embed_text` for the embedding match |
| `nyc_events` | NYC permitted events in the window, same police precinct as the site, plus large events borough-wide | 6 h | `city.event_permitted` |
| `space_weather` | NOAA Kp forecast | 3 h | `space.geomagnetic_storm` (Kp of 5 or more: GPS may degrade) |

"Near flight" = within 3 days of `flight_window.start`.

## Site config

Copy `site.example.json` to `site.json` (or pass `--site path`). Use `--context "<address>"` to fill `lat`, `lon` and `bin`. The `limits` are **placeholders for the drone experts to set**; `min_visibility_m` 4828 is Part 107's 3 statute miles.

## Event shape

Every monitor emits the same JSON, matching the event-log decision (R1/L1) so it can go straight into Postgres later:

```json
{"id": "ev_…", "source": "tfr", "kind": "airspace.tfr_new", "site": "facade-120-broadway",
 "title": "TFR 6/1234 covers the site: SECURITY", "summary": "…", "severity_hint": "high",
 "valid_from": "…", "valid_to": "…", "url": "…", "dedupe_key": "tfr:6/1234", "data": {…},
 "observed_at": "2026-11-14T21:14:27+00:00"}
```

`severity_hint` is a hint only; the attention engine does the real scoring. `dedupe_key` identifies the real-world thing, so repeated updates about the same day or TFR can update one item in place.

## Findings from the first run (2026-11-14, 120 Broadway)

- 120 Broadway is **outside the LAANC facility-map grid**: no automated approval there, so plan for a DroneZone airspace authorization (and the NYPD process).
- Wind at 120 m for 18 to 22 Nov is within the placeholder limits on all five days; EWR and JFK were reporting gusts above 25 mph at the time.
- 17 permitted events in the 1st Precinct during the window, including film-production curb closures at Chambers and Broadway.

## Adding a monitor

Subclass `Monitor` in `feeds.py`, set `name` and `cadence_s`, implement `check(prev) -> (snapshot, events)`, return events only for meaningful changes (none on the first run), and add the class to `ALL`.
