# Photobook Curator

Lokales Python-CLI-Tool zur Kuratierung eines Urlaubs-Fotobuchs aus einer großen iPhone/iCloud-Fotosammlung.

**Einstieg:** siehe [ANLEITUNG.md](ANLEITUNG.md). Unter Windows am einfachsten: `Fotobuch starten.bat` doppelklicken (Fenster-Oberfläche).

## Windows-Programm und Updates

GitHub Actions baut einen Installer `PhotoTool-Setup-<Version>.exe` und ein
portables ZIP. Veröffentlichte Versionen stehen unter
[Releases](https://github.com/Dobolino/PhotoTool/releases). Der Installer richtet
PhotoTool ohne Python-Installation im Benutzerprofil ein (Startmenü und Deinstallation).
Im Hauptfenster prüft **Updates** auf neue stabile Releases. Download und Installation
starten nach Bestätigung; der Download wird gegen den SHA256-Wert von GitHub geprüft.
Während einer Analyse wird keine Installation gestartet. Beim Update werden offene
Review-Entwürfe gesichert und PhotoTool anschliessend neu gestartet.
In Python-Entwicklungsstarts öffnet die Schaltfläche die Release-Seite.

## Nachkontrolle

- **Favoriten schützen:** Rechtsklick auf ein Bild → ★ Favorit schützen; in der
  Diashow über die Schaltfläche. Geschützte Bilder können erst nach Aufheben des
  Schutzes entfernt oder ersetzt werden. Sie bleiben beim Neuerstellen der Auswahl
  und bei erneuter Analyse derselben Dateipfade im selben Ausgabeordner erhalten.
  Übersteigt die Anzahl geschützter Bilder das Kontingent, hat der Schutz Vorrang.
- **Rückgängig / Wiederholen:** Schaltflächen oder Strg+Z / Strg+Y. Bis zu 100
  Änderungen dieser Sitzung, inklusive Kapitelwechsel, Ersatzbilder und Favoriten.
  Entwürfe speichern den aktuellen Zustand; die Undo-Historie gilt für die Sitzung.
- **Druckqualität:** gewünschte Bildgrösse in cm und Ziel-DPI eingeben (Standard
  15 × 10 cm / 300 DPI). Die Prüfung berücksichtigt Beschnitt und Drehung; unbekannte
  Bildmasse werden separat angezeigt. Ein CSV-Bericht kann gespeichert werden.
- **Auswahlgründe:** Rechtsklick oder Diashow-Schaltfläche. Zeigt vorhandene Scores,
  manuelle Entscheidungen, Schutz und Qualitäts-/Duplikathinweise. Der genaue
  automatische Rankingentscheid wird bisher nicht protokolliert.

Das Tool scannt Fotos, bewertet sie technisch, clustert GPS-Orte zu Regionen (Kapiteln), erkennt Transit-Abschnitte zwischen Städten, trennt Essens-Fotos ans Kapitelende und wählt eine diverse, chronologische Bildauswahl.

## Anforderungen

- Python 3.11+
- Optional: `GEMINI_API_KEY` für `--ai-review --ai-provider gemini` (Free Tier)
- Optional: `ANTHROPIC_API_KEY` für `--ai-review --ai-provider anthropic`
- Optional: lokales [Ollama](https://ollama.com) mit Vision-Modell (z. B. `ollama pull llava`)
- Netzwerk nur für Nominatim (Reverse Geocoding) und optional Gemini/Anthropic

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Schnellstart

```bash
# Beispieldatensatz erzeugen
python scripts/create_sample_dataset.py

# Pipeline ohne Geocoding/AI (offline-tauglich)
python -m photobook_curator \
  -i sample_photos \
  -o output_sample \
  -n 20 \
  --no-geocode \
  --skip-faces

# Mit Reverse Geocoding
python -m photobook_curator -i sample_photos -o output_sample -n 20 --geocode

# AI-Review Trockenlauf (Kostenschätzung, Anthropic)
python -m photobook_curator -i sample_photos -o output_sample -n 20 \
  --ai-review --ai-provider anthropic --dry-run --no-geocode

# Gemini Free Tier (GEMINI_API_KEY setzen)
python -m photobook_curator -i sample_photos -o output_sample -n 20 \
  --ai-provider gemini --no-geocode

# Gratis KI lokal (Ollama muss laufen, z. B. Modell llava)
python -m photobook_curator -i sample_photos -o output_sample -n 20 \
  --ai-provider ollama --no-geocode
```

## Wichtige CLI-Parameter

| Parameter | Beschreibung | Standard |
|-----------|--------------|----------|
| `-i/--input` | Eingabeordner | Pflicht |
| `-o/--output` | Ausgabeordner | Pflicht |
| `-n/--target-count` | Zielanzahl Bilder | 80 |
| `-k/--candidate-factor` | Kandidatenfaktor | 4 |
| `--geocode` / `--no-geocode` | Nominatim Reverse Geocoding | an |
| `--ai-review` | KI an (ohne Provider → Gemini) | aus |
| `--ai-provider` | `none` / `gemini` / `anthropic` / `ollama` | none |
| `--ai-model` | Optionales Modell | Provider-Default |
| `--dry-run` | Nur Kostenschätzung / Kandidaten zählen | aus |
| `--food-ratio` | Max. Essens-Anteil pro Region | 0.15 |
| `--max-landmarks` | Max. Landmark-Bilder / Region | 3 |
| `--min-transit-photos` | Min. Fotos für Transit-Abschnitt | 3 |
| `--similarity-threshold` | Diversitätsfilter | 0.92 |

## Ausgabe

- `photos_analysis.csv` – eine Zeile pro Bild mit allen Scores und Flags
- `selected/` – Kopien der Auswahl, Unterordner `01_Region/hauptteil`, `01_Region/essen`, `01b_Transit_A-B`
- `inhaltsverzeichnis.md` – kurze Kapitelübersicht
- `geocode_cache.json` – lokaler Nominatim-Cache

## Phasen

1. Scan, EXIF, Schärfe/Belichtung, Duplikate (pHash), Gesichter, technischer Score
2. DBSCAN-GPS-Cluster, Reverse Geocoding, Regionen chronologisch
3. Transit zwischen Regionen
4. Optional: Gemini 1.5 Flash, Anthropic Vision oder lokale Ollama
5. Kontingente, Essens-Trennung, Vielfalt, Buchreihenfolge, Export
