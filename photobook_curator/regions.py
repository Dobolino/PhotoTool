"""Phase 2: Feine GPS-Cluster, Reverse Geocoding, Regionenbildung."""

from __future__ import annotations

from collections import defaultdict
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sklearn.cluster import DBSCAN
from tqdm import tqdm

from .geocoding import GeocodeCache
from .models import BookPlan, FineCluster, Photo, Region


EARTH_RADIUS_M = 6_371_000.0


def cluster_fine_locations(
    photos: list[Photo],
    eps_meters: float = 400.0,
    min_samples: int = 2,
) -> list[FineCluster]:
    """GPS-Cluster mit Haversine-Distanz (ost-west-korrekt auf allen Breiten)."""
    gps_indices = [i for i, p in enumerate(photos) if p.has_gps]
    for photo in photos:
        if not photo.has_gps and (photo.gps_lat is not None or photo.gps_lon is not None):
            photo.add_flag("gps_invalid")
    if not gps_indices:
        return []

    coords = np.array(
        [[photos[i].gps_lat, photos[i].gps_lon] for i in gps_indices],
        dtype=np.float64,
    )
    coords_rad = np.radians(coords)
    eps = float(eps_meters) / EARTH_RADIUS_M
    labels = DBSCAN(
        eps=eps,
        min_samples=min_samples,
        metric="haversine",
    ).fit_predict(coords_rad)

    clusters_map: dict[int, list[int]] = defaultdict(list)
    for local_idx, label in enumerate(labels):
        photo_idx = gps_indices[local_idx]
        if label < 0:
            # Noise: eigener Singleton-Cluster
            label = -(photo_idx + 1)
        photos[photo_idx].fine_cluster_id = int(label)
        clusters_map[int(label)].append(photo_idx)

    fine_clusters: list[FineCluster] = []
    for cid, members in clusters_map.items():
        lats = [photos[i].gps_lat for i in members if photos[i].gps_lat is not None]
        lons = [photos[i].gps_lon for i in members if photos[i].gps_lon is not None]
        fine_clusters.append(
            FineCluster(
                cluster_id=cid,
                lat=float(np.mean(lats)),
                lon=float(np.mean(lons)),
                photo_indices=members,
            )
        )
    return fine_clusters


def geocode_clusters(clusters: list[FineCluster], cache: GeocodeCache) -> None:
    for cluster in tqdm(clusters, desc="Reverse Geocoding", unit="cluster"):
        info = cache.reverse(cluster.lat, cluster.lon)
        # city bewusst None lassen (Transit/Unterwegs) – kein Ort_-Platzhalter
        cluster.city = info.get("city")
        cluster.region_admin = info.get("region_admin")
        cluster.country = info.get("country")
        cluster.location_source = info.get("source", "gps_online" if cache.enabled else "gps_offline")
    cache.save()


def build_regions(photos: list[Photo], clusters: list[FineCluster]) -> list[Region]:
    by_city: dict[str, list[int]] = defaultdict(list)
    city_country: dict[str, Optional[str]] = {}
    for cluster in clusters:
        if not cluster.city:
            # Kein Ortsname (z. B. Transit/Unterwegs): später zeitlich zuordnen
            continue
        city = cluster.city
        city_country[city] = cluster.country
        for idx in cluster.photo_indices:
            if getattr(photos[idx], "is_aside", False):
                # Screenshots/Dokumente bleiben im Optional-Pool
                photos[idx].region = "Optional"
                continue
            photos[idx].region = city
            photos[idx].country = cluster.country
            photos[idx].place_label = city
            photos[idx].location_evidence = {
                "version": 1,
                "source": getattr(cluster, "location_source", "legacy"),
                "assigned_at": datetime.now(timezone.utc).isoformat(),
                "latitude": photos[idx].gps_lat,
                "longitude": photos[idx].gps_lon,
            }
            by_city[city].append(idx)

    regions: list[Region] = []
    for city, indices in by_city.items():
        times = [photos[i].datetime_taken for i in indices if photos[i].datetime_taken]
        start = min(times) if times else None
        end = max(times) if times else None
        day_count = 1
        if start and end:
            day_count = max(1, (end.date() - start.date()).days + 1)
        regions.append(
            Region(
                name=city,
                country=city_country.get(city),
                photo_indices=sorted(
                    indices,
                    key=lambda i: photos[i].datetime_taken or datetime.min,
                ),
                start_time=start,
                end_time=end,
                day_count=day_count,
            )
        )

    # Chronologisch nach erstem Foto
    regions.sort(key=lambda r: r.start_time or datetime.max)
    for i, region in enumerate(regions):
        region.chapter_index = i
    return regions


