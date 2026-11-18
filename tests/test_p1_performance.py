"""P1 Performance: Decode-Cache, int-Hashes, Histogramm-Cache."""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from photobook_curator.duplicates import _hamming_int, compute_phashes, mark_duplicates
from photobook_curator.models import Photo
from photobook_curator.quality import analyze_image_quality, compute_technical_score
from photobook_curator.selection import color_histogram
from photobook_curator.utils import (
    clear_bgr_cache,
    image_display_size,
    load_bgr_cached,
    load_image,
)


def test_image_display_size_respects_orientation(tmp_path: Path):
    import piexif

    path = tmp_path / "rot.jpg"
    Image.new("RGB", (40, 20), (10, 20, 30)).save(
        path,
        exif=piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}}),
    )
    assert image_display_size(path) == (20, 40)


def test_bgr_cache_reuses_decode(tmp_path: Path):
    path = tmp_path / "a.jpg"
    Image.new("RGB", (120, 80), (40, 80, 120)).save(path)
    clear_bgr_cache()
    a = load_bgr_cached(path)
    b = load_bgr_cached(path)
    assert a is b
    clear_bgr_cache()
    c = load_bgr_cached(path)
    assert c is not a
    assert c.shape == a.shape


def test_hamming_int_matches_imagehash():
    import imagehash

    a = int(str(imagehash.hex_to_hash("ffffffffffffffff")), 16)
    b = int(str(imagehash.hex_to_hash("fffffffffffffffe")), 16)
    assert _hamming_int(a, b) == 1
    assert _hamming_int(a, a) == 0


def test_color_histogram_cached_on_photo(tmp_path: Path):
    path = tmp_path / "h.jpg"
    Image.new("RGB", (64, 64), (200, 100, 50)).save(path)
    photo = Photo(path=path, filename="h.jpg")
    clear_bgr_cache()
    h1 = color_histogram(photo)
    h2 = color_histogram(photo)
    assert h1 is not None
    assert h1 is h2


def test_duplicates_time_window_skips_distant_similar(tmp_path: Path):
    """Gleiche Szene Jahre auseinander → kein Duplikat (Zeitfenster)."""
    photos = []
    base = datetime(2020, 1, 1, 12, 0, 0)
    for i, days in enumerate([0, 400]):
        path = tmp_path / f"s{i}.jpg"
        Image.new("RGB", (80, 60), (90, 140, 200)).save(path)
        p = Photo(
            path=path,
            filename=path.name,
            datetime_taken=base + timedelta(days=days),
            width=80,
            height=60,
        )
        analyze_image_quality(p)
        compute_technical_score(p)
        photos.append(p)
    dups, bursts = mark_duplicates(photos, hash_threshold=5, max_minutes=5.0)
    assert dups == 0
    assert bursts == 0
    assert all(not p.is_duplicate for p in photos)


def test_phash_from_cache_compatible(tmp_path: Path):
    path = tmp_path / "p.jpg"
    Image.new("RGB", (100, 80), (30, 60, 90)).save(path)
    photo = Photo(path=path, filename="p.jpg")
    clear_bgr_cache()
    compute_phashes([photo])
    assert photo.phash is not None
    assert len(photo.phash) == 16
    int(photo.phash, 16)  # gültiges Hex
