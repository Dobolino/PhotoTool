# Code-Review & Architektur-Analyse – Photobook Curator (PhotoTool)

*Erstellt als Senior-Software-Architect-/Lead-Python-Review auf Basis der kompletten Codebasis (Stand Branch `claude/phototool-review-architecture-4dmy9u`) und `PROGRAMMBESCHREIBUNG.md`.*

> **Hinweis zum Umfang:** In diesem Repo ist die **Build-/Packaging-Pipeline tatsächlich implementiert** (siehe `packaging/` und Abschnitt 7). Bugfixes, Heuristik- und UI-Vorschläge sind als konkrete, direkt anwendbare Code-Beispiele dokumentiert, aber bewusst **nicht** in die Kern-Logik committet, weil in dieser Umgebung keine Laufzeit-Dependencies (`opencv`, `mediapipe`, `Pillow`, `sklearn`) installiert sind und Änderungen am Happy Path daher nicht per Testlauf abgesichert werden konnten. Jede Empfehlung ist so formuliert, dass sie mit laufendem `pytest` gefahrlos übernommen werden kann.

---

## 0. Gesamtbild

Die Architektur ist **sauber geschnitten**: klar getrennte Phasen (`scan → quality → dupes/faces/finger/people → regions → transit → selection → output`), ein zentrales `Photo`-Datenmodell, Feature-Flags in `PipelineConfig`, und optionale Features sind konsequent hinter Flags gelegt. Fallbacks (MediaPipe → Haar → none) existieren durchgängig und werfen keine Exceptions. Das ist für ein Hobby-/Prosumer-Tool bereits überdurchschnittlich.

Die drei größten Hebel:

1. **Performance:** Jedes Bild wird pro Lauf **5–8× komplett von der Platte dekodiert** (besonders teuer bei HEIC). Ein gemeinsamer Decode-/Downscale-Cache halbiert bis drittelt die Laufzeit sofort. Zusätzlich sind Duplikat- und Personen-Erkennung O(n²) mit wiederholtem Hash-Parsing.
2. **Korrektheit:** Fehlende **EXIF-Orientierung** verfälscht Analyse (Gesichter, Screenshot-Ratio) und Thumbnails bei allen hochkant/gedreht aufgenommenen iPhone-Fotos.
3. **UX/Distribution:** Tkinter ist funktional, aber optisch veraltet; der Start über `.bat`+`venv` ist für Nicht-Techniker fragil. Ein Standalone-Executable (PyInstaller) beseitigt Python-/venv-Setup vollständig.

Bewertung nach Bereich:

| Bereich | Status |
|---|---|
| Architektur & Modultrennung | ✅ sehr gut |
| Optionale Features abschaltbar | ✅ konsequent |
| CSV ↔ `Photo` ↔ Import Synchronität | 🟡 korrekt, aber fragil (dreifach manuell gepflegt) |
| Performance Bildpipeline | 🔴 großes Optimierungspotenzial |
| Robustheit bei Netzwerk-/Modellfehlern | 🟡 gut, aber Downloads ohne Timeout |
| EXIF-Orientierung | 🔴 fehlt (Korrektheitsproblem) |
| UI/UX | 🟡 funktional, optisch ausbaufähig |
| Installation für Endnutzer | 🔴 venv/Python-Setup nötig → Pipeline ergänzt |

---

## 1. Bugs, Logik- & Korrektheitsfehler

### 1.1 🔴 EXIF-Orientierung wird nie angewendet (`utils.py:49`)

`load_image()` öffnet das Bild ohne `ImageOps.exif_transpose`. Hochkant-/gedrehte iPhone-Fotos (die überwiegende Mehrheit) werden dadurch **quer** analysiert und angezeigt. Folgen:

- **Gesichtserkennung** (MediaPipe/Haar) verliert Trefferrate auf gedrehten Bildern.
- `face_cut_off`/`face_too_small` (Randabstände) rechnen mit falschen Breiten/Höhen.
- `looks_like_screenshot`/`_looks_like_phone_ui` prüfen ein falsches Seitenverhältnis.
- **Review-Thumbnails** und **Map-Preview** zeigen Bilder seitlich.

Der Export selbst (`shutil.copy2`) kopiert die Originaldatei inkl. Orientation-Tag – dort ist es egal. Das Problem betrifft ausschließlich **Analyse & Anzeige**.

