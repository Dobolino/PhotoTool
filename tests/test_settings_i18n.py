"""Einstellungen, Themes und i18n."""

from __future__ import annotations

from pathlib import Path

from photobook_curator.i18n import set_language, t
from photobook_curator.settings import (
    AppSettings,
    THEMES,
    load_settings,
    save_settings,
    theme_colors,
    theme_choices,
)


def test_themes_have_required_keys() -> None:
    required = {
        "bg",
        "surface",
        "ink",
        "accent",
        "reject",
        "keep_border",
        "log_bg",
        "phase_done_bg",
        "slide_stage",
    }
    for tid, data in THEMES.items():
        missing = required - set(data)
        assert not missing, f"{tid} missing {missing}"


def test_settings_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "photobook_curator.settings.settings_dir", lambda: tmp_path / ".photobook_curator"
    )
    monkeypatch.setattr(
        "photobook_curator.settings.settings_path",
        lambda: tmp_path / ".photobook_curator" / "settings.json",
    )
    s = AppSettings(
        language="en",
        theme="slate",
        slideshow_auto_advance=True,
        slideshow_show_alternative=False,
    )
    path = save_settings(s)
    assert path.is_file()
    loaded = load_settings()
    assert loaded.language == "en"
    assert loaded.theme == "slate"
    assert loaded.slideshow_auto_advance is True
    assert loaded.slideshow_show_alternative is False


def test_i18n_switches() -> None:
    set_language("de")
    assert "Diashow" in t("slideshow") or "Diashow" in t("slideshow")
    de_review = t("review")
    set_language("en")
    en_review = t("review")
    assert de_review != en_review
    assert "Review" in en_review or "review" in en_review.lower()


def test_theme_choices_and_colors() -> None:
    choices = theme_choices("de")
    assert len(choices) >= 3
    c = theme_colors("ink")
    assert c["accent"].startswith("#")
    night = theme_colors("night")
    assert night["bg"].startswith("#")
    assert "chip_bg" in night
    assert "map_canvas" in night
    assert any(tid == "night" for tid, _ in choices)


def test_found_photos_spacing() -> None:
    set_language("de")
    assert t("found_photos", n=1245) == "1245 Bilder gefunden"
    set_language("en")
    assert "1245" in t("found_photos", n=1245)
    assert " " in t("found_photos", n=1245)


def test_ui_widgets_importable() -> None:
    from photobook_curator.ui_widgets import AnAusToggle, PaddedButton, StepChip

    assert callable(AnAusToggle)
    assert callable(PaddedButton)
    assert callable(StepChip)


def test_dark_mode_default_and_forest_migration(tmp_path, monkeypatch) -> None:
    from photobook_curator.settings import DEFAULT_THEME, load_settings, save_settings

    monkeypatch.setattr(
        "photobook_curator.settings.settings_dir", lambda: tmp_path / ".photobook_curator"
    )
    monkeypatch.setattr(
        "photobook_curator.settings.settings_path",
        lambda: tmp_path / ".photobook_curator" / "settings.json",
    )
    assert DEFAULT_THEME == "night"
    # Alte Default-Datei ohne theme_explicit → Dunkelmodus
    path = tmp_path / ".photobook_curator" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"language": "de", "theme": "forest"}\n', encoding="utf-8")
    loaded = load_settings()
    assert loaded.theme == "night"
    # Explizit gewähltes Hell-Theme bleibt
    save_settings(
        AppSettings(language="de", theme="forest", slideshow_auto_advance=False)
    )
    assert load_settings().theme == "forest"


def test_window_layout_helpers() -> None:
    from photobook_curator.window_layout import fit_dialog, place_window, screen_size

    assert callable(place_window)
    assert callable(fit_dialog)
    assert callable(screen_size)


def test_world_basemap_data() -> None:
    from photobook_curator.world_basemap import load_land_rings, trip_bounds, world_view_bounds

    rings = load_land_rings()
    assert len(rings) > 50
    assert len(rings[0]) >= 3
    w, e, s, n = world_view_bounds()
    assert w < e and s < n
    tw, te, ts, tn = trip_bounds([(35.0, 139.0), (34.0, 135.0)])
    assert tw < te


def test_review_has_night_header_and_wheel_fix() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    assert "_install_wheel" in src
    assert "soft_banner" in src
    assert "pack_propagate(False)" in src
    assert 'font=("Georgia"' not in src
    # Canvas-Inhalt muss tk.Frame sein (ttk → Windows-Ghosting beim Scrollen)
    assert "self.inner = tk.Frame(self.canvas" in src
    assert "_repaint_after_scroll" in src
    assert "self._scrolling" in src


def test_alternatives_helper_exists() -> None:
    from photobook_curator.review_export import alternatives_for_index

    assert callable(alternatives_for_index)


def test_review_has_new_slideshow_features() -> None:
    src = Path("photobook_curator/review_gui.py").read_text(encoding="utf-8")
    for needle in (
        "_slide_chapter_next",
        "_refresh_alt_panel",
        "_toggle_auto_advance",
        "_filtered_slide_indices",
        "alternatives_for_index",
    ):
        assert needle in src
