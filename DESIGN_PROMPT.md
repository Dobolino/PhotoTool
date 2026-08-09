# Design-Prompt für ein GUI-Redesign (Photobook Curator)

Dieser Prompt ist zum Kopieren gedacht – füge ihn bei Claude/Cursor ein, wenn du das
Aussehen der Oberfläche überarbeiten lassen willst. Häng am besten aktuelle Screenshots an.

> Hinweis: Ein Teil der unten genannten Punkte (Freeze-Fix, Hilfe, „nächster Schritt",
> einklappbare Erweitert-Optionen, Theme/Sprache) wurde bereits umgesetzt. Der Fokus
> liegt daher inzwischen auf der **visuellen Modernisierung** – die Anforderungen bleiben
> als Leitplanken trotzdem gültig, damit nichts davon beim Redesign wieder verloren geht.

---

## Worauf es bei so einem Prompt ankommt

1. **Kontext geben:** Was ist die App, welche Sprache/Framework, welche Datei.
2. **Klare Grenzen:** Was darf **nicht** kaputtgehen (Funktionen, Thread-Sicherheit, Pipeline).
3. **Konkrete Probleme benennen** statt „mach schön" – je präziser, desto besser.
4. **Design-Richtung vorgeben** (Farben, Stil, Referenz), aber Freiraum lassen.
5. **Arbeitsweise & „fertig ist wann"** definieren (Branch, Tests grün, kleine Commits).
6. **Screenshots beilegen** – hilft enorm.

---

## Der Prompt

```text
Rolle: Du bist Senior-Python-Entwickler mit Fokus auf Desktop-UI/UX. Du überarbeitest
das Design der GUI unserer Anwendung „Photobook Curator" (Fotobuch).

## Projekt & Technik
- Python 3.11+, Desktop-GUI. Aktuell Tkinter/ttk (Theme „clam").
- Die GUI liegt komplett in: photobook_curator/gui.py
- Start: `python -m photobook_curator.gui` bzw. „Fotobuch starten.bat".
- Die eigentliche Verarbeitung (run_pipeline) läuft in einem Hintergrund-Thread und
  meldet Fortschritt über einen progress-Callback und Log-Ausgaben zurück.
- Arbeitsbranch: cursor/photobook-curator-c6d6. Bitte dort committen (kleine, klare Commits).

## Ziel
Modernes, aufgeräumtes Redesign der Oberfläche – gerne mit `customtkinter`
(Dark-/Light-Mode, abgerundete Ecken, Schalter statt altmodischer Häkchen).
Falls du bei Tkinter/ttk bleibst, hebe die Optik trotzdem deutlich (Abstände,
Typografie, Karten-Layout). Bestehende Farbpalette als Ausgangspunkt:
Akzent #2F5D50, Hintergrund #F3EFE7, Fläche #FFFCF7, Text #1F1A17.

## HARTE Anforderungen – NICHT kaputt machen
1. Alle bestehenden Funktionen & Optionen bleiben erhalten und korrekt mit
   PipelineConfig verdrahtet (Ordnerwahl, Zielanzahl, alle Checkboxen/Regler,
   API-Key, KI/Dry-Run, Karten-/Kapitel-Vorschau, „Auswahl starten", „Abbrechen",
   „Auswahl prüfen", „Karte zeigen").
2. Thread-Sicherheit: UI-Elemente NUR aus dem Main-Thread ändern. Fortschritt/Logs
   kommen aus dem Worker-Thread über Queues und werden per `after()` gezeichnet.
   Niemals Widgets direkt aus dem Worker anfassen.
3. Die Pipeline-Logik (Ordner photobook_curator/, außer gui.py) NICHT verändern.
4. Alle Texte auf Deutsch. Zielgruppe: nicht-technische Endnutzer.
5. `pytest` muss weiterhin grün sein (GUI ist nicht getestet, aber nichts anderes brechen).

## Konkrete Probleme, die das Redesign mitlösen soll
1. LEISTUNG/FREEZE (wichtig): Der Live-Fortschritt (tqdm) darf die GUI NICHT einfrieren.
   Log-/Fortschritts-Updates bündeln (z. B. max. ~10×/Sekunde, nur den neuesten Stand
   anzeigen), lange Läufe (2000+ Fotos) müssen flüssig bleiben.
2. Fenster ist zu breit: sinnvolle maximale Inhaltsbreite / zentrierte Spalte.
3. Regler „Abdeckung-Stärke"/„Personen-Stärke" nur zeigen bzw. aktiv, wenn das
   zugehörige Häkchen an ist. Ebenso API-Key/Dry-Run nur bei aktiver KI.
4. Fortgeschrittene Optionen (KI, API-Key, Dry-Run, Burst-Details) in einen
   einklappbaren „Erweitert"-Bereich.
5. HILFE/ANLEITUNG in der App: ein „?"/„Hilfe"-Knopf, der die Schritte erklärt
   (Ordner wählen → Optionen → Auswahl starten → Auswahl prüfen → Ergebnis).
6. NÄCHSTER SCHRITT sichtbar machen: Der Nutzer soll klar geführt werden, wann er
   „Auswahl prüfen" klicken kann (z. B. Schritt-Anzeige 1–2–3, und nach dem Lauf
   „Auswahl prüfen" hervorheben/aktivieren).
7. Sofort-Feedback bei Ordnerwahl ist schon da („X Bilder gefunden") – bitte
   erhalten und schön einbetten.

## Ablauf des Nutzers (soll der neue Flow klar abbilden)
Ordner wählen → (optional Optionen) → „Auswahl starten" (mit Fortschritt + Abbrechen)
→ nach Fertig: „Auswahl prüfen" (Thumbnails) → Ergebnis im Ausgabe-Ordner.

## Definition of Done
- GUI startet fehlerfrei, bleibt bei 2000+ Fotos flüssig (kein „Keine Rückmeldung").
- Alle Funktionen unverändert nutzbar, deutscher Text, thread-sicher.
- `pytest` grün. Commit(s) auf cursor/photobook-curator-c6d6.
- Falls `customtkinter` neu dazukommt: in requirements.txt ergänzen und einen
  Fallback dokumentieren/behalten, falls es nicht installiert ist.

Bitte arbeite in kleinen Schritten, erkläre kurz deine Design-Entscheidungen,
und teste den Start (`python -m photobook_curator.gui`) nach jeder Etappe.
Screenshots des aktuellen Zustands hänge ich an.
```
