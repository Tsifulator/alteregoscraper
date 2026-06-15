"""OPTIONAL OpenStreetMap footprint measurement (free, no API key).

Off by default (set USE_OVERPASS=true to enable). When on, it tries to MEASURE a
company's building footprint from real OSM geometry — best for single, well-mapped
sites (malls, big-box stores, hospitals, factories, stadiums). It complements, and
never replaces, the LLM m² estimate.

Pipeline:
  1. Nominatim geocode "<company> Greece" (with polygon geometry if available).
  2. If the match is already a polygon → compute its area directly.
  3. Else Overpass: find the largest building footprint near the point.
  4. Footprint area via equirectangular shoelace; ×building:levels when tagged
     to approximate cleanable FLOOR area.

Caveats surfaced to the caller: footprint ≠ floor area (unless levels known),
single-site only, coverage is patchy. Fails soft → returns {} on any problem.
"""
import math
import time
import urllib.parse

import os

import requests

USE_OVERPASS = os.getenv("USE_OVERPASS", "false").lower() == "true"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "AlterEgoLeadScraper/1.0 (facility-lead-research)"}


def _ring_area_m2(coords: list[list[float]]) -> float:
    """Area of a lon/lat ring in m² (equirectangular projection — fine at building scale)."""
    if len(coords) < 3:
        return 0.0
    lat0 = math.radians(sum(c[1] for c in coords) / len(coords))
    xs = [math.radians(c[0]) * math.cos(lat0) * 6371000 for c in coords]
    ys = [math.radians(c[1]) * 6371000 for c in coords]
    s = 0.0
    for i in range(len(coords)):
        j = (i + 1) % len(coords)
        s += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(s) / 2.0


def _geocode(company: str) -> dict | None:
    try:
        params = {"q": f"{company} Greece", "format": "json", "countrycodes": "gr",
                  "limit": 1, "polygon_geojson": 1, "extratags": 1}
        r = requests.get(f"{NOMINATIM}?{urllib.parse.urlencode(params)}",
                         headers=HEADERS, timeout=12)
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None
    except Exception:
        return None


def _area_from_geojson(geo: dict) -> float:
    t = geo.get("type")
    if t == "Polygon":
        return _ring_area_m2(geo["coordinates"][0])
    if t == "MultiPolygon":
        return sum(_ring_area_m2(poly[0]) for poly in geo["coordinates"])
    return 0.0


def _overpass_footprint(lat: float, lon: float) -> float:
    """Largest building footprint within ~120 m of the point."""
    q = (f'[out:json][timeout:20];'
         f'(way["building"](around:120,{lat},{lon});'
         f'rel["building"](around:120,{lat},{lon}););'
         f'out geom;')
    try:
        r = requests.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        best = 0.0
        for el in r.json().get("elements", []):
            geom = el.get("geometry")
            if not geom:
                continue
            ring = [[p["lon"], p["lat"]] for p in geom]
            best = max(best, _ring_area_m2(ring))
        return best
    except Exception:
        return 0.0


def enrich(company: str) -> dict:
    """Return {'osm_footprint_m2', 'osm_floor_m2'?, 'osm_note'} or {} if off/unavailable."""
    if not USE_OVERPASS or not company:
        return {}

    hit = _geocode(company)
    time.sleep(1.1)                       # Nominatim: max ~1 req/sec
    if not hit:
        return {}

    footprint = 0.0
    geo = hit.get("geojson")
    if geo and geo.get("type") in ("Polygon", "MultiPolygon"):
        footprint = _area_from_geojson(geo)
    if footprint < 50:                    # point match or tiny — try Overpass around it
        try:
            footprint = _overpass_footprint(float(hit["lat"]), float(hit["lon"]))
        except Exception:
            footprint = 0.0

    if footprint < 50:
        return {}

    result = {"osm_footprint_m2": f"~{round(footprint):,} m²"}
    levels = (hit.get("extratags") or {}).get("building:levels")
    try:
        if levels and float(levels) > 1:
            result["osm_floor_m2"] = f"~{round(footprint * float(levels)):,} m² ({levels} floors)"
    except Exception:
        pass
    result["osm_note"] = "measured roof footprint from OSM" + (
        "" if "osm_floor_m2" in result else " — floor count unknown")
    return result


if __name__ == "__main__":
    import sys
    os.environ["USE_OVERPASS"] = "true"
    USE_OVERPASS = True
    for name in (sys.argv[1:] or ["The Mall Athens", "IKEA Greece", "Hygeia Hospital Athens"]):
        print(f"{name!r:35} → {enrich(name)}")