def assign_photos_without_gps(
    photos: list[Photo],
    regions: list[Region],
    max_hours: float = 6.0,
) -> list[int]:
    """Use immutable GPS observations, never a city's first-to-last visit span.

    Repeated visits (e.g. arrival and departure in Hong Kong) must not absorb an
    intervening trip. Inferred photos cannot themselves become location anchors.
    Opposing nearby cities leave a photo unresolved rather than guessing.
    """
    unassigned: list[int] = []
    assigned_at = datetime.now(timezone.utc).isoformat()
    # Group equal timestamps as well: two cameras can record different cities at
    # the same time when their clocks disagree. Never settle that tie by order.
    anchors: dict[datetime, list[tuple[int, Region]]] = defaultdict(list)
    for region in regions:
        for idx in region.photo_indices:
            anchor = photos[idx]
            if (anchor.has_gps and anchor.datetime_taken is not None
                    and not anchor.assigned_by_time and not anchor.is_aside
                    and anchor.region == region.name):
                anchors[anchor.datetime_taken].append((idx, region))
    times = sorted(anchors)

    def evidence(source: str, **details) -> dict:
        return dict(version=1, source=source, assigned_at=assigned_at, **details)

    def unresolved(i: int, warning: str, **details) -> None:
        photo = photos[i]
        photo.region = "Unbestimmt"
        photo.country = None
        photo.place_label = None
        photo.assigned_by_time = False
        photo.add_flag("unbestimmt")
        photo.add_flag("location_ambiguous" if warning == "conflicting_anchors" else "location_unknown")
        photo.location_evidence = evidence("unknown", warning=warning, **details)
        unassigned.append(i)

    for i, photo in enumerate(photos):
        if getattr(photo, "is_aside", False):
            photo.region = "Optional"
            continue
        if photo.region is not None:
            continue
        if photo.has_gps:
            # A real coordinate that could not be resolved is stronger evidence
            # than an unrelated nearby photo's city.
            unresolved(i, "gps_unresolved", latitude=photo.gps_lat, longitude=photo.gps_lon)
            continue
        if photo.gps_lat is not None or photo.gps_lon is not None or "gps_invalid" in photo.flags:
            unresolved(i, "invalid_gps")
            continue
        if photo.datetime_taken is None:
            unresolved(i, "missing_datetime")
            continue
        pos = bisect_left(times, photo.datetime_taken)
        nearby: dict[tuple[str, Optional[str]], tuple[float, int, Region]] = {}
        # Only the nearest recorded moment on either side is needed. Captures
        # beyond those moments cannot be a stronger temporal observation.
        for at in times[max(0, pos - 1):pos + 1]:
            delta = abs((photo.datetime_taken - at).total_seconds()) / 3600.0
            if delta > max_hours:
                continue
            for idx, region in anchors[at]:
                key = (region.name, region.country)
                if key not in nearby or delta < nearby[key][0]:
                    nearby[key] = (delta, idx, region)
        candidates = sorted(nearby.values(), key=lambda item: (item[0], str(photos[item[1]].path)))
        if len(candidates) > 1:
            unresolved(i, "conflicting_anchors", candidates=[
                dict(anchor_path=str(photos[idx].path), region=region.name,
                     country=region.country, delta_hours=round(delta, 6))
                for delta, idx, region in candidates[:2]
            ])
        elif candidates:
            best_delta, anchor_idx, best_region = candidates[0]
            photo.region = best_region.name
            photo.country = best_region.country
            photo.place_label = best_region.name
            photo.assigned_by_time = True
            photo.add_flag("assigned_by_time")
            photo.location_evidence = evidence("time_nearest",
                anchor_path=str(photos[anchor_idx].path), anchor_region=best_region.name,
                anchor_country=best_region.country, delta_hours=round(best_delta, 6))
            best_region.photo_indices.append(i)
        else:
            unresolved(i, "no_nearby_anchor")

    for region in regions:
        region.photo_indices = sorted(
            set(region.photo_indices),
            key=lambda i: photos[i].datetime_taken or datetime.min,
        )
        region_times = [photos[i].datetime_taken for i in region.photo_indices if photos[i].datetime_taken]
        if region_times:
            region.start_time, region.end_time = min(region_times), max(region_times)
            region.day_count = max(1, (region.end_time.date() - region.start_time.date()).days + 1)
    return unassigned


def build_location_plan(
    photos: list[Photo],
    cache: GeocodeCache,
    eps_meters: float = 400.0,
    gps_time_hours: float = 6.0,
) -> BookPlan:
    clusters = cluster_fine_locations(photos, eps_meters=eps_meters)
    if clusters:
        geocode_clusters(clusters, cache)
    regions = build_regions(photos, clusters)
    unassigned = assign_photos_without_gps(photos, regions, max_hours=gps_time_hours)
    return BookPlan(regions=regions, unassigned_indices=unassigned)


def promote_unassigned_to_region(photos: list[Photo], plan: BookPlan) -> Region | None:
    """
    Macht GPS-lose / unbestimmte Fotos auswählbar.
    Ohne diese Region würden Alben ohne GPS 0 Bilder bekommen.
    Nach Transit-Erkennung aufrufen (Transit hat Vorrang).
    """
    remaining: list[int] = []
    seen: set[int] = set()
    for i in plan.unassigned_indices:
        if i in seen:
            continue
        p = photos[i]
        if getattr(p, "is_aside", False):
            continue
        if p.is_duplicate or getattr(p, "is_burst_reject", False):
            continue
        remaining.append(i)
        seen.add(i)
    # Auch Fotos mit Region „Unbestimmt“, die nicht in der Liste stehen
    for i, p in enumerate(photos):
        if i in seen:
            continue
        if getattr(p, "is_aside", False):
            continue
        if p.region == "Unbestimmt":
            remaining.append(i)
            seen.add(i)

    if not remaining:
        return None

    name = "Album" if not plan.regions else "Unbestimmt"
    times = [photos[i].datetime_taken for i in remaining if photos[i].datetime_taken]
    start = min(times) if times else None
    end = max(times) if times else None
    day_count = 1
    if start and end:
        day_count = max(1, (end.date() - start.date()).days + 1)

    region = Region(
        name=name,
        photo_indices=sorted(
            remaining,
            key=lambda i: photos[i].datetime_taken or datetime.min,
        ),
        start_time=start,
        end_time=end,
        day_count=day_count,
        chapter_index=len(plan.regions),
    )
    for i in remaining:
        photos[i].region = name
        if "unbestimmt" in photos[i].flags and name == "Album":
            photos[i].flags = [f for f in photos[i].flags if f != "unbestimmt"]
    plan.regions.append(region)
    plan.unassigned_indices = [
        i for i in plan.unassigned_indices if i not in seen
    ]
    return region
