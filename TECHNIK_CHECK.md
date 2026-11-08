# Technischer Check und umgesetzte Härtung

Stand 0.5.1. Bedienung: [Reiseprojekte und moderne Fotoansicht](REISEPROJEKTE.md).
Die Messungen weiter unten dokumentieren frühere Härtungsläufe und sind ausdrücklich
synthetisch; es lagen keine privaten Urlaubsbilder vor.

Geprüfter Ausgangspunkt: `codex/review-metadata-fixes`.
Ziel: grosse Urlaubssammlungen reduzieren, Entscheidungen fortsetzen, als
Windows-Programm ausliefern. Prüfung anhand von Code, automatisierten Tests und
synthetischen Messungen; keine privaten Urlaubsbilder lagen vor.

## 0.5.1: Lange Kapitellisten und sichtbare Fotos

Die kurze native Testreise aus 0.5.0 deckte einen Fehler bei langen Kapitellisten
nicht ab: Die automatische Mindestgrösse der CSS-Grid-Zeile liess die gesamte
Fotoansicht wachsen. Mit 2.618 erzeugten JPEGs und 43 langen Kapiteln war das
Dokument bei 1280 × 720 etwa 3.598 Pixel hoch. Bilder und Aktionen lagen ausserhalb
des Fensters. Die Fotoanalyse und der gespeicherte Auswahlstand waren nicht die
Ursache.

App-Zeile und Vorschau sind nun durch die Fensterhöhe begrenzt. Kapitel und
Bilderraster scrollen unabhängig; Fotos werden vollständig eingepasst.
563 lokale Tests bestanden. Im echten Chromium bestanden alle 18 Kombinationen
aus Diashow, Vergleich und Albumübersicht bei 1920 × 1080, 1536 × 864,
1366 × 768, 1280 × 720, 1093 × 614 und 980 × 600. Die letzten kompakten Prüfungen
bestätigten sichtbare Aktionen, Kapitel-Scrollposition nach Hinzufügen/Undo,
geladenes Logo und Ortsdialog ohne Veränderung der Auswahl.

Reproduktion mit Node und Chromium, neuer/leerer Ausgabeordner erforderlich:

```bash
python scripts/check_review_layout.py --output /tmp/phototool-layout-check
```

Die native Windows-Prüfung verwendet jetzt 92 Test-JPEGs und 44 Kapitel. Sie
verlangt nach dem Rendern jeder Ansicht eine neue, geometrisch geprüfte
Bestätigung. Ein bereits geladenes, aber ausserhalb des Fensters liegendes Foto
genügt nicht mehr. Der Windows-Lauf für 0.5.1 steht bei diesem Quellstand noch aus.

Unbelegte Ortsangaben und eindeutige Konflikte zwischen gespeicherter Stadt und
Motivbeschreibung werden nur als prüfbedürftig markiert. KI-Text wird nie zum
Ortsnachweis. Die vorhandene GPS-/Zeitprüfung bietet Änderungsvorschläge vor
dem Speichern; Auswahl und Favoriten bleiben bestehen. Eindeutig passende
Transit-Alternativen verwenden beim Aufnehmen und Ersetzen denselben Exportordner.

## 0.5.0: Lokale Fotooberfläche und Export

Die freigegebene HTML-Oberfläche ist mit den echten `Photo`-/`BookPlan`-Daten
verbunden. Diashow (A), Vergleich (B) und Albumübersicht (C) verwenden denselben
Auswahlzustand; es gibt keinen zweiten Browser-Datensatz mit unabhängigen
Entscheidungen. Nicht ausgewählte Miniaturen sind grau, die grosse Vorschau bleibt
farbig. Klicken zum Betrachten und Häkchen/Leertaste zum Auswählen sind getrennt.
Die Alternativen bleiben nach Aufnahme sichtbar. Hinzufügen und positionsgetreues
Ersetzen sind eigene Aktionen; Ersetzen ist gemeinsam rückgängig zu machen.

`modern_review_session.py` bündelt Änderungen, Revisionen, autospeicherbare
Entwürfe und Hintergrundaufgaben. Bestehende Projekte, Favoriten, dauerhafte
Vorgaben, Auswahlprotokolle und Ortsnachweise werden weiterverwendet. Der Entwurf
speichert auch Ansicht, Kapitel und Fokus. Die vorhandenen erweiterten Tk-Werkzeuge
bleiben über eine Desktop-Brücke erreichbar; Import und Analyse bleiben native
Tk-Ansichten im passenden Farbsystem.

`modern_review.py` stellt die gebündelten Webdateien und zugelassene Foto-IDs über
einen sitzungsgebundenen HTTP-Dienst ausschliesslich auf `127.0.0.1` bereit.
Sitzungstoken und Host-/Ursprungsprüfungen begrenzen den Zugriff. Unter Windows
öffnet ein eigener Prozess das native pywebview-/WebView2-Fenster; Tk behält den
Projekt- und Speicher-Lebenszyklus. Es werden weder externe Webassets geladen noch
Fotos für die Oberfläche an einen gehosteten Dienst gesendet. Optionale KI,
Geocoding, Updates und anfängliche Modell-/Laufzeitdownloads sind davon getrennt.

Der Filmstreifen rendert einen begrenzten Ausschnitt, die Albumübersicht einzelne
Seiten. Die Exportvorschau zeigt die gewählte Ordnerstruktur; der Export validiert
Dateinamen und Zielpfade vor dem Schreiben. `flat` schreibt
nur ausgewählte Kopien mit globaler Albumreihenfolge in `selected/`, `chapters`
nutzt die bisherige Kapitelstruktur. Staging und Rollback schützen einen bisherigen
Export bei Kopier-/Publikationsfehlern. Originaldateien werden nicht geändert.

