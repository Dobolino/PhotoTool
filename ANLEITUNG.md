# Schritt-für-Schritt: Fotobuch auswählen

Du brauchst: einen Computer mit Python 3.11+, deine Urlaubsfotos in einem Ordner, optional einen Anthropic-API-Key (nur für KI-Bewertung).

---

## 1. Projekt holen

Falls noch nicht geschehen: dieses Repository klonen und in den Ordner wechseln.

```bash
git clone https://github.com/Dobolino/PhotoTool.git
cd PhotoTool
```

Wenn du den Pull Request nutzt:

```bash
git checkout cursor/photobook-curator-c6d6
```

---

## 2. Python-Umgebung einrichten (einmalig)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Unter Windows statt `source .venv/bin/activate`:

```bash
.venv\Scripts\activate
```

Ab jetzt immer zuerst die Umgebung aktivieren (`source .venv/bin/activate`), bevor du Befehle ausführst.

---

## 3. Fotos bereitlegen

Lege deine iPhone-/Urlaubsfotos in einen Ordner, z. B.:

```text
/Users/DU/Urlaubsfotos/
```

Unterordner sind ok — das Tool sucht rekursiv nach `.jpg`, `.jpeg`, `.png`, `.heic`.

---

## 4. Optional: kurz mit Beispieldaten testen

Nur zum Ausprobieren, nicht mit deinen echten Fotos nötig:

```bash
python scripts/create_sample_dataset.py
python -m photobook_curator -i sample_photos -o output_sample -n 20 --no-geocode
```

Danach findest du unter `output_sample/`:
- `selected/` — ausgewählte Bilder
- `photos_analysis.csv` — alle Bewertungen
- `inhaltsverzeichnis.md` — Kapitelübersicht

---

## 5. Ersten echten Lauf starten (ohne KI)

Ersetze die Pfade durch deine:

```bash
source .venv/bin/activate

python -m photobook_curator \
  -i /Users/DU/Urlaubsfotos \
  -o /Users/DU/Fotobuch_Ausgabe \
  -n 80
```

Bedeutung:
- `-i` = Ordner mit deinen Fotos
- `-o` = neuer Ausgabeordner
- `-n 80` = ca. 80 Bilder im Buch (Zahl nach Bedarf ändern)

Das Tool:
- filtert unscharfe/doppelte Fotos
- baut Kapitel nach Städten
- erkennt Zug-/Auto-/Flug-Abschnitte dazwischen
- legt Essensfotos ans Ende jedes Kapitels

**Dauer:** bei mehreren tausend Fotos kann das eine Weile dauern. Fortschrittsbalken zeigt den Stand.

---

## 6. Ergebnis anschauen

Im Ausgabeordner:

| Datei / Ordner | Inhalt |
|----------------|--------|
| `selected/` | Die finalen Bilder, sortiert nach Kapiteln |
| `01_Paris/hauptteil/` | Hauptteil einer Region |
| `01_Paris/essen/` | Essensfotos dieser Region |
| `01b_Transit_Paris-Lyon/` | Fotos der Reise dazwischen |
| `inhaltsverzeichnis.md` | Kurze Übersicht pro Kapitel |
| `photos_analysis.csv` | Alle Fotos mit Scores (auch nicht ausgewählte) |

Öffne `inhaltsverzeichnis.md` und blättere durch `selected/`. Wenn dir zu wenig/zu viele Bilder gefallen: Schritt 5 mit anderem `-n` wiederholen.

---

## 7. Optional: KI-Bewertung mit Anthropic

Ein Claude-Chat-Abo reicht dafür **nicht**. Du brauchst einen API-Key:

1. Gehe zu [https://console.anthropic.com/](https://console.anthropic.com/)
2. Einloggen / Account anlegen
3. Zahlungsmittel hinterlegen (API wird getrennt abgerechnet)
4. API-Key erzeugen und kopieren

Dann im Terminal (Key nicht ins Repo legen):

**macOS / Linux:**
```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY='sk-ant-...'
```

Zuerst Kosten schätzen:

```bash
python -m photobook_curator \
  -i /Users/DU/Urlaubsfotos \
  -o /Users/DU/Fotobuch_Ausgabe \
  -n 80 \
  --ai-review \
  --dry-run
```

Wenn die Schätzung ok ist, denselben Befehl **ohne** `--dry-run` ausführen:

```bash
python -m photobook_curator \
  -i /Users/DU/Urlaubsfotos \
  -o /Users/DU/Fotobuch_Ausgabe \
  -n 80 \
  --ai-review
```

Die KI bewertet nur Kandidaten (nicht alle tausende Fotos), erkennt besser Essen/Sehenswürdigkeiten und stuft Bildqualität fürs Buch ein.

---

## 8. Nützliche Knöpfe (bei Bedarf)

| Parameter | Wann nutzen |
|-----------|-------------|
| `-n 120` | Mehr Bilder im Buch |
| `-n 40` | Kürzeres Buch |
| `--no-geocode` | Ohne Internet / ohne Ortsnamen von Nominatim |
| `--food-ratio 0.1` | Weniger Essensfotos (10 %) |
| `--max-landmarks 2` | Weniger „Postkarten“-Motive pro Stadt |
| `--min-transit-photos 5` | Transit-Kapitel erst ab 5 Fotos |
| `--skip-faces` | Schneller, ohne Gesichtserkennung |

Alle Optionen:

```bash
python -m photobook_curator --help
```

---

## Checkliste

1. [ ] Repo geklont, Branch ausgecheckt  
2. [ ] `.venv` erstellt und Dependencies installiert  
3. [ ] Foto-Ordner bereit  
4. [ ] Ersten Lauf mit `-i`, `-o`, `-n` gestartet  
5. [ ] `selected/` und `inhaltsverzeichnis.md` geprüft  
6. [ ] (Optional) Anthropic-API-Key gesetzt und `--ai-review` genutzt  
7. [ ] Bilder aus `selected/` ins Fotobuch-Tool deiner Wahl übernehmen  

Fertig — ab hier gestaltest du das Buch mit den ausgewählten Dateien.
