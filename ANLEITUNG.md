# PhotoTool 0.5.0: Schritt für Schritt zur Fotoauswahl

Für Windows ist der Installer `PhotoTool-Setup-<Version>.exe` unter
[GitHub Releases](https://github.com/Dobolino/PhotoTool/releases) der einfachste
Einstieg. Er installiert PhotoTool und richtet bei Bedarf Microsoft Edge WebView2
ein. Python brauchst du dafür nicht. Eine bestehende Installation aktualisierst
du über **Updates** im Programm oder den neueren Installer.

Ausführliche Bedienung: [Reiseprojekte und Fotoansicht](REISEPROJEKTE.md).
Für den Quellcode-Start und dessen Aktualisierung: [START.md](START.md).

## 1. Reise anlegen

Originalfotos lokal verfügbar machen, besonders bei OneDrive oder iCloud. Eine
neue Reise mit Namen, Originalordner und einem separaten Projekt-/Ausgabeordner
anlegen. Das Projekt speichert Einstellungen und Entscheidungen für diese Reise.

Für einen Japan-Urlaub mit etwa 2.000 Fotos sind **200 Zielbilder** ein brauchbarer
Start. Die passende Anzahl hängt von deiner Seitenzahl und den gewünschten
Bildgrössen ab. Weitere Startwerte stehen im [Japan-Workflow](JAPAN_WORKFLOW.md).

## 2. Lokale Auswahl erstellen

Profil und Zielanzahl einstellen, dann **Lokale Auswahl erstellen** starten.
Damit entsteht bereits eine vollständige Auswahl ohne externen KI-Anbieter.
KI lässt sich später ergänzen; **Nur Kosten schätzen** erzeugt keine fertige
Auswahl. Optionale Ortsabfragen und anfängliche Modelldownloads benötigen Internet.

## 3. Bilder prüfen

- **Diashow:** grosse Vorschau und Filmstreifen mit ausgewählten und abgewählten Bildern.
- **Vergleichen:** Albumfoto und Alternative nebeneinander prüfen.
  **Zusätzlich aufnehmen** behält beide; **Als Ersatz wählen** tauscht genau ein
  Albumfoto am bisherigen Platz aus.
- **Albumübersicht:** die Sammlung als durchblätterbares Raster ansehen.

**Miniatur anklicken = ansehen. Häkchen / Leertaste = Auswahl ändern.** Grau
bedeutet „nicht im Album“, farbig mit Häkchen bedeutet „im Album“. Die grosse
Vorschau bleibt farbig. Aufgenommene Alternativen bleiben zum Vergleichen sichtbar.

Unverzichtbare Erinnerungen als Favoriten schützen. **Warum dieses Bild?** zeigt
vorhandene Auswahlgründe und Ortsnachweise. Über **Werkzeuge** erreichst du den
Prüfbericht, die Ortsprüfung und weitere Prüfwerkzeuge. Alte Analysen ohne
Entscheidungsprotokoll erhalten keine nachträglich erfundenen Gründe.

## 4. Speichern und exportieren

**Pause & speichern** sichert Auswahl und Ansicht und schliesst die Prüfung.
Später dasselbe Reiseprojekt fortsetzen. Änderungen werden zusätzlich automatisch
gespeichert; bei einem Speicherfehler die sichtbare Meldung zuerst beheben.

**Finale Auswahl** kopiert nur die endgültig ausgewählten Originaldateien:

- **Ein gemeinsamer Ordner:** alle Kopien direkt in `selected/`, in Albumreihenfolge nummeriert.
- **Nach Kapiteln aufteilen:** Unterordner für die Reiseabschnitte.

Die Originaldateien bleiben unverändert. Im Projektordner stehen ausserdem
`photos_analysis.csv`, `selection_draft.json` und der Prüfbericht als HTML/CSV.
Ein optionaler Dokumentpool gehört nicht automatisch zum Album. Für Vorschau
und spätere Weiterarbeit müssen die Originale weiterhin erreichbar sein.

Das endgültige Drucklayout erstellst du danach in deiner Fotobuchsoftware.