```python
# utils.py
from PIL import Image, ImageOps

def load_image(path: Path) -> Image.Image:
    register_heif()
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)   # <-- Orientierung anwenden
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    return img
```

> Nebeneffekt beachten: In `scan.extract_exif` werden `width/height` aus `img.size` gelesen – nach `exif_transpose` sind das die **angezeigten** Maße (gut, konsistent mit der Analyse).

### 1.2 🟠 Transiente Geocoding-Fehler vergiften den Cache dauerhaft (`geocoding.py:107`)

```python
except (GeocoderTimedOut, GeocoderServiceError, Exception):
    self._cache[key] = empty      # <-- wird gespeichert
    return empty
```

Ein **temporärer** Netzwerkfehler (Timeout, 5xx, DNS) wird als `empty` in den Cache geschrieben und via `cache.save()` **persistiert**. Beim nächsten Lauf wird dieselbe Koordinate nie wieder aufgelöst → Regionen bleiben dauerhaft „Transit/Unbestimmt“. „No result“ (echtes `loc is None`) und „Fehler“ müssen unterschieden werden – Fehler dürfen nicht persistiert werden:

```python
try:
    loc = self._geocoder.reverse((lat, lon), language="de", exactly_one=True)
except (GeocoderTimedOut, GeocoderServiceError) as exc:
    # transienter Fehler: NICHT cachen, damit ein Folgelauf erneut versucht
    return empty
except Exception:
    return empty

if loc is None:
    self._cache[key] = empty   # echtes „kein Ort“ – cachebar
    return empty
```

Zusätzlich: `except (..., Exception)` fängt alles inkl. bewusst nicht abgefangener Fehler; die spezifischen Klassen davor sind dadurch wirkungslos (Code-Smell).

### 1.3 🟠 Modell-Downloads ohne Timeout können die Pipeline aufhängen (`faces.py:29`, `face_quality.py:59`, `finger_obstruction.py:33`, `people_balance.py:33`)

`urlretrieve(url, path)` hat **keinen** Timeout. Auf einem Netz, das Verbindungen offen hält aber keine Daten liefert, blockiert der komplette Lauf unbegrenzt – das widerspricht dem Anspruch „stabile Fallbacks bei Netzwerkfehlern“. Fix (global, minimal-invasiv):

```python
import socket
from urllib.request import urlretrieve

def _download(url: str, dest: Path, timeout: float = 30.0) -> bool:
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        urlretrieve(url, dest)
        return dest.stat().st_size > 1000
    except Exception:
        dest.unlink(missing_ok=True)
        return False
    finally:
        socket.setdefaulttimeout(old)
```

### 1.4 🟡 Inkonsistente Download-Validierung (`faces.py` / `people_balance.py`)

`face_quality._ensure_landmarker_model` und `finger_obstruction._ensure_hand_model` prüfen **nach** dem Download `st_size < 1000` und verwerfen abgeschnittene Dateien. `faces._ensure_mp_model` und `people_balance._ensure_detector_model` tun das **nicht** – eine unvollständig heruntergeladene `.tflite` bleibt liegen und lässt MediaPipe beim nächsten Lauf hart scheitern (fällt dann still auf Haar/none zurück, aber ohne Grund). Beim Vereinheitlichen über den `_download`-Helper aus 1.3 gelöst.

### 1.5 🟡 Finger-Penalty wird außerhalb von `compute_technical_score` gesetzt (`finger_obstruction.py:202`)

`apply_finger_obstruction` zieht `technical_score -= 50` direkt ab. Wird danach für dasselbe Foto `compute_technical_score()` erneut aufgerufen (z. B. wenn ein Finger-Foto zusätzlich `is_burst_reject` wird, `bursts.py:121`), geht der Abzug verloren, weil `compute_technical_score` `finger_on_lens` nicht kennt. Praktisch unkritisch (Finger-Fotos werden ohnehin aus Kandidaten/Auswahl ausgeschlossen), aber fragil. Sauberer: `finger_on_lens` als Abzug **in** `compute_technical_score` aufnehmen und aus `apply_finger_obstruction` nur das Flag setzen + `compute_technical_score` aufrufen.

### 1.6 🟡 Haar-Fallback erzeugt viele „Augen zu“-Falschpositive (`face_quality.py:255`)

```python
if len(eyes) == 0 and fh > 80:
    any_closed = True     # → Score −35
```

