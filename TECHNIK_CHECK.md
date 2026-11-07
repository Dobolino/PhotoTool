# Technischer Check und umgesetzte Härtung

Geprüfter Ausgangspunkt: `codex/review-metadata-fixes`.
Ziel: grosse Urlaubssammlungen reduzieren, Entscheidungen fortsetzen, als
Windows-Programm ausliefern. Prüfung anhand von Code, automatisierten Tests und
synthetischen Messungen; keine privaten Urlaubsbilder lagen vor.

## Architektur

Die fachliche Trennung Scan → lokale Analyse → Duplikate/Serien → Orte/Transit →
Kandidaten/optionale KI → Auswahl → Export ist sinnvoll. `Photo` und `BookPlan`
verbinden die Stufen. Die Analyse nutzt bis zu vier Worker mit eigenen Analyzern;
SQLite speichert Merkmale. CSV plus JSON-Entwurf sind für ein lokales Einzelprojekt
angemessen; eine zweite Datenbank für UI-Zustand ist derzeit nicht nötig.

GUI und Review sind sehr grosse Module. Weitere Fachlogik in testbare Dienste
extrahieren, besonders Auswahlzustand, Quellenverwaltung und Exporttransaktionen.
Kein Komplettumbau vor der ersten echten Japan-Testauswahl erforderlich.

## Korrigierte Befunde

| Bereich | Vorher | Jetzt |
|---|---|---|
| Erneuter Export | Bisheriges Album vor erfolgreichem Kopieren gelöscht | Temporäre Verzeichnisse, Austausch nach Kopierabschluss, Rollback bei Publikationsfehler |
| CSV/Entwurf/Einstellungen | Teilweise direkte bzw. unzureichend gesicherte Schreibvorgänge | Atomarer Dateiaustausch; CSV und Entwurf zusätzlich fsync |
| Update | Installation trotz fehlgeschlagener Entwurfssicherung möglich | Fehler verhindert Installerstart und Schliessen der App |
| Versionsangaben | Paket 0.2.0, App/Installer 0.3.0 | Konsistente 0.3.0, Build prüft Übereinstimmung |
| Analyse-Cache | Standardfelder konnten übersprungene Analysestufen vortäuschen | Versions-/Options-/Backend-Kennungen, geänderte Filter neu analysieren |
| Hochauflösende JPEGs | Voller Decode vor Verkleinerung | JPEG-Draft vor Analyse-Resize; kleinerer Bildcache mit Dateiänderungsschlüssel |
| Inhaltsähnlichkeit | Einfacher Ersatzvektor konnte echte Motive aussortieren | Automatische Gruppierung nur mit neuronalem Embedding; unpassende Dimensionen nicht vergleichen |
| Serien | Gruppenkennungen konnten nach zweiter Erkennung kollidieren | Fortlaufende eindeutige Kennungen |
| Kontingente | Viele Kapitel/Transits konnten Gesamtziel überschreiten | Begrenzte Budgetverteilung nach geeigneten Bildern |
| Tagesabdeckung | Ruhige Tage konnten schon vor optionaler KI aus Kandidaten verschwinden | Tagesgewichtung schon in Kandidatenbildung |
| Harte Caps | Nicht vorhanden | Albumweite Tagesgrenze, Kapitelgrenze inkl. Essen, Nachbesetzung, Favoritenvorrang |
| Import | Verschachtelte Ausgabe konnte erneut eingelesen werden | Ausgabe-Unterbaum ausgeschlossen, explizite Video-Standbilder weiter zulässig |
| Abbruch | Lokaler Fortschrittshelfer verschluckte Abbruch | Abbruch weitergeben, Cache sichern/schliessen |

## Speicher und Laufzeit

Bilder werden für Analyse und Histogramme verkleinert; ein JPEG-Draft vermeidet
unnötigen Voll-Decode. HEIC/PNG und tatsächliche Modellinferenz können weiterhin
mehr Zeit/Speicher beanspruchen. Parallelität nicht unbesehen erhöhen.

