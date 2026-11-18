# Photobook Curator (PhotoTool) – Programmübersicht für Code-Review

Dieses Dokument beschreibt Zweck, Architektur und Verhalten des Repos, damit ein Agent (z. B. Claude Code) den Code prüfen und Änderungen einordnen kann.

- **Repo:** PhotoTool (`photobook_curator`)
- **Sprache:** Python 3
- **UI:** Tkinter (Windows-first) + CLI
- **Einstieg für Menschen:** `ANLEITUNG.md`, Windows: `Fotobuch starten.bat`

---

## 1. Zweck

Lokales Tool, das aus einem großen iPhone-/iCloud-Urlaubsfoto-Ordner automatisch eine **Fotobuch-Auswahl** erzeugt:

- technisch schwache / doppelte / Serienbilder aussortieren
- optional Finger vor der Linse erkennen und aussortieren
- Orte (GPS → Städte/Regionen) und Transit-Abschnitte erkennen
- eine wählbare **Zielanzahl** Bilder (`target_n` / GUI-Spinner / CLI `-n`) mit Vielfalt, Tages-Abdeckung und Personen-Balance auswählen
- Kapitelstruktur erzeugen (Region → Hauptteil / Essen, dazwischen Transit)
- Screenshots/Dokumente **nicht** automatisch ins Buch, sondern in einen Optional-Pool
- danach manuell per Thumbnail-Review nachjustieren
- optional Kapitel-/Karten-Vorschau **vor** dem Datei-Export (GUI)

Kein Cloud-Upload außer optionaler Anthropic-API und optionalem Nominatim-Geocoding.

---

## 2. Einstiegspunkte

| Einstieg | Befehl / Datei |
|----------|----------------|
| CLI | `python -m photobook_curator -i <fotos> -o <ausgabe> -n 80` |
| GUI | `python -m photobook_curator.gui` oder `python -m photobook_curator --gui` |
| Windows | `Fotobuch starten.bat` (legt `.venv` an, installiert deps, startet GUI) |
| Sample-Daten | `python scripts/create_sample_dataset.py` → `sample_photos/` |

Paket-Entry-Points (pyproject): `photobook-curator`, `photobook-curator-gui`.

---

## 3. Typischer Benutzerablauf (GUI)

1. Fotos-Ordner + Ausgabe-Ordner wählen, **Zielanzahl** setzen (z. B. 80 – ungefähre finale Bildanzahl im Buch).
2. Optionen anhaken (Gesichter, Bursts, Dokumente, Finger vor Linse, Tages-Abdeckung, Personen-Balance, Karten-Vorschau, KI).
3. **Auswahl starten** → Pipeline im Hintergrundthread.
4. Wenn **Kapitel-/Karten-Vorschau** aktiv:
   - Pipeline wählt aus, schreibt Analyse-CSV (+ HTML-Karte), **kopiert noch nicht** nach `selected/`.
   - Modal-Fenster: Kapitelliste + einfache GPS-Karte; „Karte im Browser“ öffnet Leaflet-HTML.
   - **So exportieren** → Ordner kopieren; **Abbrechen** → kein `selected/`.
5. Sonst: sofort exportieren.
6. Frage: Thumbnail-**Auswahl prüfen**? Keep/Remove/Add, Speichern schreibt Outputs neu.
7. Später erneut: Buttons **Auswahl prüfen** / **Karte zeigen** (kann aus CSV nachladen).

CLI exportiert immer sofort; `--map-preview` schreibt zusätzlich `kapitel_karte.html`.

---

## 4. Paketstruktur (`photobook_curator/`)