Der OpenCV-Augen-Cascade ist unzuverlässig (Brillen, Seitenprofile, Schatten). „Keine Augen gefunden“ als „Augen geschlossen“ zu werten, bestraft im MediaPipe-losen Fallback viele **gute** Fotos hart. Empfehlung: Im Haar-Modus `eyes_closed` **nicht** setzen (nur `face_cut_off`/`face_too_small` sind dort robust genug) oder den Abzug im Haar-Modus deutlich reduzieren.

### 1.7 🟢 Toter Code in `distribute_quotas` (`selection.py:60`)

```python
transit_total = sum(min(max_transit_quota, max(1, t.quota or max_transit_quota)) for t in plan.transits)
# ... direkt darunter wird t.quota neu gesetzt und transit_total überschrieben:
transit_total = sum(t.quota for t in plan.transits)
```

Die erste Zeile ist wirkungslos (Ergebnis wird sofort überschrieben) – löschen.

### 1.8 🟢 `models.py`: `asdict` importiert, nie benutzt (`models.py:5`). Lint-Rauschen.

---

## 2. Performance & Memory (OpenCV/Pillow)

### 2.1 🔴 Mehrfaches Dekodieren jedes Bildes

Ein einzelnes Foto wird pro Standard-Lauf in **mehreren** Modulen unabhängig neu geladen und nach BGR konvertiert:

| Modul | Ladeaufruf |
|---|---|
| `scan.extract_exif` | `load_image` (nur für `width/height`) |
| `quality.analyze_image_quality` | `load_image` + `to_cv_bgr` |
| `documents.mark_aside_documents` | ggf. `load_image` + `to_cv_bgr` |
| `duplicates.compute_phashes` | `load_image` |
| `faces.count_faces` | `load_image` + `to_cv_bgr` |
| `face_quality.analyze_face_quality` | `load_image` + `to_cv_bgr` |
| `finger_obstruction` (optional) | `load_image` + `to_cv_bgr` |
| `people_balance` (optional) | `load_image` + `to_cv_bgr` |
| `selection.color_histogram` | `load_image` (mehrfach pro Kandidat!) |
| `ai_review.image_to_jpeg_b64` | `load_image` |

Bei HEIC ist der Decode der mit Abstand teuerste Schritt. **Empfehlungen (nach Wirkung):**

1. **Gemeinsamer, größenbegrenzter Decode-Cache.** Ein `functools.lru_cache`-basierter Loader, der ein herunterskaliertes BGR-Array (z. B. max. Kante 1024 px) zurückgibt, deckt Quality/Documents/Faces/FaceQuality/Finger/People ab. Für die technische Analyse (Schärfe/Belichtung) reicht die verkleinerte Version völlig; nur pHash und AI-Encoding wollen ggf. mehr.

   ```python
   # utils.py
   from functools import lru_cache

   @lru_cache(maxsize=64)
   def load_bgr_cached(path_str: str, max_edge: int = 1024) -> "np.ndarray":
       img = resize_max_edge(load_image(Path(path_str)), max_edge)
       return to_cv_bgr(img)
   ```
   Da die Phasen sequentiell über dieselbe Fotoliste laufen, genügt bereits ein **kleiner** Cache (z. B. 8–64 Einträge) oder – noch besser – eine Umstellung auf **eine** Analyse-Schleife pro Bild (siehe 2.2).

2. **`extract_exif` sollte das Bild nicht komplett dekodieren, nur um `width/height` zu bekommen.** `Image.open(path)` liefert `.size` **ohne** `.load()` (kein voller Decode) für JPEG/PNG. Für HEIC ist der Header-Read via `pillow-heif` ebenfalls günstiger als der volle Decode.

3. **`color_histogram` auf verkleinerter Kopie rechnen** und pro Foto **einmal** cachen (aktuell wird das Histogramm in jedem `_select_diverse`-Aufruf neu berechnet – bei aktivierter Tages-Abdeckung mehrfach pro Foto).

### 2.2 🟠 Architektur-Empfehlung: „One decode per photo"

Statt N Phasen, die je über die volle Fotoliste iterieren und je neu laden, ein **Analyzer-Pass** pro Bild, der Decode-Ergebnisse teilt:

