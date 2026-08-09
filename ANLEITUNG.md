# Schritt-für-Schritt: Fotobuch auswählen

Du brauchst: einen Computer mit Python 3.11+, deine Urlaubsfotos in einem Ordner, optional einen Anthropic-API-Key (nur für KI-Bewertung).

Diese Anleitung ist für **Windows (PowerShell)** geschrieben. Am Ende gibt es kurz die macOS/Linux-Varianten.

---

## 1. Projekt holen

Öffne PowerShell und wechsle in den Ordner, in dem das Projekt liegen soll:

```powershell
cd $HOME\Downloads
git clone https://github.com/Dobolino/PhotoTool.git
cd PhotoTool
git checkout cursor/photobook-curator-c6d6
```

Falls du den Ordner schon hast (z. B. unter `Downloads\PhotoTool`):

```powershell
cd $HOME\Downloads\PhotoTool
git checkout cursor/photobook-curator-c6d6
```

---

## 2. Python-Umgebung einrichten (einmalig)

In PowerShell, im Projektordner:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Wichtig:** Unter Windows heißt der Befehl **nicht** `source`, sondern:

```powershell
.\.venv\Scripts\Activate.ps1
```

Wenn PowerShell meldet, dass Skripte nicht ausgeführt werden dürfen:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Danach nochmal `.\.venv\Scripts\Activate.ps1` ausführen.

Wenn die Umgebung aktiv ist, steht vor dem Prompt oft `(.venv)`.

In **cmd.exe** (nicht PowerShell) wäre es:

```bat
.venv\Scripts\activate.bat
```

---

## 3. Fotos bereitlegen

Lege deine iPhone-/Urlaubsfotos in einen Ordner, z. B.:

```text
C:\Users\Alexandre\Pictures\Urlaubsfotos
```

Unterordner sind ok — das Tool sucht rekursiv nach `.jpg`, `.jpeg`, `.png`, `.heic`.

---

## 4. Optional: kurz mit Beispieldaten testen

Nur zum Ausprobieren:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\create_sample_dataset.py
python -m photobook_curator -i sample_photos -o output_sample -n 20 --no-geocode
```

Danach findest du unter `output_sample\`:
- `selected\` — ausgewählte Bilder
- `photos_analysis.csv` — alle Bewertungen
- `inhaltsverzeichnis.md` — Kapitelübersicht

---

## 5. Ersten echten Lauf starten (ohne KI)

Ersetze die Pfade durch deine:

```powershell
.\.venv\Scripts\Activate.ps1

python -m photobook_curator `
  -i "C:\Users\Alexandre\Pictures\Urlaubsfotos" `
  -o "C:\Users\Alexandre\Pictures\Fotobuch_Ausgabe" `
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
| `selected\` | Die finalen Bilder, sortiert nach Kapiteln |
| `01_Paris\hauptteil\` | Hauptteil einer Region |
| `01_Paris\essen\` | Essensfotos dieser Region |
| `01b_Transit_Paris-Lyon\` | Fotos der Reise dazwischen |
| `inhaltsverzeichnis.md` | Kurze Übersicht pro Kapitel |
| `photos_analysis.csv` | Alle Fotos mit Scores (auch nicht ausgewählte) |

Öffne `inhaltsverzeichnis.md` und blättere durch `selected\`. Wenn dir zu wenig/zu viele Bilder gefallen: Schritt 5 mit anderem `-n` wiederholen.

---

## 7. Optional: KI-Bewertung mit Anthropic

Ein Claude-Chat-Abo reicht dafür **nicht**. Du brauchst einen API-Key:

1. Gehe zu [https://console.anthropic.com/](https://console.anthropic.com/)
2. Einloggen / Account anlegen
3. Zahlungsmittel hinterlegen (API wird getrennt abgerechnet)
4. API-Key erzeugen und kopieren

Dann in PowerShell (Key nicht ins Repo legen):

```powershell
$env:ANTHROPIC_API_KEY='sk-ant-...'
```

Zuerst Kosten schätzen:

```powershell
python -m photobook_curator `
  -i "C:\Users\Alexandre\Pictures\Urlaubsfotos" `
  -o "C:\Users\Alexandre\Pictures\Fotobuch_Ausgabe" `
  -n 80 `
  --ai-review `
  --dry-run
```

Wenn die Schätzung ok ist, denselben Befehl **ohne** `--dry-run` ausführen:

```powershell
python -m photobook_curator `
  -i "C:\Users\Alexandre\Pictures\Urlaubsfotos" `
  -o "C:\Users\Alexandre\Pictures\Fotobuch_Ausgabe" `
  -n 80 `
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

```powershell
python -m photobook_curator --help
```

---

## Checkliste

1. [ ] Repo geklont, Branch ausgecheckt  
2. [ ] `.venv` erstellt und mit `.\.venv\Scripts\Activate.ps1` aktiviert  
3. [ ] Dependencies installiert (`pip install -r requirements.txt`)  
4. [ ] Foto-Ordner bereit  
5. [ ] Ersten Lauf mit `-i`, `-o`, `-n` gestartet  
6. [ ] `selected\` und `inhaltsverzeichnis.md` geprüft  
7. [ ] (Optional) Anthropic-API-Key gesetzt und `--ai-review` genutzt  
8. [ ] Bilder aus `selected\` ins Fotobuch-Tool deiner Wahl übernehmen  

---

## Anhang: macOS / Linux

Umgebung aktivieren:

```bash
source .venv/bin/activate
```

API-Key setzen:

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

Pfad-Beispiele dann z. B. `/Users/DU/Urlaubsfotos`.
