# Fotobuch (Photobook Curator) – Komplettanleitung von Anfang an

Diese Anleitung führt dich **von Null** bis zum fertigen Fotobuch-Ordner – auf dem
Branch **`cursor/photobook-curator-c6d6`** (der aktuelle, vollständige Stand mit allen
Verbesserungen).

Es gibt drei Wege, je nachdem was du willst:

- **A – Einfach benutzen** (empfohlen): Projekt holen → Doppelklick → loslegen.
- **Programm aktualisieren** – wenn du schon eine Installation hast (siehe unten).
- **B – Standalone-App bauen**: eine `Fotobuch.exe` zum Weitergeben (Ziel-PC braucht kein Python).
- **C – Für Entwickler**: Tests laufen lassen, Code ändern.

---

## 0. Voraussetzungen (einmalig)

- **Windows 10/11**
- **Python 3.11 oder neuer** – von [python.org/downloads](https://www.python.org/downloads/) installieren.
  ⚠️ Beim Setup unbedingt **„Add python.exe to PATH"** anhaken.
- **Git** (nur wenn du das Projekt per `git` holen willst) – [git-scm.com](https://git-scm.com/download/win).
  Ohne Git geht auch der ZIP-Download (siehe unten).

---

## A – Einfach benutzen

### Schritt 1: Projekt holen

**Mit Git (empfohlen, weil Updates einfach sind):**

PowerShell öffnen (Startmenü → „PowerShell") und:

```powershell
cd $HOME\Downloads
git clone https://github.com/Dobolino/PhotoTool.git
cd PhotoTool
git checkout cursor/photobook-curator-c6d6
```

**Ohne Git (ZIP):**

1. Auf GitHub oben Branch **`cursor/photobook-curator-c6d6`** auswählen.
2. Grüner Button **`Code` → `Download ZIP`**.
3. ZIP nach z. B. `Downloads\PhotoTool` entpacken.

> Schon installiert und nur den neuesten Stand wollen? → **[Programm aktualisieren](#programm-aktualisieren)** weiter unten.

### Schritt 2: Starten

Im Ordner `PhotoTool` **Doppelklick auf:**

```
Fotobuch starten.bat
```

- Zuerst erscheint ein **schwarzes Textfenster** mit Statusmeldungen – das ist Absicht.
- Beim **ersten Start** legt das Skript automatisch eine Python-Umgebung an und
  installiert die Pakete (oft 3–10 Minuten – nur beim ersten Mal). Fenster nicht schließen.
- Danach öffnet sich das **Programmfenster** („Fotobuch-Auswahl“).
  Kurz steht dort „lade Erkennungsmodule…“, danach **Bereit**.

> Beim allerersten Auswahl-Lauf lädt das Programm einmalig kleine Erkennungs-Modelle
> aus dem Internet nach. Danach funktioniert es auch offline.

#### Wenn nur ein leeres Fenster kommt

| Was du siehst | Ursache | Lösung |
|---|---|---|
| Leeres / Store-Fenster, kein Text | Windows-Store-Alias statt echtem Python | Python von python.org, PATH anhaken; unter **Einstellungen → Apps → Aliase für App-Ausführung** `python.exe` / `python3.exe` **aus** |
| Schwarzes Fenster ohne Text / schließt sofort | Python fehlt oder Start bricht ab | Erneut starten; Text lesen; ggf. Python neu installieren |
| Schwarzes Fenster mit Fehlermeldung | Installation unvollständig | Meldung lesen; Bat erneut starten (repariert `.venv`) |
| Kein Programmfenster | Fehler beim GUI-Start | Dateien `start_log.txt` und `fehler_beim_start.txt` im Ordner öffnen |

### Schritt 3: Bedienung

1. **Fotos-Ordner** → `Durchsuchen` → z. B. `OneDrive\Bilder\Urlaub\Japan`.
2. **Ausgabe-Ordner** → `Durchsuchen` → einen **neuen, leeren** Ordner wählen.
3. **Zielanzahl Bilder** setzen (z. B. 80 – so viele sollen ungefähr ins Buch).
4. Optionen nach Wunsch anhaken:
   - *Gesichtserkennung / Augen zu* (an) – wertet schlechte Gesichter ab.
   - *Serien/Bursts* (an) – behält aus Serien nur die besten 1–2.
   - *Dokumente & Screenshots separat* (an) – Tickets/Screenshots kommen in einen Extra-Pool.
   - *Finger vor der Linse* (aus) – sortiert typische Fehlaufnahmen aus.
   - *Tages-Abdeckung* – verhindert, dass fast alles vom ersten Tag stammt.
   - *Personen-Balance* – verhindert, dass eine Person das Album dominiert.
   - *Kapitel-/Karten-Vorschau* – zeigt Kapitel & Karte **vor** dem Export.
   - *KI-Bewertung* – optional, braucht einen Anthropic-API-Key.
5. **Auswahl starten** – der Fortschrittsbalken zeigt die Phasen.
6. Bei „Fertig" die Frage **Auswahl prüfen?** → **Ja**:
   - **Raster:** Klick auf ein Bild = **raus / wieder rein**.
   - **Diashow:** großes Bild, Nachbar-Vorschau, Filter (Alle/Dabei/Entfernt),
     Kapitel-Sprung, beste Alternative daneben (Taste **A**), optional
     Auto-weiter nach Entfernen; Esc zurück zum Raster.
   - **Darstellung & Sprache** (oben rechts): Deutsch/English, Design
     (Wald / Schiefer / Tinte), Diashow-Optionen.
   - Unten **Alternativen** und der **Dokumente-Pool** zum Hinzufügen.
   - **Speichern & Ordner neu schreiben**.

### Auswahl unterbrechen / fortsetzen (ohne neue KI)

- **Du musst nichts nochmal von vorn machen**, wenn der Ausgabe-Ordner (dein „Backup“)
  noch da ist.
- Während **Auswahl prüfen** wird automatisch `selection_draft.json` gespeichert.
  Fenster schließen oder Absturz → später wieder **Auswahl prüfen / fortsetzen**.
- Nach der KI schreibt das Programm einen Zwischenstand in `photos_analysis.csv`.
  Die teure KI musst du **nicht** wiederholen – gleicher Ausgabe-Ordner wählen,
  dann **Auswahl prüfen / fortsetzen**.
- Wenn es eine CSV mit Analyse gibt, aber noch keine fertige Auswahl: das Programm
  fragt, ob es die Auswahl **aus der Analyse ohne KI** erzeugen soll.

### Schritt 4: Ergebnis

Im **Ausgabe-Ordner** findest du:

| Datei/Ordner | Inhalt |
|---|---|
| `selected\` | Die ausgewählten Bilder, nach Kapiteln sortiert |
| `inhaltsverzeichnis.md` | Übersicht der Kapitel |
| `optional_dokumente\` | Screenshots/Dokumente zum Durchsehen |
| `photos_analysis.csv` | Alle Details je Foto |
| `kapitel_karte.html` | Karte der Orte (falls Vorschau aktiv) |

Später erneut prüfbar über den Button **Auswahl prüfen** (nutzt die `photos_analysis.csv`
im Ausgabe-Ordner).

---

## Programm aktualisieren

Wenn Cursor/Claude neue Verbesserungen gepusht hat und du sie auf dem PC haben willst:

### Variante 1 – Doppelklick (einfachste, mit Git)

Im Ordner `PhotoTool`:

```text
Programm aktualisieren.bat
```

Das wechselt auf den Branch `cursor/photobook-curator-c6d6` und holt den neuesten Stand.  
Danach wieder **`Fotobuch starten.bat`** starten.

### Variante 2 – PowerShell (mit Git)

```powershell
cd $HOME\Downloads\PhotoTool
git checkout cursor/photobook-curator-c6d6
git pull origin cursor/photobook-curator-c6d6
```

Dann erneut `Fotobuch starten.bat` doppelklicken.

### Variante 3 – Ohne Git (ZIP neu laden)

1. Auf GitHub Branch **`cursor/photobook-curator-c6d6`** wählen → **Code → Download ZIP**.
2. Alten Ordner umbenennen (z. B. `PhotoTool_alt`) oder ersetzen.
3. ZIP neu entpacken.
4. `Fotobuch starten.bat` starten (legt `.venv` bei Bedarf neu an).

**Hinweis:** Deine **Fotos** und der **Ausgabe-Ordner** liegen getrennt – die bleiben unberührt.  
Nur der Programmordner `PhotoTool` wird aktualisiert.

### Nach dem Update

- Normal reicht: `Fotobuch starten.bat` erneut starten.
- Wenn etwas mit Paketen hakt: im Ordner `PhotoTool` den Unterordner `.venv` löschen und erneut starten (Neuinstallation der Pakete).
- Standalone-`Fotobuch.exe`: nach Code-Updates einmal neu bauen mit `packaging\build_windows.bat`.

---

## B – Standalone-App bauen (zum Weitergeben)

Wenn du eine `Fotobuch.exe` willst, die auf jedem Windows-PC **ohne Python** läuft:

1. Im Ordner `PhotoTool` **Doppelklick auf:**
   ```
   packaging\build_windows.bat
   ```
   (Baut eine eigene Umgebung und erzeugt die App – dauert einige Minuten.)
2. Ergebnis: **`dist\Fotobuch\Fotobuch.exe`**.
3. Den **kompletten Ordner** `dist\Fotobuch` weitergeben (z. B. als ZIP). Auf dem Ziel-PC
   einfach `Fotobuch.exe` doppelklicken.

> Details, Offline-Modelle und Code-Signing: siehe `packaging\README.md`.

---

## C – Für Entwickler (Tests & Code)

PowerShell im Ordner `PhotoTool`:

```powershell
# Umgebung aktivieren (nach dem ersten .bat-Start vorhanden)
.\.venv\Scripts\Activate.ps1

# Test-Werkzeug einmalig installieren
pip install pytest

# Alle Tests laufen lassen
python -m pytest -v
```

Erwartet: alle Tests **grün** (`passed`). CLI-Nutzung ohne GUI:

```powershell
python -m photobook_curator -i "C:\Pfad\zu\Fotos" -o "C:\Pfad\zur\Ausgabe" -n 80
```

Wichtige CLI-Optionen: `--no-faces`, `--no-bursts`, `--finger-filter`,
`--coverage-intensity 0.5`, `--people-balance-intensity 0.5`, `--map-preview`,
`--ai-review` (+ `--dry-run`), `--no-analysis-cache`.

---

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| **„Python wurde nicht gefunden"** | Python 3.11+ installieren, dabei **„Add python.exe to PATH"** anhaken; PC neu starten. |
| **PowerShell blockt `Activate.ps1`** | Einmal: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, dann erneut aktivieren. |
| **Erster Start dauert lange** | Normal – Pakete werden einmalig installiert. |
| **Update / `git pull` fehlgeschlagen** | Internet prüfen; siehe Abschnitt **Programm aktualisieren**. Bei Konflikten Ordner sichern und ZIP neu laden. |
| **„Git wurde nicht gefunden"** | [Git installieren](https://git-scm.com/download/win) oder ZIP-Variante nutzen. |
| **HEIC-Bilder werden nicht geladen** | Sollte automatisch gehen (pillow-heif ist dabei); mit einem echten `.heic` testen. |
| **Kein Internet beim ersten Lauf** | Die Erkennungs-Modelle werden einmalig geladen; ohne Netz läuft nur die Heuristik. |
| **Pfade mit Leerzeichen** | In der CLI in Anführungszeichen setzen: `"C:\Meine Fotos"`. |

---

## Kurzfassung

1. `git clone` + `git checkout cursor/photobook-curator-c6d6` (oder ZIP).
2. `Fotobuch starten.bat` doppelklicken.
3. Fotos-Ordner + Ausgabe-Ordner wählen, Zielanzahl setzen, **Auswahl starten**.
4. **Auswahl prüfen**, speichern.
5. Ergebnis liegt im Ausgabe-Ordner unter `selected\`.
6. **Später updaten:** `Programm aktualisieren.bat` (oder `git pull`) → wieder starten.

Für eine weitergebbare App: `packaging\build_windows.bat` → `dist\Fotobuch\Fotobuch.exe`.