```python
def analyze_photo(photo, backends):
    bgr = to_cv_bgr(load_image(photo.path))     # genau EIN Decode
    quality(photo, bgr)
    if backends.faces:      faces(photo, bgr)
    if backends.finger:     finger(photo, bgr)
    ...
```

Das reduziert Decodes von ~6–8 auf **1** pro Bild und ermöglicht später einfaches `ProcessPoolExecutor`-Parallelisieren (CPU-gebunden – echter Speedup, anders als bei Threads).

### 2.3 🟠 O(n²)-Duplikaterkennung mit wiederholtem Hash-Parsing (`duplicates.py:84`)

```python
for idx_a, (i, a) in enumerate(indexed):
    for j, b in indexed[idx_a+1:]:
        if _hamming(a.phash, b.phash) <= hash_threshold ...
```

`_hamming` ruft pro Vergleich `imagehash.hex_to_hash(...)` **zweimal** auf – bei 3000 Fotos sind das ~4,5 Mio. Vergleiche mit je zwei Hex-Parses. Zwei Optimierungen:

1. pHash **einmal** in ein `numpy`-Bit-Array / int vorwandeln und XOR-popcount rechnen (Faktor 10–50).
2. Kandidatenpaare über **Zeitfenster** vorfiltern (wie `bursts.py` es bereits tut): Duplikate liegen praktisch immer zeitnah beieinander. Das senkt die Komplexität von O(n²) auf ~O(n·k).

### 2.4 🟡 Personen-Clustering O(m²) (`people_balance.py:164`)

Alle Gesichts-Signaturen paarweise vergleichen. Bei vielen Personenfotos teuer. Gleiche Abhilfe: int-Hashes + optional BK-Tree/Buckets. Zusätzlich in `PROGRAMMBESCHREIBUNG.md` bereits als Fallstrick notiert.

### 2.5 🟡 `mark_bursts` prüft nur 40 Vorgänger (`bursts.py:91`)

`timed[max(0, pos-40):pos]` – eine sehr lange, dichte Serie (>40 Aufnahmen in 30 s, z. B. Serienbild-Modus) kann in mehrere Bursts zerfallen. Das reine Zeitfenster (`t_a - t_b > window: continue`) ist bereits ausreichend als Grenze; die feste `40` kann entfallen oder über `burst_max_seconds`/Aufnahmefrequenz dynamisch gewählt werden.

### 2.6 Memory: PIL-Handles

`load_image` ruft `img.load()` (schließt den Datei-Handle für die meisten Formate). Keine Leaks erkennbar. Bei Umstellung auf einen Cache darauf achten, große Arrays nicht unbegrenzt zu halten (`maxsize` setzen). In `review_gui` wächst `_photo_images` nur um eindeutige Thumbnails (durch `_thumb_cache` begrenzt) – ok.

---

## 3. Robustheit, Edge Cases & Fallbacks

### 3.1 ✅ Optionale Features sauber abschaltbar

Positiv bestätigt: Bei `enable_faces=False` etc. werden die Phasen komplett übersprungen, Default-Werte im `Photo`-Modell (`face_count=0`, `bad_face=False`, `person_cluster_ids=[]`) halten den Happy Path stabil. `finger`/`coverage`/`people`/`map-preview` sind default-off. `_ok()`/`mark_candidates` schließen `is_duplicate`/`is_burst_reject`/`is_aside`/`finger_on_lens` konsequent aus. **Kein Handlungsbedarf** – nur durch Tests absichern (siehe 8).

### 3.2 🟡 MediaPipe-/Modell-Fallbacks

Fallback-Kette funktioniert ohne Crash. Offene Punkte:
- Download-Timeout (1.3) und Größenprüfung (1.4).
- Wenn **kein** Face-Detector verfügbar ist (`FaceCropper` mode `none`), liefert People-Balance stille `[]`-Cluster → Balance wirkungslos. Das ist korrektes Verhalten, aber der Nutzer erhält keinen Hinweis. Empfehlung: einmalige Warnung ins Log („Personen-Balance ohne MediaPipe-Detector wirkungslos“).

### 3.3 🟡 GUI-Deferred-Export

Der Abbruch-Pfad (`_cancel_export_after_preview`) schreibt kein `selected/` – korrekt. Die CSV bleibt (gewollt). `write_chapter_map` wird jedoch **doppelt** ausgeführt (einmal in der Pipeline bei `skip_export`, einmal in `MapPreviewWindow.__init__`) – harmlos, aber unnötige IO. Beim Deferred-Pfad die Pipeline-seitige Karte weglassen und nur das Vorschaufenster schreiben lassen.

