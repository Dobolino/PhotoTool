"""Tests für Kapitel-/Karten-Vorschau."""

from datetime import datetime
from pathlib import Path

from photobook_curator.map_preview import build_chapter_previews, write_chapter_map
from photobook_curator.models import BookPlan, Photo, Region, TransitSection


def _sample():
    photos = [
        Photo(
            path=Path("a.jpg"),
            filename="a.jpg",
            datetime_taken=datetime(2024, 6, 1, 10),
            gps_lat=48.8566,
            gps_lon=2.3522,
            region="Paris",
            is_selected=True,
            chapter_type="Hauptteil",
        ),
        Photo(
            path=Path("b.jpg"),
            filename="b.jpg",
            datetime_taken=datetime(2024, 6, 2, 10),
            gps_lat=45.7640,
            gps_lon=4.8357,
            region="Lyon",
            is_selected=True,
            chapter_type="Hauptteil",
        ),
        Photo(
            path=Path("t.jpg"),
            filename="t.jpg",
            datetime_taken=datetime(2024, 6, 1, 18),
            gps_lat=47.2,
            gps_lon=3.5,
            region="Transit:Paris->Lyon",
            is_selected=True,
            chapter_type="Transit",
        ),
    ]
    plan = BookPlan(
        regions=[
            Region(
                name="Paris",
                photo_indices=[0],
                start_time=datetime(2024, 6, 1),
                end_time=datetime(2024, 6, 1),
                chapter_index=0,
            ),
            Region(
                name="Lyon",
                photo_indices=[1],
                start_time=datetime(2024, 6, 2),
                end_time=datetime(2024, 6, 2),
                chapter_index=1,
            ),
        ],
        transits=[
            TransitSection(
                from_region="Paris",
                to_region="Lyon",
                photo_indices=[2],
                chapter_index=0,
            )
        ],
    )
    order = [
        (0, "01_Paris/hauptteil", "Hauptteil"),
        (2, "01b_Transit_Paris-Lyon", "Transit"),
        (1, "02_Lyon/hauptteil", "Hauptteil"),
    ]
    return photos, plan, order


def test_build_chapter_previews_includes_regions_and_transit():
    photos, plan, order = _sample()
    chapters = build_chapter_previews(photos, plan, order)
    titles = [c.title for c in chapters]
    assert any("Paris" in t for t in titles)
    assert any("Lyon" in t for t in titles)
    assert any("Transit" in t for t in titles)
    paris = next(c for c in chapters if "Paris" in c.title and c.kind == "region")
    assert paris.selected_count == 1
    assert paris.mean_lat is not None


def test_write_chapter_map_html(tmp_path: Path):
    photos, plan, order = _sample()
    path = write_chapter_map(photos, plan, tmp_path, order)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "leaflet" in text.lower()
    assert "Paris" in text
    assert "Lyon" in text
