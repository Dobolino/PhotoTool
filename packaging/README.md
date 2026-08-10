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
