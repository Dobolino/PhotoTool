# PhotoTool starten und aktualisieren

Für die normale Nutzung unter Windows lade den Installer
`PhotoTool-Setup-<Version>.exe` von
[GitHub Releases](https://github.com/Dobolino/PhotoTool/releases). Er richtet
PhotoTool mit Startmenü und Deinstallation ein. Python wird mitgeliefert.
Eine fehlende Microsoft-Edge-WebView2-Laufzeit wird über den offiziellen
Microsoft-Bootstrapper eingerichtet; dafür ist Internet nötig.

Ein portables ZIP vollständig entpacken und darin `Fotobuch.exe` starten.
Diese Variante setzt eine vorhandene WebView2-Laufzeit voraus.

Zur Bedienung: [Kurzanleitung](ANLEITUNG.md),
[Reiseprojekte und Fotoansicht](REISEPROJEKTE.md),
[Japan-Workflow](JAPAN_WORKFLOW.md).

## Start aus dem Quellcode unter Windows

Dieser Weg ist für einen heruntergeladenen Quellstand oder einen Git-Checkout
gedacht. Den stabilen Quellcode unter **Source code (zip)** beim gewünschten
GitHub Release herunterladen, zum Beispiel `v0.5.0` nach dessen Veröffentlichung.
Für den aktuellen Entwicklungsstand mit Git:

```powershell
git clone --branch codex/japan-workflow-hardening https://github.com/Dobolino/PhotoTool.git
cd PhotoTool
```

Der Standardbranch `main` enthält noch einen älteren Stand. Ein vorhandener
Checkout eines älteren Branches erhält die neue Version deshalb nicht allein
durch Aktualisieren seines bisherigen Upstreams. Für die stabile Nutzung ist
der Installer der empfohlene Updateweg.

Voraussetzungen für den Quellcode-Start:

- Python **3.11 oder neuer** von [python.org](https://www.python.org/downloads/),
  mit **Add python.exe to PATH** sowie Tcl/Tk installieren.
- Internet für die erste Paketinstallation und gegebenenfalls Modelldownloads.
- Microsoft Edge WebView2 für das moderne Foto-Fenster. Falls die Laufzeit fehlt,
  ist der PhotoTool-Installer der einfachere Einstieg.
- Git nur dann, wenn du einen Checkout über Git aktualisieren möchtest.

Im vollständigen Programmordner **Fotobuch starten.bat** doppelklicken.
Das schwarze Statusfenster bleibt sichtbar. Beim ersten Start legt das Skript
`.venv` an und installiert die Pakete; das kann einige Minuten dauern.
Danach öffnet sich das Hauptfenster. Die Originalfotos und Projektordner solltest
du ausserhalb des Programmordners aufbewahren.

Manuell geht es in PowerShell im Programmordner so:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m photobook_curator --gui
```

Falls `.venv` bereits vorhanden ist, reichen die Paketinstallation und der Start.
Die Paketinstallation ist bei einem Versionswechsel wichtig: Eine vorhandene
0.4.x-Umgebung benötigt für das neue Foto-Fenster zusätzliche Abhängigkeiten.
`Fotobuch starten.bat` allein erkennt diese Ergänzungen nicht vollständig.

## Programm aktualisieren

### Installiertes Windows-Programm

Im Hauptfenster **Updates** verwenden oder den neueren offiziellen Installer
von GitHub Releases ausführen. Vor dem Update offene Prüfungen über
**Pause & speichern** abschliessen. Der Updater prüft Download-Grösse und SHA256
und sichert offene Entwürfe vor dem Installerstart. Die Installation ersetzt
keine Fotoquellen oder Reiseprojekte.
Die Details stehen in der [README](README.md#windows-programm-und-updates).

### Quellcode mit Git

Im Programmordner **Programm aktualisieren.bat** doppelklicken. Das Skript
aktualisiert den aktuellen Branch von dessen bereits eingerichtetem Upstream
mit `git pull --ff-only`. Es wechselt keinen Branch und setzt keine lokalen
Änderungen zurück. Anschliessend aktualisiert es die Pakete einer vorhandenen
`.venv`. Danach **Fotobuch starten.bat** ausführen.

Ein Checkout eines Release-Tags hat keinen aktiven Branch. Auch ein Branch ohne
Upstream lässt sich damit nicht automatisch aktualisieren. In diesem Fall den
gewünschten Quellstand bewusst wählen oder den Quellcode eines neueren Releases
in einen neuen Programmordner entpacken. Ein altes Update-Skript, das einen
bestimmten Branch erzwingt, nicht zum Aktualisieren auf 0.5.0 verwenden.

Manuell in einem Branch mit eingerichtetem Upstream:

```powershell
git status
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Scheitert `--ff-only`, die Git-Meldung prüfen und lokale Änderungen sichern.
Ein automatischer Merge oder Branchwechsel ist nicht Teil dieses Updatewegs.

### Quellcode ohne Git

**Source code (zip)** des gewünschten neueren Releases herunterladen und in
einen neuen Ordner entpacken. Dort **Fotobuch starten.bat** ausführen und das
bestehende Reiseprojekt öffnen. Fotos und Projektordner weiterverwenden;
den neuen Programmordner nicht über den Foto- oder Projektordner entpacken.

## Wenn der Quellcode-Start scheitert

| Meldung oder Verhalten | Nächster Schritt |
|---|---|
| Python fehlt oder der Microsoft Store öffnet sich | Python von python.org mit PATH installieren; gegebenenfalls die Windows-Ausführungsaliase für `python.exe` und `python3.exe` deaktivieren. |
| `tkinter` fehlt | Python-Installation mit Tcl/Tk ergänzen. |
| Neue Fotoansicht startet nach einem Update nicht | Pakete mit dem obigen pip-Befehl aktualisieren und WebView2-Verfügbarkeit prüfen; alternativ den offiziellen Installer verwenden. |
| Paketinstallation scheitert | Fehlermeldung im Statusfenster lesen, Internetzugang prüfen und den pip-Befehl erneut ausführen. |
| Hauptfenster startet nicht | `start_log.txt` und gegebenenfalls `fehler_beim_start.txt` im Programmordner öffnen. |
| Fotos fehlen in der Vorschau | Originale lokal verfügbar machen oder **Werkzeuge → Originale wiederfinden** verwenden. |
| Speichern scheitert | Schreibrechte und freien Speicher im Projektordner prüfen; die Prüfung erst nach erfolgreichem Speichern schliessen. |

Die lokale Fotoauswahl benötigt keinen externen KI-Anbieter. Online-Ortsnamen,
externe KI sowie anfängliche Modell- und Laufzeitdownloads sind eigenständige
Netzwerkfunktionen; **ohne KI** bedeutet deshalb nicht automatisch **ohne Netzwerk**.

## Eigene Windows-EXE bauen

Für Entwickler: **packaging\build_windows.bat** starten oder den Ablauf in
[packaging/README.md](packaging/README.md) verwenden. Ergebnis ist der komplette
Ordner `dist\Fotobuch` mit `Fotobuch.exe`. Diesen Ordner vollständig weitergeben.
Für den Installer und die WebView2-Voraussetzung gelten die dort beschriebenen
zusätzlichen Build-Schritte und Prüfungen.

Tests aus einer eingerichteten Entwicklungsumgebung:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```
