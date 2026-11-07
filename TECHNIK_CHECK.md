# Technischer Check und umgesetzte Härtung

Historischer Check der Härtung 0.3.1; für die neue Oberfläche und Reiseverwaltung
siehe [Reiseprojekte 0.4](REISEPROJEKTE.md). Die damalige private Updatequelle ist
inzwischen öffentlich.

Geprüfter Ausgangspunkt: `codex/review-metadata-fixes`.
Ziel: grosse Urlaubssammlungen reduzieren, Entscheidungen fortsetzen, als
Windows-Programm ausliefern. Prüfung anhand von Code, automatisierten Tests und
synthetischen Messungen; keine privaten Urlaubsbilder lagen vor.

## Ergänzung 0.4.2: Nachvollziehbarkeit und Nachkontrolle

- Auswahlentscheidungen werden am tatsächlichen Filter-/Vergleichs-/Kontingent-
  Schritt protokolliert, maximal 24 Ereignisse pro Bild. Nur ein erfolgreich
  abgeschlossener Lauf erhält einen endgültigen Status; alte oder abgebrochene
  Protokolle liefern keine erfundenen Rankinggründe. CSV und Entwurf bewahren
  Protokolle, manuelle Vorgaben und Ortsnachweise getrennt.
- Wiederholte Ortsbesuche erzeugen keine flächendeckende Zeitzuordnung mehr:
  unveränderliche GPS-Anker, binäre Zeitsuche, keine Kette über abgeleitete Bilder.
  Widersprüchliche Anker und ungültige GPS-Daten werden kenntlich gemacht.
- Ortsreparaturen besitzen eine Vorschau und gemeinsamen CSV-/Entwurf-Commit
  mit Journal-Wiederherstellung. Neuere Ortsnachweise werden nicht durch alte
  automatische Kapitelzuordnungen im Entwurf überschrieben.
- Vergleichsansicht zeigt Albumfoto und Alternative mit explizitem Ersetzen oder
  Hinzufügen; gemeinsamer Undo-Schritt, Albumplatz und Wiederaufnahme geprüft.
  Schmale Fenster schalten die Bildseite um.

Zusätzlicher End-to-End-Test mit 2.000 physischen synthetischen 24-MP-JPEGs:
Pipeline mit neuem Analyse-Cache **28,345 s / 288,4 MiB**, Prüfbericht aufbauen
**0,100 s**, HTML/CSV **0,157 s**, CSV laden **0,186 s**, Entwurf speichern und
erneut anwenden **0,653 s**, manueller Export **0,358 s**. 177 Originalkopien wurden
vor und nach manueller Anpassung über exakten Zielpfad und SHA-256 geprüft;
Favoriten, Behalten/Ablehnen, Begründungen und Protokolle blieben erhalten.
Gesamter Prüfprozess: **344,8 MiB** Spitzen-RAM. Wiederholte geometrische Vorlagen;
Gesichter, Embeddings, KI, HEIC, Online-Geocoding und GUI aus dieser Messung
ausgeschlossen. Kein Qualitäts- oder Laufzeitversprechen für echte Reisebilder.

Separat mit derselben 2.000-Dateien-Sammlung in der nativen Tk-Oberfläche geprüft:
Projekt öffnen, Variantenvergleich, genau ein Bild ersetzen, gemeinsames
Rückgängig/Wiederholen, Rückkehr zum gleichen Albumplatz, Pause und Wiederaufnahme,
Prüfbericht öffnen und erneuter Albumexport mit Bericht. Alle Auswahlindizes
blieben bei der Wiederaufnahme exakt erhalten. Zusätzlich automatisierte native
Bedientests und Windows-Aufnahmen für reguläre/maximierte Fenstergrössen.

Reproduktion nach Datensatzerzeugung mit `benchmark_pipeline_scale.py`:

