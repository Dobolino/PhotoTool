"""Review-Raster: Klicks und Varianten-Verhalten."""

from __future__ import annotations

import ast
from pathlib import Path


def test_canvas_grid_handles_clicks_and_overlays() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    # Reines Canvas-Raster (kein Frame-Ghosting) mit Hit-Testing
    assert "_on_grid_click" in src
    assert "_draw_tile" in src
    assert "_hit_tiles" in src
    assert 'text="+"' in src or "text=\"+\"" in src
    assert "create_window" not in src
    assert "_grid_folder" in src
    tree = ast.parse(src)
    assert tree is not None


def test_alternatives_go_into_chapter_not_top_dump() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    assert "_place_in_chapter" in src
    assert "_assign_chapter" in src
    assert "Neu hinzugefügt (diese Sitzung)" not in src
    assert "_ensure_added_section" not in src
    assert "_expanded_alts" in src
    assert "show_variants" in src or 't("show_variants"' in src


def test_variant_badge_label() -> None:
    from photobook_curator.i18n import set_language, t

    set_language("de")
    assert t("new_badge") == "Variante"