`scripts/benchmark_selection_scale.py` misst pHash/Serien und Embedding-Vergleiche
mit synthetischen Metadaten/Vektoren. `scripts/benchmark_decode_memory.py` vergleicht
JPEG-Decodes. Messungen in `benchmark-results/` sind reproduzierbare **Mikrobenchmarks**,
keine Aussage über die Dauer einer vollständigen 2.000-Bilder-Analyse. Modellstart,
Gesichter, Geocoding, HEIC und Export sind separat zu messen.

Gemessen mit Python 3.12.14 auf dem Linux-Prüfsystem:

| Mikrobenchmark | Zeit | Prozess-Spitzen-RAM |
|---|---:|---:|
| Inhaltscluster, 2.000 Metadaten/Vektoren | 0,287 s | 115,6 MiB |
| Inhaltscluster, 5.000 Metadaten/Vektoren | 1,642 s | 157,9 MiB |
| 8 Decodes einer synthetischen 24-MP-JPEG, Volldecode | 2,254 s | 286,3 MiB |
| Gleicher Decoder-Test, optimierter Draft | 0,421 s | 117,1 MiB |

Der Decoder-Vergleich zeigt hier rund 59 % weniger Spitzen-RAM, kein allgemeines
Laufzeitversprechen für Windows oder echte Urlaubsbilder.

## Standalone und Updates

Windows-Build: `packaging/build_windows.bat` bzw. GitHub Actions **Windows build**.
Ergebnis: `PhotoTool-Setup-0.3.0.exe`, portables ZIP, SHA256-Prüfsummen. Der Build
enthält einen Starttest des gebündelten EXE. Die CI erstellt bei Pull Requests
Artefakte; eine Release-Veröffentlichung erfolgt nur bei passenden Versionstags.

**Verteilungslücke:** Das Quellrepository ist privat. Zum Prüfzeitpunkt gab es
keine veröffentlichten Releases. Der Updater nutzt anonyme GitHub-Release-Abfragen;
private Release-Dateien sind für installierte Clients ohne Authentifizierung
nicht erreichbar. Eine 404 wird nun als nicht verfügbare Updatequelle gemeldet,
nicht als Bestätigung einer aktuellen Installation.

Empfohlen: separater öffentlich lesbarer Release-Speicher mit ausschliesslich
Installern/ZIP/Prüfsummen, Quellcode weiter privat. Alternativ authentifizierter
Update-Dienst. Dafür müssen Updatequelle/Release-Workflow angepasst werden;
kein GitHub-Zugriffstoken ins Programm einbauen. SHA256 prüft Dateiintegrität,
ersetzt aber keine Windows-Codesignatur. Für reguläre Verteilung Codesignatur
und Tests von Neuinstallation, Aktualisierung und Deinstallation vorsehen.

## Verbleibende Grenzen

- Kein transaktionaler Gesamtcommit über CSV, Album und Dokumentpool. Jedes Ziel
  ist besser geschützt, aber ein Fehler kann verschiedene Exportstände hinterlassen.
  Staging braucht zusätzlichen freien Speicher ungefähr in Grösse der exportierten Kopien;
  ein harter Prozessabbruch zwischen Verzeichnis-Renames kann ein Sicherungsverzeichnis
  `.selected-previous-*` hinterlassen.
- Kein Projekt-Locking gegen zwei gleichzeitig schreibende App-Instanzen.
- Review hängt an Originalpfaden; keine interaktive Neuverknüpfung.
- Neuberechnung bewahrt Favoriten, keine dauerhafte Ablehnungsregel.
- Histogrammvielfalt und Motiv-/Gesichtsheuristiken sind keine objektive Bewertung
  persönlicher Erinnerungen. KI-Anbieter wurden ohne Schlüssel nicht live geprüft.
- Sehr grosse Kapitel und Motive ohne Aufnahmedatum können weiterhin quadratische
  Ähnlichkeitsarbeit verursachen; die Messung auf 2.000/5.000 synthetischen Datensätzen
  ersetzt keinen Durchlauf auf dem späteren Windows-Zielrechner.
