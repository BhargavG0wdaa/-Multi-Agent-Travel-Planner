"""
geocode.py — place name -> coordinates, via OpenStreetMap's Nominatim (no key).

Nominatim's usage policy allows at most 1 request per second, so calls are
throttled, and results are cached in memory so repeat lookups are free.
"""

from __future__ import annotations
import threading
import time
from dataclasses import dataclass

from travel_planner.services.http import get_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@dataclass(frozen=True)
class Location:
    name: str       # Nominatim's full display name, e.g. "Goa, India"
    lat: float
    lon: float


_cache: dict[tuple[str, str | None], Location | None] = {}
_lock = threading.Lock()
_last_call = 0.0


def geocode(place: str, country_code: str | None = None) -> Location | None:
    """Best match for a place name, or None if nothing matches.

    country_code (e.g. "in") restricts the search to one country.
    """
    global _last_call
    key = (place.strip().lower(), country_code)
    if key in _cache:
        return _cache[key]

    params = {"q": place, "format": "json", "limit": 1}
    if country_code:
        params["countrycodes"] = country_code
    with _lock:                      # one request at a time, >= 1s apart
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            data = get_json(NOMINATIM_URL, params)
        finally:
            _last_call = time.monotonic()

    loc = Location(data[0]["display_name"], float(data[0]["lat"]), float(data[0]["lon"])) if data else None
    _cache[key] = loc
    return loc
