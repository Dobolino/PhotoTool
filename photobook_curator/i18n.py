"""Einfache DE/EN-Texte für die GUI."""

from __future__ import annotations

from typing import Any

from .settings import DEFAULT_LANGUAGE, load_settings

_STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "app_title": "Fotobuch-Auswahl",
        "brand": "Fotobuch",
        "workflow_subtitle": "Aus vielen Reisefotos wird eine Geschichte.",
        "workflow_import": "Reise importieren",
        "workflow_plan": "Album planen",
        "workflow_review": "Prüfen & exportieren",
        "import_title": "Deine Reise",
        "import_hint": "Fotos wählen oder ein gespeichertes Projekt fortsetzen.",
        "project_open": "Projekte",
        "resume_album": "Auswahl öffnen",
        "project_not_saved": "Dein Projekt wird beim Analysestart gespeichert.",
        "album_title": "Dein Album",
        "travel_profile": "Reiseprofil",
        "book_pages": "Buchseiten · 0 = manuell",
        "photos_per_page": "Fotos je Seite",
        "reserved_pages": "Seiten für Titel / Text",
        "budget_manual_hint": "Zielanzahl selbst wählen oder aus Buchseiten berechnen.",
        "budget_calculated": "{n} Fotos für {pages} Fotoseiten · Titel-/Textseiten berücksichtigt",
        "budget_invalid": "Bitte gültige Seitenzahlen und Fotos je Seite eingeben.",
        "target_invalid": "Die Zielanzahl muss grösser als 0 sein.",
        "album_invalid": "Album-Einstellungen prüfen",
        "show_details": "Analyse-Details anzeigen ▾",
        "hide_details": "Analyse-Details ausblenden ▴",
        "footer_safe": "Originale bleiben erhalten.\nAuswahl jederzeit prüfen und anpassen.",
        "advanced_heading": "Analyse & Vielfalt anpassen",
        "storytelling_strength": "Abwechslung & Reisegeschichte",
        "project_wait": "Bitte zuerst die laufende Analyse beenden.",
        "project_loaded": "Projekt „{name}“ geladen. Analysieren oder Auswahl öffnen.",
        "project_save_failed": "Projekt konnte nicht gespeichert werden",
        "relink_sources": "Originale wiederfinden…",
        "relink_need_project": "Bitte zuerst einen vorhandenen Ausgabeordner wählen.",
        "sources_relinked": "Originale neu verknüpft. Du kannst die Auswahl jetzt öffnen.",
        "legacy_album": "Vorhandene Auswahl · zum Neu-Analysieren zuerst den Fotos-Ordner wählen.",
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
        "opt_ai": "KI-Bewertung",
        "opt_dry": "Nur Kosten / Kandidaten schätzen",
        "ai_provider": "KI wählen",
        "ai_section": "KI-Bewertung",
        "ai_provider_none": "Keine KI (nur lokale Heuristik)",
        "ai_provider_gemini": "Google Gemini 1.5 Flash (Gratis / Free Tier)",
        "ai_provider_anthropic": "Anthropic Claude (kostenpflichtig)",
        "ai_provider_ollama": "Ollama lokal (Gratis, starke GPU)",
        "ai_api_key": "API-Key",
        "ai_api_key_gemini": "Gemini API-Key",
        "ai_api_key_anthropic": "Anthropic API-Key",
        "ai_key_link": "API-Key erstellen…",
        "ai_ollama_hint": (
            "Vision-Modell wählen (Liste aus Ollama, falls erreichbar). "
            "Standard: llava – vorher „ollama pull llava“."
        ),
        "ai_ollama_model": "Ollama-Modell",
        "help_tip_title": "Erklärung",
        "help_tip_close": "Schließen",
        "ai_blurb_none": "100 % lokal & schnell – nur OpenCV / MediaPipe / pHash (keine Cloud).",
        "ai_blurb_gemini": (
            "Gratis im Free Tier (ca. 1.500 Bilder/Tag) – stark bei Ästhetik, "
            "Motiven und Text auf Schildern/Speisekarten. Braucht Internet + Key."
        ),
        "ai_blurb_anthropic": (
            "Pay-per-Use – höchste Präzision bei Komposition, Stimmung und "
            "feinen Bildnuancen. Braucht Internet + Key."
        ),
        "ai_blurb_ollama": (
            "100 % lokal & offline – nutzt deine GPU; bei vielen Fotos oft langsam."
        ),
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
        "filter_duplicates": "Duplikate",
        "dup_badge_phash": "Duplikat",
        "dup_badge_burst": "Serie",
        "dup_badge_content": "Ähnlich",
        "dup_of": "wie {name}",
        "dup_section_title": "Aussortierte Duplikate ({n})",
        "dup_related_title": "Duplikate / Serien-Varianten",
        "dup_none": "Keine Duplikate markiert.",
        "show_duplicates": "Duplikate anzeigen ({n})",
        "hide_duplicates": "Duplikate ausblenden",
        "alt_swapped": "Getauscht → {name}",
        "warn_day_gaps": "⚠ {n} Tag(e) ohne Auswahl (z. B. {sample})",
        "warn_people_missing": (
            "⚠ {n} erkannte Person(en) fehlen in der Auswahl "
            "(Gesichter, die nirgends im Buch vorkommen)"
        ),
        "warn_low_res": "⚠ {n} Bild(er) mit niedriger Auflösung (<1000px)",
        "warn_empty_chapter": "⚠ Dieses Kapitel hat keine Auswahl",
        "warn_thin_chapter": "⚠ Nur 1 Foto in diesem Kapitel",
        "note_eyes_closed": "Augen zu",
        "note_bad_face": "Gesicht problematisch",
        "note_looking_away": "Blick weg",
        "note_smiling": "Lächeln",
        "note_finger": "Finger vor Linse",
        "note_accidental": "Fehlauslösung?",
        "note_weak_night": "Schwache Nachtaufnahme",
        "note_blurry": "Unscharf",
        "note_dark": "Zu dunkel",
        "note_bright": "Überbelichtet",
        "note_mood": "Stimmung",
        "note_ai_reject": "KI: eher weglassen",
        "note_faces": "{n} Gesichter",
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
        "max_per_day": "Max. Bilder pro Tag",
        "max_per_chapter": "Max. Bilder pro Kapitel",
        "selection_caps_hint": "0 = unbegrenzt. Geschützte Favoriten haben Vorrang.",
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
            "Sortiert Bilder aus, die wie versehentliche Aufnahmen wirken. "
            "Für die erste Auswahl besser ausgeschaltet lassen und später selbst prüfen."
        ),
        "help_opt_weak_night": (
            "Sortiert sehr dunkle und unscharfe Nachtbilder aus. "
            "Bei Nachtmärkten und Neon-Szenen zunächst ausgeschaltet lassen."
        ),
        "help_opt_content": (
            "Vergleicht ähnliche Motive und reduziert Wiederholungen. "
            "Entfernte Varianten kannst du bei der Nachkontrolle wieder hinzufügen."
        ),
        "help_opt_aesthetic": (
            "Bewertet Bildaufbau und Licht auf deinem Computer, ohne Fotos zu versenden. "
            "Wird bei einer KI-Bewertung nicht zusätzlich verwendet."
        ),
        "help_opt_timezone": (
            "Korrigiert eine falsch eingestellte Kamerauhr. Sonst auf 0 lassen; "
            "die Zeitzone des Reiseziels ist nicht automatisch die richtige Korrektur."
        ),
        "help_opt_video": (
            "Extrahiert den schärfsten Frame aus kurzen Videos ohne Schwester-JPG/HEIC "
            "(typisch Live Photo ohne Standbild)."
        ),
        "help_opt_finger": (
            "Typische Fehlaufnahmen mit Finger/Hand vor der Kamera aussortieren."
        ),
        "help_opt_coverage": (
            "Verteilt die Auswahl auf möglichst viele Reisetage. "
            "Je höher die Stärke, desto gleichmässiger werden die Tage berücksichtigt."
        ),
        "help_opt_people": (
            "Berücksichtigt, welche Personen häufig vorkommen, und bevorzugt "
            "eine ausgewogenere Mischung. Besonders nützlich bei Gruppenreisen."
        ),
        "help_opt_map": (
            "Vor dem Kopieren Kapitel und Karte zeigen, dann bestätigen."
        ),
        "help_opt_ai": (
            "Optional: Ein KI-Anbieter bewertet Bildvorschauen zusätzlich. "
            "Für den ersten Durchlauf reicht die lokale Auswahl."
        ),
        "help_ai_provider": (
            "Keine KI: empfohlener Start. Die Bewertung läuft auf deinem Computer.\n\n"
            "Gemini oder Claude: Bildvorschauen werden an den Anbieter gesendet. "
            "Benötigt Internet und einen API-Schlüssel; es können Kosten entstehen.\n\n"
            "Ollama: zusätzliche KI auf deinem Computer. Dafür muss Ollama mit "
            "einem passenden Bildmodell eingerichtet sein."
        ),
        "help_opt_dry": (
            "Bei eingeschalteter KI wird nur eine Schätzung der Kandidaten und Kosten "
            "erstellt. Es werden keine Bilder an die KI gesendet und kein Album exportiert."
        ),
        "help_ai_ollama_model": (
            "Name des Vision-Modells in Ollama (z. B. llava oder llama3.2-vision). "
            "Aus der Liste wählen oder – falls nötig – exakt so eintippen, "
            "wie „ollama list“ es zeigt. Ohne Vision-Modell funktioniert die "
            "Bildbewertung nicht."
        ),
    },
    "en": {
        "app_title": "Photobook curator",
        "brand": "Photobook",
        "workflow_subtitle": "Turn your travel photos into a story.",
        "workflow_import": "Import your trip",
        "workflow_plan": "Plan your album",
        "workflow_review": "Review & export",
        "import_title": "Your trip",
        "import_hint": "Choose photographs or continue a saved project.",
        "project_open": "Projects",
        "resume_album": "Open selection",
        "project_not_saved": "Your project is saved when analysis starts.",
        "album_title": "Your album",
        "travel_profile": "Travel profile",
        "book_pages": "Book pages · 0 = manual",
        "photos_per_page": "Photos per page",
        "reserved_pages": "Title / text pages",
        "budget_manual_hint": "Choose a photo count or calculate it from book pages.",
        "budget_calculated": "{n} photos across {pages} photo pages · title/text pages reserved",
        "budget_invalid": "Enter valid page counts and photos per page.",
        "target_invalid": "The target photo count must be greater than 0.",
        "album_invalid": "Check album settings",
        "show_details": "Show analysis details ▾",
        "hide_details": "Hide analysis details ▴",
        "footer_safe": "Original photographs are preserved.\nReview and adjust your selection at any time.",
        "advanced_heading": "Adjust analysis & variety",
        "storytelling_strength": "Variety & travel storytelling",
        "project_wait": "Please finish the running analysis first.",
        "project_loaded": "Project “{name}” loaded. Analyze or open its selection.",
        "project_save_failed": "Project could not be saved",
        "relink_sources": "Locate original files…",
        "relink_need_project": "Choose an existing output folder first.",
        "sources_relinked": "Original files relinked. You can now open the selection.",
        "legacy_album": "Existing selection · choose its photo folder before running a new analysis.",
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
        "opt_ai": "AI review",
        "opt_dry": "Estimate cost / candidates only",
        "ai_provider": "Choose AI",
        "ai_section": "AI review",
        "ai_provider_none": "No AI (local heuristics only)",
        "ai_provider_gemini": "Google Gemini 1.5 Flash (free tier)",
        "ai_provider_anthropic": "Anthropic Claude (paid)",
        "ai_provider_ollama": "Ollama local (free, strong GPU)",
        "ai_api_key": "API key",
        "ai_api_key_gemini": "Gemini API key",
        "ai_api_key_anthropic": "Anthropic API key",
        "ai_key_link": "Create API key…",
        "ai_ollama_hint": (
            "Pick a vision model (from Ollama if reachable). "
            "Default: llava – run “ollama pull llava” first."
        ),
        "ai_ollama_model": "Ollama model",
        "help_tip_title": "Help",
        "help_tip_close": "Close",
        "ai_blurb_none": "100% local & fast – OpenCV / MediaPipe / pHash only (no cloud).",
        "ai_blurb_gemini": (
            "Free tier (~1,500 images/day) – strong on aesthetics, subjects, "
            "and text on signs/menus. Needs internet + key."
        ),
        "ai_blurb_anthropic": (
            "Pay-per-use – highest precision for composition, mood, and fine nuance. "
            "Needs internet + key."
        ),
        "ai_blurb_ollama": (
            "100% local & offline – uses your GPU; often slow with many photos."
        ),
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
        "filter_duplicates": "Duplicates",
        "dup_badge_phash": "Duplicate",
        "dup_badge_burst": "Burst",
        "dup_badge_content": "Similar",
        "dup_of": "like {name}",
        "dup_section_title": "Excluded duplicates ({n})",
        "dup_related_title": "Duplicates / burst variants",
        "dup_none": "No duplicates marked.",
        "show_duplicates": "Show duplicates ({n})",
        "hide_duplicates": "Hide duplicates",
        "alt_swapped": "Swapped → {name}",
        "warn_day_gaps": "⚠ {n} day(s) with no selection (e.g. {sample})",
        "warn_people_missing": (
            "⚠ {n} recognized person(s) missing from selection "
            "(faces that never appear in the book)"
        ),
        "warn_low_res": "⚠ {n} low-resolution photo(s) (<1000px)",
        "warn_empty_chapter": "⚠ This chapter has no selection",
        "warn_thin_chapter": "⚠ Only 1 photo in this chapter",
        "note_eyes_closed": "Eyes closed",
        "note_bad_face": "Face issue",
        "note_looking_away": "Looking away",
        "note_smiling": "Smiling",
        "note_finger": "Finger on lens",
        "note_accidental": "Accidental shot?",
        "note_weak_night": "Weak night shot",
        "note_blurry": "Blurry",
        "note_dark": "Too dark",
        "note_bright": "Overexposed",
        "note_mood": "Mood",
        "note_ai_reject": "AI: prefer drop",
        "note_faces": "{n} faces",
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
        "max_per_day": "Max. photos per day",
        "max_per_chapter": "Max. photos per chapter",
        "selection_caps_hint": "0 = unlimited. Protected favorites take priority.",
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
            "Filters photos that appear accidental. For your first selection, "
            "leave this off and review these pictures yourself later."
        ),
        "help_opt_weak_night": (
            "Filters very dark, blurry night photos. Leave this off initially "
            "for night markets and neon scenes."
        ),
        "help_opt_content": (
            "Compares similar subjects and reduces repetition. You can add "
            "removed alternatives back during review."
        ),
        "help_opt_aesthetic": (
            "Rates composition and light on your computer without sending photos. "
            "Not used in addition to AI review."
        ),
        "help_opt_timezone": (
            "Corrects an incorrectly set camera clock. Otherwise leave at 0; "
            "the destination's time zone is not automatically the right correction."
        ),
        "help_opt_video": (
            "Extract the sharpest frame from short videos without a sibling JPG/HEIC "
            "(typical Live Photo without a still)."
        ),
        "help_opt_finger": (
            "Filter typical finger/hand-over-lens shots."
        ),
        "help_opt_coverage": (
            "Includes as many travel days as possible. A higher strength "
            "distributes the selection more evenly across days."
        ),
        "help_opt_people": (
            "Considers how often people appear and favours a more balanced mix. "
            "Especially useful for group trips."
        ),
        "help_opt_map": (
            "Show chapters and map before copying files, then confirm."
        ),
        "help_opt_ai": (
            "Optional: an AI provider additionally rates picture previews. "
            "Local selection is enough for a first run."
        ),
        "help_ai_provider": (
            "No AI: the recommended starting point. Rating runs on your computer.\n\n"
            "Gemini or Claude: picture previews are sent to the provider. Requires "
            "internet and an API key; charges may apply.\n\n"
            "Ollama: additional AI on your computer. Requires an installed Ollama "
            "service with a suitable image model."
        ),
        "help_opt_dry": (
            "With AI enabled, only an estimate of candidates and cost is produced. "
            "No pictures are sent to AI and no album is exported."
        ),
        "help_ai_ollama_model": (
            "Vision model name in Ollama (e.g. llava or llama3.2-vision). "
            "Pick from the list or type it exactly as shown by “ollama list”. "
            "Without a vision model, image review will not work."
        ),
    },
}

