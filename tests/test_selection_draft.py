"""Auswahl-Entwurf speichern/laden."""

from __future__ import annotations

from pathlib import Path

from photobook_curator.models import Photo
from photobook_curator.selection_draft import (
    apply_selection_draft,
    load_selection_draft,
    save_selection_draft,
)


def test_draft_roundtrip(tmp_path: Path):
    photos = [
        Photo(path=tmp_path / "a.jpg", filename="a.jpg", is_selected=True, chapter_folder="01_Tokyo/hauptteil"),
        Photo(path=tmp_path / "b.jpg", filename="b.jpg", is_selected=False),
        Photo(path=tmp_path / "c.jpg", filename="c.jpg", is_selected=True, chapter_folder="01_Tokyo/essen"),
    ]
    out = tmp_path / "out"
    save_selection_draft(out, photos, {0, 2})
    draft = load_selection_draft(out)
    assert draft is not None
    assert draft["kept_count"] == 2

    photos2 = [
        Photo(path=tmp_path / "a.jpg", filename="a.jpg"),
        Photo(path=tmp_path / "b.jpg", filename="b.jpg"),
        Photo(path=tmp_path / "c.jpg", filename="c.jpg"),
    ]
    kept = apply_selection_draft(photos2, draft)
    assert kept == {0, 2}
    assert photos2[0].is_selected and photos2[2].is_selected
    assert not photos2[1].is_selected
    assert photos2[0].chapter_folder == "01_Tokyo/hauptteil"
