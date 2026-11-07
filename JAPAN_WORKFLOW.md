# Japan-Reise: von 2.000+ Fotos zur Fotobuch-Auswahl

PhotoTool erstellt eine Bildauswahl und Kapitelordner, kein druckfertiges Layout.
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
5. Karten/Kapitel prüfen, danach Varianten vergleichen und unverzichtbare Erinnerungen
   als Favoriten schützen. Ein niedriger Qualitätsscore ist kein Löschgrund.
6. **Pause & speichern**, später denselben Ausgabeordner öffnen. **Album exportieren**
   kopiert die fertige Auswahl für die Fotobuchsoftware.

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
  --burst-seconds 30 --burst-keep 2 `
  --food-ratio 0.15 --no-weak-night-filter --no-accidental-filter
```

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
- `selection_draft.json`: Auswahlentscheidungen, Favoriten, Kapiteländerungen,
  Variantenherkunft und Vorschauposition für das Wiederaufnehmen.
- `analysis_cache.sqlite`: wiederverwendbare lokale Analysemerkmale nach Dateipfad,
  Änderungszeit und Grösse. Dies ist ein Feature-Cache, kein Ersatz für den Entwurf.
- `selected/`: exportierte Kopien; Originalbilder bleiben für Review/Vorschau nötig.

**Öffnen/Fortsetzen** bewahrt die Entscheidungen des Entwurfs. **Auswahl neu erstellen**
oder eine frische Analyse berechnet die Auswahl neu; Favoriten bleiben geschützt,
explizite dauerhafte Behalten-/Ausschliessen-Entscheidungen werden ebenfalls übernommen. Vor einem Experiment den Projektordner sichern. Verschobene Originale
können über „Originale wiederfinden“ anhand der relativen Pfade neu verknüpft werden.

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
5. **Unsichere Entscheidungen zuerst prüfen**: beste Alternative plus konkrete
   Auswahlgründe zeigen, statt alle 2.000 Bilder gleich intensiv durchsehen.

Lokale Gesichterkennung, Gesichtsqualität, Personenbalance, Serienvergleich,
Druckqualitätsprüfung, Favoriten, Undo/Redo und Vorschau sind bereits vorhanden.
Personenbalance ist eine optionale Heuristik und keine verlässlich benannte
Personenerkennung. Vor neuen Modulen zuerst diese vorhandenen Funktionen mit
50–100 repräsentativen Japanbildern prüfen.
