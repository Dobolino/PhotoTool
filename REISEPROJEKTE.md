# PhotoTool 0.5.0: Jede Reise, ein eigenes Album

PhotoTool reduziert grosse Fotosammlungen für ein Fotobuch. Das endgültige
Drucklayout entsteht danach in deiner Fotobuchsoftware. Reiseprojekte speichern
Quellen, Einstellungen, Auswahl und Entscheidungen für beliebige Urlaube.
Bestehende Projekte und Entwürfe bleiben nutzbar.

## Der Ablauf

1. **Reise importieren:** Projektname, Originalordner und eigenen Projekt-/
   Ausgabeordner festlegen. Bestehende Reisen über die Projektliste oder ihre
   Projektdatei öffnen. Originale müssen lokal verfügbar sein.
2. **Album planen:** Reiseprofil und Zielanzahl wählen oder aus Buchseiten,
   reservierten Seiten und Fotos pro Seite berechnen lassen. Beispiel: 80 Seiten,
   davon 4 für Titel/Text, bei 2,5 Fotos pro Bildseite ergeben 190 Zielbilder.
   Das ist ein Auswahlbudget, kein Layout.
3. **Analysieren:** Die lokale Analyse prüft Qualität, Duplikate, Serien und Orte.
   Tages-/Kapitelgrenzen und optionale Erzählbalance steuern die Verteilung.
4. **Auswahl prüfen:** grosse Vorschau, direkter Vergleich und Albumübersicht
   verwenden. Entscheidungen werden automatisch gespeichert.
5. **Finale Auswahl:** nur die ausgewählten Originaldateien als Kopien in einen
   gemeinsamen Ordner oder Kapitelordner exportieren. Originale bleiben unverändert.

## Die moderne Fotoansicht

Die freigegebene HTML-Oberfläche ist mit den echten Projektbildern und dem
bestehenden Python-Auswahlzustand verbunden. Links wählst du die ganze Reise oder
ein Kapitel. **Dunkel / Hell** ändert die Darstellung. Die drei Ansichten teilen
sich Auswahl, Favoriten und denselben gespeicherten Zwischenstand:

- **Diashow (A):** ein grosses Foto mit Informationen rechts und einem gemischten
  Filmstreifen unten. **Alle**, **Im Album** und **Alternativen** filtern die Leiste.
- **Vergleichen (B):** Albumfoto und Alternative mit eigenen Bildleisten vergleichen.
  **Zusätzlich aufnehmen** behält beide; **Als Ersatz wählen** tauscht genau das
  gewählte Albumfoto am bisherigen Platz aus. Ein Rückgängig-Schritt nimmt den
  gesamten Austausch zurück.
- **Albumübersicht (C):** Bilder als durchblätterbares Raster überblicken und öffnen.
  Die Ansicht lädt grosse Sammlungen abschnittsweise.

**Miniatur anklicken = ansehen. Häkchen / Leertaste = auswählen.** Die grosse
Vorschau bleibt auch für ein nicht ausgewähltes Bild farbig. Im Filmstreifen sind
nicht ausgewählte Fotos grau, ausgewählte Fotos farbig mit Häkchen. Der Rahmen
kennzeichnet separat das aktuell betrachtete Foto. Grau bedeutet „nicht im Album“;
es sagt nichts über eine dauerhafte Ablehnung oder die Originaldatei aus.

Eine aufgenommene Alternative bleibt in ihrer Vergleichsleiste sichtbar und wird
farbig. Dadurch verschwindet sie beim Entscheiden nicht sofort aus dem Blick.
Entfernte Albumfotos werden als Alternativen erreichbar. Ein Alternativvorschlag
ist kein Beweis für dasselbe Motiv; vorhandene Serien-/Motivnachweise und weitere
Aufnahmen werden in den Informationen unterschieden.

