"""Preview and durably apply location corrections without selecting photos."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .geocoding import GeocodeCache
from .location_repair import apply_location_repair, preview_location_repair
from .location_repair_state import persist_location_repair
from .location_schema import normalize_location_evidence
from .review_export import plan_from_photos
from .review_history import ReviewHistory


PAGE_SIZE = 100
SOURCES = {"gps_offline": "GPS / Offline-Näherung", "gps_online": "GPS / Online-Ortsname",
           "time_nearest": "Zeitnaher GPS-Anker", "unknown": "Ungeklärt",
           "legacy": "Herkunft unbekannt", "manual": "Manuelle Zuordnung"}
WARNINGS = {"conflicting_anchors": "Nahe GPS-Anker zeigen unterschiedliche Orte; keine automatische Zuordnung.",
            "no_nearby_anchor": "Kein GPS-Anker innerhalb des gewählten Zeitfensters.",
            "gps_unresolved": "Für diese GPS-Koordinaten wurde kein Ortsname ermittelt.",
            "invalid_gps": "GPS-Angaben sind unvollständig oder ungültig.",
            "missing_datetime": "Ohne Aufnahmezeit ist keine Zeitzuordnung möglich."}


class _CancelledPreview(Exception):
    pass


class _CancellableCache(GeocodeCache):
    def __init__(self, *args, stop: threading.Event, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop = stop

    def reverse(self, lat, lon):
        if self._stop.is_set():
            raise _CancelledPreview()
        return super().reverse(lat, lon)


@dataclass(frozen=True)
class _Row:
    index: int
    filename: str
    old_region: str
    new_region: str
    old_folder: str
    new_folder: str
    source: str
    warning: str
    changed: bool


def _style(win):
    from .review_gui import COLORS, FONT_UI
    style = ttk.Style(win)
    style.configure("Location.TFrame", background=COLORS["bg"])
    style.configure("Location.TNotebook", background=COLORS["bg"], borderwidth=0,
                    bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("Location.TNotebook.Tab", padding=(12, 8), background=COLORS["surface"],
                    foreground=COLORS["muted"], font=(FONT_UI, 10))
    style.map("Location.TNotebook.Tab", background=[("selected", COLORS["accent_soft"])],
              foreground=[("selected", COLORS["ink"])])
    style.configure("Location.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT_UI, 10))
    style.configure("Location.TButton", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                    font=(FONT_UI, 10), padding=(10, 7), borderwidth=0)
    style.map("Location.TButton", background=[("active", COLORS["line"])])
    style.configure("Location.TCheckbutton", background=COLORS["bg"], foreground=COLORS["ink"], font=(FONT_UI, 10))
    style.map("Location.TCheckbutton", background=[("active", COLORS["bg"])])
    style.configure("Location.TCombobox", fieldbackground=COLORS["surface"], background=COLORS["chip_bg"],
                    foreground=COLORS["ink"], arrowcolor=COLORS["muted"], padding=6)
    style.map("Location.TCombobox", fieldbackground=[("readonly", COLORS["surface"])],
              foreground=[("readonly", COLORS["ink"])], selectbackground=[("readonly", COLORS["surface"])],
              selectforeground=[("readonly", COLORS["ink"])])
    style.configure("Location.Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"],
                    foreground=COLORS["ink"], rowheight=32, font=(FONT_UI, 10), borderwidth=0,
                    bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("Location.Treeview.Heading", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                    font=(FONT_UI, 10), padding=(7, 9), bordercolor=COLORS["line"],
                    lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.map("Location.Treeview", background=[("selected", COLORS["accent_soft"])],
              foreground=[("selected", COLORS["ink"])])
    style.configure("Location.Vertical.TScrollbar", background=COLORS["chip_bg"], troughcolor=COLORS["surface"],
                    arrowcolor=COLORS["muted"], bordercolor=COLORS["line"])
    return COLORS, FONT_UI


class LocationRepairDialog(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.preview = None
        self._rows = []
        self._by_index = {}
        self._filtered = []
        self._page = 0
        self._busy = False
        self._closed = False
        self._stop = threading.Event()
        self._results = queue.Queue()
        self._poll_after = None
        self._preview_settings = None
        colors, font = _style(self)
        self.title("Ortszuordnung prüfen und reparieren")
        self.configure(bg=colors["bg"])
        self.geometry("1040x740")
        self.minsize(800, 600)
        self.transient(owner)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        head = ttk.Frame(self, padding=(20, 12, 20, 8), style="Location.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="Ortszuordnung prüfen", bg=colors["bg"], fg=colors["ink"],
                 font=(font, 18, "bold")).pack(anchor=tk.W)
        self.notebook = ttk.Notebook(self, style="Location.TNotebook")
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=20)
        settings = ttk.Frame(self.notebook, padding=14, style="Location.TFrame")
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(4, weight=1)
        self.notebook.add(settings, text="1. Einstellungen")
        self.results_page = ttk.Frame(self.notebook, padding=12, style="Location.TFrame")
        self.notebook.add(self.results_page, text="2. Vorschau")
        self.results_page.columnconfigure(0, weight=1)
        self.results_page.rowconfigure(1, weight=3, minsize=120)
        self.results_page.rowconfigure(2, weight=1, minsize=80)

        self.online_var = tk.BooleanVar(value=False)
        self.online_check = ttk.Checkbutton(settings, text="Online-Ortsnamen (optional)",
            variable=self.online_var, style="Location.TCheckbutton")
        self.online_check.grid(row=0, column=0, sticky="w")
        self.hours_var = tk.StringVar(value="6")
        time_options = ttk.Frame(settings, style="Location.TFrame")
        time_options.grid(row=1, column=0, sticky="w", pady=10)
        ttk.Label(time_options, text="Zeitnähe bis", style="Location.TLabel").pack(side=tk.LEFT, padx=(0, 7))
        self.hours_combo = ttk.Combobox(time_options, textvariable=self.hours_var, values=("1", "3", "6", "12", "24"),
            state="readonly", width=4, style="Location.TCombobox")
        self.hours_combo.pack(side=tk.LEFT)
        ttk.Label(time_options, text="Stunden", style="Location.TLabel").pack(side=tk.LEFT, padx=(7, 0))
        self.mode_var = tk.StringVar()
        mode = ttk.Label(settings, textvariable=self.mode_var, style="Location.TLabel", wraplength=960, justify=tk.LEFT)
        mode.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        privacy = ttk.Label(settings, text="Online: GPS-Koordinaten an Nominatim / OpenStreetMap, keine Fotos.",
            style="Location.TLabel", wraplength=960, justify=tk.LEFT)
        privacy.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        settings.bind("<Configure>", lambda event: (mode.configure(wraplength=max(300, event.width-28)),
                                                    privacy.configure(wraplength=max(300, event.width-28))))
        help_host = ttk.Frame(settings, style="Location.TFrame")
        help_host.grid(row=4, column=0, sticky="nsew")
        help_text = tk.Text(help_host, height=4, width=1, wrap=tk.WORD, bg=colors["surface"], fg=colors["ink"],
            font=(font, 10), padx=10, pady=8, relief=tk.FLAT, borderwidth=0, takefocus=True)
        help_text.insert("1.0", "So entsteht die Vorschau\n\n"
            "GPS liefert die Ortsbasis. Ohne GPS werden nur nahe, eindeutige Zeitanker verwendet. "
            "Bei wechselnden Orten oder fehlender Grundlage bleibt die Zuordnung ungeklärt.\n\n"
            "Offline werden bekannte Städte im Umkreis von 25 km angenähert. Außerhalb des Katalogs "
            "können Online-Ortsnamen helfen.\n\n"
            "Gespeichert werden nur Ortsmetadaten und Kapitelzuordnungen. Bildauswahl, Favoriten, "
            "manuelle Entscheidungen und Buchpositionen bleiben erhalten.")
        help_text.configure(state=tk.DISABLED)
        help_scroll = ttk.Scrollbar(help_host, command=help_text.yview, style="Location.Vertical.TScrollbar")
        help_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        help_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        help_text.configure(yscrollcommand=help_scroll.set)

        result_tools = ttk.Frame(self.results_page, style="Location.TFrame")
        result_tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        result_tools.columnconfigure(0, weight=1)
        self.summary_var = tk.StringVar(value=f"{len(owner.photos)} Bilder. Noch keine Vorschau berechnet.")
        ttk.Label(result_tools, textvariable=self.summary_var, style="Location.TLabel", width=1).grid(row=0, column=0, sticky="ew")
        self.filter_var = tk.StringVar(value="Änderungen und Ungeklärte")
        self.filter_combo = ttk.Combobox(result_tools, textvariable=self.filter_var,
            values=("Änderungen und Ungeklärte", "Nur Änderungen", "Nur Ungeklärte", "Alle Bilder"),
            state="readonly", width=25, style="Location.TCombobox")
        self.filter_combo.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.filter_combo.bind("<<ComboboxSelected>>", self._filter_rows)
        table_host = ttk.Frame(self.results_page, style="Location.TFrame")
        table_host.grid(row=1, column=0, sticky="nsew")
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(table_host, columns=("photo", "old", "new", "basis"), show="headings",
            selectmode="browse", style="Location.Treeview", height=9)
        for key, title, width in (("photo", "Bild", 190), ("old", "Bisheriger Ort", 200),
                                  ("new", "Neuer Ort", 200), ("basis", "Grundlage", 270)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=70, stretch=True)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_host, command=self.table.yview, style="Location.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._show_row)
        detail_host = ttk.Frame(self.results_page, style="Location.TFrame")
        detail_host.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.detail_var = tk.StringVar(value="Die Vorschau verändert deine Fotos und Entscheidungen noch nicht.")
        self._detail_text = tk.Text(detail_host, height=3, width=1, wrap=tk.WORD, state=tk.DISABLED,
            bg=colors["surface"], fg=colors["ink"], font=(font, 10), padx=8, pady=5,
            relief=tk.FLAT, borderwidth=0, takefocus=True)
        detail_scroll = ttk.Scrollbar(detail_host, command=self._detail_text.yview, style="Location.Vertical.TScrollbar")
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._detail_text.configure(yscrollcommand=detail_scroll.set)
        self.detail_var.trace_add("write", self._update_detail)
        self._update_detail()

        foot = ttk.Frame(self, padding=(20, 8, 20, 12), style="Location.TFrame")
        foot.grid(row=2, column=0, sticky="ew")
        paging = ttk.Frame(foot, style="Location.TFrame")
        paging.pack(fill=tk.X)
        self.prev_btn = ttk.Button(paging, text="< Zurück", command=lambda: self._change_page(-1), style="Location.TButton", state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT)
        self.page_var = tk.StringVar(value="0 Bilder")
        ttk.Label(paging, textvariable=self.page_var, style="Location.TLabel").pack(side=tk.LEFT, padx=10)
        self.next_btn = ttk.Button(paging, text="Weiter >", command=lambda: self._change_page(1), style="Location.TButton", state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(paging, mode="indeterminate", length=100)
        self.status_var = tk.StringVar(value="Bildauswahl und Entscheidungen bleiben erhalten.")
        self._status_text = tk.Text(foot, height=1, width=1, wrap=tk.WORD, state=tk.DISABLED,
            bg=colors["bg"], fg=colors["muted"], font=(font, 10), relief=tk.FLAT, borderwidth=0, takefocus=True)
        self._status_text.pack(fill=tk.X, pady=(5, 0))
        self.status_var.trace_add("write", self._update_status)
        self._update_status()
        ttk.Label(foot, text="Speichern setzt den Rückgängig-Verlauf zurück.",
                  style="Location.TLabel").pack(anchor=tk.W, pady=(4, 7))
        buttons = ttk.Frame(foot, style="Location.TFrame")
        buttons.pack(fill=tk.X)
        self.preview_btn = ttk.Button(buttons, text="Vorschau berechnen", command=self._start_preview, style="Location.TButton")
        self.preview_btn.pack(side=tk.LEFT)
        ttk.Button(buttons, text="Schließen", command=self.destroy, style="Location.TButton").pack(side=tk.LEFT, padx=8)
        self.apply_btn = ttk.Button(buttons, text="Alle Ortskorrekturen speichern", command=self._apply,
                                    style="Location.TButton", state=tk.DISABLED)
        self.apply_btn.pack(side=tk.RIGHT)
        self.online_var.trace_add("write", self._invalidate)
        self.hours_var.trace_add("write", self._invalidate)
        self._invalidate()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _update_status(self, *_):
        self._status_text.configure(state=tk.NORMAL)
        self._status_text.delete("1.0", tk.END)
        self._status_text.insert("1.0", self.status_var.get())
        self._status_text.configure(state=tk.DISABLED)
        self._status_text.yview_moveto(0)

    def _update_detail(self, *_):
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert("1.0", self.detail_var.get())
        self._detail_text.configure(state=tk.DISABLED)
        self._detail_text.yview_moveto(0)

    def _invalidate(self, *_):
        if self._busy:
            return
        self.preview = None
        self._rows = []
        self._by_index = {}
        self._filtered = []
        self._page = 0
        self.table.delete(*self.table.get_children())
        self.apply_btn.configure(state=tk.DISABLED)
        self.mode_var.set("Offline: bekannte Städte bis 25 km; sonst bleibt der GPS-Ort ungeklärt." if not self.online_var.get() else
            "Online-Ortsnamen werden bei Bedarf abgefragt und lokal zwischengespeichert.")
        self.summary_var.set(f"{len(self.owner.photos)} Bilder. Vorschau mit diesen Einstellungen neu berechnen.")
        self.detail_var.set("Die Vorschau verändert deine Fotos und Entscheidungen noch nicht.")
        self._render_page()

    def _set_busy(self, busy):
        self._busy = busy
        self.preview_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.online_check.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.hours_combo.configure(state=tk.DISABLED if busy else "readonly")
        if busy:
            self.progress.pack(side=tk.RIGHT, padx=(15, 0))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def _start_preview(self):
        if self._busy:
            return
        self._invalidate()
        try:
            hours = float(self.hours_var.get())
            if hours not in {1.0, 3.0, 6.0, 12.0, 24.0}:
                raise ValueError()
        except ValueError:
            self.status_var.set("Wähle ein Zeitfenster zwischen 1 und 24 Stunden.")
            return
        online = self.online_var.get()
        self._preview_settings = (online, hours)
        self._stop = threading.Event()
        self._set_busy(True)
        self.notebook.select(self.results_page)
        self.status_var.set("Ortsgrundlagen werden geprüft..." + (" Online-Abfragen können etwas dauern." if online else " Alles läuft lokal."))
        photos = list(self.owner.photos)
        cache_path = Path(self.owner.output_dir) / "geocode_cache.json"
        stop = self._stop

        def worker():
            try:
                cache = _CancellableCache(cache_path, enabled=online, stop=stop)
                preview = preview_location_repair(photos, cache, max_hours=hours)
                if stop.is_set():
                    return
                cache_warning = ""
                try:
                    cache.save()
                except OSError as exc:
                    cache_warning = f"Ortscache konnte nicht gespeichert werden: {exc}"
                self._results.put((preview, None, cache_warning))
            except _CancelledPreview:
                pass
            except Exception as exc:
                if not stop.is_set():
                    self._results.put((None, exc, ""))

        threading.Thread(target=worker, name="location-preview", daemon=True).start()
        self._poll_after = self.after(40, self._poll)

    def _poll(self):
        self._poll_after = None
        if self._closed:
            return
        try:
            preview, error, cache_warning = self._results.get_nowait()
        except queue.Empty:
            self._poll_after = self.after(40, self._poll)
            return
        self._set_busy(False)
        if error is not None:
            self.status_var.set("Vorschau fehlgeschlagen: " + str(error))
            return
        self.preview = preview
        changes = {change.index: change for change in preview.changes}
        rows = []
        for index, corrected in enumerate(preview.photos):
            original = self.owner.photos[index]
            evidence = normalize_location_evidence(getattr(corrected, "location_evidence", {}))
            change = changes.get(index)
            rows.append(_Row(index, corrected.filename, original.region or "Unbekannt", corrected.region or "Unbekannt",
                original.chapter_folder or "", corrected.chapter_folder or "",
                change.source if change else evidence.get("source", "unknown"),
                change.warning if change else str(evidence.get("warning") or ""), change is not None))
        self._rows = rows
        self._by_index = {row.index: row for row in rows}
        self.summary_var.set(f"{preview.changed_count} Änderungen  ·  {preview.unresolved_count} Orte ungeklärt  ·  {len(rows)} Bilder geprüft")
        self.apply_btn.configure(state=tk.NORMAL if preview.changed_count else tk.DISABLED)
        self.status_var.set(cache_warning or ("Vorschau fertig. Speichern übernimmt alle Korrekturen."
            if preview.changed_count else "Keine Metadatenkorrekturen erforderlich."))
        self._filter_rows()

    def _filter_rows(self, _event=None):
        mode = self.filter_var.get()
        self._filtered = [row for row in self._rows if mode == "Alle Bilder" or
            (mode == "Nur Änderungen" and row.changed) or
            (mode == "Nur Ungeklärte" and row.source in {"unknown", "legacy"}) or
            (mode == "Änderungen und Ungeklärte" and (row.changed or row.source in {"unknown", "legacy"}))]
        self._page = 0
        self._render_page()

    def _change_page(self, delta):
        self._page = max(0, min(self._page + delta, max(0, (len(self._filtered)-1)//PAGE_SIZE)))
        self._render_page()

    def _render_page(self):
        self.table.delete(*self.table.get_children())
        start = self._page * PAGE_SIZE
        visible = self._filtered[start:start+PAGE_SIZE]
        for row in visible:
            self.table.insert("", tk.END, iid=str(row.index), values=(row.filename, row.old_region, row.new_region,
                SOURCES.get(row.source, row.source)))
        total = len(self._filtered)
        self.page_var.set(f"{start+1 if total else 0}-{min(start+PAGE_SIZE, total)} von {total}")
        self.prev_btn.configure(state=tk.NORMAL if self._page else tk.DISABLED)
        self.next_btn.configure(state=tk.NORMAL if start+PAGE_SIZE < total else tk.DISABLED)
        if visible:
            self.table.selection_set(str(visible[0].index))
            self._show_row()
        elif self.preview is not None:
            self.detail_var.set("Keine Bilder für diesen Filter. Wähle einen anderen Filter.")

    def _show_row(self, _event=None):
        selection = self.table.selection()
        if not selection or self.preview is None:
            return
        row = self._by_index[int(selection[0])]
        evidence = normalize_location_evidence(getattr(self.preview.photos[row.index], "location_evidence", {}))
        parts = [f"{row.filename}: {row.old_region} -> {row.new_region}", SOURCES.get(row.source, row.source)]
        if row.warning:
            parts.append("Hinweis: " + WARNINGS.get(row.warning, row.warning))
        if evidence.get("candidates"):
            parts.append("Zeitanker: " + "; ".join(f"{candidate.get('region', '?')} "
                f"({candidate.get('delta_hours', 0):.2f} h)" for candidate in evidence["candidates"]))
        if evidence.get("anchor_path"):
            parts.append("GPS-Anker: " + Path(evidence["anchor_path"]).name)
        delta = evidence.get("delta_hours", evidence.get("anchor_delta_hours"))
        if isinstance(delta, (int, float)):
            parts.append(f"Zeitabstand: {delta:.2f} Stunden")
        if row.old_folder != row.new_folder:
            parts.append(f"Kapitel: {row.old_folder or 'Ohne Kapitel'} -> {row.new_folder or 'Ohne Kapitel'}")
        self.detail_var.set("  |  ".join(parts))

    def _apply(self):
        if self.preview is None or self._busy or self._preview_settings != (self.online_var.get(), float(self.hours_var.get())):
            return
        try:
            persist_location_repair(self.preview.photos, self.owner.kept, self.owner.output_dir,
                                    review_state=self.owner._review_view_state())
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Ortskorrekturen nicht gespeichert", str(exc), parent=self)
            return
        try:
            apply_location_repair(self.owner.photos, self.preview)
            self.owner.plan = plan_from_photos(self.owner.photos)
            self.owner._history = ReviewHistory(self.owner.photos)
            self.owner._known_folders = []
            self.owner._refresh_review_edit()
            self.owner._autosave_draft()
        except Exception as exc:
            messagebox.showerror("Ansicht konnte nicht aktualisiert werden",
                "Die Korrekturen wurden gespeichert. Öffne das Projekt erneut.\n\n" + str(exc), parent=self)
            self.destroy()
            return
        if not getattr(self.owner, "_draft_save_error", None):
            self.owner._flash_status(f"{self.preview.changed_count} Ortskorrekturen gespeichert. Auswahl unverändert.")
        self.destroy()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        if self._poll_after is not None:
            self.after_cancel(self._poll_after)
            self._poll_after = None
        if hasattr(self, "progress"):
            self.progress.stop()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        super().destroy()


def open_location_repair(owner):
    return LocationRepairDialog(owner)
