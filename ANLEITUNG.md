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

1. **Fotos-Ordner** → `Durchsuchen…` → z. B. `OneDrive\Bilder\Urlaubfotos\Japan`
2. **Ausgabe-Ordner** → `Durchsuchen…` → neuen leeren Ordner wählen
3. **Zielanzahl** einstellen (z. B. 80)
4. Auf **Start** klicken
5. Warten, bis „Fertig“ erscheint

### 5. Ergebnis

Im Ausgabeordner:
- `selected\` — die ausgewählten Bilder nach Kapiteln
- `inhaltsverzeichnis.md` — Übersicht
- `photos_analysis.csv` — alle Details

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
