"""Phase 1: phash-basierte Duplikat- und Ähnlichkeitserkennung."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Optional

import imagehash
from tqdm import tqdm

from .models import Photo
from .quality import compute_technical_score
from .utils import load_image


def compute_phashes(photos: list[Photo]) -> None:
    for photo in tqdm(photos, desc="pHash berechnen", unit="img"):
        try:
            img = load_image(photo.path)
            photo.phash = str(imagehash.phash(img))
        except Exception:
            photo.phash = None
            photo.add_flag("phash_failed")


def _hamming(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def _near_in_time(a: Photo, b: Photo, max_minutes: float) -> bool:
    if a.datetime_taken is None or b.datetime_taken is None:
        return True  # ohne Zeit: nur Hash entscheiden lassen
    return abs(a.datetime_taken - b.datetime_taken) <= timedelta(minutes=max_minutes)


def _near_in_space(a: Photo, b: Photo, max_km: float = 0.5) -> bool:
    """True wenn beide keine GPS haben oder Distanz klein ist."""
    if not a.has_gps or not b.has_gps:
        return True
    # grobe Haversine-Näherung
    from math import radians, cos, sin, asin, sqrt

    lon1, lat1, lon2, lat2 = map(
        radians, [a.gps_lon, a.gps_lat, b.gps_lon, b.gps_lat]  # type: ignore[arg-type]
    )
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    km = 2 * 6371 * asin(sqrt(h))
    return km <= max_km


def mark_duplicates(
    photos: list[Photo],
    hash_threshold: int = 8,
    max_minutes: float = 5.0,
) -> None:
    """Gruppiert ähnliche Bilder; behält das technisch beste, markiert Rest als Duplikat."""
    compute_phashes(photos)
    n = len(photos)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    indexed = [(i, p) for i, p in enumerate(photos) if p.phash]
    for idx_a, (i, a) in enumerate(tqdm(indexed, desc="Duplikate prüfen", unit="img")):
        for j, b in indexed[idx_a + 1 :]:
            if _hamming(a.phash, b.phash) <= hash_threshold and _near_in_time(
                a, b, max_minutes
            ) and _near_in_space(a, b):
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        if photos[i].phash:
            groups[find(i)].append(i)

    for members in groups.values():
        if len(members) < 2:
            continue
        # technisch bestes behalten
        best = max(members, key=lambda i: photos[i].technical_score)
        for i in members:
            if i == best:
                continue
            photos[i].is_duplicate = True
            photos[i].duplicate_of = photos[best].filename
            photos[i].add_flag("duplicate")
            compute_technical_score(photos[i])