### 3.4 🟡 Fehlende/kaputte EXIF-Zeit

Fotos ohne `datetime_taken` fallen in `Unbestimmt` und damit aus dem Buchkontingent (`regions.assign_photos_without_gps`). Bei iCloud-Exporten ohne EXIF (z. B. bearbeitete Bilder) kann das viele Fotos betreffen. Optional: Fallback auf Datei-`mtime`/`birthtime` als grobe Zeitquelle.

### 3.5 🟡 Screenshot-Heuristik zu strikt an Auflösungsliste gebunden

`looks_like_screenshot` triggert nur bei exakter Auflösung **und** fehlendem Kameramodell. Neue iPhone-Modelle/zugeschnittene Screenshots fehlen. `documents._looks_like_phone_ui` fängt über das Seitenverhältnis (≥1.9) mehr ab – gut. Empfehlung: Auflösungsliste durch die **Ratio-Heuristik als Primärsignal** ergänzen (Auflösungsliste als schneller Sonderfall behalten).

### 3.6 🟢 `_review_one` (AI): Exceptions gefangen, Lauf läuft weiter, Flag gesetzt. ✅ Robust.

---

## 4. Synchronität CSV ↔ `Photo` ↔ Import/Export

**Ergebnis: aktuell konsistent, aber strukturell fragil.**

`CSV_FIELDS` (`output.py:13`), `Photo.to_csv_row()` (`models.py:101`) und `load_photos_from_csv` (`review_export.py:175`) sind an drei Stellen **manuell** gepflegt. Sie stimmen momentan überein, aber jede neue Spalte muss an drei Orten synchron nachgezogen werden – klassische Quelle für Drift.

Beobachtungen:
- `load_photos_from_csv` liest bewusst nicht alle Felder zurück (z. B. `country`, `place_label`, `fine_cluster_id`, `is_screenshot`-Restore ist da, `mood` da). Für den Review-Zweck ausreichend.
- **Empfehlung (Härtung):** Einen Test ergänzen, der garantiert, dass `set(Photo(...).to_csv_row().keys()) == set(CSV_FIELDS)`. Das fängt Drift sofort:

```python
def test_csv_fields_match_row():
    p = Photo(path=Path("x.jpg"), filename="x.jpg")
    assert set(p.to_csv_row().keys()) == set(CSV_FIELDS)
```

- **Mittelfristig:** Die Feldliste aus einer einzigen Quelle ableiten (z. B. Dataclass-Feld-Metadaten oder ein `FIELD_SPEC`-Dict mit `{name: (getter, parser)}`), damit `to_csv_row`, `CSV_FIELDS` und Loader nicht divergieren können.

---

## 5. Funktionale Lücken & Heuristik-Optimierung

### 5.1 Fehlende Use-Cases / Features

| Lücke | Auswirkung | Empfehlung |
|---|---|---|
| **Keine Analyse-Persistenz** | Jeder Lauf re-scannt & re-analysiert alles neu (teuer bei großen Ordnern) | Analyse-Cache je Datei über `(path, mtime, size)`-Key (JSON/SQLite) → inkrementelle Läufe |
| **Kein Video/Live-Photo** | `.mov`-Teil von Live Photos wird ignoriert | Bewusst dokumentieren; optional Live-Photo-Standbild bevorzugen |
| **`target_n` nur ungefähr** | Nutzer erwartet ~exakte Zahl | Nach `build_book_order` global auf `target_n` trimmen/auffüllen |
| **Unassigned nie im Buch** | Fotos ohne Region/Zeit fallen raus | Optionales „Sonstiges“-Kapitel am Ende |
| **Keine Fortschrittsanzeige in GUI** | Nur Log-Text; wirkt „hängend“ | Progress-Callback statt `tqdm`→stdout (siehe 6) |
| **Kein Dedup Auswahl ↔ Aside** | – | Prüfen, aber aktuell kein konkreter Konflikt |
| **`burst_min_size` nicht in CLI** | Doku nennt es als Fallstrick | CLI-Flag ergänzen |

### 5.2 Heuristik-Zuverlässigkeit

