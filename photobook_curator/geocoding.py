"""Reverse Geocoding via Nominatim mit lokalem Cache und Rate Limit."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Optional

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

# Offline-Näherung für Tests / --no-geocode: Städte innerhalb max. Distanz
OFFLINE_CITIES = [
    {"city": "Paris", "region_admin": "Île-de-France", "country": "Frankreich", "lat": 48.8566, "lon": 2.3522},
    {"city": "Lyon", "region_admin": "Auvergne-Rhône-Alpes", "country": "Frankreich", "lat": 45.7640, "lon": 4.8357},
    {"city": "Marseille", "region_admin": "Provence-Alpes-Côte d'Azur", "country": "Frankreich", "lat": 43.2965, "lon": 5.3698},
    {"city": "Berlin", "region_admin": "Berlin", "country": "Deutschland", "lat": 52.5200, "lon": 13.4050},
    {"city": "München", "region_admin": "Bayern", "country": "Deutschland", "lat": 48.1351, "lon": 11.5820},
    {"city": "Rom", "region_admin": "Latium", "country": "Italien", "lat": 41.9028, "lon": 12.4964},
    {"city": "Florenz", "region_admin": "Toskana", "country": "Italien", "lat": 43.7696, "lon": 11.2558},
    {"city": "Barcelona", "region_admin": "Katalonien", "country": "Spanien", "lat": 41.3874, "lon": 2.1686},
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def offline_reverse(lat: float, lon: float, max_km: float = 25.0) -> dict[str, Optional[str]]:
    """Ordnet Koordinaten der nächsten bekannten Stadt zu; sonst kein Ortsname (Transit)."""
    best = None
    best_d = float("inf")
    for city in OFFLINE_CITIES:
        d = _haversine_km(lat, lon, city["lat"], city["lon"])
        if d < best_d:
            best_d = d
            best = city
    if best is None or best_d > max_km:
        return {"city": None, "region_admin": None, "country": None, "raw_display": None}
    return {
        "city": best["city"],
        "region_admin": best["region_admin"],
        "country": best["country"],
        "raw_display": f"{best['city']}, {best['country']}",
    }


class GeocodeCache:
    def __init__(
        self,
        cache_path: Path,
        user_agent: str = "photobook-curator/0.1",
        min_interval_s: float = 1.1,
        enabled: bool = True,
    ) -> None:
        self.cache_path = cache_path
        self.enabled = enabled
        self.min_interval_s = min_interval_s
        self._last_call = 0.0
        self._cache: dict[str, Any] = {}
        if cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}
        self._geocoder: Optional[Nominatim] = None
        if enabled:
            self._geocoder = Nominatim(user_agent=user_agent, timeout=15)

    def _key(self, lat: float, lon: float, precision: int = 4) -> str:
        return f"{lat:.{precision}f},{lon:.{precision}f}"

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.time()

    def reverse(self, lat: float, lon: float) -> dict[str, Optional[str]]:
        """Gibt city, region_admin, country zurück."""
        key = self._key(lat, lon)
        if key in self._cache:
            return self._cache[key]

        empty = {"city": None, "region_admin": None, "country": None, "raw_display": None}
        if not self.enabled or self._geocoder is None:
            result = offline_reverse(lat, lon)
            self._cache[key] = result
            return result

        self._throttle()
        try:
            loc = self._geocoder.reverse((lat, lon), language="de", exactly_one=True)
        except (GeocoderTimedOut, GeocoderServiceError, Exception):
            self._cache[key] = empty
            return empty

        if loc is None:
            self._cache[key] = empty
            return empty

        addr = loc.raw.get("address", {}) if hasattr(loc, "raw") else {}
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
            or addr.get("suburb")
            or addr.get("hamlet")
        )
        region_admin = addr.get("state") or addr.get("region") or addr.get("county")
        country = addr.get("country")
        result = {
            "city": city,
            "region_admin": region_admin,
            "country": country,
            "raw_display": getattr(loc, "address", None),
        }
        self._cache[key] = result
        return result
