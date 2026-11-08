"""App-Einstellungen: Sprache, Design, Diashow-Verhalten."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


SETTINGS_DIR_NAME = ".photobook_curator"
SETTINGS_FILE = "settings.json"

# Modern palettes share the approved review's Edeco/NOVA colours. Theme IDs and
# explicit choices remain stable so an update does not reset personal settings.
THEMES: dict[str, dict[str, str]] = {
    "night": {
        "name_de": "Dunkelmodus",
        "name_en": "Dark mode",
        "bg": "#10191F",
        "surface": "#17232B",
        "ink": "#E8F0F3",
        "muted": "#A3B5BF",
        "line": "#2D414D",
        "accent": "#64C3D1",
        "accent_hover": "#83D4DF",
        "accent_soft": "#193E48",
        "on_accent": "#102A32",
        "cta": "#FF8C00",
        "cta_hover": "#E07B00",
        "cta_ink": "#1A1206",
        "reject": "#FF8B9B",
        "keep_border": "#64C3D1",
        "reject_border": "#48616F",
        "danger": "#FF8B9B",
        "log_bg": "#111D25",
        "log_fg": "#C4D3DB",
        "phase_pending_bg": "#1C2B34",
        "phase_pending_fg": "#A3B5BF",
        "phase_run_bg": "#FF8C00",
        "phase_run_fg": "#1A1206",
        "phase_done_bg": "#193E48",
        "phase_done_fg": "#83D4DF",
        "phase_skip_bg": "#1C2B34",
        "phase_skip_fg": "#A3B5BF",
        "hero_fg": "#102A32",
        "hero_muted": "#173D46",
        "slide_stage": "#111D25",
        "slide_fg": "#E8F0F3",
        "thumb_pad": "#24353F",
        "chip_bg": "#1C2B34",
        "map_canvas": "#24353F",
    },
    "modern": {
        "name_de": "Hell · Modern",
        "name_en": "Light · Modern",
        "bg": "#F4F7F8",
        "surface": "#FFFFFF",
        "ink": "#203039",
        "muted": "#64757F",
        "line": "#E1E8EC",
        "accent": "#017C92",
        "accent_hover": "#01667A",
        "accent_soft": "#E7F4F6",
        "on_accent": "#FFFFFF",
        "cta": "#FF8C00",
        "cta_hover": "#E07B00",
        "cta_ink": "#1A1206",
        "reject": "#BC3548",
        "keep_border": "#017C92",
        "reject_border": "#C6D3DA",
        "danger": "#BC3548",
        "log_bg": "#EDF2F4",
        "log_fg": "#203039",
        "phase_pending_bg": "#EDF2F4",
        "phase_pending_fg": "#64757F",
        "phase_run_bg": "#975B06",
        "phase_run_fg": "#FFFFFF",
        "phase_done_bg": "#E7F4F6",
        "phase_done_fg": "#01667A",
        "phase_skip_bg": "#EDF2F4",
        "phase_skip_fg": "#64757F",
        "hero_fg": "#FFFFFF",
        "hero_muted": "#E7F4F6",
        "slide_stage": "#E4EBEE",
        "slide_fg": "#203039",
        "thumb_pad": "#EDF2F4",
        "chip_bg": "#F8FAFB",
        "map_canvas": "#E4EBEE",
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
_THEME_ALIASES = {"dark": "night", "nacht": "night", "dunkel": "night",
                  "light": "modern", "hell": "modern"}


def _theme_id(value) -> str:
    theme = str(value or DEFAULT_THEME).strip().lower()
    theme = _THEME_ALIASES.get(theme, theme)
    return theme if theme in THEMES else DEFAULT_THEME


@dataclass
class AppSettings:
    language: str = DEFAULT_LANGUAGE
    theme: str = DEFAULT_THEME
    slideshow_auto_advance: bool = False
    slideshow_show_alternative: bool = True
    max_per_day: int = 0
    max_per_chapter: int = 0

    def normalized(self) -> "AppSettings":
        lang = (self.language or DEFAULT_LANGUAGE).lower()
        if lang not in ("de", "en"):
            lang = DEFAULT_LANGUAGE
        theme = _theme_id(self.theme)
        return AppSettings(
            language=lang,
            theme=theme,
            slideshow_auto_advance=bool(self.slideshow_auto_advance),
            slideshow_show_alternative=bool(self.slideshow_show_alternative),
            max_per_day=_normalize_cap(self.max_per_day),
            max_per_chapter=_normalize_cap(self.max_per_chapter),
        )


def _normalize_cap(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


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
    raw_theme = _theme_id(data.get("theme"))
    # Alias + Migration: altes Standard-Theme „forest“ → Dunkelmodus
    migrated = False
    if raw_theme == "forest" and not data.get("theme_explicit"):
        raw_theme = DEFAULT_THEME
        migrated = True
    settings = AppSettings(
        language=str(data.get("language") or DEFAULT_LANGUAGE),
        theme=raw_theme,
        slideshow_auto_advance=bool(data.get("slideshow_auto_advance", False)),
        slideshow_show_alternative=bool(data.get("slideshow_show_alternative", True)),
        max_per_day=data.get("max_per_day", 0),
        max_per_chapter=data.get("max_per_chapter", 0),
    ).normalized()
    if migrated:
        try:
            _write_settings_dict(
                {
                    **asdict(settings),
                    "theme_explicit": False,
                    "migrated_to_dark": True,
                }
            )
        except Exception:
            pass
    return settings


def _write_settings_dict(data: dict) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def save_settings(settings: AppSettings) -> Path:
    settings = settings.normalized()
    # Nutzerwahl merken – kein erneutes Auto-Migrieren von forest
    return _write_settings_dict({**asdict(settings), "theme_explicit": True})


def theme_colors(theme_id: Optional[str] = None) -> dict[str, str]:
    sid = _theme_id(theme_id or load_settings().theme)
    base = THEMES.get(sid) or THEMES[DEFAULT_THEME]
    # Nur Farbkeys zurückgeben
    skip = {"name_de", "name_en"}
    colors = {k: v for k, v in base.items() if k not in skip}
    # Existing palettes retain their colours while newer controls can always
    # request an explicit foreground for accent and primary-action surfaces.
    colors.setdefault("on_accent", colors.get("hero_fg", "#FFFFFF"))
    colors.setdefault("cta", colors["accent"])
    colors.setdefault("cta_hover", colors["accent_hover"])
    colors.setdefault("cta_ink", colors["on_accent"])
    return colors


def theme_choices(language: str = "de") -> list[tuple[str, str]]:
    """[(id, label), ...]"""
    out: list[tuple[str, str]] = []
    for tid, data in THEMES.items():
        label = data["name_de"] if language == "de" else data["name_en"]
        out.append((tid, label))
    return out
