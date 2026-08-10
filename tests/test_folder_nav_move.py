"""Ordner-Navigation + Verschieben im Review (Entwurf / Persistenz)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from photobook_curator.documents import ASIDE_FOLDER
from photobook_curator.models import Photo
from photobook_curator.selection_draft import (
    apply_selection_draft,
    load_selection_draft,
    save_selection_draft,
)


def _photo(name: str, folder: str, *, aside: bool = False) -> Photo:
    return Photo(
        path=Path(name),
        filename=name,
        datetime_taken=datetime(2024, 6, 1, 10, 0),
        region="Optional" if aside else "Paris",
        chapter_folder=folder,
        chapter_type="Optional" if aside else "Hauptteil",
        is_selected=True,
        book_position=1,
        is_candidate=True,
        is_aside=aside,
        technical_score=70,
        final_score=70,
    )


def test_draft_preserves_moved_chapter_and_clears_aside(tmp_path):
    photos = [
        _photo("doc.jpg", ASIDE_FOLDER, aside=True),
        _photo("street.jpg", "01_Paris/hauptteil"),
    ]
    # Verschieben wie im Review
    photos[0].chapter_folder = "01_Paris/hauptteil"
    photos[0].chapter_type = "Hauptteil"
    photos[0].is_aside = False

    save_selection_draft(tmp_path, photos, {0, 1})
    draft = load_selection_draft(tmp_path)
    assert draft is not None
    assert draft["kept"][0]["chapter_folder"] == "01_Paris/hauptteil"

    # Frischer Stand mit is_aside wieder True – Entwurf muss korrigieren
    fresh = [
        _photo("doc.jpg", ASIDE_FOLDER, aside=True),
        _photo("street.jpg", "01_Paris/hauptteil"),
    ]
    kept = apply_selection_draft(fresh, draft)
    assert kept == {0, 1}
    assert fresh[0].chapter_folder == "01_Paris/hauptteil"
    assert fresh[0].is_aside is False


def test_review_gui_has_folder_nav_and_move():
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    assert "_grid_folder" in src
    assert "_grid_folder_prev" in src
    assert "_grid_folder_next" in src
    assert "_move_photo_to_folder" in src
    assert "_on_grid_right_click" in src
    assert "empty_folder" in src
    # Nur aktueller Ordner wird gezeichnet
    assert "folder == current" in src or "if folder == current" in src
