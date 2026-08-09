"""App-Einstellungen: Sprache, Design, Diashow-Verhalten."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


SETTINGS_DIR_NAME = ".photobook_curator"
SETTINGS_FILE = "settings.json"

# Design-Varianten – „night“ ist die aktuelle Haupt-UI (Screenshots + Fixes)
THEMES: dict[str, dict[str, str]] = {
    "night": {
        "name_de": "Nacht (Standard)",
        "name_en": "Night (default)",
        "bg": "#12141C",
        "surface": "#1C2030",
        "ink": "#E8EAF2",
        "muted": "#9AA3B5",
        "line": "#2C3348",
        "accent": "#7B6CFF",
        "accent_hover": "#6958F0",
        "accent_soft": "#2A2750",
        "reject": "#C45C5C",
        "keep_border": "#7B6CFF",
        "reject_border": "#3A4158",
        "danger": "#C45C5C",
        "log_bg": "#0E1018",
        "log_fg": "#C5CAD8",
        "phase_pending_bg": "#2A3145",
        "phase_pending_fg": "#9AA3B5",
        "phase_run_bg": "#C47A3A",
        "phase_run_fg": "#FFF8F0",
        "phase_done_bg": "#7B6CFF",
        "phase_done_fg": "#FFFFFF",
        "phase_skip_bg": "#242A3A",
        "phase_skip_fg": "#7A8296",
        "hero_fg": "#FFFFFF",
        "hero_muted": "#C8C4FF",
        "slide_stage": "#0E1018",
        "slide_fg": "#E8EAF2",
        "thumb_pad": "#242A3A",
        "chip_bg": "#262C40",
        "map_canvas": "#161A28",
    },
    "forest": {
        "name_de": "Wald",
        "name_en": "Forest",
        "bg": "#F3EFE7",
        "surface": "#FFFCF7",
        "ink": "#1F1A17",
        "muted": "#6E645C",
        "line": "#D9D0C4",
        "accent": "#2F5D50",
        "accent_hover": "#244A40",
        "accent_soft": "#E2EDE8",
        "reject": "#8B3A2C",
        "keep_border": "#2F5D50",
        "reject_border": "#C4B8AA",
        "danger": "#8B3A2C",
        "log_bg": "#1C2421",
        "log_fg": "#D7E0DB",
        "phase_pending_bg": "#E8E2D8",
        "phase_pending_fg": "#6E645C",
        "phase_run_bg": "#C47A3A",
        "phase_run_fg": "#FFF8F0",
        "phase_done_bg": "#2F5D50",
        "phase_done_fg": "#F4FBF7",
        "phase_skip_bg": "#D9D0C4",
        "phase_skip_fg": "#5A524C",
        "hero_fg": "#F7F3EC",
        "hero_muted": "#D5E4DE",
        "slide_stage": "#1F1A17",
        "slide_fg": "#E8E2D8",
        "thumb_pad": "#F5F1E9",
        "chip_bg": "#E8E2D8",
        "map_canvas": "#E8E2D6",
    },
    "slate": {
        "name_de": "Schiefer",
        "name_en": "Slate",
        "bg": "#EEF1F4",
        "surface": "#FBFCFD",
        "ink": "#1A2330",
        "muted": "#5C6B7A",
        "line": "#CDD5DE",
        "accent": "#2F5F7A",
        "accent_hover": "#244A60",
        "accent_soft": "#DCE8F0",
        "reject": "#8B3A2C",
        "keep_border": "#2F5F7A",
        "reject_border": "#B8C2CC",
        "danger": "#8B3A2C",
        "log_bg": "#1A2330",
        "log_fg": "#D5DEE6",
        "phase_pending_bg": "#E0E6EC",
        "phase_pending_fg": "#5C6B7A",
        "phase_run_bg": "#C47A3A",
        "phase_run_fg": "#FFF8F0",
        "phase_done_bg": "#2F5F7A",
        "phase_done_fg": "#F4F8FB",
        "phase_skip_bg": "#CDD5DE",
        "phase_skip_fg": "#4A5560",
        "hero_fg": "#F4F8FB",
        "hero_muted": "#C5D6E2",
        "slide_stage": "#1A2330",
        "slide_fg": "#E2E8EE",
        "thumb_pad": "#E8EEF2",
        "chip_bg": "#E0E6EC",
        "map_canvas": "#E4E9EF",
    },
    "ink": {
        "name_de": "Tinte",
        "name_en": "Ink",
        "bg": "#E8E6E1",
        "surface": "#F7F6F2",
        "ink": "#141816",
        "muted": "#5A615C",
        "line": "#C9C6BE",
        "accent": "#1F4D3D",
        "accent_hover": "#16382D",
        "accent_soft": "#D5E5DE",
        "reject": "#7A3228",
        "keep_border": "#1F4D3D",
        "reject_border": "#B0AAA0",
        "danger": "#7A3228",
        "log_bg": "#141816",
        "log_fg": "#D2D8D4",
        "phase_pending_bg": "#DCD8D0",
        "phase_pending_fg": "#5A615C",
        "phase_run_bg": "#A66B2E",
        "phase_run_fg": "#FFF8F0",
        "phase_done_bg": "#1F4D3D",
        "phase_done_fg": "#F0F7F3",
        "phase_skip_bg": "#C9C6BE",
        "phase_skip_fg": "#4A504C",
        "hero_fg": "#F0F7F3",
        "hero_muted": "#C5D8CF",
        "slide_stage": "#141816",
        "slide_fg": "#E2E6E3",
        "thumb_pad": "#E4E1DA",
        "chip_bg": "#DCD8D0",
        "map_canvas": "#E4E1DA",
    },
}

DEFAULT_THEME = "night"
DEFAULT_LANGUAGE = "de"


@dataclass
class AppSettings:
    language: str = DEFAULT_LANGUAGE
    theme: str = DEFAULT_THEME
    slideshow_auto_advance: bool = False
    slideshow_show_alternative: bool = True

    def normalized(self) -> "AppSettings":
        lang = (self.language or DEFAULT_LANGUAGE).lower()
        if lang not in ("de", "en"):
            lang = DEFAULT_LANGUAGE
        theme = (self.theme or DEFAULT_THEME).lower()
        if theme not in THEMES:
            theme = DEFAULT_THEME
        return AppSettings(
            language=lang,
            theme=theme,
            slideshow_auto_advance=bool(self.slideshow_auto_advance),
            slideshow_show_alternative=bool(self.slideshow_show_alternative),
        )


def settings_dir() -> Path:
    return Path.home() / SETTINGS_DIR_NAME


def settings_path() -> Path:
    return settings_dir() / SETTINGS_FILE


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.is_file():
        return AppSettings().normalized()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings().normalized()
    if not isinstance(data, dict):
        return AppSettings().normalized()
    return AppSettings(
        language=str(data.get("language") or DEFAULT_LANGUAGE),
        theme=str(data.get("theme") or DEFAULT_THEME),
        slideshow_auto_advance=bool(data.get("slideshow_auto_advance", False)),
        slideshow_show_alternative=bool(data.get("slideshow_show_alternative", True)),
    ).normalized()


def save_settings(settings: AppSettings) -> Path:
    settings = settings.normalized()
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def theme_colors(theme_id: Optional[str] = None) -> dict[str, str]:
    sid = (theme_id or load_settings().theme).lower()
    base = THEMES.get(sid) or THEMES[DEFAULT_THEME]
    # Nur Farbkeys zurückgeben
    skip = {"name_de", "name_en"}
    return {k: v for k, v in base.items() if k not in skip}


def theme_choices(language: str = "de") -> list[tuple[str, str]]:
    """[(id, label), ...]"""
    out: list[tuple[str, str]] = []
    for tid, data in THEMES.items():
        label = data["name_de"] if language == "de" else data["name_en"]
        out.append((tid, label))
    return out
