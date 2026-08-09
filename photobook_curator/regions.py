"""Phase 2: Feine GPS-Cluster, Reverse Geocoding, Regionenbildung."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sklearn.cluster import DBSCAN
from tqdm import tqdm

from .geocoding import GeocodeCache
from .models import BookPlan, FineCluster, Photo, Region


# ~400 m Radius in Grad (Erde ~111 km/Grad)
DEFAULT_EPS_DEG = 400.0 / 111_000.0


def cluster_fine_locations(
    photos: list[Photo],
    eps_meters: float = 400.0,
    min_samples: int = 2,
) -> list[FineCluster]:
    gps_indices = [i for i, p in enumerate(photos) if p.has_gps]
    if not gps_indices:
        return []

    coords = np.array([[photos[i].gps_lat, photos[i].gps_lon] for i in gps_indices])
    eps = eps_meters / 111_000.0
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean").fit_predict(coords)

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
    """Ordnet GPS-lose Bilder zeitlich naheliegenden Regionen zu. Gibt Unbestimmt-Indizes zurück."""
    unassigned: list[int] = []
    threshold = timedelta(hours=max_hours)

    for i, photo in enumerate(photos):
        if getattr(photo, "is_aside", False):
            photo.region = "Optional"
            continue
        if photo.region is not None:
            continue
        if photo.datetime_taken is None or not regions:
            photo.region = "Unbestimmt"
            photo.add_flag("unbestimmt")
            unassigned.append(i)
            continue

        best_region: Optional[Region] = None
        best_delta: Optional[timedelta] = None
        for region in regions:
            if region.start_time is None or region.end_time is None:
                continue
            if region.start_time <= photo.datetime_taken <= region.end_time:
                delta = timedelta(0)
            else:
                delta = min(
                    abs(photo.datetime_taken - region.start_time),
                    abs(photo.datetime_taken - region.end_time),
                )
            if delta <= threshold and (best_delta is None or delta < best_delta):
                best_delta = delta
                best_region = region

        if best_region is not None:
            photo.region = best_region.name
            photo.country = best_region.country
            photo.assigned_by_time = True
            photo.add_flag("assigned_by_time")
            best_region.photo_indices.append(i)
            # Zeiten aktualisieren
            times = [
                photos[j].datetime_taken
                for j in best_region.photo_indices
                if photos[j].datetime_taken
            ]
            if times:
                best_region.start_time = min(times)
                best_region.end_time = max(times)
                best_region.day_count = max(
                    1, (best_region.end_time.date() - best_region.start_time.date()).days + 1
                )
        else:
            photo.region = "Unbestimmt"
            photo.add_flag("unbestimmt")
            unassigned.append(i)

    for region in regions:
        region.photo_indices = sorted(
            set(region.photo_indices),
            key=lambda i: photos[i].datetime_taken or datetime.min,
        )
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