| Modul | Verantwortung |
|-------|----------------|
| `pipeline.py` | Orchestrierung: `PipelineConfig`, `run_pipeline`, `export_book_outputs` |
| `cli.py` / `gui.py` | Bedienung → Config → Pipeline |
| `models.py` | `Photo`, `Region`, `TransitSection`, `BookPlan`, `ChapterType` |
| `scan.py` | Rekursiv Bilder finden, EXIF (Zeit, GPS, Kamera) |
| `utils.py` | HEIC-Load, OpenCV-Hilfen, slugify, Screenshot-Auflösungen |
| `quality.py` | Schärfe/Belichtung/Kontrast/Sättigung → `technical_score` |
| `duplicates.py` | pHash-Duplikate; enge Serien als Burst |
| `bursts.py` | Zeitfenster-ähnliche Serien, beste N behalten |
| `documents.py` | Heuristik: Screenshot/Dokument/Karte/Ticket → Aside-Pool |
| `faces.py` | Gesichtszählung (MediaPipe / Haar-Fallback) |
| `face_quality.py` | Augen zu, abgeschnitten, zu klein → `bad_face` |
| `finger_obstruction.py` | Optional: Finger vor der Linse → `finger_on_lens`, aus Auswahl |
| `people_balance.py` | Gesichtscrops clustern → `person_cluster_ids`, Penalty in Auswahl |
| `geocoding.py` | Nominatim + Cache; Ortsnamen **Englisch** (`language=en`); Offline-Stadt-Fallback |
| `regions.py` | DBSCAN auf GPS → Städte/Regionen; GPS-lose per Zeit zuordnen |
| `transit.py` | Fotos zwischen Regionen → Transit-Kapitel |
| `selection.py` | Kontingente, Kandidaten, Vielfalt, Coverage, Food-Split, Buchreihenfolge |
| `ai_review.py` | Optional Anthropic Vision; sonst Heuristik-`scene_type` |
| `output.py` | CSV, `selected/`, `optional_dokumente/`, Markdown-TOC |
| `map_preview.py` | Kapitelvorschau-Fenster + `kapitel_karte.html` |
| `review_gui.py` | Thumbnail Keep/Reject/Add |
| `review_export.py` | Manuelle Auswahl anwenden, CSV laden, Plan rekonstruieren |

---

## 5. Pipeline-Phasen (`run_pipeline`)

Reihenfolge im Code:

### Phase 1 – Einlesen & technische Filter
1. `scan_photos(input_dir)`
2. `analyze_all(photos)` – technische Scores
3. optional `mark_aside_documents` (`enable_document_aside`)
4. `mark_duplicates` – bei Bursts: enge near-identical Gruppen behalten `burst_keep`
5. optional Faces: `count_faces` → `analyze_face_quality`
6. optional Finger: `analyze_finger_obstruction` wenn `enable_finger_filter` → `finger_on_lens`
7. optional Personen-Balance: `analyze_people_clusters` wenn `people_balance_intensity > 0`
8. optional `mark_bursts` – lockerere Serien

### Phase 2 – Orte
- `build_location_plan` mit `GeocodeCache`
- DBSCAN (`cluster_eps_meters`), Reverse-Geocode (**Englisch**, z. B. Tokyo statt 東京), Regionen bilden
- Cache-Key enthält Sprache (`lat,lon:en`), damit alte de/ja-Einträge nicht greifen
- Transiente Geocode-Fehler werden **nicht** persistiert
- Fotos ohne GPS per Zeitfenster (`gps_time_hours`) zuordnen

### Phase 3 – Transit
- `detect_transits` zwischen aufeinanderfolgenden Regionen
- Mindestanzahl `min_transit_photos`, Quota-Cap `max_transit_quota`

### Kandidaten
- `mark_candidates` / `distribute_quotas`
- pro Region/Transit: beste `quota * candidate_factor` nach `technical_score`
- Aside/Duplikate/Burst-Rejects/`finger_on_lens` ausgeschlossen

### Phase 4 – AI (optional)
- `ai_review=True`: `run_ai_review` (Anthropic)
- sonst: `ensure_scene_types` (Heuristik)
- `dry_run and ai_review`: nur Kostenschätzung + CSV, dann Return

### Phase 5 – Finale Auswahl
- `build_book_order` → pro Region Hauptteil + Essen, dazwischen Transit
- Coverage / People-Balance je nach Intensity
- Chronologische Sortierung innerhalb der Kapitel

### Ausgabe
- wenn `enable_map_preview`: `write_chapter_map` → `kapitel_karte.html`
- wenn `skip_export` (GUI+Vorschau): nur CSV
- sonst `export_book_outputs`: CSV + `selected/` + Optional-Pool + `inhaltsverzeichnis.md`

---

## 6. `PipelineConfig` (Felder & Defaults)

