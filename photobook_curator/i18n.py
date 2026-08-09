"""Einfache DE/EN-Texte für die GUI."""

from __future__ import annotations

from typing import Any

from .settings import DEFAULT_LANGUAGE, load_settings

_STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "app_title": "Fotobuch-Auswahl",
        "brand": "Fotobuch",
        "help": "Hilfe",
        "settings": "Darstellung & Sprache",
        "settings_title": "Einstellungen",
        "photos_folder": "Fotos-Ordner",
        "output_folder": "Ausgabe-Ordner",
        "browse": "Durchsuchen",
        "options_box": "  Einstellungen  ",
        "target_count": "Zielanzahl Bilder",
        "more_options": "Weitere Optionen ▸",
        "more_options_open": "Weitere Optionen ▾",
        "explain_options": "Optionen erklären",
        "start": "Auswahl starten",
        "cancel": "Abbrechen",
        "review": "Auswahl prüfen / fortsetzen",
        "map": "Karte",
        "next_pick_folders": "Nächster Schritt: Ordner wählen…",
        "loading_modules": "Lade Erkennungsmodule…",
        "steps_hint": "Schritte (orange = läuft, grün = fertig)",
        "log": "Verlauf",
        "close": "Schließen",
        "language": "Sprache",
        "theme": "Design",
        "lang_de": "Deutsch",
        "lang_en": "English",
        "auto_advance": "Nach Entfernen automatisch weiter",
        "show_alt": "Alternative neben dem Bild zeigen",
        "save_settings": "Speichern",
        "settings_saved": "Einstellungen gespeichert.",
        "settings_hint": "Sprache und Design gelten sofort für neue Fenster; "
        "das Hauptfenster aktualisiert sich nach Speichern.",
        "opt_geocode": "Ortsnamen per Internet",
        "opt_faces": "Gesichtserkennung / Augen zu",
        "opt_bursts": "Serien/Bursts (beste 1–2)",
        "opt_aside": "Dokumente & Screenshots separat",
        "opt_finger": "Finger vor der Linse aussortieren",
        "opt_coverage": "Tages-Abdeckung",
        "opt_people": "Personen-Balance",
        "opt_map": "Kapitel-/Karten-Vorschau vor Export",
        "opt_ai": "KI-Bewertung (Anthropic API)",
        "opt_dry": "Nur Kosten schätzen",
        "review_title": "Auswahl prüfen",
        "review_hint_grid": "Raster: Klick = raus/rein · Diashow: großes Bild, Filter, Alternativen.",
        "review_hint_slide": "Diashow: Filter/Kapitel · Vorschau · Alternative · Esc = Raster.",
        "slideshow": "Diashow-Ansicht",
        "grid_view": "Raster-Ansicht",
        "save_export": "Speichern & Ordner neu schreiben",
        "close_draft": "Schließen (Entwurf bleibt)",
        "draft_auto": "Änderungen werden automatisch als selection_draft.json gesichert "
        "(Absturz/Pause → später „Auswahl prüfen“ fortsetzen, ohne neue KI).",
        "filter_all": "Alle",
        "filter_kept": "Dabei",
        "filter_removed": "Entfernt",
        "chapter_all": "Alle Kapitel",
        "chapter_jump_prev": "Kapitel ←",
        "chapter_jump_next": "Kapitel →",
        "prev": "← Zurück",
        "next": "Weiter →",
        "remove": "Rausnehmen",
        "restore": "Wieder reinnehmen",
        "back_grid": "Zurück zum Raster",
        "surroundings": "Umgebung",
        "loading_image": "Bild wird geladen…",
        "alt_title": "Beste Alternative",
        "alt_none": "Keine Alternative in diesem Kapitel",
        "alt_take": "Alternative übernehmen",
        "alt_swap": "Tauschen",
        "kept_state": "DABEI",
        "removed_state": "ENTFERNT",
        "selected_count": "{n} Bilder ausgewählt (Entwurf auto-gespeichert)",
        "slide_tip": "← → blättern · Filter/Kapitel · Leertaste = raus/rein · A = Alternative · Esc = Raster",
        "no_slide_photos": "Keine Bilder für diesen Filter.",
        "auto_on": "Auto-weiter: an",
        "auto_off": "Auto-weiter: aus",
        "added_to_chapter": "Variante hinzugefügt zu {folder}",
        "new_badge": "Variante",
        "in_chapter_hint": "Grün = dabei · Klick = raus/rein · Varianten landen im Kapitel",
        "show_variants": "Varianten anzeigen ({n})",
        "hide_variants": "Varianten ausblenden",
    },
    "en": {
        "app_title": "Photobook curator",
        "brand": "Photobook",
        "help": "Help",
        "settings": "Appearance & language",
        "settings_title": "Settings",
        "photos_folder": "Photos folder",
        "output_folder": "Output folder",
        "browse": "Browse",
        "options_box": "  Settings  ",
        "target_count": "Target photo count",
        "more_options": "More options ▸",
        "more_options_open": "More options ▾",
        "explain_options": "Explain options",
        "start": "Start selection",
        "cancel": "Cancel",
        "review": "Review / continue selection",
        "map": "Map",
        "next_pick_folders": "Next: choose folders…",
        "loading_modules": "Loading detection modules…",
        "steps_hint": "Steps (orange = running, green = done)",
        "log": "Log",
        "close": "Close",
        "language": "Language",
        "theme": "Theme",
        "lang_de": "Deutsch",
        "lang_en": "English",
        "auto_advance": "Auto-advance after remove",
        "show_alt": "Show alternative beside photo",
        "save_settings": "Save",
        "settings_saved": "Settings saved.",
        "settings_hint": "Language and theme apply immediately to new windows; "
        "the main window updates after saving.",
        "opt_geocode": "Place names via internet",
        "opt_faces": "Face detection / closed eyes",
        "opt_bursts": "Bursts (keep best 1–2)",
        "opt_aside": "Documents & screenshots aside",
        "opt_finger": "Filter finger-on-lens shots",
        "opt_coverage": "Day coverage",
        "opt_people": "People balance",
        "opt_map": "Chapter/map preview before export",
        "opt_ai": "AI review (Anthropic API)",
        "opt_dry": "Estimate cost only",
        "review_title": "Review selection",
        "review_hint_grid": "Grid: click = keep/remove · Slideshow: large view, filters, alternatives.",
        "review_hint_slide": "Slideshow: filters/chapters · previews · alternative · Esc = grid.",
        "slideshow": "Slideshow view",
        "grid_view": "Grid view",
        "save_export": "Save & rewrite folders",
        "close_draft": "Close (keep draft)",
        "draft_auto": "Changes auto-save to selection_draft.json "
        "(crash/pause → later continue review without new AI).",
        "filter_all": "All",
        "filter_kept": "Kept",
        "filter_removed": "Removed",
        "chapter_all": "All chapters",
        "chapter_jump_prev": "Chapter ←",
        "chapter_jump_next": "Chapter →",
        "prev": "← Back",
        "next": "Next →",
        "remove": "Remove",
        "restore": "Keep again",
        "back_grid": "Back to grid",
        "surroundings": "Nearby",
        "loading_image": "Loading image…",
        "alt_title": "Best alternative",
        "alt_none": "No alternative in this chapter",
        "alt_take": "Use alternative",
        "alt_swap": "Swap",
        "kept_state": "KEPT",
        "removed_state": "REMOVED",
        "selected_count": "{n} photos selected (draft auto-saved)",
        "slide_tip": "← → browse · filters/chapters · Space = keep/remove · A = alternative · Esc = grid",
        "no_slide_photos": "No photos for this filter.",
        "auto_on": "Auto-advance: on",
        "auto_off": "Auto-advance: off",
        "added_to_chapter": "Variant added to {folder}",
        "new_badge": "Variant",
        "in_chapter_hint": "Green = kept · click = remove/keep · variants go into the chapter",
        "show_variants": "Show variants ({n})",
        "hide_variants": "Hide variants",
    },
}

_current_lang = DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    global _current_lang
    lang = (lang or DEFAULT_LANGUAGE).lower()
    _current_lang = lang if lang in _STRINGS else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current_lang


def sync_language_from_settings() -> str:
    lang = load_settings().language
    set_language(lang)
    return lang


def t(key: str, **kwargs: Any) -> str:
    lang = _current_lang if _current_lang in _STRINGS else DEFAULT_LANGUAGE
    text = _STRINGS.get(lang, {}).get(key) or _STRINGS["de"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
