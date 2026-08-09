# Schritt-für-Schritt: Fotobuch auswählen

Du brauchst: **Python 3.11+** (einmalig installieren) und deine Urlaubsfotos in einem Ordner.

---

## Einfachster Weg (Windows): Doppelklick

### 1. Python installieren (nur einmal)

Falls noch nicht vorhanden: von [python.org/downloads](https://www.python.org/downloads/) installieren.  
Beim Setup **„Add python.exe to PATH“** anhaken.

### 2. Projekt aktualisieren

Im Ordner `PhotoTool` (z. B. `Downloads\PhotoTool`) PowerShell öffnen:

```powershell
cd $HOME\Downloads\PhotoTool
git checkout cursor/photobook-curator-c6d6
git pull
```

### 3. Programm starten

Im Explorer doppelklicken:

```text
Fotobuch starten.bat
```

Beim ersten Start werden die Pakete automatisch installiert (kann ein paar Minuten dauern).  
Danach öffnet sich ein Fenster.

### 4. Im Fenster

1. **Fotos-Ordner** → `Durchsuchen` → z. B. `OneDrive\Bilder\Urlaubfotos\Japan`
2. **Ausgabe-Ordner** → `Durchsuchen` → neuen leeren Ordner wählen
3. **Zielanzahl** einstellen (z. B. 80)
4. Auf **Auswahl starten** klicken
5. Warten, bis „Fertig“ erscheint
6. Bei Nachfrage **Ja** → **Auswahl prüfen** (Thumbnails)
   - Klick auf ein Bild = rausnehmen / wieder reinnehmen
   - Unten Alternativen mit **+ HINZUFÜGEN**
   - **Speichern & Ordner neu schreiben**

Später erneut prüfbar über den Button **Auswahl prüfen** (braucht `photos_analysis.csv` im Ausgabeordner).

### 5. Ergebnis

Im Ausgabeordner:
- `selected\` — die ausgewählten Bilder nach Kapiteln
- `inhaltsverzeichnis.md` — Übersicht
- `photos_analysis.csv` — alle Details

Das Tool erkennt lokal auch **geschlossene Augen** und problematische Gesichter (angeschnitten / zu klein), markiert sie in der Prüfung und bevorzugt sie nicht fürs Buch.

**Serien/Bursts:** Aus ähnlichen Fotos innerhalb von ~30 Sekunden behält es nur die besten 1–2 Bilder.

**Dokumente & Screenshots** (Tickets, Karten, Chat-Screens …) kommen **nicht** automatisch ins Buch, sondern in den Ordner `optional_dokumente/`. In **Auswahl prüfen** kannst du sie bei Bedarf mit einem Klick ins Album übernehmen (`99_Optional_Dokumente`).

### Optionen (GUI oder CLI)

| Option | Standard | Bedeutung |
|--------|----------|-----------|
| Gesichtserkennung / Augen zu | an | `--faces` / `--no-faces` |
| Serien/Bursts | an | `--bursts` / `--no-bursts` |
| Dokumente separat | an | `--aside-documents` / `--no-aside-documents` |
| Tages-Abdeckung | aus | Checkbox + Stärke-Regler, CLI: `--coverage-intensity 0.0–1.0` |
| Personen-Balance | aus | Checkbox + Stärke-Regler, CLI: `--people-balance-intensity 0.0–1.0` |
| Kapitel-/Karten-Vorschau | aus | Checkbox, CLI: `--map-preview` |
| KI-Bewertung | aus | `--ai-review` |
| Auswahl prüfen | nach dem Lauf | manuell |

**Tages-Abdeckung:** Verhindert, dass fast alle Bilder vom ersten Tag kommen.  
`0` = aus, `0.5` = sanft, `1.0` = stark gleichmäßig über die Tage.

**Personen-Balance:** Verhindert, dass dieselbe Person das Album dominiert; unterrepräsentierte Gesichter werden bevorzugt.  
`0` = aus, `0.5` = sanft, `1.0` = stark ausgewogen.

**Kapitel-/Karten-Vorschau:** Zeigt vor dem Kopieren die Kapitelreihenfolge und GPS-Punkte (Fenster + `kapitel_karte.html`).  
Erst nach „So exportieren“ werden `selected/` und Co. geschrieben. In der CLI erzeugt `--map-preview` die HTML-Karte mit.

Optional: Haken bei **KI-Bewertung** setzen und API-Key eintragen (braucht Account auf [console.anthropic.com](https://console.anthropic.com/) — Claude-Chat-Abo reicht nicht).

---

## Alternative: Kommandozeile

Nur falls du keine GUI willst. Details früherer Version:

```powershell
cd $HOME\Downloads\PhotoTool
.\.venv\Scripts\Activate.ps1
python -m photobook_curator -i "C:\Pfad\zu\Fotos" -o "C:\Pfad\zur\Ausgabe" -n 80
```

GUI auch so startbar:

```powershell
python -m photobook_curator --gui
```

---

## Checkliste

1. [ ] Python installiert (mit PATH)  
2. [ ] `git pull` auf Branch `cursor/photobook-curator-c6d6`  
3. [ ] `Fotobuch starten.bat` doppelgeklickt  
4. [ ] Eingabe- und Ausgabeordner gewählt, Start gedrückt  
5. [ ] `selected\` und `inhaltsverzeichnis.md` geprüft  