```text
input_dir, output_dir          # Pflicht
target_n = 80
candidate_factor = 4.0
geocode = True
ai_review = False
dry_run = False
food_ratio = 0.15
max_landmarks = 3
min_transit_photos = 3
max_transit_quota = 5
similarity_threshold = 0.92
gps_time_hours = 6.0
cluster_eps_meters = 400.0
ai_concurrency = 5
enable_faces = True
enable_bursts = True
enable_document_aside = True
enable_finger_filter = False     # Finger vor Linse aussortieren
coverage_intensity = 0.0         # 0=aus … 1=stark gleichmäßig über Tage
people_balance_intensity = 0.0   # 0=aus … 1=starke Personen-Balance
enable_map_preview = False
skip_export = False              # nur GUI-Karten-Vorschau-Pfad
burst_max_seconds = 30.0
burst_keep = 2
burst_min_size = 3               # nicht in CLI exponiert
```

### Optionale Features (Standard)

| Feature | Standard | GUI | CLI |
|---------|----------|-----|-----|
| Gesichtserkennung / Augen zu | an | Checkbox | `--faces` / `--no-faces` |
| Serien/Bursts | an | Checkbox | `--bursts` / `--no-bursts` |
| Dokumente separat | an | Checkbox | `--aside-documents` / `--no-…` |
| Finger vor der Linse | aus | Checkbox | `--finger-filter` / `--no-finger-filter` |
| Tages-Abdeckung | aus | Checkbox + Regler | `--coverage-intensity 0..1` |
| Personen-Balance | aus | Checkbox + Regler | `--people-balance-intensity 0..1` |
| Kapitel-/Karten-Vorschau | aus | Checkbox (+ Button) | `--map-preview` (nur HTML, kein Deferred-Export) |
| KI-Bewertung | aus | Checkbox + API-Key | `--ai-review` (+ `--dry-run`) |
| Zielanzahl Bilder | 80 | Spinbox „Zielanzahl Bilder“ | `-n` / `--target-count` |

---

## 7. Datenmodell `Photo` (relevant)

**Ort/Zeit:** `datetime_taken`, `gps_lat`/`gps_lon`, `region`, `assigned_by_time`, `fine_cluster_id`

**Aussortieren:** `is_duplicate`, `is_burst_reject`, `burst_group_id`, `is_aside`, `aside_type`, `finger_on_lens`, `flags` (z. B. `unreadable`, `finger_on_lens`)

**Scores:** `technical_score`, `aesthetic_score`, `final_score`, `keep_recommendation`, `quality_issue`, `landmark`

**Gesichter / Finger:** `face_count`, `eyes_closed`, `face_cut_off`, `face_too_small`, `bad_face`, `finger_on_lens`, `person_cluster_ids`

**Auswahl/Export:** `scene_type`, `is_candidate`, `is_selected`, `chapter_type`, `chapter_folder`, `book_position`

`BookPlan`: Liste `regions`, `transits`, `unassigned_indices`.

---

## 8. Auswahl-Logik (Kern)

### Kontingente
- Transit zuerst begrenzen (`max_transit_quota`).
- Restbudget `target_n - transit` auf Regionen nach Gewicht `n_photos * day_count`.

### Food-Split
- `scene_type == "essen"` → Unterkapitel Essen.
- Anteil ca. `food_ratio` (Default 15 %), mindestens 1 wenn Food-Kandidaten existieren.

### Final Score
- Mit Aesthetic: `0.45 * tech + 0.55 * aesthetic`, sonst tech.
- Multiplikatoren: `keep_recommendation=False` ×0.4, `quality_issue` ×0.7, `bad_face` ×0.45.
- Landmark: +5 (wenn nicht bad_face). Clamp 0–100.

### Vielfalt (`_select_diverse`)
- Round-Robin über Szenetypen.
- Zu ähnliche Farbhistogramme (Korrelation ≥ `similarity_threshold`) überspringen.
- Landmark-Deckel `max_landmarks` im Hauptteil.
- Bei People-Balance: greedy `final_score - people_balance_penalty`.

### Tages-Abdeckung
- `allocate_day_quotas`: mischt proportional vs. gleichmäßig je `coverage_intensity`.
- Danach diverse Auswahl pro Tag.

### Personen-Balance
- Face-Crops → pHash → Union-Find-Cluster → `person_cluster_ids`.
- Penalty: `intensity * (14 * over - 6 * new_people)`.

