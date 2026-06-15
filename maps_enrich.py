"""Location enrichment via Nominatim (OpenStreetMap) — 100% free, no API key.

Searches for a company's locations in Greece, returns the primary address and
a list of all addresses found. Respects Nominatim's 1-request-per-second policy.

IMPORTANT: OSM does NOT expose building floor area / square meters. The m²
figure stays an LLM estimate; this only adds addresses + location count.
"""
import time
import requests

_ENDPOINT = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "AlterEgoLeadScraper/1.0 (tsiflik@bc.edu)"}
_last_request = 0.0


def _throttle():
    """Enforce ≥1.1s between Nominatim requests."""
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    _last_request = time.time()


def enrich(company: str) -> dict:
    """Return {'maps_address': str, 'maps_locations': int, 'maps_all_addresses': [...]} or {} if failed."""
    if not company:
        return {}
    try:
        _throttle()
        r = requests.get(
            _ENDPOINT,
            headers=_HEADERS,
            params={
                "q": f"{company}, Greece",
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 20,
                "countrycodes": "gr",
            },
            timeout=12,
        )
        r.raise_for_status()
        places = r.json()
        if not places:
            return {}
        all_addresses = [
            p.get("display_name", "")
            for p in places
            if p.get("display_name")
        ]
        return {
            "maps_address": all_addresses[0],
            "maps_locations": len(places),
            "maps_all_addresses": all_addresses,
        }
    except Exception as e:
        print(f"[WARN] Location enrich failed for {company}: {e}")
        return {}


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Jumbo"
    result = enrich(name)
    print(f"Locations found: {result.get('maps_locations', 0)}")
    for i, addr in enumerate(result.get("maps_all_addresses", []), 1):
        print(f"  {i}. {addr}")