**Pause & speichern** sichert den Stand und schliesst die Prüfung. Beim Fortsetzen
werden Auswahl, Kapitel, Vorschau, Ansicht und Darstellung wiederhergestellt.
Automatisches Speichern ergänzt diese Aktion. Bei einem Speicherfehler bleibt der
reguläre Abschluss blockiert und die Meldung sichtbar. Undo/Redo gilt für die Sitzung.

## Warum ein Bild ausgewählt wurde

**Warum dieses Bild?** zeigt technische Merkmale, aufgezeichnete automatische
Entscheidungen, aktuelle manuelle Vorgaben und tatsächliche Ortsnachweise.
**Werkzeuge → Prüfbericht als HTML / CSV** exportiert den aktuellen Stand;
beim Albumexport entstehen ebenfalls `selection_audit.html` und
`selection_audit.csv`. Diese Berichte funktionieren offline.

Nur tatsächlich protokollierte Vergleiche, Filter und Kontingentschritte werden
erklärt. Bei alten oder unvollständigen Läufen fehlen die damaligen Gründe
sichtbar; ein heutiger Score wird nicht als damalige Entscheidungsursache ausgegeben.
Eine Motivbeschreibung ist kein verifizierter GPS-Ort.

## Werkzeuge und Ortsprüfung

**Werkzeuge** hält vorhandene Funktionen erreichbar: Prüfbericht, **Orte neu
prüfen**, **Originale wiederfinden**, Druckqualität, Motivgruppen, Erzählmix,
Kapitelplanung und Neuberechnung. Erweiterte Prüfwerkzeuge öffnen bei Bedarf die
vorhandene native Oberfläche mit dem gespeicherten aktuellen Projektstand.

Die Ortsprüfung zeigt Änderungen vor dem Speichern. GPS-Aufnahmen sind die
Grundlage; GPS-lose Bilder verwenden nur nahe echte GPS-Zeitanker. Widersprüche
und fehlende Grundlagen bleiben ungeklärt. Offline dient ein kleiner Städtekatalog
als Näherung bis 25 km, keine Stadtteilerkennung. Optional liefert Nominatim
Online-Ortsnamen. Die Auswahl und manuellen Entscheidungen bleiben erhalten.

**Motivgruppen** nutzen vorhandene Serien, Inhaltscluster, pHash und Szenenlabels.
„Beste 1–2 übernehmen“ bleibt eine bewusste Benutzeraktion, unter Berücksichtigung
geschützter Bilder. Die Gruppen sind Vergleichsvorschläge. **Erzählmix** zeigt
Übersicht, Menschen, Details und Atmosphäre je Kapitel anhand vorhandener Merkmale.
Eine Naturreise muss nicht alle Kategorien abdecken. Die **Druckqualitätsprüfung**
berücksichtigt Bildmasse, gewünschte Druckgrösse, Beschnitt und Ziel-DPI.

## Lokal auswählen oder mit KI ergänzen

**Lokale Auswahl erstellen** liefert bereits eine vollständige Auswahl ohne
KI-Anbieter. Bildqualität, Duplikate, Serien, Tage und Kapitel werden berücksichtigt.
Danach kannst du prüfen, verändern und exportieren.

KI ist eine optionale zusätzliche Bewertung. Nach Wahl eines Anbieters kannst du
einen weiteren Lauf starten; vorhandene lokale Analysewerte werden soweit möglich
wiederverwendet. Innerhalb eines KI-Laufs gilt: lokale Analyse → Kandidaten →
KI-Bewertung → endgültige Auswahl. Es werden nicht automatisch alle Originale an
einen Anbieter geschickt. **Nur Kosten schätzen** startet keine KI-Bewertung und
liefert keine fertige Auswahl. API-Schlüssel werden nicht in Projektdateien gespeichert.

## Einstellungen, Profile und Entscheidungen