### Finger vor der Linse (`finger_obstruction.py`, optional)
- Aktiv nur wenn `enable_finger_filter=True` (GUI-Checkbox / `--finger-filter`).
- Heuristik: große, **weiche** Hautfläche am **Bildrand** (typischer Finger vor der Linse) via `detect_soft_border_skin`.
- Zusätzlich MediaPipe Hand Landmarker: sehr große Hand nahe Kamera / am Rand (`detect_large_hand_mediapipe`).
- Bei Treffer: `finger_on_lens=True`, Flag `finger_on_lens`, `quality_issue`, Score −50.
- Wird in `mark_candidates` und `_ok` der Auswahl **vollständig ausgeschlossen** (wie Burst-Reject/Aside).
- Review-GUI zeigt Badge „Finger“.

### Buchordner
- `01_<Region>/hauptteil`, `01_<Region>/essen`
- Transit: `01b_Transit_<A>-<B>`
- Manuell hinzugefügte Docs: `99_Optional_Dokumente`

---

## 9. Ausgabeartefakte (`output_dir/`)

| Pfad | Inhalt |
|------|--------|
| `photos_analysis.csv` | Alle Fotos + Flags/Scores |
| `selected/...` | Kopierte Buchauswahl |
| `optional_dokumente/` | Aside-Pool |
| `inhaltsverzeichnis.md` | Kapitelübersicht |
| `kapitel_karte.html` | Leaflet/OSM-Karte (optional) |
| `geocode_cache.json` | Geocode-Cache |

---

## 10. Review & Map Preview

### Review (`review_gui` / `review_export`)
- Thumbnails nach Kapiteln.
- Keep/Reject; Alternativen aus Kandidaten; Aside-Pool einfügen.
- Badges u. a. für „Augen zu“ / „Gesicht?“ / „Finger“.
- Speichern: `apply_manual_selection` → CSV/`selected`/Markdown/Pool neu.

### Map Preview (`map_preview`)
- `build_chapter_previews` – Kapitel, Counts, GPS-Schwerpunkte.
- Tk-Fenster mit Liste + Canvas-Scatter.
- HTML mit Leaflet CDN (braucht Netz für Kacheln).
- GUI-Deferred-Export nur wenn `enable_map_preview` und `skip_export`.

---

## 11. Abhängigkeiten (warum)

| Paket | Verwendung |
|-------|------------|
| Pillow / pillow-heif | Bilder, HEIC, Thumbnails |
| exifread | EXIF Zeit/GPS |
| opencv-python-headless | Qualität, Histogramme, Dokument-Heuristik, Haar |
| numpy / scikit-learn | Arrays, DBSCAN |
| imagehash | pHash Duplikate/Bursts/Personen |
| mediapipe | Faces + Face Landmarker + Hand Landmarker (Finger) + People-Crops |
| geopy | Nominatim |
| anthropic | optionale Vision-Bewertung |
| tqdm | Progress |
| piexif | nur Sample-Dataset-Skript |
| tkinter | GUI |

MediaPipe-Modelle werden nach `~/.cache/photobook_curator/` geladen:
- Face Detector: `blaze_face_short_range.tflite`
- Face Landmarker: `face_landmarker.task` (nicht `.tflite`)
- Hand Landmarker: `hand_landmarker.task` (für Finger-Filter; Heuristik läuft auch ohne)

---

## 12. Tests

Unter `tests/`:

- `test_ai_parse.py` – AI-JSON, Heuristik-Szenen, Kosten
- `test_regions_transit.py` – Cluster, Regionen, Transit, Offline-Geocode
- `test_bursts.py` – Burst vs. Duplikat
- `test_documents.py` – Aside-Pool
- `test_face_quality.py` – Augen/Qualität → Score
- `test_finger_obstruction.py` – Haut-/Finger-Heuristik, Flags, Ausschluss aus Kandidaten
- `test_coverage.py` – Tageskontingente
- `test_people_balance.py` – Penalty + Auswahl
- `test_review_export.py` – manuelle Auswahl / CSV-Roundtrip
- `test_map_preview.py` – Kapitel-Previews + HTML

Ausführen: `pytest` (im venv).

---

## 13. Wichtige Design-Entscheidungen / Fallstricke

