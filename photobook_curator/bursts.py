"""Serien-/Burst-Erkennung: aus kurzen Aufnahmeserien nur die besten behalten."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import imagehash
from tqdm import tqdm

from .models import Photo
from .quality import compute_technical_score


def _hamming(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 999
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def _near_space(a: Photo, b: Photo, max_km: float = 0.3) -> bool:
    if not a.has_gps or not b.has_gps:
        return True
    from math import asin, cos, radians, sin, sqrt

    lon1, lat1, lon2, lat2 = map(
        radians, [a.gps_lon, a.gps_lat, b.gps_lon, b.gps_lat]  # type: ignore[arg-type]
    )
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(h)) <= max_km


def _burst_score(photo: Photo) -> float:
    """Ranking innerhalb einer Serie: technischer Score, Abzug für schlechte Gesichter."""
    score = photo.technical_score
    if getattr(photo, "bad_face", False):
        score -= 40.0
    if getattr(photo, "eyes_closed", False):
        score -= 20.0
    if photo.face_count > 0:
        score += 3.0
    return score


def mark_bursts(
    photos: list[Photo],
    *,
    max_seconds: float = 30.0,
    hash_threshold: int = 14,
    keep_per_burst: int = 2,
    min_burst_size: int = 3,
) -> int:
    """
    Findet Serien ähnlicher Fotos innerhalb weniger Sekunden.
    Behält die besten `keep_per_burst` Bilder, Rest als burst_reject.
    Läuft nach der strikten Duplikaterkennung; bereits markierte Duplikate werden übersprungen.
    """
    timed = [
        (i, p)
        for i, p in enumerate(photos)
        if p.datetime_taken is not None
        and not p.is_duplicate
        and not getattr(p, "is_burst_reject", False)
        and p.phash
        and p.burst_group_id is None
    ]
    timed.sort(key=lambda ip: ip[1].datetime_taken or datetime.min)

    if len(timed) < min_burst_size:
        return 0

    parent = {i: i for i, _ in timed}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    window = timedelta(seconds=max_seconds)
    # Nur gegen zeitlich nahe Vorgänger prüfen (effizient)
    for pos, (i, a) in enumerate(tqdm(timed, desc="Serien/Bursts", unit="img")):
        t_a = a.datetime_taken
        assert t_a is not None
        for j, b in timed[max(0, pos - 40) : pos]:
            t_b = b.datetime_taken
            assert t_b is not None
            if t_a - t_b > window:
                continue
            if _hamming(a.phash, b.phash) <= hash_threshold and _near_space(a, b):
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i, _ in timed:
        groups[find(i)].append(i)

    burst_id = 0
    rejected = 0
    for members in groups.values():
        if len(members) < min_burst_size:
            continue
        burst_id += 1
        ranked = sorted(members, key=lambda idx: _burst_score(photos[idx]), reverse=True)
        keep = set(ranked[: max(1, keep_per_burst)])
        for idx in members:
            photos[idx].burst_group_id = burst_id
            if idx in keep:
                photos[idx].add_flag("burst_keep")
            else:
                photos[idx].is_burst_reject = True
                photos[idx].add_flag("burst_reject")
                # Referenz auf bestes Bild der Serie
                best = ranked[0]
                photos[idx].duplicate_of = photos[idx].duplicate_of or photos[best].filename
                compute_technical_score(photos[idx])
                rejected += 1

    return rejected