_STRINGS["de"].update({
    "update_title": "Updates", "update_checking": "Suche nach einer neuen Version…",
    "update_available": "Version {version} ist verfügbar.",
    "update_current": "Keine neuere veröffentlichte Version verfügbar.",
    "update_install": "Herunterladen und installieren",
    "update_busy": "Bitte zuerst die laufende Analyse beenden.",
    "update_confirm": "Update herunterladen? Nach der Prüfung schliesst PhotoTool und der Installer startet. Offene Review-Entwürfe werden gesichert.",
    "update_downloading": "Lade Installer herunter und prüfe SHA256…",
    "update_error": "Update fehlgeschlagen: {error}",
    "undo": "Rückgängig", "redo": "Wiederholen", "favorite": "★ Favorit schützen",
    "unfavorite": "☆ Schutz aufheben", "favorite_blocked": "Favorit geschützt – zuerst Schutz aufheben.",
    "print_check": "Druckqualität", "print_size": "Bildgrösse in cm (Breite × Höhe)",
    "print_target": "Zielauflösung (DPI)", "print_run": "Prüfen", "print_report": "Bericht speichern",
    "print_hint": "Gilt für alle ausgewählten Bilder. Einpassen durch Beschnitt, Drehung erlaubt. Schärfe und Druckmaterial werden nicht bewertet.",
    "print_ok": "Ausreichend", "print_low": "Unter Zielauflösung", "print_unknown": "Bildmasse unbekannt",
    "print_invalid": "Bitte positive, endliche Zahlen für Bildgrösse und DPI eingeben.",
    "print_summary": "{n} Bilder · {low} unter Zielauflösung · {unknown} ohne Bildmasse",
    "reason_title": "Auswahlgründe", "reason_selected": "Aktuell im Buch behalten.",
    "reason_not_selected": "Aktuell nicht im Buch.", "reason_favorite": "Als Favorit vor Abwahl geschützt.",
    "reason_manual_add": "Manuell hinzugefügt.", "reason_manual_reject": "Manuell entfernt.",
    "reason_manual_keep": "Dauerhaft behalten: gilt auch bei einer neuen Analyse.",
    "reason_manual_exclude": "Dauerhaft ausgeschlossen: gilt auch bei einer neuen Analyse; Favoritenschutz hat Vorrang.",
    "reason_decision_note": "Deine Begründung: {reason}",
    "reason_duplicate": "Als Duplikat erkannt; Original: {name}.", "reason_burst": "Als Serienvariante aussortiert.",
    "reason_aside": "Dokument oder Screenshot im optionalen Pool.",
    "reason_scores": "Technischer Score: {technical:.1f} · Gesamtscore: {final:.1f}",
    "reason_ai": "KI-Bewertung vorhanden.",
    "reason_unknown": "Der genaue automatische Auswahlgrund wurde nicht gespeichert; Kontingent und Vielfalt können mitentscheiden.",
})
_STRINGS["en"].update({
    "update_title": "Updates", "update_checking": "Checking for a new version…",
    "update_available": "Version {version} is available.",
    "update_current": "No newer published version available.",
    "update_install": "Download and install",
    "update_busy": "Please finish the current analysis first.",
    "update_confirm": "Download the update? After verification, PhotoTool closes and setup starts. Open review drafts will be saved.",
    "update_downloading": "Downloading installer and verifying SHA256…",
    "update_error": "Update failed: {error}",
    "undo": "Undo", "redo": "Redo", "favorite": "★ Protect favorite",
    "unfavorite": "☆ Remove protection", "favorite_blocked": "Favorite protected – remove protection first.",
    "print_check": "Print quality", "print_size": "Print size in cm (width × height)",
    "print_target": "Target resolution (DPI)", "print_run": "Check", "print_report": "Save report",
    "print_hint": "Applies to all selected photos. Fill by cropping, rotation allowed. Sharpness and print material are not assessed.",
    "print_ok": "Sufficient", "print_low": "Below target resolution", "print_unknown": "Unknown image dimensions",
    "print_invalid": "Enter positive, finite numbers for print size and DPI.",
    "print_summary": "{n} photos · {low} below target · {unknown} with unknown dimensions",
    "reason_title": "Selection reasons", "reason_selected": "Currently kept in the book.",
    "reason_not_selected": "Currently outside the book.", "reason_favorite": "Protected against removal as a favorite.",
    "reason_manual_add": "Added manually.", "reason_manual_reject": "Removed manually.",
    "reason_manual_keep": "Always keep: also applies to a new analysis.",
    "reason_manual_exclude": "Always exclude: also applies to a new analysis; favorite protection takes priority.",
    "reason_decision_note": "Your reason: {reason}",
    "reason_duplicate": "Detected as a duplicate; original: {name}.", "reason_burst": "Rejected as a burst variant.",
    "reason_aside": "Document or screenshot in the optional pool.",
    "reason_scores": "Technical score: {technical:.1f} · Final score: {final:.1f}",
    "reason_ai": "AI review available.",
    "reason_unknown": "The exact automatic decision was not recorded; quotas and diversity can also affect selection.",
})

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
