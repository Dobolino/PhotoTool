"""Alternativen-Kacheln müssen Klicks auf dem Overlay annehmen."""

from __future__ import annotations

import ast
from pathlib import Path


def test_overlay_binds_toggle_in_apply_tile_visual() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    # Regression: "+ HINZUFÜGEN" lag oben ohne Click-Handler
    assert "_bind_tile_click(overlay" in src
    assert 'text="+ HINZUFÜGEN"' in src
    tree = ast.parse(src)
    assert tree is not None


def test_alternatives_go_into_chapter_not_top_dump() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    assert "_place_in_chapter" in src
    assert "_assign_chapter" in src
    assert "Neu hinzugefügt (diese Sitzung)" not in src
    assert "_ensure_added_section" not in src
    assert "_add_outers" in src
    assert "show_variants" in src or 't("show_variants"' in src


def test_variant_badge_label() -> None:
    from photobook_curator.i18n import set_language, t

    set_language("de")
    assert t("new_badge") == "Variante"