`scripts/modern_end_to_end.py` prüft die echte HTML-Ansicht gegen ein vorhandenes
synthetisches Foto-Projekt: alle importierten Bilder erreichbar, begrenztes
Rendering, Vorschau ohne Auswahländerung, Auswahl über Häkchen, stabile Alternativen,
Hinzufügen/Ersetzen/Undo, Speichern/Fortsetzen sowie Flat- und Kapitelexport mit
Datei-/Hashvergleich. Der abschliessende lokale Chromium-Lauf bestand in
**34,345 s** mit **2.000 synthetischen 24-MP-JPEGs** und bereits vorhandener Analyse.
Er prüfte zusätzlich
Kapitelgrenzen im Vergleich, leere Kapitel und das Speichern zuletzt eingereihter
Auswahl-/Ansichtsänderungen beim Schliessen. Nach dem bewusst hinzugefügten letzten
Foto blieben 178 Bilder ausgewählt. Flat- und Kapitelexport wurden bytegenau sowie
nach erneutem Öffnen kontrolliert. Nach der abschliessenden Härtung bestanden
**542 lokale Tests** in **16,10 s**.
Diese Zahlen messen weder eine frische Bildanalyse noch die Qualität einer echten
Japan-Auswahl. Es wurden keine privaten Reisebilder oder KI-/Geocodingdienste
verwendet. Der Lauf prüft Chromium unter Linux; er ersetzt keinen nativen
Windows-/WebView2-Durchlauf.

Der [Windows-Durchlauf](https://github.com/Dobolino/PhotoTool/actions/runs/42433269474)
bestand mit **537 Tests und 2 übersprungenen Fällen**. Quellstart und gebündelte EXE
haben alle drei Ansichten mit echten Testdateien gerendert und das Schliessen mit
Speicherbestätigung geprüft. Auch frische Installation und erneute Installation
in denselben Ordner bestanden einschliesslich Start der installierten Fotoansicht.
Die [Windows-Aufnahmen](docs/screenshots/phototool-0.5.0-review-a-windows-test.png)
zeigen die gebündelte App mit erzeugten Testmotiven. Die Veröffentlichung verlangt
dieselben Prüfungen erneut auf dem endgültigen Release-Tag.

## Historische Ergänzung 0.4.2: Nachvollziehbarkeit und Nachkontrolle

- Auswahlentscheidungen werden am tatsächlichen Filter-/Vergleichs-/Kontingent-
  Schritt protokolliert, maximal 24 Ereignisse pro Bild. Nur ein erfolgreich
  abgeschlossener Lauf erhält einen endgültigen Status; alte oder abgebrochene
  Protokolle liefern keine erfundenen Rankinggründe. CSV und Entwurf bewahren
  Protokolle, manuelle Vorgaben und Ortsnachweise getrennt.
- Wiederholte Ortsbesuche erzeugen keine flächendeckende Zeitzuordnung mehr:
  unveränderliche GPS-Anker, binäre Zeitsuche, keine Kette über abgeleitete Bilder.
  Widersprüchliche Anker und ungültige GPS-Daten werden kenntlich gemacht.
  Die Albumgewichtung zählt tatsächliche Fototage statt Zeitspannen zwischen
  wiederholten Besuchen derselben Stadt.
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

Im damaligen 0.4.2-Prüflauf separat mit derselben synthetischen
2.000-Dateien-Sammlung in der nativen Tk-Oberfläche geprüft:
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

Die neue Fotoansicht trennt Session, lokale Übertragung, Frontend und nativen
Fensterhost. Die bestehenden grossen Tk-Module bleiben für Analyse und erweiterte
Werkzeuge relevant. Gemeinsame Fachlogik sollte weiterhin in testbare Dienste
wandern, ohne die gespeicherten Projekte oder bestehenden Werkzeuge zu duplizieren.

## Historische Härtung ab 0.3.1

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
Ergebnis: `PhotoTool-Setup-<Version>.exe`, portables ZIP und SHA256-Prüfsummen.
Die CI erstellt bei Pull Requests Artefakte; eine Release-Veröffentlichung erfolgt
nur bei passenden Versionstags und bestandenen Prüfungen. Paket, Installer und
Tag müssen dieselbe Version tragen. Gebündelte Webassets und der native
WebView2-Foto-Render sind Teil der Build-/Installer-Prüfkriterien.

Der Installer enthält Microsofts signaturgeprüften WebView2-Bootstrapper und
startet ihn nur bei fehlender Laufzeit. Dieser lädt die Laufzeit über das Internet.
Das portable ZIP setzt WebView2 voraus. Python selbst ist im Programm enthalten.

**Historischer Befund aus 0.3.1 (inzwischen öffentlich):** Das Quellrepository war privat. Zum Prüfzeitpunkt gab es
keine veröffentlichten Releases. Der Updater nutzt anonyme GitHub-Release-Abfragen;
private Release-Dateien sind für installierte Clients ohne Authentifizierung
nicht erreichbar. Eine 404 wird nun als nicht verfügbare Updatequelle gemeldet,
nicht als Bestätigung einer aktuellen Installation.

Die aktuelle Updatequelle ist das öffentliche GitHub-Repository; ein privater
Release-Dienst ist dafür nicht nötig. Kein GitHub-Zugriffstoken ins Programm
einbauen. SHA256 prüft Dateiintegrität und ersetzt keine Windows-Codesignatur.
Neuinstallation, Aktualisierung und Deinstallation bleiben auf Windows zu prüfen;
ein bestandener Linux-/Chromium-Lauf ersetzt diese Tests nicht.

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
