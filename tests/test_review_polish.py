"""Tests: Gruppenbonus, Swap-Kandidat, Review-Warnungen."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from photobook_curator.models import Photo
from photobook_curator.quality import compute_technical_score
from photobook_curator.review_export import best_swap_candidate
from photobook_curator.review_warnings import collect_review_warnings
from photobook_curator.selection import compute_final_score


def test_group_photo_bonus_raises_score() -> None:
    solo = Photo(
        path=Path("a.jpg"),
        filename="a.jpg",
        face_count=1,
        sharpness=400,
        exposure_mean=120,
        contrast=50,
        saturation=80,
    )
    group = Photo(
        path=Path("b.jpg"),
        filename="b.jpg",
        face_count=4,
        person_cluster_ids=[1, 2, 3, 4],
        sharpness=400,
        exposure_mean=120,
        contrast=50,
        saturation=80,
    )
    compute_technical_score(solo)
    compute_technical_score(group)
    s_solo = compute_final_score(solo)
    s_group = compute_final_score(group)
    assert s_group > s_solo


def test_best_swap_prefers_related_duplicate() -> None:
    photos = [
        Photo(path=Path("a.jpg"), filename="a.jpg", is_selected=True, burst_group_id=1),
        Photo(
            path=Path("b.jpg"),
            filename="b.jpg",
            is_duplicate=True,
            duplicate_of="a.jpg",
            burst_group_id=1,
            technical_score=80,
            final_score=80,
        ),
        Photo(
            path=Path("c.jpg"),
            filename="c.jpg",
            is_candidate=True,
            technical_score=90,
            final_score=90,
            chapter_folder="01_Rome/hauptteil",
        ),
    ]
    photos[0].chapter_folder = "01_Rome/hauptteil"
    kept = {0}
    alt = best_swap_candidate(photos, 0, kept)
    assert alt == 1


def test_collect_review_warnings_day_people_res() -> None:
    base = datetime(2024, 6, 1, 10, 0, 0)
    photos = [
        Photo(
            path=Path("d1.jpg"),
            filename="d1.jpg",
            datetime_taken=base,
            width=4000,
            height=3000,
            person_cluster_ids=[1],
            chapter_folder="01_A/hauptteil",
            is_selected=True,
        ),
        Photo(
            path=Path("d2.jpg"),
            filename="d2.jpg",
            datetime_taken=base + timedelta(days=1),
            width=4000,
            height=3000,
            person_cluster_ids=[2],
            chapter_folder="01_A/hauptteil",
        ),
        Photo(
            path=Path("tiny.jpg"),
            filename="tiny.jpg",
            datetime_taken=base,
            width=640,
            height=480,
            person_cluster_ids=[1],
            chapter_folder="01_A/hauptteil",
            is_selected=True,
        ),
    ]
    kept = {0, 2}
    warns = collect_review_warnings(photos, kept, folder="01_A/hauptteil")
    keys = {w.key for w in warns}
    assert "warn_day_gaps" in keys
    assert "warn_people_missing" in keys
    assert "warn_low_res" in keys
