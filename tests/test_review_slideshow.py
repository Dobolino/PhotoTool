"""Diashow-Modus in Auswahl prüfen muss vorhanden und bedienbar sein."""

from __future__ import annotations

import ast
from pathlib import Path


def test_slideshow_api_in_review_gui() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    for needle in (
        't("slideshow")',
        "_enter_slideshow",
        "_exit_slideshow",
        "_slide_toggle_current",
        "_request_slide",
        "_rebuild_filmstrip",
        "_show_slide_placeholder",
        "_apply_folder_change",
        "_sync_slide_chapter_to_grid_folder",
        "_refresh_alt_panel",
        'bind("<Left>"',
        'bind("<space>"',
    ):
        assert needle in src, f"missing: {needle}"
    # Ordner-Buttons nur oben – nicht nochmal in der unteren Diashow-Leiste
    assert 'command=self._slide_chapter_prev' not in src
    assert 'command=self._slide_chapter_next' not in src
    tree = ast.parse(src)
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)
    }
    assert "_enter_slideshow" in names
    assert "_slide_next" in names
    assert "_slide_prev" in names
    assert "_rebuild_filmstrip" in names
    assert "_apply_folder_change" in names


def test_load_image_scaled_exists() -> None:
    src = Path("photobook_curator/utils.py").read_text(encoding="utf-8")
    assert "def load_image_scaled" in src
    assert 'img.draft("RGB"' in src


def test_review_init_does_not_shadow_i18n_t() -> None:
    """Regression: `for t in loaders` machte t() UnboundLocalError."""
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    assert "for t in self._loaders" not in src
    assert "for loader in self._loaders" in src
