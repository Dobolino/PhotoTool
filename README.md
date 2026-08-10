# Photobook Curator

Lokales Python-CLI-Tool zur Kuratierung eines Urlaubs-Fotobuchs aus einer großen iPhone/iCloud-Fotosammlung.

**Einstieg:** siehe [ANLEITUNG.md](ANLEITUNG.md). Unter Windows am einfachsten: `Fotobuch starten.bat` doppelklicken (Fenster-Oberfläche).

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
