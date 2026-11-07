"""Reverse Geocoding via Nominatim mit lokalem Cache und Rate Limit."""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

# Ortsnamen bewusst auf Englisch (Kapitel/UI einheitlich, z. B. Tokyo statt 東京)
GEOCODE_LANGUAGE = "en"

# Offline-Näherung für Tests / --no-geocode: Städte innerhalb max. Distanz
OFFLINE_CITIES = [
    {"city": "Paris", "region_admin": "Ile-de-France", "country": "France", "lat": 48.8566, "lon": 2.3522},
    {"city": "Lyon", "region_admin": "Auvergne-Rhone-Alpes", "country": "France", "lat": 45.7640, "lon": 4.8357},
    {"city": "Marseille", "region_admin": "Provence-Alpes-Cote d'Azur", "country": "France", "lat": 43.2965, "lon": 5.3698},
    {"city": "Berlin", "region_admin": "Berlin", "country": "Germany", "lat": 52.5200, "lon": 13.4050},
    {"city": "Munich", "region_admin": "Bavaria", "country": "Germany", "lat": 48.1351, "lon": 11.5820},
    {"city": "Rome", "region_admin": "Lazio", "country": "Italy", "lat": 41.9028, "lon": 12.4964},
    {"city": "Florence", "region_admin": "Tuscany", "country": "Italy", "lat": 43.7696, "lon": 11.2558},
    {"city": "Barcelona", "region_admin": "Catalonia", "country": "Spain", "lat": 41.3874, "lon": 2.1686},
    {"city": "Tokyo", "region_admin": "Tokyo", "country": "Japan", "lat": 35.6762, "lon": 139.6503},
    {"city": "Kyoto", "region_admin": "Kyoto", "country": "Japan", "lat": 35.0116, "lon": 135.7681},
    {"city": "Osaka", "region_admin": "Osaka", "country": "Japan", "lat": 34.6937, "lon": 135.5023},
    {"city": "Hiroshima", "region_admin": "Hiroshima", "country": "Japan", "lat": 34.3853, "lon": 132.4553},
    {"city": "Nara", "region_admin": "Nara", "country": "Japan", "lat": 34.6851, "lon": 135.8048},
    {"city": "Sapporo", "region_admin": "Hokkaido", "country": "Japan", "lat": 43.0618, "lon": 141.3545},
    {"city": "Fukuoka", "region_admin": "Fukuoka", "country": "Japan", "lat": 33.5904, "lon": 130.4017},
    {"city": "Nagoya", "region_admin": "Aichi", "country": "Japan", "lat": 35.1815, "lon": 136.9066},
    {"city": "Hong Kong", "region_admin": "Hong Kong", "country": "China", "lat": 22.3193, "lon": 114.1694},
]


def valid_coordinates(lat: float, lon: float) -> bool:
    return (not isinstance(lat, bool) and not isinstance(lon, bool)
            and isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and -90 <= lat <= 90 and -180 <= lon <= 180
            and math.isfinite(lat) and math.isfinite(lon))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def offline_reverse(lat: float, lon: float, max_km: float = 25.0) -> dict[str, Optional[str]]:
    """Ordnet Koordinaten der nächsten bekannten Stadt zu; sonst kein Ortsname (Transit)."""
    if not valid_coordinates(lat, lon):
        return {"city": None, "region_admin": None, "country": None, "raw_display": None}
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
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                self._cache = loaded if isinstance(loaded, dict) else {}
            except Exception:
                self._cache = {}
        self._geocoder: Optional[Nominatim] = None
        if enabled:
            self._geocoder = Nominatim(user_agent=user_agent, timeout=15)

    def _key(self, lat: float, lon: float, precision: int = 4) -> str:
        # Old versions mixed offline approximations with online results. Such
        # entries have no reliable origin and must not acquire one retroactively.
        mode = "online" if self.enabled else "offline"
        return f"v2:{mode}:{lat:.{precision}f},{lon:.{precision}f}:{GEOCODE_LANGUAGE}"

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        pending = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                    dir=self.cache_path.parent, suffix=".tmp", delete=False) as handle:
                pending = Path(handle.name)
                json.dump(self._cache, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(pending, self.cache_path)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.time()

    def reverse(self, lat: float, lon: float) -> dict[str, Optional[str]]:
        """Gibt city, region_admin, country zurück (Namen auf Englisch)."""
        empty = {"city": None, "region_admin": None, "country": None, "raw_display": None}
        if not valid_coordinates(lat, lon):
            return empty
        key = self._key(lat, lon)
        if key in self._cache:
            cached = self._cache[key]
            if (isinstance(cached, dict) and all(cached.get(k) is None
                    or isinstance(cached.get(k), str) for k in empty)
                    and cached.get("source") == ("gps_online" if self.enabled else "gps_offline")):
                return cached

        if not self.enabled or self._geocoder is None:
            result = offline_reverse(lat, lon)
            result["source"] = "gps_offline"
            self._cache[key] = result
            return result

        self._throttle()
        try:
            loc = self._geocoder.reverse(
                (lat, lon), language=GEOCODE_LANGUAGE, exactly_one=True
            )
        except (GeocoderTimedOut, GeocoderServiceError):
            # Transient: nicht cachen, damit ein Folgelauf erneut versucht
            return empty
        except Exception:
            return empty

        if loc is None:
            empty["source"] = "gps_online"
            self._cache[key] = empty
            return empty

        addr = loc.raw.get("address", {}) if hasattr(loc, "raw") else {}
        if not isinstance(addr, dict):
            return empty
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
            "source": "gps_online",
        }
        self._cache[key] = result
        return result
