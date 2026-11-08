# Packaging: Standalone-Executable (Windows-first)

Ziel: Endnutzer sollen das Fotobuch-Tool **ohne** Python-, venv- oder pip-Setup
starten können – ein Ordner mit `Fotobuch.exe`, fertig.

## Für Maintainer: Build unter Windows

1. Python 3.11+ installiert (nur auf dem **Build-Rechner**, nicht beim Endnutzer).
2. Doppelklick auf `packaging\build_windows.bat` **oder** manuell:

   ```powershell
   python -m venv .venv-build
   .\.venv-build\Scripts\Activate.ps1
   pip install -r packaging\requirements-build.txt -c packaging\constraints-windows.txt
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
einen Tag wie `v0.5.1` auf diesen Commit pushen. Tag und App-Version müssen übereinstimmen.
`python packaging/build.py --check` prüft die drei Versionsangaben ohne Build;
auch jeder Bundle-Build und der Windows-Workflow brechen bei Abweichungen ab.
Erst nach erfolgreichem Test, EXE-Smoke-Test, Installer-Build und nativem
Installer-Test wird ein GitHub Release
mit den Dateien veröffentlicht. PR-/manuelle Builds bleiben herunterladbare Actions-Artefakte.
Der Installer-Test installiert in einen Pfad mit Leerzeichen, prüft den
automatischen Programmstart und wiederholt Installation und Start als In-place-Update.
Ab 0.5.0 öffnen beide installierten Durchläufe zusätzlich die echte moderne
Fotoansicht in WebView2. Der Test verlangt einen erfolgreichen HTML-/Foto-Render;
ein bloss gestarteter Prozess reicht nicht.

### Moderne Fotoansicht und Windows-Laufzeit

Die neue Ansicht verwendet die lokal gebündelten Dateien in
`photobook_curator/web_review/` und einen auf `127.0.0.1` begrenzten Python-Dienst.
Der native Windows-Host nutzt pywebview 6.2.1 und Microsoft Edge WebView2. Fotos
werden darüber nicht ins Internet übertragen. Vorschauen und Projektentscheidungen
bleiben in den bestehenden Python-Diensten; der Browserteil enthält keinen
zweiten Auswahldatensatz.

Das Programmsymbol liegt zusammen mit dem Logo in `photobook_curator/assets/`.
PyInstaller, Installer, Tk-Fenster und WebView2 nutzen dieselbe Bildmarke;
das ICO enthält die üblichen Windows-Grössen bis 256 Pixel. Paketdaten werden
über `importlib.resources` geladen, damit ein anderer Arbeitsordner oder ein
installierter Startmenü-Aufruf keine Symbole verschwinden lässt. Der native
EXE-Smoke öffnet beide Bilddateien und sperrt Releases bei fehlenden Ressourcen.

`prepare_webview2.ps1` lädt den Evergreen-Bootstrapper ausschliesslich von
Microsofts offiziellem Endpunkt und akzeptiert ihn nur mit gültiger Microsoft-
Authenticode-Signatur. Der Installer enthält diesen kleinen Bootstrapper. Ist
WebView2 bereits installiert, wird er nicht gestartet. Nur bei fehlender Laufzeit
lädt er die kostenlose Microsoft-Laufzeit nach. Windows 11 und viele Windows-10-
Installationen haben diese Laufzeit bereits. Das Programm selbst enthält weiterhin
Python und seine Pakete; eine Python-Installation beim Anwender ist nicht nötig.
Das portable ZIP setzt eine vorhandene WebView2-Laufzeit voraus; für einen Rechner
ohne diese Laufzeit ist der Installer der einfachere Einstieg.

Der Build prüft die moderne Ansicht zuerst aus dem Quellstand und anschliessend
aus `dist/Fotobuch/Fotobuch.exe` über `--review-smoke <Ergebnisdatei>`.
`--review-capture-dir <Ordner>` erzeugt zusätzliche native Prüfaufnahmen.
`PhotoTool-packaged-review-ui` enthält die Aufnahmen und den Rendernachweis der
wirklich gebündelten Anwendung. Fehlende Webdateien, CLR-Assemblies oder ein
ausbleibender Render sperren die Veröffentlichung. Die bestehenden Tk-Aufnahmen
dienen zusätzlich der Hauptfenster- und Rückfallansicht-Regressionsprüfung.

Der Windows-Workflow lädt zusätzlich `PhotoTool-windows-ui` hoch: native Aufnahmen
des regulären und maximierten Hauptfensters, der Einstellungen und eines
ausdrücklich simulierten Fortschritts-/Kostenbeispiels. Hinzu kommen die
fokussierte Albumvorschau, der Variantenvergleich und der Prüfbericht mit fünf
kleinen, erzeugten DEMO-Bildern. Ihre Metadaten und Auswahlbelege sind konstruierte
Testdaten; die Aufnahmen behaupten keine tatsächlich gemessene Bildbewertung.
Zusätzlich werden der Prüfbericht bei 920 × 580 und die Offline-Ortsprüfung
regulär sowie bei 800 × 600 aufgenommen. Die Ortsprüfung verwendet nur zwei
öffentliche Stadtmittelpunkt-Koordinaten als ausdrücklich synthetische Metadaten;
sie startet keine Online-Abfrage. Tabellen-/Detailhöhen und tatsächliche
Schaltflächengeometrien stehen ebenfalls in den Metadaten.
`metadata.json` hält
tatsächliche Bildschirmauflösung, DPI und Fenster-/Inhaltsgeometrie fest.
1920 × 1080 wird nur verwendet, wenn der Runner diesen Modus unterstützt;
sonst dokumentieren die Aufnahmen den tatsächlich verfügbaren Bildschirm.
Die Hauptfensterquellen bleiben leer. Die Aufnahmen verwenden keine privaten
Fotos oder API-Schlüssel, keine KI-Aufrufe und isolierte Einstellungen.
Die Aufnahme läuft auch nach einem fehlgeschlagenen Test für die Fehlerdiagnose.
Fehlgeschlagene Tests sperren weiterhin Build und Veröffentlichung.

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

Der Desktop-Updater greift ohne GitHub-Anmeldung auf die öffentlichen Releases zu.
Für jede stabile Version muss der Windows-Workflow den passenden Installer im
Release veröffentlichen; ein Actions-Artefakt allein wird nicht als Update angeboten.
Ein HTTP 404 wird als nicht verfügbare Release-Quelle gemeldet, nicht als
erfolgreicher Versionsvergleich. Es wird kein GitHub-Token in die EXE eingebaut.

Beim Update von 0.4.x auf 0.5.x bleiben Installer-ID und Installationspfad gleich.
Bestehende Projekte verwenden weiterhin Projektformat 1; Ausgabeordner,
Auswahlentwürfe, Favoriten und Originalbilder werden vom Installer nicht ersetzt.
Das Projekt kann nach dem Update über **Projekt öffnen** fortgesetzt werden.
Ältere Analysen bleiben lesbar. Wenn sie noch keine automatische
Entscheidungshistorie enthalten, darf der Prüfbericht daraus keine nachträgliche
Rankingbegründung ableiten; historische Entscheidungsdaten sind erst nach einer
neuen Auswahl mit 0.4.2 verfügbar.

- **Einfach:** Ordner `dist\Fotobuch` als **ZIP** weitergeben → entpacken →
  `Fotobuch.exe` doppelklicken. Kein Python nötig.
- **Komfortabel:** Der Windows-Workflow baut mit
  [Inno Setup](https://jrsoftware.org/isinfo.php) und `packaging/installer.iss`
  einen Installer mit Startmenü-Eintrag und Deinstallation.
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
