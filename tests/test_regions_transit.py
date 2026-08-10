"""Tests für Regionenbildung und Transit-Erkennung."""

from datetime import datetime, timedelta
from pathlib import Path

from photobook_curator.geocoding import GeocodeCache, offline_reverse
from photobook_curator.models import Photo
from photobook_curator.regions import assign_photos_without_gps, build_regions, cluster_fine_locations
from photobook_curator.transit import detect_transits
from photobook_curator.models import BookPlan, Region


def _photo(name, dt, lat=None, lon=None, region=None):
    p = Photo(path=Path(name), filename=name, datetime_taken=dt, gps_lat=lat, gps_lon=lon)
    p.region = region
    return p


def test_offline_reverse_cities():
    assert offline_reverse(48.8566, 2.3522)["city"] == "Paris"
    assert offline_reverse(45.7640, 4.8357)["city"] == "Lyon"
    # zwischen Paris und Lyon: kein Stadtname
    assert offline_reverse(47.3, 3.6)["city"] is None
    # Japan offline auf Englisch
    tokyo = offline_reverse(35.6762, 139.6503)
    assert tokyo["city"] == "Tokyo"
    assert tokyo["country"] == "Japan"


def test_geocode_cache_key_includes_english_language(tmp_path):
    from photobook_curator.geocoding import GEOCODE_LANGUAGE

    assert GEOCODE_LANGUAGE == "en"
    cache = GeocodeCache(tmp_path / "cache.json", enabled=False)
    assert cache._key(35.6762, 139.6503).endswith(":en")


def test_cluster_and_regions(tmp_path):
    base = datetime(2024, 6, 1, 10, 0, 0)
    photos = [
        _photo("p1.jpg", base, 48.8566, 2.3522),
        _photo("p2.jpg", base + timedelta(hours=1), 48.8570, 2.3530),
        _photo("l1.jpg", base + timedelta(days=2), 45.7640, 4.8357),
        _photo("l2.jpg", base + timedelta(days=2, hours=2), 45.7645, 4.8360),
    ]
    clusters = cluster_fine_locations(photos, eps_meters=500, min_samples=1)
    cache = GeocodeCache(tmp_path / "cache.json", enabled=False)
    from photobook_curator.regions import geocode_clusters

    geocode_clusters(clusters, cache)
    regions = build_regions(photos, clusters)
    names = [r.name for r in regions]
    assert names == ["Paris", "Lyon"]


def test_transit_detection():
    base = datetime(2024, 6, 1, 10, 0, 0)
    photos = [
        _photo("a1.jpg", base, region="Paris"),
        _photo("a2.jpg", base + timedelta(hours=2), region="Paris"),
        _photo("t1.jpg", base + timedelta(days=1, hours=1)),
        _photo("t2.jpg", base + timedelta(days=1, hours=2)),
        _photo("t3.jpg", base + timedelta(days=1, hours=3)),
        _photo("b1.jpg", base + timedelta(days=2), region="Lyon"),
    ]
    plan = BookPlan(
        regions=[
            Region(
                name="Paris",
                photo_indices=[0, 1],
                start_time=photos[0].datetime_taken,
                end_time=photos[1].datetime_taken,
                chapter_index=0,
            ),
            Region(
                name="Lyon",
                photo_indices=[5],
                start_time=photos[5].datetime_taken,
                end_time=photos[5].datetime_taken,
                chapter_index=1,
            ),
        ],
        unassigned_indices=[2, 3, 4],
    )
    for i in [0, 1]:
        photos[i].region = "Paris"
    photos[5].region = "Lyon"
    transits = detect_transits(photos, plan, min_photos=3, max_transit_quota=5)
    assert len(transits) == 1
    assert transits[0].from_region == "Paris"
    assert transits[0].to_region == "Lyon"
    assert len(transits[0].photo_indices) == 3


def test_assign_without_gps():
    base = datetime(2024, 6, 1, 10, 0, 0)
    photos = [
        _photo("a1.jpg", base, 48.85, 2.35, region="Paris"),
        _photo("nogps.jpg", base + timedelta(hours=1)),  # innerhalb Region
        _photo("far.jpg", base + timedelta(days=5)),
    ]
    regions = [
        Region(
            name="Paris",
            photo_indices=[0],
            start_time=base,
            end_time=base + timedelta(hours=3),
            chapter_index=0,
        )
    ]
    photos[0].region = "Paris"
    unassigned = assign_photos_without_gps(photos, regions, max_hours=6)
    assert photos[1].region == "Paris"
    assert photos[1].assigned_by_time is True
    assert 2 in unassigned


def test_promote_unassigned_makes_album_without_gps():
    """Alben ohne GPS dürfen nicht bei 0 Auswahl landen."""
    from photobook_curator.models import BookPlan
    from photobook_curator.regions import promote_unassigned_to_region
    from photobook_curator.selection import build_book_order, mark_candidates

    base = datetime(2024, 6, 1, 10, 0, 0)
    photos = [
        _photo("a.jpg", base),
        _photo("b.jpg", base + timedelta(minutes=5)),
        _photo("c.jpg", base + timedelta(minutes=10)),
    ]
    for p in photos:
        p.technical_score = 70.0
        p.region = "Unbestimmt"
        p.add_flag("unbestimmt")
    plan = BookPlan(regions=[], unassigned_indices=[0, 1, 2])
    promoted = promote_unassigned_to_region(photos, plan)
    assert promoted is not None
    assert promoted.name == "Album"
    assert len(plan.regions) == 1
    mark_candidates(photos, plan, target_n=2, candidate_factor=2.0)
    order = build_book_order(photos, plan, similarity_threshold=1.1)
    assert len(order) >= 1
    assert any(p.is_selected for p in photos)
