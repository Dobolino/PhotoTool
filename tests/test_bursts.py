"""Tests für Serien-/Burst-Erkennung."""

from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from photobook_curator.bursts import mark_bursts
from photobook_curator.duplicates import compute_phashes, mark_duplicates
from photobook_curator.models import Photo
from photobook_curator.quality import analyze_image_quality, compute_technical_score


def _make_burst_photos(tmp_path: Path, n: int = 5) -> list[Photo]:
    photos: list[Photo] = []
    base = datetime(2024, 6, 10, 15, 30, 0)
    # Gemeinsame Basisszene, leichte Variationen
    base_img = Image.new("RGB", (400, 300), (80, 140, 200))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(base_img)
    draw.rectangle([0, 150, 400, 300], fill=(40, 120, 50))
    draw.ellipse([300, 40, 360, 100], fill=(255, 220, 80))

    for i in range(n):
        path = tmp_path / f"burst_{i}.jpg"
        img = base_img.copy()
        # kleine visuelle Unterschiede
        ImageDraw.Draw(img).rectangle([10 + i * 3, 10, 40 + i * 3, 40], fill=(200, 50 + i * 10, 50))
        img.save(path, quality=92 - i)
        photo = Photo(
            path=path,
            filename=path.name,
            datetime_taken=base + timedelta(seconds=3 * i),
            gps_lat=48.8566,
            gps_lon=2.3522,
            width=400,
            height=300,
            camera_model="iPhone 14 Pro",
        )
        analyze_image_quality(photo)
        compute_technical_score(photo)
        photos.append(photo)
    compute_phashes(photos)
    return photos


def test_burst_keeps_top_two(tmp_path):
    photos = _make_burst_photos(tmp_path, n=5)
    rejected = mark_bursts(photos, max_seconds=30, keep_per_burst=2, min_burst_size=3, hash_threshold=20)
    assert rejected == 3
    kept = [p for p in photos if not p.is_burst_reject]
    assert len(kept) == 2
    assert all(p.burst_group_id == 1 for p in photos)
    assert sum(1 for p in photos if "burst_keep" in p.flags) == 2


def test_short_pair_not_burst(tmp_path):
    photos = _make_burst_photos(tmp_path, n=2)
    rejected = mark_bursts(photos, max_seconds=30, keep_per_burst=2, min_burst_size=3)
    assert rejected == 0
    assert all(not p.is_burst_reject for p in photos)


def test_near_identical_burst_keeps_two_via_duplicates(tmp_path):
    """Sehr ähnliche Burst-Frames: mark_duplicates behält 2, nicht nur 1."""
    photos = _make_burst_photos(tmp_path, n=5)
    dup_count, burst_reject = mark_duplicates(
        photos,
        hash_threshold=5,
        max_minutes=5,
        burst_seconds=30,
        keep_per_burst=2,
        min_burst_size=3,
    )
    assert dup_count == 0
    assert burst_reject == 3
    assert sum(1 for p in photos if "burst_keep" in p.flags) == 2


def test_exact_pair_is_duplicate_not_burst(tmp_path):
    photos = _make_burst_photos(tmp_path, n=2)
    # gleiches Bild nochmal wenige Minuten später → klassisches Duplikat
    import shutil

    src = photos[0].path
    dup_path = tmp_path / "exact_dup.jpg"
    shutil.copy2(src, dup_path)
    dup = Photo(
        path=dup_path,
        filename=dup_path.name,
        datetime_taken=photos[0].datetime_taken + timedelta(minutes=2),
        gps_lat=photos[0].gps_lat,
        gps_lon=photos[0].gps_lon,
        width=400,
        height=300,
        camera_model="iPhone 14 Pro",
    )
    analyze_image_quality(dup)
    compute_technical_score(dup)
    photos.append(dup)
    compute_phashes(photos)
    dup_count, burst_reject = mark_duplicates(photos, hash_threshold=5, max_minutes=5)
    assert dup_count >= 1
    assert burst_reject == 0
