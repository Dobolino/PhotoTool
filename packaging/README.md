# Packaging: Standalone-Executable (Windows-first)

Ziel: Endnutzer sollen das Fotobuch-Tool **ohne** Python-, venv- oder pip-Setup
starten können – ein Ordner mit `Fotobuch.exe`, fertig.

## Für Maintainer: Build unter Windows

1. Python 3.11+ installiert (nur auf dem **Build-Rechner**, nicht beim Endnutzer).
2. Doppelklick auf `packaging\build_windows.bat` **oder** manuell:

   ```powershell
   python -m venv .venv-build
   .\.venv-build\Scripts\Activate.ps1
   pip install -r packaging\requirements-build.txt
   python packaging\build.py
   ```

3. Ergebnis: `dist\Fotobuch\Fotobuch.exe` (kompletter Ordner `dist\Fotobuch`).

## Distribution an Endnutzer

### GitHub-Build und Releases

`.github/workflows/windows-build.yml` testet und baut unter Windows bei Pull Requests,
manuellem Workflow-Start und Tags `v*`. Der Build erzeugt den Installer mit Inno Setup
6.7.3, ein portables ZIP und SHA256SUMS. Python-Abhängigkeiten sind für diesen Build
in `constraints-windows.txt` auf die getesteten Versionen begrenzt.

Für eine Veröffentlichung zuerst `photobook_curator/__init__.py`, `pyproject.toml`
und den Default in `installer.iss` auf dieselbe Version setzen. Nach Prüfung und Merge
einen Tag wie `v0.2.0` auf diesen Commit pushen. Tag und App-Version müssen übereinstimmen.
Erst nach erfolgreichem Test, EXE-Smoke-Test und Installer-Build wird ein GitHub Release
mit den Dateien veröffentlicht. PR-/manuelle Builds bleiben herunterladbare Actions-Artefakte.

Solange `main` nur die ursprüngliche README enthält, zuerst den Entwicklungsstand
einschliesslich dieses Workflows übernehmen. Ein manueller Workflow-Start wird in
GitHub erst angeboten, wenn die Workflow-Datei auf dem Standardbranch vorhanden ist.

### Update im Programm

Die Schaltfläche **Updates** fragt ausschliesslich das neueste stabile GitHub Release
von `Dobolino/PhotoTool` ab. Erwartet wird `PhotoTool-Setup-X.Y.Z.exe` mit einem
SHA256-`digest` in GitHubs Asset-Metadaten. Ohne passenden Installer/Prüfsumme wird
keine Installation gestartet. Download-Grösse und SHA256 müssen vor dem Start passen.
SHA256 stellt die Übereinstimmung mit dem GitHub-Asset sicher; es ersetzt keine
Windows-Codesignatur. Der Installer aktualisiert die Installation im Benutzerprofil;
Fotoquellen, Ausgabeordner und Benutzereinstellungen sind nicht Teil des Installers.

- **Einfach:** Ordner `dist\Fotobuch` als **ZIP** weitergeben → entpacken →
  `Fotobuch.exe` doppelklicken. Kein Python nötig.
- **Komfortabel:** Mit [Inno Setup](https://jrsoftware.org/isinfo.php) einen
  Installer erzeugen (Startmenü-Eintrag, Deinstallation). Beispiel-Script kann
  bei Bedarf ergänzt werden.
- **Code-Signing (empfohlen):** Ohne Signatur zeigt Windows SmartScreen beim
  ersten Start eine Warnung. Mit einem Code-Signing-Zertifikat:

  ```powershell
  signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 ^
    dist\Fotobuch\Fotobuch.exe
  ```

## Warum `--onedir` und PyInstaller?

- **`--onedir`** (statt `--onefile`): onefile entpackt bei **jedem** Start ins
  Temp-Verzeichnis → langsamer Start und häufig Virenscanner-Fehlalarme bei den
  großen ML-DLLs. onedir startet schnell und ist stabiler.
- **PyInstaller** hat ausgereifte `collect_all`-Hooks für die kritischen Pakete
  hier (`mediapipe`, `opencv`, `pillow_heif`, `sklearn`). **Nuitka** erzeugt
  kleinere/schnellere Binaries, ist bei nativen ML-Paketen (MediaPipe-`.tflite`/
  `.task`, protobuf, OpenCV-DLLs) aber deutlich fummeliger – daher hier optional
  für später, nicht als Default.

## Modelle (MediaPipe) – online vs. offline

MediaPipe lädt `blaze_face_short_range.tflite`, `face_landmarker.task` und
`hand_landmarker.task` zur Laufzeit nach in einen beschreibbaren User-Cache.
Der Runtime-Hook `hooks/rthook_model_cache.py` setzt diesen Cache-Pfad im
Bundle korrekt (`%LOCALAPPDATA%\photobook_curator`).

Zwei Betriebsarten:

1. **Offline-fähig (empfohlen für Endnutzer):** Die drei Modelldateien nach
   `packaging/models/` legen. Die Spec bündelt sie mit; der Runtime-Hook kopiert
   sie beim ersten Start in den User-Cache. Kein Internet nötig.
2. **Kleineres Bundle (Lazy-Download):** `packaging/models/` leer lassen. Beim
   ersten Start lädt das Tool die Modelle einmalig herunter (Internet nötig).
   Wichtig: dafür den **Download-Timeout** aus dem Code-Review (Abschnitt 1.3)
   einbauen, damit ein hängendes Netz den Start nicht blockiert.

## Bekannte Fallstricke

- **Antivirus:** Unsignierte, frisch gebaute Executables mit ML-Libs werden
  gelegentlich fälschlich als verdächtig markiert → signieren hilft.
- **HEIC:** `pillow-heif` bringt native Libs mit; `collect_all("pillow_heif")`
  in der Spec deckt das ab. Nach dem Build mit einem echten `.heic`-Bild testen.
- **Erststart-Diagnose:** `entry_gui.py` fängt Startfehler ab und zeigt sie in
  einer MessageBox (im `--windowed`-Modus gäbe es sonst keine Ausgabe).
- **Icon:** Optional `packaging/icon.ico` ablegen – wird automatisch verwendet.

## macOS / Linux (2. Ausbaustufe)

`python packaging/build.py` funktioniert plattformneutral. Für eine echte
`.app` unter macOS zusätzlich `--windowed` (in der Spec bereits `console=False`)
sowie `codesign`/Notarisierung – analog dokumentierbar, wenn benötigt.