- **Szenenerkennung ohne KI (`ai_review.heuristic_scene_type`)** ist stark dateiname-getrieben (iCloud-Dateien heißen `IMG_1234.HEIC` → greift kaum). Der Food-Split hängt daran → oft ungenau. Verbesserung ohne KI:
  - „essen“: warme Farbtemperatur + hohe Sättigung + Nahdistanz (kleine Schärfentiefe) + fehlende Gesichter → grobe, aber deutlich bessere Food-Erkennung als Dateiname.
  - „landschaft“: großer Himmel-/Grünanteil (HSV-Verteilung) + niedrige Gesichtszahl.
- **Dokumentenerkennung ohne OCR** (`documents.classify_document_image`) ist solide (Weißanteil/Sättigung/Kanten). False Positives bei sehr hellen, kontrastarmen echten Fotos möglich. Ein **leichtgewichtiger OCR-Gate** (nur wenn `is_aside` unsicher) mit `pytesseract` würde die Präzision spürbar heben – als optionale Dependency.
- **Finger-Filter**: Heuristik (weiche Hautfläche am Rand) ist bewusst default-off wegen False Positives. Zusatzsignal, das hilft: **stark defokussierter Randbereich bei gleichzeitig scharfem Zentrum** (Laplacian-Varianz Rand vs. Mitte) – ein Finger vor der Linse erzeugt genau dieses Muster. Ist teilweise via `softness` schon da; das Zentrum als Referenz explizit einzubeziehen reduziert Fehlalarme.
- **DBSCAN auf Roh-Lat/Lon** (`regions.cluster_fine_locations`) nutzt euklidische Distanz auf Grad; Längengrade schrumpfen mit dem Breitengrad (cos-Faktor). Für Europa/Japan (~35–52° N) verzerrt das Cluster ost-west um ~30–40 %. Besser: `metric="haversine"` mit `radians`-Koordinaten, oder lokale Längengrad-Korrektur `lon *= cos(mean_lat)`.

---

## 6. UI/UX-Modernisierung

Aktuell: klassisches Tkinter/`ttk` mit `clam`-Theme und Handpalette. Funktional und farblich bereits durchdacht (ruhige Foto-Editor-Palette), aber die Widgets wirken nach „Windows-Standard“. Zwei Ausbaustufen:

### 6.1 Schneller Gewinn (kein neues Framework)

- **Fortschritt sichtbar machen:** Pipeline sollte einen `progress_callback(stage, current, total)` bekommen statt nur nach stdout zu drucken. Damit ein echter `ttk.Progressbar` + Phasentext. Das behebt den „hängt es?“-Eindruck.
- **Thumbnail-Review flüssiger:** Aktuell rendert `_render()` bei **jedem** Klick alle Kacheln neu (`child.destroy()` + Neuaufbau). Bei 80+ Bildern spürbar träge. Fix: nur die betroffene Kachel umfärben (Border/Overlay togglen), nicht das ganze Grid neu bauen. Thumbnails zusätzlich **lazy** im Hintergrundthread laden (Platzhalter → nachladen), statt synchron beim Aufbau.

### 6.2 Optisches Redesign mit `customtkinter`

`customtkinter` bringt abgerundete Ecken, HighDPI, modernes Flat-Design und Dark-Mode – bei nahezu identischem API. Empfehlung: als **optionale** GUI (`gui_modern.py`) mit Fallback auf die bestehende, damit kein Zwang zur neuen Dependency entsteht.

