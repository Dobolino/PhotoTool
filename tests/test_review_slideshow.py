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
        "_slide_chapter_next",
        "_refresh_alt_panel",
        'bind("<Left>"',
        'bind("<space>"',
    ):
        assert needle in src, f"missing: {needle}"
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


def test_load_image_scaled_exists() -> None:
    src = Path("photobook_curator/utils.py").read_text(encoding="utf-8")
    assert "def load_image_scaled" in src
    assert 'img.draft("RGB"' in src
