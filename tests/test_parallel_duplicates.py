"""Tests für Parallelisierung und Duplikat-Anzeige."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from photobook_curator.local_analysis import LocalAnalysisOptions, run_local_analysis
from photobook_curator.models import Photo
from photobook_curator.review_export import (
    all_duplicate_indices,
    duplicate_kind,
    related_duplicates,
)
from photobook_curator.scan import scan_photos
from photobook_curator.utils import clear_bgr_cache


def test_local_analysis_parallel_matches_serial(tmp_path: Path) -> None:
    inp = tmp_path / "in"
    inp.mkdir()
    for i, color in enumerate(((10, 20, 30), (200, 40, 10), (80, 90, 100), (5, 5, 5))):
        Image.new("RGB", (120, 90), color).save(inp / f"{i}.jpg")
    photos_a = scan_photos(inp)
    photos_b = scan_photos(inp)
    clear_bgr_cache()
    opts = LocalAnalysisOptions(
        enable_documents=False,
        enable_faces=False,
        enable_finger=False,
        enable_accidental=False,
        enable_weak_night=False,
        enable_embeddings=False,
        enable_local_aesthetic=True,
        workers=1,
    )
    r1 = run_local_analysis(photos_a, opts)
    clear_bgr_cache()
    opts.workers = 2
    r2 = run_local_analysis(photos_b, opts)
    assert r1.decoded == r2.decoded == 4
    assert r2.workers == 2
    for a, b in zip(photos_a, photos_b):
        assert abs(a.sharpness - b.sharpness) < 1e-3
        assert abs((a.aesthetic_score or 0) - (b.aesthetic_score or 0)) < 0.5


def test_duplicate_kind_and_related() -> None:
    photos = [
        Photo(path=Path("a.jpg"), filename="a.jpg", is_selected=True),
        Photo(
            path=Path("b.jpg"),
            filename="b.jpg",
            is_duplicate=True,
            duplicate_of="a.jpg",
            burst_group_id=1,
        ),
        Photo(
            path=Path("c.jpg"),
            filename="c.jpg",
            is_burst_reject=True,
            burst_group_id=1,
        ),
        Photo(
            path=Path("d.jpg"),
            filename="d.jpg",
            is_duplicate=True,
            flags=["content_duplicate"],
            content_cluster_id=7,
        ),
    ]
    photos[0].burst_group_id = 1
    photos[0].content_cluster_id = 7
    assert duplicate_kind(photos[1]) == "phash"
    assert duplicate_kind(photos[2]) == "burst"
    assert duplicate_kind(photos[3]) == "content"
    related = related_duplicates(photos, 0)
    assert 1 in related and 2 in related
    assert set(all_duplicate_indices(photos)) == {1, 2, 3}