```python
# gui_modern.py  (Skizze – optionaler moderner Ersatz für gui.py)
import customtkinter as ctk
from pathlib import Path
from .pipeline import PipelineConfig, run_pipeline

ctk.set_appearance_mode("system")      # light/dark folgt dem OS
ctk.set_default_color_theme("green")   # passt zur bestehenden Akzentfarbe #2F5D50

class PhotobookApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Fotobuch")
        self.geometry("860x760")
        self.grid_columnconfigure(0, weight=1)

        # Hero
        hero = ctk.CTkFrame(self, corner_radius=0, fg_color="#2F5D50")
        hero.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hero, text="Fotobuch",
                     font=ctk.CTkFont("Georgia", 26, "bold"),
                     text_color="#F7F3EC").pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(hero, text="Urlaubsfotos automatisch kuratieren",
                     text_color="#D5E4DE").pack(anchor="w", padx=24, pady=(0, 18))

        # Ordner-Karten
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        body.grid_columnconfigure(0, weight=1)

        self.input_var = ctk.StringVar()
        self.output_var = ctk.StringVar()
        self._folder_row(body, 0, "Fotos-Ordner", self.input_var)
        self._folder_row(body, 1, "Ausgabe-Ordner", self.output_var)

        # Zielanzahl als Slider + Live-Label
        self.target = ctk.IntVar(value=80)
        ctk.CTkLabel(body, text="Zielanzahl Bilder").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ctk.CTkSlider(body, from_=10, to=300, variable=self.target,
                      command=lambda v: self.target_lbl.configure(text=f"{int(float(v))}")
                      ).grid(row=3, column=0, sticky="ew")
        self.target_lbl = ctk.CTkLabel(body, text="80")
        self.target_lbl.grid(row=3, column=1, padx=(8, 0))

        # Optionen als Switches (statt Checkbuttons)
        opts = ctk.CTkFrame(body)
        opts.grid(row=4, column=0, columnspan=2, sticky="ew", pady=12)
        self.faces = ctk.BooleanVar(value=True)
        self.bursts = ctk.BooleanVar(value=True)
        for i, (txt, var) in enumerate([
                ("Gesichter / Augen zu", self.faces),
                ("Serien/Bursts", self.bursts)]):
            ctk.CTkSwitch(opts, text=txt, variable=var).grid(
                row=i, column=0, sticky="w", padx=12, pady=6)

        self.progress = ctk.CTkProgressBar(body)
        self.progress.set(0)
        self.progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        ctk.CTkButton(body, text="Auswahl starten", height=44,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=self._start).grid(row=6, column=0, columnspan=2,
                                                sticky="ew", pady=8)

    def _folder_row(self, parent, row, label, var):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, columnspan=2, sticky="ew", pady=6)
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f, textvariable=var, placeholder_text=label,
                     height=40).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(f, text="Durchsuchen", width=120,
                      command=lambda: self._pick(var)).grid(row=0, column=1, padx=(8, 0))

    def _pick(self, var):
        from tkinter import filedialog
        p = filedialog.askdirectory()
        if p: var.set(p)

    def _start(self):
        ...  # gleiche Worker-Thread-Logik wie gui.py, plus self.progress.set(...)
```

**UX-Fluss (Ordnerwahl → Export) verbessern:**
1. **Ein-Fenster-Wizard** statt vieler Checkboxen untereinander: Schritt 1 Ordner, Schritt 2 Optionen (mit sinnvollen Defaults eingeklappt unter „Erweitert“), Schritt 3 Ergebnis.
2. **Sofort-Feedback** bei Ordnerwahl: Anzahl gefundener Bilder anzeigen (kurzer Vorab-`find_images`), damit der Nutzer Zielanzahl realistisch setzt.
3. **Zielanzahl als Slider** mit Live-Wert (siehe oben) statt Spinbox – haptischer.
4. **Nach dem Lauf** direkt große Ergebnis-Kacheln + „Auswahl prüfen“/„Ordner öffnen“ als primäre Aktionen.
5. **Drag & Drop** von Ordnern (via `tkinterdnd2`) als Komfort.

---

## 7. Installation, Download & Start – umgesetzte Pipeline

**Ziel:** Endnutzer sollen **kein** Python/venv installieren müssen. Umgesetzt ist in `packaging/` eine PyInstaller-basierte Windows-first-Pipeline (siehe `packaging/README.md`).

### 7.1 Warum PyInstaller (nicht Nuitka) als Default

- **PyInstaller** hat robuste, dokumentierte Collect-Hooks für die kritischen Pakete hier (`mediapipe`, `pillow_heif`, `opencv`, `sklearn`) und produziert zuverlässig ein `--onedir`-Bundle. Nuitka erzeugt kleinere/schnellere Binaries, ist aber bei nativen ML-Paketen (MediaPipe-`.task`/`.tflite`, protobuf, OpenCV-DLLs) deutlich fummeliger. Empfehlung: **PyInstaller als Haupt-Pipeline**, Nuitka optional für später.
- **`--onedir` statt `--onefile`:** onefile entpackt bei jedem Start in ein Temp-Verzeichnis (langsamer Start, Virenscanner-Probleme). Für ein Tool mit großen ML-Libs ist onedir + ZIP der bessere Kompromiss.

