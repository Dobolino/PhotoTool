"""Einfache DE/EN-Texte für die GUI."""

from __future__ import annotations

from typing import Any

from .settings import DEFAULT_LANGUAGE, load_settings

_STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "app_title": "Fotobuch-Auswahl",
        "brand": "Fotobuch",
        "help": "Hilfe",
        "settings": "Darstellung",
        "settings_title": "Darstellung & Sprache",
        "photos_folder": "Fotos-Ordner",
        "output_folder": "Ausgabe-Ordner",
        "browse": "Durchsuchen",
        "options_box": "Einstellungen",
        "folders_box": "Ordner",
        "target_count": "Zielanzahl Bilder",
        "more_options": "Weitere Optionen ▸",
        "more_options_open": "Weitere Optionen ▾",
        "explain_options": "Optionen erklären",
        "start": "Auswahl starten",
        "cancel": "Abbrechen",
        "review": "Auswahl prüfen",
        "map": "Karte",
        "next_pick_folders": "Nächster Schritt: Ordner wählen…",
        "loading_modules": "Lade Erkennungsmodule…",
        "steps_hint": "Analyse-Schritte",
        "log": "Verlauf",
        "close": "Schließen",
        "step_folders": "1 · Ordner",
        "step_options": "2 · Optionen",
        "step_run": "3 · Start",
        "found_photos": "{n} Bilder gefunden",
        "found_none": "Keine Bilder gefunden",
        "found_counting": "Zähle Bilder…",
        "placeholder_folder": "Noch kein Ordner gewählt",
        "opt_geocode_long": "Ortsnamen per Internet ermitteln",
        "opt_faces_long": "Gesichtserkennung / Augen zu",
        "tip_resume": "Pause oder Absturz? Der Zwischenstand wird automatisch gesichert.",
        "toggle_on": "An",
        "toggle_off": "Aus",
        "language": "Sprache",
        "theme": "Design",
        "lang_de": "Deutsch",
        "lang_en": "English",
        "auto_advance": "Nach Entfernen automatisch weiter",
        "show_alt": "Alternative neben dem Bild zeigen",
        "save_settings": "Speichern",
        "settings_saved": "Einstellungen gespeichert.",
        "settings_restart_hint": "Für das volle Farbschema das Fenster einmal schließen und neu öffnen.",
        "settings_hint": "Sprache gilt sofort. Design-Farben für Karten und Fenster "
        "wirken nach dem Speichern; Hauptfenster ggf. neu öffnen.",
        "map_title": "Kapitel- & Karten-Vorschau",
        "map_subtitle": "Übersicht der geplanten Kapitel und GPS-Punkte.",
        "map_subtitle_export": "Prüfe Orte und Reihenfolge, bevor die Dateien kopiert werden.",
        "map_chapters": "Kapitel",
        "map_browser": "Karte im Browser",
        "map_export": "So exportieren",
        "map_no_gps": "Keine GPS-Daten – Weltkarte ohne Reise-Punkte",
        "map_no_chapters": "Keine Kapitel erkannt",
        "map_selected": "ausgewählt",
        "map_world": "Weltkarte",
        "map_trip": "Reise-Ausschnitt",
        "opt_geocode": "Ortsnamen per Internet",
        "opt_faces": "Gesichtserkennung / Augen zu",
        "opt_bursts": "Serien/Bursts (beste 1–2)",
        "opt_aside": "Dokumente & Screenshots separat",
        "opt_accidental": "Fehlaufnahmen aussortieren",
        "opt_weak_night": "Schwache Nachtaufnahmen entfernen",
        "opt_finger": "Finger vor der Linse aussortieren",
        "opt_content": "Ähnliche Motive clustern",
        "opt_aesthetic": "Lokale Ästhetik (ohne API)",
        "opt_video": "Video-/Live-Photo-Standbilder",
        "opt_timezone": "Zeitzone korrigieren (Stunden)",
        "opt_coverage": "Tages-Abdeckung",
        "opt_people": "Personen-Balance",
        "opt_map": "Kapitel-/Karten-Vorschau vor Export",
        "opt_ai": "KI-Bewertung (Anthropic API)",
        "opt_dry": "Nur Kosten schätzen",
        "review_title": "Auswahl prüfen",
        "review_hint_grid": "Ein Ordner nach dem anderen · Klick = raus/rein · Rechtsklick = verschieben.",
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
        "chapter_jump_prev": "← Vorheriger Ordner",
        "chapter_jump_next": "Nächster Ordner →",
        "folder_nav": "Ordner",
        "folder_of": "Ordner {i} / {n}",
        "folder_count": "{n} Bilder in diesem Ordner",
        "move_to": "Verschieben nach…",
        "moved_to": "Verschoben nach {folder}",
        "empty_folder": "Keine Bilder in diesem Ordner.",
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
        "help_title": "Hilfe – Fotobuch",
        "coverage_strength": "Abdeckung-Stärke",
        "people_strength": "Personen-Stärke",
        "help_body": (
            "Kurzanleitung\n"
            "─────────────\n\n"
            "1. Fotos-Ordner wählen (z. B. iCloud-/Urlaubsfotos).\n"
            "2. Ausgabe-Ordner wählen (am besten leer / neu).\n"
            "3. Zielanzahl einstellen (z. B. 80).\n"
            "4. Optionen nach Bedarf – Erklärungen über das ? neben jeder Option.\n"
            "5. „Auswahl starten“ – Schritte werden farbig angezeigt.\n"
            "6. Wenn fertig: „Auswahl prüfen“, anpassen, speichern.\n\n"
            "Auswahl prüfen\n"
            "  Raster: Klick = raus/rein · Rechtsklick = Ordner wechseln.\n"
            "  Diashow: großes Bild, Alternative (A), Esc = Raster.\n\n"
            "Darstellung\n"
            "  Oben rechts: Sprache (DE/EN), Design, Diashow-Optionen.\n\n"
            "Pause / Update\n"
            "  selection_draft.json und photos_analysis.csv speichern den Stand.\n"
            "  „Programm aktualisieren.bat“ für Updates. Details: START.md."
        ),
        "help_target_count": (
            "Ungefähre Anzahl Fotos im fertigen Buch (z. B. 80 oder 400)."
        ),
        "help_opt_geocode": (
            "GPS → Städtenamen (z. B. Tokyo, Kyoto). Treffer werden in "
            "geocode_cache.json gespeichert. Ohne GPS entsteht ein Album-Kapitel."
        ),
        "help_opt_faces": (
            "Findet Gesichter, markiert geschlossene Augen / schlechte Ausschnitte "
            "sowie Lächeln und Blick zur Kamera. Solche Fotos werden eher abgewertet."
        ),
        "help_opt_bursts": (
            "Ähnliche Fotos kurz hintereinander → nur die besten 1–2 behalten."
        ),
        "help_opt_aside": (
            "Tickets, Maps, Chats usw. nicht automatisch ins Buch, sondern in den "
            "Ordner optional_dokumente/ (später manuell reinnehmbar)."
        ),
        "help_opt_accidental": (
            "Typische Auslöser-Misses: viel Boden/Himmel, Motiv am Rand, "
            "starke Schräglage – werden nicht ins Buch genommen."
        ),
        "help_opt_weak_night": (
            "Dunkle, weiche, „schwummerige“ Nachtbilder aussortieren."
        ),
        "help_opt_content": (
            "Erkennt inhaltsgleiche Szenen (nicht nur pixelgleiche Duplikate) "
            "und behält die besten – nutzt Embeddings und den Analyse-Cache."
        ),
        "help_opt_aesthetic": (
            "Schätzt Bildqualität lokal (Schärfe, Belichtung, Komposition) ohne Cloud. "
            "Bei KI-Bewertung wird das übersprungen."
        ),
        "help_opt_timezone": (
            "Verschiebt alle EXIF-Zeiten um X Stunden (z. B. +9, wenn die Kamera "
            "noch auf Heimatzeit stand)."
        ),
        "help_opt_video": (
            "Extrahiert den schärfsten Frame aus kurzen Videos ohne Schwester-JPG/HEIC "
            "(typisch Live Photo ohne Standbild)."
        ),
        "help_opt_finger": (
            "Typische Fehlaufnahmen mit Finger/Hand vor der Kamera aussortieren."
        ),
        "help_opt_coverage": (
            "Verhindert, dass fast alles vom ersten Tag kommt. "
            "Stärke: sanft bis stark gleichmäßig über die Tage."
        ),
        "help_opt_people": (
            "Verhindert, dass immer dieselbe Person das Album dominiert."
        ),
        "help_opt_map": (
            "Vor dem Kopieren Kapitel und Karte zeigen, dann bestätigen."
        ),
        "help_opt_ai": (
            "Sendet Kandidatenbilder an die Anthropic-API zur Qualitäts-/Szenenbewertung. "
            "Kostet Geld – siehe Kostenzeile unter der Zielanzahl. Optional."
        ),
        "help_opt_dry": (
            "Kein echter KI-Aufruf: zählt nur Kandidaten und schätzt den Betrag. "
            "Nur sinnvoll, wenn KI-Bewertung an ist."
        ),
    },
    "en": {
        "app_title": "Photobook curator",
        "brand": "Photobook",
        "help": "Help",
        "settings": "Appearance",
        "settings_title": "Appearance & language",
        "photos_folder": "Photos folder",
        "output_folder": "Output folder",
        "browse": "Browse",
        "options_box": "Settings",
        "folders_box": "Folders",
        "target_count": "Target photo count",
        "more_options": "More options ▸",
        "more_options_open": "More options ▾",
        "explain_options": "Explain options",
        "start": "Start selection",
        "cancel": "Cancel",
        "review": "Review selection",
        "map": "Map",
        "next_pick_folders": "Next: choose folders…",
        "loading_modules": "Loading detection modules…",
        "steps_hint": "Analysis steps",
        "log": "Log",
        "close": "Close",
        "step_folders": "1 · Folders",
        "step_options": "2 · Options",
        "step_run": "3 · Start",
        "found_photos": "{n} photos found",
        "found_none": "No photos found",
        "found_counting": "Counting photos…",
        "placeholder_folder": "No folder selected yet",
        "opt_geocode_long": "Resolve place names online",
        "opt_faces_long": "Face detection / closed eyes",
        "tip_resume": "Paused or crashed? Progress is saved automatically.",
        "toggle_on": "On",
        "toggle_off": "Off",
        "language": "Language",
        "theme": "Theme",
        "lang_de": "Deutsch",
        "lang_en": "English",
        "auto_advance": "Auto-advance after remove",
        "show_alt": "Show alternative beside photo",
        "save_settings": "Save",
        "settings_saved": "Settings saved.",
        "settings_restart_hint": "Close and reopen the window once for the full color refresh.",
        "settings_hint": "Language applies immediately. Theme colors for maps and windows "
        "apply after saving; reopen the main window if needed.",
        "map_title": "Chapter & map preview",
        "map_subtitle": "Overview of planned chapters and GPS points.",
        "map_subtitle_export": "Check places and order before files are copied.",
        "map_chapters": "Chapters",
        "map_browser": "Map in browser",
        "map_export": "Export like this",
        "map_no_gps": "No GPS data – world map without trip points",
        "map_no_chapters": "No chapters detected",
        "map_selected": "selected",
        "map_world": "World map",
        "map_trip": "Trip view",
        "opt_geocode": "Place names via internet",
        "opt_faces": "Face detection / closed eyes",
        "opt_bursts": "Bursts (keep best 1–2)",
        "opt_aside": "Documents & screenshots aside",
        "opt_accidental": "Remove accidental shots",
        "opt_weak_night": "Remove weak night shots",
        "opt_finger": "Filter finger-on-lens shots",
        "opt_content": "Cluster similar scenes",
        "opt_aesthetic": "Local aesthetic (no API)",
        "opt_video": "Video / Live Photo stills",
        "opt_timezone": "Timezone correction (hours)",
        "opt_coverage": "Day coverage",
        "opt_people": "People balance",
        "opt_map": "Chapter/map preview before export",
        "opt_ai": "AI review (Anthropic API)",
        "opt_dry": "Estimate cost only",
        "review_title": "Review selection",
        "review_hint_grid": "One folder at a time · click = keep/remove · right-click = move.",
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
        "chapter_jump_prev": "← Previous folder",
        "chapter_jump_next": "Next folder →",
        "folder_nav": "Folder",
        "folder_of": "Folder {i} / {n}",
        "folder_count": "{n} photos in this folder",
        "move_to": "Move to…",
        "moved_to": "Moved to {folder}",
        "empty_folder": "No photos in this folder.",
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
        "help_title": "Help – Photobook",
        "coverage_strength": "Coverage strength",
        "people_strength": "People-balance strength",
        "help_body": (
            "Quick start\n"
            "───────────\n\n"
            "1. Choose the photos folder (e.g. iCloud / trip photos).\n"
            "2. Choose an output folder (preferably empty / new).\n"
            "3. Set the target count (e.g. 80).\n"
            "4. Adjust options as needed – explanations via ? next to each option.\n"
            "5. Start selection – steps are color-coded.\n"
            "6. When done: review selection, adjust, save.\n\n"
            "Review\n"
            "  Grid: click = keep/remove · right-click = move folder.\n"
            "  Slideshow: large image, alternative (A), Esc = grid.\n\n"
            "Appearance\n"
            "  Top right: language (DE/EN), theme, slideshow options.\n\n"
            "Pause / update\n"
            "  selection_draft.json and photos_analysis.csv keep progress.\n"
            "  Use Programm aktualisieren.bat for updates. Details: START.md."
        ),
        "help_target_count": (
            "Approximate number of photos in the finished book (e.g. 80 or 400)."
        ),
        "help_opt_geocode": (
            "GPS → city names (e.g. Tokyo, Kyoto). Hits are stored in "
            "geocode_cache.json. Without GPS an Album chapter is created."
        ),
        "help_opt_faces": (
            "Finds faces, flags closed eyes / bad crops, plus smile and "
            "looking-at-camera cues. Such photos are down-ranked."
        ),
        "help_opt_bursts": (
            "Similar photos taken seconds apart → keep only the best 1–2."
        ),
        "help_opt_aside": (
            "Tickets, maps, chats etc. stay out of auto chapters and go to "
            "optional_dokumente/ (you can add them later)."
        ),
        "help_opt_accidental": (
            "Typical trigger misses: mostly ground/sky, subject at the edge, "
            "strong tilt – excluded from the book."
        ),
        "help_opt_weak_night": (
            "Remove dark, soft, mushy night shots."
        ),
        "help_opt_content": (
            "Finds near-duplicate scenes (not only pixel duplicates) and keeps "
            "the best – uses embeddings and the analysis cache."
        ),
        "help_opt_aesthetic": (
            "Local quality estimate (sharpness, exposure, composition) with no cloud. "
            "Skipped when AI review is on."
        ),
        "help_opt_timezone": (
            "Shift all EXIF times by X hours (e.g. +9 if the camera was still "
            "on home time)."
        ),
        "help_opt_video": (
            "Extract the sharpest frame from short videos without a sibling JPG/HEIC "
            "(typical Live Photo without a still)."
        ),
        "help_opt_finger": (
            "Filter typical finger/hand-over-lens shots."
        ),
        "help_opt_coverage": (
            "Avoids almost everything coming from day one. "
            "Strength: gentle to strongly even across days."
        ),
        "help_opt_people": (
            "Avoids one person dominating the whole album."
        ),
        "help_opt_map": (
            "Show chapters and map before copying files, then confirm."
        ),
        "help_opt_ai": (
            "Sends candidate photos to the Anthropic API for quality/scene review. "
            "Costs money – see the estimate under the target count. Optional."
        ),
        "help_opt_dry": (
            "No real AI call: counts candidates and estimates cost only. "
            "Only useful when AI review is enabled."
        ),
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