1. **Dokumente:** Heuristik ohne OCR → Fehlklassifikation möglich. Aside nie in Auto-Kapitel, nur Pool + manueller Add.
2. **Burst vs. Duplikat:** Zwei Pfade – enge pHash-Gruppen in `duplicates.py`, lockere Serien in `bursts.py`. Flags unterscheiden sich (`is_duplicate` vs. `is_burst_reject`).
3. **Face Landmarker:** Datei muss `.task` sein; alter `.tflite`-Cache wird verworfen.
4. **Personen-Clustering:** O(n²) über Face-Signaturen; ohne MediaPipe-Detector keine Cluster → Balance wirkungslos.
5. **Scene types ohne AI:** stark dateiname-/heuristikbasiert → Food-Split ungenau möglich.
6. **Karten-Vorschau CLI ≠ GUI:** CLI exportiert sofort; nur GUI deferred `skip_export`.
7. **Windows:** PowerShell `Activate.ps1` / ExecutionPolicy; Pfade mit Leerzeichen in Anführungszeichen; Anthropic-Key ≠ Claude-Chat-Abo.
8. **Unassigned:** Fotos ohne Region landen nicht automatisch im Buchkontingent.
9. **`burst_min_size`:** in Config, aber nicht als CLI-Flag.
10. **Finger-Filter:** Heuristik (Haut + Weichheit + Rand) kann False Positives haben (z. B. große weiche Hautflächen); deshalb **default aus**. Ohne Hand-Modell bleibt nur die Heuristik. Manuell im Review trotzdem wieder einfügbar, falls gewünscht.
11. **EXIF-Orientierung:** `load_image` wendet `ImageOps.exif_transpose` an – Analyse/Thumbnails nutzen die sichtbare Ausrichtung.
12. **Modell-Downloads:** zentral über `utils.download_model` mit Timeout (30 s) und Mindestgröße; abgeschnittene Dateien werden verworfen.
13. **Performance (P1):** `load_bgr_cached` (LRU, max. Kante 1024) teilt Decodes über Quality/Faces/Finger/People/Dokumente; Scan nutzt `image_display_size` ohne Voll-Decode; Duplikate mit int-Hamming + Zeitfenster-Zwei-Zeiger; Farbhistogramme pro Foto gecacht (256px).
14. **UX (P2):** `run_pipeline(..., progress=callback)` meldet Phasen + Fortschritt 0–1; GUI zeigt Progressbar. Review: Keep/Remove aktualisiert nur die Kachel (kein Full-Rerender); Thumbnails laden lazy im Hintergrundthread. Standalone-Build: `packaging/` (PyInstaller).
15. **Heuristik/Cluster (P3):** DBSCAN mit Haversine; Food/Landschaft auch über Farb-/Himmel-Heuristik; Haar-Fallback setzt kein `eyes_closed`; `analysis_cache.json` cacht Quality/pHash pro `(path,mtime,size)` (abschaltbar `--no-analysis-cache`).

---

## 14. Was der Reviewer prüfen soll (Vorschläge)

Bei Code-Review / Refactor bitte u. a. darauf achten:

1. Bleiben optionale Features wirklich **default-off bzw. abschaltbar**, ohne den Happy Path zu zerlegen?
2. Werden Aside/Duplikate/Burst-Rejects/`finger_on_lens` konsequent aus Kandidaten **und** Auto-Auswahl ausgeschlossen?
3. Bleibt die Kapitelreihenfolge Region → Essen → Transit chronologisch und stabil?
4. GUI-Deferred-Export: Abbruch darf `selected/` nicht halb schreiben; CSV darf bleiben.
5. CSV-Felder ↔ `Photo.to_csv_row` ↔ `CSV_FIELDS` ↔ `load_photos_from_csv` synchron?
6. MediaPipe-Fallbacks (Haar / none) ohne Crash?
7. Keine Secrets committen; API-Key nur env/`ANTHROPIC_API_KEY`.
8. Tests für geänderte Auswahl-/Export-Logik ergänzen.

---

## 15. Kurz: „Happy Path“-Datenfluss

```text
Ordner mit Fotos
  → scan + EXIF
  → quality / aside / dupes / faces [/ finger] / bursts [/ people clusters]
  → GPS-Cluster → Regionen + Transit
  → Kandidaten (technisch beste × Faktor; ohne finger_on_lens)
  → [optional AI-Szenen/Ästhetik]
  → finale Auswahl (~target_n; Vielfalt + Coverage + People + Food)
  → [optional Karten-Vorschau]
  → Export: CSV + selected/ + optional_dokumente/ + Markdown
  → [optional Thumbnail-Review → Re-Export]
```

---

*Stand: Branch mit Review, Face-Qualität, Bursts, Dokument-Pool, Coverage, People-Balance, Map-Preview, Finger-Filter. Primäre Doku für Nutzer: `ANLEITUNG.md`.*