### 7.2 Enthaltene Artefakte (`packaging/`)

- `photobook.spec` – PyInstaller-Spec inkl. `collect_all` für `mediapipe`, `pillow_heif`, `cv2`, `sklearn`; GUI-Entry (`--windowed`).
- `build_windows.bat` – Ein-Klick-Build unter Windows (venv anlegen, deps + PyInstaller installieren, Spec bauen).
- `build.py` – plattformneutraler Build-Treiber (ruft PyInstaller mit der Spec).
- `hooks/` – Runtime-Hooks, u. a. Setzen eines beschreibbaren Modell-Cache-Pfads.
- `requirements-build.txt` – `-r ../requirements.txt` + `pyinstaller`.
- `README.md` – Schritt-für-Schritt für Maintainer + Hinweise zu Code-Signing.

### 7.3 Modelle & Cache im Bundle

MediaPipe lädt `.tflite`/`.task` aktuell zur Laufzeit nach `~/.cache/photobook_curator/`. Zwei Optionen, beide in der Pipeline vorgesehen:
1. **Vorab bündeln** (empfohlen für Offline-Fähigkeit): Modelle in `packaging/models/` legen und via Spec-`datas` mitliefern; der Runtime-Hook zeigt den Cache-Pfad auf dieses Bundle-Verzeichnis (read-only) bzw. kopiert bei Bedarf in einen beschreibbaren User-Pfad.
2. **Lazy-Download beibehalten** (kleineres Bundle): funktioniert, braucht aber beim ersten Start Internet → mit Download-Timeout aus 1.3 absichern.

### 7.4 Distribution für Nicht-Techniker

- Ergebnis: `dist/Fotobuch/Fotobuch.exe` → als **ZIP** oder mit **Inno Setup** zu einem Installer bündeln (Startmenü-Eintrag, Deinstallation).
- **Code-Signing** (Windows SmartScreen) dringend empfohlen, sonst Warnhinweis beim ersten Start – in der README dokumentiert.
- macOS analog via `--windowed` + `.app` + `codesign`/Notarisierung (zweite Ausbaustufe).

---

## 8. Tests – Ergänzungsvorschläge

Die vorhandene Test-Suite deckt die Kern-Logik gut ab. Für die obigen Änderungen ergänzen:

- `test_csv_fields_match_row` (Abschnitt 4) – Drift-Schutz.
- EXIF-Orientierung: Bild mit Orientation-Tag laden, prüfen dass `size` gedreht ist.
- Geocode-Cache: transienter Fehler wird **nicht** persistiert, echtes „kein Ort“ schon.
- Selection-Invarianten: `finger_on_lens`/`is_aside`/`is_burst_reject` erscheinen nie in `order`.
- Kapitelreihenfolge Region→Essen→Transit bleibt chronologisch & stabil (Regressionstest über `build_book_order`).

---

## 9. Priorisierte Roadmap

**P0 – Korrektheit/Stabilität (klein, hohe Wirkung)**
1. EXIF-Orientierung in `load_image` (1.1)
2. Download-Timeout für Modelle (1.3) + einheitliche Größenprüfung (1.4)
3. Geocode-Cache: transiente Fehler nicht persistieren (1.2)
4. `test_csv_fields_match_row` als Drift-Schutz (4)

**P1 – Performance**
5. Gemeinsamer Decode-Cache / „one decode per photo“ (2.1/2.2)
6. int-basierte Hashes + Zeitfenster-Vorfilter für Duplikate (2.3)
7. Histogramm cachen + verkleinert rechnen (2.1.3)

**P2 – Distribution & UX**
8. PyInstaller-Build finalisieren & signieren (7) – *Pipeline liegt vor*
9. Fortschritts-Callback + flüssigeres Thumbnail-Review (6.1)
10. `customtkinter`-GUI als optionaler moderner Aufsatz (6.2)

**P3 – Heuristik & Features**
11. Analyse-Persistenz (inkrementelle Läufe) (5.1)
12. Bessere Food-/Szenen-Heuristik ohne KI (5.2)
13. Haversine-DBSCAN (5.2)
14. Haar-„Augen zu“-Falschpositive entschärfen (1.6)

---

*Ende des Reviews. Konkrete Code-Snippets oben sind direkt anwendbar; empfohlen wird, P0-Änderungen mit laufendem `pytest` einzeln zu übernehmen.*
