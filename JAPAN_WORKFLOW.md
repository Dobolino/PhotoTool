# Japan-Reise: von 2.000+ Fotos zur Fotobuch-Auswahl

PhotoTool erstellt eine Bildauswahl mit gemeinsamem Exportordner oder Kapitelordnern,
kein druckfertiges Layout. Die Funktionen eignen sich ebenso für spätere Reisen.
Für eine zweiwöchige Reise sind **180–250 Bilder als erste Auswahl** ein sinnvoller
Start. Die endgültige Anzahl hängt von Seitenzahl, Bildgrössen und persönlichen
Erinnerungen ab. Automatische Qualitätswerte ersetzen die persönliche Prüfung nicht.

## Oberfläche

1. Originale lokal verfügbar machen, besonders bei iCloud/OneDrive; Originalordner
   behalten. Ausgabe in einen separaten Projektordner schreiben.
2. Zielanzahl z. B. **200**, Tages-Abdeckung **80 %**, Serien maximal **2** Bilder.
3. Unter den erweiterten Optionen: **18 Bilder je Tag**, **60 je Kapitel** als
   Startwerte. `0` hebt die jeweilige Grenze auf. Kapitelgrenzen gelten gemeinsam
   für Hauptteil und Essen, Tagesgrenzen albumweit über alle Kapitel/Transits.
4. Für Japans Nachtstrassen, Restaurants und Tempel zunächst den Filter für schwache
   Nachtaufnahmen sowie den Fehlaufnahmefilter ausschalten. Gegenlicht, Neon und
   Architektur können von einfachen Heuristiken falsch bewertet werden.
5. In der modernen Fotoansicht links die Kapitel prüfen. Bei falschen Ortsnamen
   **Werkzeuge → Orte neu prüfen…** öffnen und die Änderungsvorschau ansehen.
   Offline gibt es nur eine grobe Zuordnung zu bekannten Städten, keine Stadtteile;
   für andere Orte optional Online-Ortsnamen aktivieren.
6. **Diashow** für den gemischten Filmstreifen verwenden: ein Miniaturklick zeigt
   das Foto, **Häkchen / Leertaste** ändert die Auswahl. Grau bedeutet „nicht im
   Album“; die grosse Vorschau bleibt farbig. In **Vergleichen** Albumfoto und
   Alternative ansehen: **Als Ersatz wählen** tauscht ein Foto am selben Platz,
   **Zusätzlich aufnehmen** behält beide. Aufgenommene Alternativen bleiben farbig
   in ihrer Leiste sichtbar. **Albumübersicht** zeigt die Sammlung als Raster.
   **Warum dieses Bild?** und der **Prüfbericht** erklären protokollierte Gründe.
   Unverzichtbare Erinnerungen schützen; ein niedriger Score ist kein Löschgrund.
7. **Pause & speichern**, später dasselbe Reiseprojekt fortsetzen. **Finale Auswahl**
   kopiert die endgültig ausgewählten Bilder: **Ein gemeinsamer Ordner** ist für
   den Import in die Fotobuchsoftware meist am einfachsten; **Nach Kapiteln
   aufteilen** bewahrt die Reiseabschnitte. Alle Originaldateien bleiben unverändert.

Geschützte Favoriten haben Vorrang vor Zielzahl und Grenzen. Manuelle Änderungen
im Review dürfen die automatischen Caps überschreiten. Ohne Aufnahmedatum teilen
Bilder einen gemeinsamen Tages-Bucket; Zeiten deshalb vor der Analyse prüfen.
Eine starre Kapitelgrenze kann die Zielzahl unerreichbar machen. Das Programm
meldet eine kleinere Auswahl und lockert harte Grenzen nicht stillschweigend.

## Reproduzierbarer Kommandozeilenstart

Nach Installation der Entwicklungsabhängigkeiten (siehe README):

