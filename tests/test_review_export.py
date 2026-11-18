"""Tests für manuelle Auswahl-Nachkontrolle."""

from datetime import datetime
from pathlib import Path

from photobook_curator.models import BookPlan, Photo, Region
from photobook_curator.review_export import (
    apply_manual_selection,
    chapter_sections,
    plan_from_photos,
    rebuild_order_from_kept,
)


def _photo(name, selected=True, folder="01_Paris/hauptteil", pos=1, region="Paris"):
    p = Photo(
        path=Path(name),
        filename=name,
        datetime_taken=datetime(2024, 6, 1, 10, pos),
        region=region,
        chapter_folder=folder,
        chapter_type="Hauptteil",
        is_selected=selected,
        book_position=pos if selected else None,
        is_candidate=True,
        technical_score=70,
        final_score=70,
    )
    return p


def test_rebuild_order_keeps_chapter_blocks():
    photos = [
        _photo("a.jpg", pos=1, folder="01_Paris/hauptteil"),
        _photo("b.jpg", pos=2, folder="01_Paris/essen", region="Paris"),
        _photo("c.jpg", pos=3, folder="02_Lyon/hauptteil", region="Lyon"),
    ]
    photos[1].chapter_type = "Essen"
    photos[1].scene_type = "essen"
    order = rebuild_order_from_kept(photos, [0, 2, 1])
    folders = [f for _i, f, _t in order]
    assert folders == ["01_Paris/hauptteil", "01_Paris/essen", "02_Lyon/hauptteil"]


def test_apply_manual_selection(tmp_path):
    # minimale echte Dateien zum Kopieren
    src = tmp_path / "src"
    src.mkdir()
    from PIL import Image

    paths = []
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        p = src / name
        Image.new("RGB", (80, 60), (100, 120, 140)).save(p)
        paths.append(p)

    photos = [
        _photo("a.jpg", pos=1),
        _photo("b.jpg", pos=2, folder="01_Paris/essen"),
        _photo("c.jpg", pos=3, folder="02_Lyon/hauptteil", region="Lyon"),
    ]
    for photo, path in zip(photos, paths):
        photo.path = path
    photos[1].chapter_type = "Essen"

    plan = BookPlan(
        regions=[
            Region(name="Paris", photo_indices=[0, 1], chapter_index=0),
            Region(name="Lyon", photo_indices=[2], chapter_index=1),
        ]
    )
    out = tmp_path / "out"
    order = apply_manual_selection(photos, plan, [0, 2], out)
    assert len(order) == 2
    assert photos[0].is_selected and photos[2].is_selected
    assert not photos[1].is_selected
    assert (out / "photos_analysis.csv").exists()
    assert (out / "inhaltsverzeichnis.md").exists()
    assert (out / "selected").exists()


def test_chapter_sections_and_plan():
    photos = [
        _photo("a.jpg", pos=1),
        _photo("b.jpg", pos=2, folder="01_Paris/essen"),
    ]
    photos[1].chapter_type = "Essen"
    sections = chapter_sections(photos, [0, 1])
    assert len(sections) == 2
    plan = plan_from_photos(photos)
    assert [r.name for r in plan.regions] == ["Paris"]


def test_moved_folder_survives_apply_manual_selection(tmp_path):
    """Verschieben im Review muss in CSV/selected landen (inkl. is_aside-Clear)."""
    from PIL import Image

    from photobook_curator.documents import ASIDE_FOLDER

    src = tmp_path / "src"
    src.mkdir()
    paths = []
    for name in ("a.jpg", "b.jpg"):
        p = src / name
        Image.new("RGB", (80, 60), (100, 120, 140)).save(p)
        paths.append(p)

    photos = [
        _photo("a.jpg", pos=1, folder=ASIDE_FOLDER, region="Optional"),
        _photo("b.jpg", pos=2, folder="01_Paris/hauptteil"),
    ]
    photos[0].is_aside = True
    photos[0].chapter_type = "Optional"
    for photo, path in zip(photos, paths):
        photo.path = path

    # Wie Review: aus Optional nach Lyon verschieben
    photos[0].chapter_folder = "02_Lyon/hauptteil"
    photos[0].chapter_type = "Hauptteil"
    photos[0].is_aside = False
    photos[0].region = "Lyon"

    plan = BookPlan(
        regions=[
            Region(name="Paris", photo_indices=[1], chapter_index=0),
            Region(name="Lyon", photo_indices=[0], chapter_index=1),
        ]
    )
    out = tmp_path / "out"
    order = apply_manual_selection(photos, plan, [0, 1], out)
    folders = {i: f for i, f, _t in order}
    assert folders[0] == "02_Lyon/hauptteil"
    assert photos[0].chapter_folder == "02_Lyon/hauptteil"
    assert not photos[0].is_aside
    csv_text = (out / "photos_analysis.csv").read_text(encoding="utf-8")
    assert "02_Lyon/hauptteil" in csv_text
    assert (out / "selected" / "02_Lyon" / "hauptteil").is_dir()
