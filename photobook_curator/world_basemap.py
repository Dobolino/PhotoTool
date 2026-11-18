"""Vereinfachte Weltkarte (Landumrisse) für die Tk-Karten-Vorschau."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parent / "data" / "world_land.json"


@lru_cache(maxsize=1)
def load_land_rings() -> list[list[list[float]]]:
    """Liste von Ringen: [[[lon, lat], ...], ...]."""
    if not _DATA.is_file():
        return []
    try:
        data = json.loads(_DATA.read_text(encoding="utf-8"))
    except Exception:
        return []
    rings: list[list[list[float]]] = []
    if isinstance(data, list):
        for feat in data:
            if isinstance(feat, list) and feat and isinstance(feat[0], list):
                # Feature = list of rings OR single ring of [lon,lat]
                if feat and isinstance(feat[0][0], (int, float)):
                    rings.append(feat)  # type: ignore[arg-type]
                else:
                    for ring in feat:
                        if isinstance(ring, list) and len(ring) >= 3:
                            rings.append(ring)
    return rings


def lonlat_to_xy(
    lon: float,
    lat: float,
    *,
    width: int,
    height: int,
    west: float = -180.0,
    east: float = 180.0,
    south: float = -85.0,
    north: float = 85.0,
    pad: float = 8.0,
) -> tuple[float, float]:
    span_x = max(east - west, 0.01)
    span_y = max(north - south, 0.01)
    x = pad + (lon - west) / span_x * (width - 2 * pad)
    y = pad + (north - lat) / span_y * (height - 2 * pad)
    return x, y


def draw_world_basemap(
    canvas,
    *,
    width: int,
    height: int,
    land_fill: str,
    land_outline: str,
    water_fill: str,
    grid_color: str,
    west: float = -180.0,
    east: float = 180.0,
    south: float = -85.0,
    north: float = 85.0,
) -> None:
    """Zeichnet Ozean, Gradnetz und Landumrisse (equirectangular)."""
    canvas.create_rectangle(0, 0, width, height, fill=water_fill, outline="")

    # Dezentes Gradnetz
    for lon in range(-180, 181, 30):
        if lon < west or lon > east:
            continue
        x, _ = lonlat_to_xy(lon, 0, width=width, height=height, west=west, east=east, south=south, north=north)
        canvas.create_line(x, 0, x, height, fill=grid_color)
    for lat in range(-60, 61, 30):
        if lat < south or lat > north:
            continue
        _, y = lonlat_to_xy(0, lat, width=width, height=height, west=west, east=east, south=south, north=north)
        canvas.create_line(0, y, width, y, fill=grid_color)

    rings = load_land_rings()
    for ring in rings:
        pts: list[float] = []
        for lon, lat in ring:
            if lon < west - 5 or lon > east + 5 or lat < south - 5 or lat > north + 5:
                # Punkt weit außerhalb – Ring trotzdem zeichnen (Clipping durch Canvas)
                pass
            x, y = lonlat_to_xy(
                lon, lat, width=width, height=height, west=west, east=east, south=south, north=north
            )
            pts.extend([x, y])
        if len(pts) >= 6:
            canvas.create_polygon(
                *pts,
                fill=land_fill,
                outline=land_outline,
                width=1,
                smooth=False,
            )


def trip_bounds(
    points: list[tuple[float, float]],
    *,
    pad_deg: float = 8.0,
    min_span: float = 20.0,
) -> tuple[float, float, float, float]:
    """(west, east, south, north) mit Luft, mind. Weltausschnitt."""
    if not points:
        return -180.0, 180.0, -85.0, 85.0
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    south, north = min(lats), max(lats)
    west, east = min(lons), max(lons)
    span_lat = max(north - south, min_span)
    span_lon = max(east - west, min_span)
    mid_lat = (south + north) / 2
    mid_lon = (west + east) / 2
    south = max(-85.0, mid_lat - span_lat / 2 - pad_deg)
    north = min(85.0, mid_lat + span_lat / 2 + pad_deg)
    west = max(-180.0, mid_lon - span_lon / 2 - pad_deg)
    east = min(180.0, mid_lon + span_lon / 2 + pad_deg)
    return west, east, south, north


def world_view_bounds() -> tuple[float, float, float, float]:
    return -180.0, 180.0, -85.0, 85.0