```bash
python scripts/benchmark_audit_lifecycle.py --input /tmp/phototool-benchmark/input --output /tmp/phototool-audit-test
```

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
| Versionsangaben | Paket 0.2.0, App/Installer 0.3.0 | Neue Version 0.3.1, Build prüft Übereinstimmung |
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

Zusätzlicher vollständiger Pipeline-Test mit 2.000 physischen 6.000×4.000-JPEGs
(rund 1 GB), zehn wiederholten geometrischen Vorlagen, 14 EXIF-Aufnahmetagen und
GPS für Tokyo/Kyoto/Osaka:

- Kalter Analyse-Cache: **36,945 s**, **288,5 MiB** Prozess-Spitzen-RAM; Ziel 80,
  80 ausgewählt und tatsächlich exportiert, keine unlesbaren Dateien.
- Wiederverwendeter Cache, Japan-Einstellungen (Ziel 200, Tages-Abdeckung 0,8,
  Tagesgrenze 18, Kapitelgrenze 60): **5,066 s**, **211,4 MiB**; 177 Bilder
  ausgewählt und exportiert. Alle 14 Tage vertreten, höchstens 15 Bilder je Tag;
  Kapitel Tokyo/Kyoto/Osaka: 60/60/57 Bilder. Drei Kapitel mit je maximal 60
  erlauben höchstens 180 Bilder; 200 sind mit diesen Grenzen unerreichbar.
- Enthalten: Scan/EXIF, lokale Qualität/Dokument-/Kompositions-/Ästhetikprüfung,
  pHash/Serien, Orte, Auswahl, CSV, Kopierexport. Ausgeschlossen: Gesichter,
  Embeddings, externe KI, Netzwerk-Geocoding, HEIC und GUI. Wiederholte Vorlagen
  vereinfachen die Reduktion; keine Aussage über reale Auswahlqualität.

Reproduktion auf einem Entwicklungscheckout (ca. 1 GB freie Platte zusätzlich
zum Export einplanen; Verzeichnis ausschliesslich für Testdateien verwenden):

```bash
python scripts/benchmark_pipeline_scale.py --work-dir /tmp/phototool-benchmark generate
python scripts/benchmark_pipeline_scale.py --work-dir /tmp/phototool-benchmark run --target 80
python scripts/benchmark_pipeline_scale.py --work-dir /tmp/phototool-benchmark run --target 200 --coverage 0.8 --max-per-day 18 --max-per-chapter 60
```

## Standalone und Updates

Windows-Build: `packaging/build_windows.bat` bzw. GitHub Actions **Windows build**.
Ergebnis: `PhotoTool-Setup-0.3.1.exe`, portables ZIP, SHA256-Prüfsummen. Der Build
enthält einen Starttest des gebündelten EXE. Die CI erstellt bei Pull Requests
Artefakte; eine Release-Veröffentlichung erfolgt nur bei passenden Versionstags.

**Historischer Befund aus 0.3.1 (inzwischen öffentlich):** Das Quellrepository war privat. Zum Prüfzeitpunkt gab es
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
- Weiterhin kein allgemeines Projekt-Locking gegen zwei gleichzeitig schreibende App-Instanzen.
- Ab 0.4.0 gibt es interaktive Neuverknüpfung per Stammordner mit Vorschau.
- Ab 0.4.0 bewahrt Neuberechnung auch explizite Behalten-/Ablehnen-Entscheidungen.
- Histogrammvielfalt und Motiv-/Gesichtsheuristiken sind keine objektive Bewertung
  persönlicher Erinnerungen. KI-Anbieter wurden ohne Schlüssel nicht live geprüft.
- Sehr grosse Kapitel und Motive ohne Aufnahmedatum können weiterhin quadratische
  Ähnlichkeitsarbeit verursachen; die Messung auf 2.000/5.000 synthetischen Datensätzen
  ersetzt keinen Durchlauf auf dem späteren Windows-Zielrechner.