**Auswahl anpassen** gruppiert Bildqualität, Abwechslung und KI; Änderungen gelten
für den nächsten Analyselauf. Nach dem Start zeigt eine eigene Fortschrittsansicht
die aktuelle Aufgabe. Das technische Protokoll bleibt bei Bedarf aufklappbar.

Profile sind veränderbare Startwerte: **Ausgewogene Reise**, **Städtereise**,
**Strand / Natur**, **Rundreise** oder **Eigene Einstellungen**. Ein Profilwechsel
startet keine Analyse und ändert keine Bildentscheidung von selbst.

Die aktuelle Auswahl und eine dauerhafte Vorgabe sind verschieden:

- **Dauerhaft behalten:** auch bei neuer Analyse oder Auswahl berücksichtigen.
- **Dauerhaft ausschliessen:** bei Neuberechnung nicht automatisch aufnehmen.
- **Automatik:** die dauerhafte Vorgabe aufheben.

Eine eigene Begründung lässt sich speichern. Favoritenschutz hat Vorrang; Schutz
zuerst aufheben, wenn ein Bild entfernt werden soll. Geschützte oder dauerhaft
behaltene Bilder können Zielzahl und automatische Caps überschreiten. Die
Entscheidungsaktionen bleiben über die Fotoaktionen und Prüfwerkzeuge zugänglich.

## Verschobene Originale wiederfinden

**Originale wiederfinden** ordnet einen bisherigen gemeinsamen Originalordner
einem neuen Stammordner zu. Die relative Ordnerstruktur muss erhalten sein.
Die Vorschau zeigt fehlende oder mehrdeutige Ziele, statt sie zu raten. CSV und
Entwurf werden gemeinsam mit Wiederherstellungsprotokoll aktualisiert; Originale
werden weder verändert noch neu analysiert. Bei einem gespeicherten Reiseprojekt
wird auch dessen Originalordner aktualisiert. Unvollständige Quellkopien werden
nicht als neuer gemeinsamer Stammordner übernommen.

## Export, Dateien und Updates

**Finale Auswahl** zeigt vor dem Schreiben die aktuelle Auswahl und Zielstruktur:
**gemeinsamer Ordner** erzeugt `selected/001_Dateiname.ext`, **Kapitel** unterteilt
`selected/` nach der bestehenden Kapitelzuordnung. Nur endgültig ausgewählte
Bilder gehören zum Albumexport. Ein optionaler separater Dokumentpool bleibt davon
getrennt. Vorschau und spätere Weiterarbeit brauchen weiterhin die Originale.

`phototool_project.json` speichert Reise, Quellen und Einstellungen;
`selection_draft.json` den Bearbeitungsstand; `photos_analysis.csv` Analyse,
Metadaten und Protokolle. `analysis_cache.sqlite` beschleunigt weitere Läufe.
Ein neuer Export übernimmt die aktuellen Entscheidungen; eine Neuberechnung
entscheidet erneut unter Berücksichtigung von Favoriten und dauerhaften Vorgaben.

Stabile Windows-Installer und portable ZIPs stehen in GitHub Releases. Die moderne
Fotoansicht läuft unter Windows im eigenen WebView2-Programmfenster; HTML und Fotos
werden ausschliesslich lokal über einen sitzungsgebundenen Dienst bereitgestellt.
Der Installer richtet eine fehlende Microsoft-WebView2-Laufzeit per Internet ein;
das portable ZIP setzt sie voraus. Für PhotoTool selbst ist kein Python nötig.
**Updates** prüft neue stabile Versionen. Vor einer Installation werden Entwürfe
gesichert; Fehler verhindern den Installerstart. Online-Geocoding und externe KI
bleiben unabhängig davon optionale Netzwerkfunktionen.

## Frühere Aufnahmen

Die Bilder unter `docs/screenshots/phototool-0.4.*` dokumentieren die damalige
Tk-Oberfläche und synthetische Testprojekte. Sie zeigen nicht die neue
Standard-Fotoansicht von 0.5.0.