```powershell
.\.venv\Scripts\python.exe -m photobook_curator `
  -i "D:\Fotos\Japan_Originale" -o "D:\Fotoalben\Japan_Projekt" `
  -n 200 --coverage-intensity 0.8 `
  --max-per-day 18 --max-per-chapter 60 `
  --burst-seconds 30 --burst-keep 2 --export-layout flat `
  --food-ratio 0.15 --no-weak-night-filter --no-accidental-filter
```

`--export-layout flat` schreibt die finalen Kopien gemeinsam in `selected/`;
`--export-layout chapters` teilt sie in Kapitel-Unterordner (CLI-Standard).

Ohne externe KI: Standard `--ai-provider none`. Für einen Lauf ohne Ortsabfragen
zusätzlich `--no-geocode` setzen. Aktivierte Gesichtserkennung/Embeddings können
Modelldateien beim ersten Start herunterladen; die Fotoanalyse damit erfolgt lokal.
`--no-faces --no-content-clusters` verhindert diese beiden Modellpfade.
Embeddings werden nur bei verfügbarem neuronalem Modell zum automatischen
Aussortieren verwendet; der einfache Ersatzvergleich ist dafür zu unzuverlässig.

Die Zeitkorrektur standardmässig auf **0** lassen. iPhones speichern üblicherweise
bereits die lokale Aufnahmezeit. Japan liegt UTC+9, aber `--timezone-offset-hours 9`
ist deshalb **keine** pauschal richtige Korrektur: Nur die tatsächlich falsche
Kamerazeit korrigieren, sonst verschieben sich Tagesgrenzen.

## Was gespeichert wird

- `photos_analysis.csv`: Metadaten, Scores, Kapitel, Auswahl und Kennzeichnungen.
  Ab 0.4.2 auch begrenzte automatische Auswahlprotokolle und Ortsnachweise.
- `selection_audit.html` / `.csv`: offline lesbarer Prüfbericht der letzten
  Analyse/Ausgabe; im Review lässt sich der aktuelle Stand erneut exportieren.
- `selection_draft.json`: Auswahlentscheidungen, Favoriten, Kapiteländerungen,
  Variantenherkunft, aktuelle Ansicht und Vorschauposition zum Wiederaufnehmen.
- `analysis_cache.sqlite`: wiederverwendbare lokale Analysemerkmale nach Dateipfad,
  Änderungszeit und Grösse. Dies ist ein Feature-Cache, kein Ersatz für den Entwurf.
- `selected/`: nur finale ausgewählte Originalkopien, gemeinsam als
  `001_Dateiname.ext` oder nach Kapiteln. Ein optionaler Dokumentpool gehört nicht
  automatisch zum Album. Originalbilder bleiben für Vorschau und Weiterarbeit nötig.

**Öffnen/Fortsetzen** bewahrt die Entscheidungen des Entwurfs. **Auswahl neu erstellen**
oder eine frische Analyse berechnet die Auswahl neu; Favoriten bleiben geschützt,
explizite dauerhafte Behalten-/Ausschliessen-Entscheidungen werden ebenfalls übernommen. Vor einem Experiment den Projektordner sichern. Verschobene Originale
können über „Originale wiederfinden“ anhand der relativen Pfade neu verknüpft werden.

## Falsche Stadt oder fehlendes GPS

Frühere Versionen konnten bei Hin- und Rückreise über dieselbe Stadt den ganzen
Zwischenzeitraum als Aufenthalt behandeln. Ab 0.4.2 zählen einzelne echte
GPS-Aufnahmen als Zeitanker, nicht der Zeitraum zwischen erstem und letztem Besuch.
Standardmässig darf ein Anker höchstens sechs Stunden entfernt sein; liegen nahe
Anker in unterschiedlichen Städten, bleibt die Zuordnung ungeklärt. Abgeleitete
Bilder verlängern das Zeitfenster nicht. Unterschiedlich eingestellte Kamerauhren
können weiterhin eine manuelle Zeitkorrektur erfordern.
Für die Albumgewichtung zählen nur Tage mit tatsächlichen Aufnahmen in der Stadt,
nicht alle Tage zwischen Hin- und Rückreise über diesen Ort.

Bestehende Projekte werden über **Werkzeuge → Orte neu prüfen…** korrigiert. Die
Vorschau zeigt alte/neue Orte, Kapitel, GPS- oder Zeitbasis und offene Fälle. Erst
das gemeinsame Speichern übernimmt die angezeigten Metadatenkorrekturen. Bestehende
Exportkopien werden beim nächsten Albumexport aktualisiert. Manuell zugewiesene Kapitel bleiben
erhalten. Der Rückgängig-Verlauf beginnt nach dem Speichern neu.

Eine Motivbeschreibung wie „Nara Park, Japan“ ist kein verifizierter Ortsnachweis.
Der Bericht nennt deshalb die tatsächliche GPS-/Zeitquelle separat. Bei älteren
Auswahlen fehlen die damaligen automatischen Auswahlgründe; eine neue lokale
Auswahl zeichnet sie auf, ohne einen kostenpflichtigen KI-Dienst zu benötigen.

## Erweiterungen ab 0.4.0

Die folgenden Vorschläge sind inzwischen als allgemeine Reisefunktionen umgesetzt
(siehe [Bedienung](REISEPROJEKTE.md)); Motive und Erzählrollen bleiben Heuristiken.

1. **Dauerhaft behalten/ablehnen mit Begründung**: getrennt vom aktuellen Auswahlstatus;
   bei Neuberechnung und erneuter Analyse konsequent übernehmen.
2. **Originalordner neu verknüpfen** und portable Projektdatei: Urlaub später von einer
   externen Platte öffnen, ohne manuelle CSV-Pfadkorrektur.
3. **Motivgruppen als Vorschläge**: z. B. Fushimi Inari, Street, Essen, Tempel. Pro
   konkretem Motiv 1–2 Varianten wählen; Ähnlichkeit allein nicht mit Duplikat
   gleichsetzen. Aktuell sind neuronale Embeddings MobileNet-basiert, kein CLIP-
   Reiseverständnis. Schwellenwerte mit echten Japanbildern kalibrieren.
4. **Erzählstruktur und Seitenbudget**: Tageshöhepunkte, Übersicht–Detail–Menschen,
   ruhige und belebte Szenen, Hoch-/Querformat und Platz für Doppelseiten.
5. **Unsichere Entscheidungen zuerst prüfen**: vergleichbare Aufnahmen und
   aufgezeichnete Auswahlgründe ansehen, statt alle 2.000 Bilder gleich intensiv
   durchzusehen. Erweiterte Prüfwerkzeuge bleiben über **Werkzeuge** erreichbar.

Lokale Gesichterkennung, Gesichtsqualität, Personenbalance, Serienvergleich,
Druckqualitätsprüfung, Favoriten, Undo/Redo und Vorschau sind bereits vorhanden.
Personenbalance ist eine optionale Heuristik und keine verlässlich benannte
Personenerkennung. Vor neuen Modulen zuerst diese vorhandenen Funktionen mit
50–100 repräsentativen Japanbildern prüfen.

## Windows und lokales Arbeiten

Die neue Fotoansicht läuft im eigenen WebView2-Programmfenster mit lokal
gebündelten HTML-Dateien und einem nur auf `127.0.0.1` erreichbaren,
sitzungsgebundenen Dienst. Dafür werden keine Fotos ins Internet übertragen.
Der Windows-Installer installiert eine fehlende Microsoft-WebView2-Laufzeit per
Internet; das portable ZIP benötigt diese bereits. Für das fertige Programm ist
kein Python nötig. Online-Ortsnamen, externe KI und Modell-/Update-Downloads sind
separate Netzwerkfunktionen.

Die bisherigen 2.000er-Messungen und der moderne Oberflächen-Prüflauf verwenden
synthetische Testdaten. Sie belegen keine Auswahlqualität für deine persönlichen
Japanbilder. Vor der ganzen Sammlung 50–100 repräsentative Fotos prüfen und
anschliessend den vollständigen Lauf auf deinem Windows-PC kontrollieren.
