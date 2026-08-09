"""Phase 1: phash-basierte Duplikat- und Ähnlichkeitserkennung."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import cv2
import imagehash
from PIL import Image
from tqdm import tqdm

from .bursts import _burst_score
from .models import Photo
from .quality import compute_technical_score
from .utils import load_bgr_cached


def _phash_int_from_bgr(bgr) -> int | None:
    try:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        return int(str(imagehash.phash(img)), 16)
    except Exception:
        return None


def compute_phashes(photos: list[Photo]) -> None:
    for photo in tqdm(photos, desc="pHash berechnen", unit="img"):
        try:
            bgr = load_bgr_cached(photo.path)
            value = _phash_int_from_bgr(bgr)
            if value is None:
                photo.phash = None
                photo.add_flag("phash_failed")
            else:
                # Hex-String bleibt für CSV/Kompatibilität
                photo.phash = f"{value:016x}"
        except Exception:
            photo.phash = None
            photo.add_flag("phash_failed")


def _hamming_int(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _near_in_time(a: Photo, b: Photo, max_minutes: float) -> bool:
    if a.datetime_taken is None or b.datetime_taken is None:
        return True  # ohne Zeit: nur Hash entscheiden lassen
    return abs(a.datetime_taken - b.datetime_taken) <= timedelta(minutes=max_minutes)


def _near_in_space(a: Photo, b: Photo, max_km: float = 0.5) -> bool:
    """True wenn beide keine GPS haben oder Distanz klein ist."""
    if not a.has_gps or not b.has_gps:
        return True
    from math import asin, cos, radians, sin, sqrt

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
    hash_threshold: int = 5,
    max_minutes: float = 5.0,
    *,
    burst_seconds: float = 30.0,
    keep_per_burst: int = 2,
    min_burst_size: int = 3,
) -> tuple[int, int]:
    """
    Gruppiert nahezu identische Bilder.
    - Kurze Serie (<= burst_seconds, >= min_burst_size): beste keep_per_burst behalten
    - Sonst: 1 bestes behalten, Rest Duplikat
    Returns (duplicate_count, burst_reject_count).
    """
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

    # int-Hashes einmalig parsen
    phash_ints: list[int | None] = []
    for p in photos:
        if p.phash:
            try:
                phash_ints.append(int(p.phash, 16))
            except ValueError:
                phash_ints.append(None)
        else:
            phash_ints.append(None)

    with_time: list[int] = []
    no_time: list[int] = []
    for i, p in enumerate(photos):
        if phash_ints[i] is None:
            continue
        if p.datetime_taken is None:
            no_time.append(i)
        else:
            with_time.append(i)
    with_time.sort(key=lambda i: photos[i].datetime_taken or datetime.min)

    window = timedelta(minutes=max_minutes)

    # Zwei-Zeiger: nur Paare innerhalb des Zeitfensters vergleichen
    right = 0
    for left in tqdm(range(len(with_time)), desc="Duplikate prüfen", unit="img"):
        i = with_time[left]
        t_i = photos[i].datetime_taken
        assert t_i is not None
        if right < left + 1:
            right = left + 1
        while right < len(with_time):
            j = with_time[right]
            t_j = photos[j].datetime_taken
            assert t_j is not None
            if t_j - t_i > window:
                break
            right += 1
        ha = phash_ints[i]
        assert ha is not None
        for k in range(left + 1, right):
            j = with_time[k]
            hb = phash_ints[j]
            assert hb is not None
            if _hamming_int(ha, hb) <= hash_threshold and _near_in_space(photos[i], photos[j]):
                union(i, j)

    # Fotos ohne Zeitstempel: untereinander + gegen alle mit Hash (selten)
    for a_pos, i in enumerate(no_time):
        ha = phash_ints[i]
        assert ha is not None
        for j in no_time[a_pos + 1 :]:
            hb = phash_ints[j]
            assert hb is not None
            if _hamming_int(ha, hb) <= hash_threshold and _near_in_space(photos[i], photos[j]):
                union(i, j)
        for j in with_time:
            hb = phash_ints[j]
            assert hb is not None
            if (
                _hamming_int(ha, hb) <= hash_threshold
                and _near_in_time(photos[i], photos[j], max_minutes)
                and _near_in_space(photos[i], photos[j])
            ):
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        if phash_ints[i] is not None:
            groups[find(i)].append(i)

    dup_count = 0
    burst_reject = 0
    burst_id = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        times = [photos[i].datetime_taken for i in members if photos[i].datetime_taken]
        span_s = (max(times) - min(times)).total_seconds() if times else 10**9
        is_burst = span_s <= burst_seconds and len(members) >= min_burst_size

        if is_burst:
            burst_id += 1
            ranked = sorted(members, key=lambda idx: _burst_score(photos[idx]), reverse=True)
            keep = set(ranked[: max(1, keep_per_burst)])
            for i in members:
                photos[i].burst_group_id = burst_id
                if i in keep:
                    photos[i].add_flag("burst_keep")
                else:
                    photos[i].is_burst_reject = True
                    photos[i].add_flag("burst_reject")
                    photos[i].duplicate_of = photos[ranked[0]].filename
                    compute_technical_score(photos[i])
                    burst_reject += 1
        else:
            best = max(members, key=lambda i: photos[i].technical_score)
            for i in members:
                if i == best:
                    continue
                photos[i].is_duplicate = True
                photos[i].duplicate_of = photos[best].filename
                photos[i].add_flag("duplicate")
                compute_technical_score(photos[i])
                dup_count += 1

    return dup_count, burst_reject
