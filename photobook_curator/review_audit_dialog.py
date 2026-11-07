"""Read-only selection explanations and a paged, local review report."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .audit_report import build_audit_report, build_photo_audit, write_audit_csv, write_audit_report


PAGE_SIZE = 100
FILTERS = ("Alle Bilder", "Im Album", "Ausgelassen", "Prüfhinweise", "Manuelle Vorgaben")


def _sections(audit):
    """Keep current intent, recorded decisions and observations visibly separate."""
    automatic = ("Im Album" if audit.automatic_selected else "Ausgelassen") if audit.automatic_selected is not None else "Unbekannt"
    manual = {"keep": "Dauerhaft behalten", "reject": "Dauerhaft ablehnen"}.get(
        audit.manual_decision, "Keine dauerhafte manuelle Vorgabe.")
    if audit.manual_reason:
        manual += "\nDeine Begründung: " + audit.manual_reason
    sections = [
        ("Aktueller Stand", "\n".join(audit.primary_reasons)),
        ("Letzte automatische Auswahl: " + automatic,
         "\n".join((*getattr(audit, "automatic_reasons", ()), audit.provenance_note))),
        ("Deine aktuelle Entscheidung", manual),
        ("Qualitätsmerkmale",
         f"Technischer Score: {audit.technical_score:.1f}  |  Gesamtscore: {audit.final_score:.1f}\n" +
         ("\n".join(audit.quality_hints) or "Keine zusätzlichen Qualitätsmerkmale gespeichert.")),
    ]
    if getattr(audit, "location_reasons", ()):
        sections.append(("Ort und Kapitelzuordnung", "\n".join(audit.location_reasons)))
    if audit.comparisons:
        sections.append(("Gespeicherte Vergleiche", "\n\n".join(
            comparison.filename + "\n" + comparison.explanation for comparison in audit.comparisons)))
    else:
        sections.append(("Gespeicherte Vergleiche", "Kein konkreter Vergleich mit einem anderen Bild gespeichert."))
    if audit.recorded_decisions:
        sections.append(("Alle aufgezeichneten Auswahlschritte", "\n\n".join(audit.recorded_decisions)))
    sections.append(("Originaldatei", str(audit.path)))
    return sections


def _style(win):
    from .review_gui import COLORS, FONT_UI
    style = ttk.Style(win)
    style.configure("Audit.TFrame", background=COLORS["bg"])
    style.configure("Audit.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT_UI, 10))
    style.configure("Audit.TButton", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                    font=(FONT_UI, 10), padding=(12, 8), borderwidth=0)
    style.map("Audit.TButton", background=[("active", COLORS["line"])])
    style.configure("Audit.TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["ink"],
                    insertcolor=COLORS["ink"], padding=7)
    style.configure("Audit.TCombobox", fieldbackground=COLORS["surface"], background=COLORS["chip_bg"],
                    foreground=COLORS["ink"], arrowcolor=COLORS["muted"], padding=7)
    style.map("Audit.TCombobox", fieldbackground=[("readonly", COLORS["surface"])],
              foreground=[("readonly", COLORS["ink"])], selectbackground=[("readonly", COLORS["surface"])],
              selectforeground=[("readonly", COLORS["ink"])])
    style.configure("Audit.Vertical.TScrollbar", background=COLORS["chip_bg"], troughcolor=COLORS["surface"],
                    arrowcolor=COLORS["muted"], bordercolor=COLORS["line"])
    style.configure("Audit.Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"],
                    foreground=COLORS["ink"], rowheight=34, font=(FONT_UI, 10), borderwidth=0,
                    bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("Audit.Treeview.Heading", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                    font=(FONT_UI, 10), padding=(8, 10), bordercolor=COLORS["line"],
                    lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.map("Audit.Treeview", background=[("selected", COLORS["accent_soft"])],
              foreground=[("selected", COLORS["ink"])])
    return COLORS, FONT_UI


class AuditDetail(ttk.Frame):
    """Selectable text works with keyboard navigation, scrolling and copying."""
    def __init__(self, master):
        super().__init__(master, style="Audit.TFrame")
        colors, font = _style(self)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.title_var = tk.StringVar(value="Bild auswählen")
        self.status_var = tk.StringVar(value="Die Begründung erscheint hier.")
        title = tk.Label(self, textvariable=self.title_var, bg=colors["bg"], fg=colors["ink"],
                         font=(font, 16, "bold"), anchor=tk.W, justify=tk.LEFT, wraplength=460)
        title.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        status = ttk.Label(self, textvariable=self.status_var, style="Audit.TLabel", wraplength=460,
                           justify=tk.LEFT)
        status.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.bind("<Configure>", lambda event: (title.configure(wraplength=max(100, event.width-18)),
                                                 status.configure(wraplength=max(100, event.width-18))))
        self.text = tk.Text(self, wrap=tk.WORD, bg=colors["surface"], fg=colors["ink"],
                            insertbackground=colors["ink"], relief=tk.FLAT, borderwidth=0,
                            padx=16, pady=12, font=(font, 10), width=35, height=12,
                            takefocus=True, state=tk.DISABLED)
        self.text.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview,
                               style="Audit.Vertical.TScrollbar")
        scroll.grid(row=2, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)
        self.text.tag_configure("heading", font=(font, 11, "bold"), foreground=colors["accent"],
                                spacing1=12, spacing3=6)
        self.text.tag_configure("body", spacing3=8)

    def show(self, audit):
        self.title_var.set(audit.filename)
        self.status_var.set(("IM ALBUM" if audit.selected else "AUSGELASSEN") + "  |  " +
                            (audit.chapter or "Ohne Kapitel") + "  |  " + (audit.day or "Ohne Datum"))
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        for title, body in _sections(audit):
            self.text.insert(tk.END, title + "\n", "heading")
            self.text.insert(tk.END, body.strip() + "\n", "body")
        self.text.configure(state=tk.DISABLED)
        self.text.yview_moveto(0)


def open_photo_audit(review, index):
    """Explain selected and omitted photos using the same persisted evidence."""
    audit = build_photo_audit(review.photos, index, selected_override=index in review.kept)
    win = tk.Toplevel(review)
    colors, _ = _style(win)
    win.configure(bg=colors["bg"])
    win.title("Warum dieses Bild? · " + audit.filename)
    win.geometry("760x700")
    win.minsize(560, 460)
    win.transient(review)
    host = ttk.Frame(win, padding=22, style="Audit.TFrame")
    host.pack(fill=tk.BOTH, expand=True)
    host.columnconfigure(0, weight=1)
    host.rowconfigure(0, weight=1)
    detail = AuditDetail(host)
    detail.grid(row=0, column=0, sticky="nsew")
    detail.show(audit)
    buttons = ttk.Frame(host, style="Audit.TFrame")
    buttons.grid(row=1, column=0, sticky="ew", pady=(14, 0))

    def preview():
        win.destroy()
        review._open_review_pool([index], "Warum dieses Bild?")
        review.lift()

    def report():
        win.destroy()
        open_audit_report(review, initial_index=index)

    ttk.Button(buttons, text="Foto in Vorschau öffnen", style="Audit.TButton", command=preview).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Gesamter Prüfbericht", style="Audit.TButton", command=report).pack(side=tk.LEFT, padx=8)
    ttk.Button(buttons, text="Schließen", style="Audit.TButton", command=win.destroy).pack(side=tk.RIGHT)
    win.bind("<Escape>", lambda _e: win.destroy())
    win.detail = detail
    return win


class AuditReportWindow(tk.Toplevel):
    def __init__(self, review, initial_index=None):
        super().__init__(review)
        self.review = review
        # Freeze metadata and decisions together. Export remains identical to this
        # report even if the underlying review is edited while the window is open.
        self.photos = deepcopy(review.photos)
        self.kept = frozenset(review.kept)
        self.project_name = review.output_dir.name
        self.snapshot = build_audit_report(self.photos, kept=self.kept, project_name=self.project_name)
        self.audits = self.snapshot.photos
        self._by_index = {audit.photo_index: audit for audit in self.audits}
        self._searchable = {audit.photo_index: " ".join((audit.filename, audit.chapter or "", audit.day or "",
            audit.manual_reason, *audit.primary_reasons, *audit.recorded_decisions,
            *audit.quality_hints, *getattr(audit, "automatic_reasons", ()),
            *getattr(audit, "location_reasons", ()),
            *(c.filename + " " + c.explanation for c in audit.comparisons))).casefold() for audit in self.audits}
        self._search_job = None
        self._page = 0
        self._filtered = list(self.audits)
        colors, font = _style(self)
        self.configure(bg=colors["bg"])
        self.title("Prüfbericht · " + self.project_name)
        self.geometry("1180x760")
        self.minsize(920, 580)
        self.transient(review)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        head = ttk.Frame(self, padding=(22, 18, 22, 12), style="Audit.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="Prüfbericht", bg=colors["bg"], fg=colors["ink"],
                 font=(font, 23, "bold")).pack(anchor=tk.W)
        selected = sum(a.selected for a in self.audits)
        unknown = sum(not a.provenance_available for a in self.audits)
        summary = (f"{len(self.audits)} Bilder  ·  {selected} im Album  ·  {len(self.audits)-selected} ausgelassen  ·  "
                   f"{sum(a.needs_review for a in self.audits)} mit Prüfhinweisen")
        ttk.Label(head, text=summary, style="Audit.TLabel").pack(anchor=tk.W, pady=(5, 4))
        ttk.Label(head, text=f"Stand beim Öffnen. {unknown} Bilder ohne präzise protokollierten automatischen Auswahlgrund.",
                  style="Audit.TLabel").pack(anchor=tk.W)

        filters = ttk.Frame(self, padding=(22, 0, 22, 12), style="Audit.TFrame")
        filters.grid(row=1, column=0, sticky="ew")
        ttk.Label(filters, text="Zeigen", style="Audit.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.filter_var = tk.StringVar(value=FILTERS[0])
        self.filter_combo = ttk.Combobox(filters, textvariable=self.filter_var, values=FILTERS,
                                         state="readonly", width=20, style="Audit.TCombobox")
        self.filter_combo.pack(side=tk.LEFT)
        self.filter_combo.bind("<<ComboboxSelected>>", self._apply_filters)
        ttk.Label(filters, text="Suchen", style="Audit.TLabel").pack(side=tk.LEFT, padx=(18, 8))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var, width=28, style="Audit.TEntry")
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_var.trace_add("write", self._schedule_search)
        self.search_entry.bind("<Escape>", self._escape_search)

        content = ttk.Frame(self, padding=(22, 0, 22, 0), style="Audit.TFrame")
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=6)
        content.columnconfigure(1, weight=5)
        content.rowconfigure(0, weight=1)
        list_host = ttk.Frame(content, style="Audit.TFrame")
        list_host.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(list_host, columns=("status", "photo", "why"), show="headings",
                                 style="Audit.Treeview", selectmode="browse")
        for key, title, width in (("status", "Stand", 90), ("photo", "Bild", 140), ("why", "Hauptgrund", 270)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=65, stretch=True)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_host, command=self.table.yview, style="Audit.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._select)
        self.table.bind("<Double-1>", lambda _e: self._preview())
        self.table.bind("<Return>", lambda _e: self._preview())
        self.detail = AuditDetail(content)
        self.detail.grid(row=0, column=1, sticky="nsew")

        foot = ttk.Frame(self, padding=(22, 12, 22, 16), style="Audit.TFrame")
        foot.grid(row=3, column=0, sticky="ew")
        pages = ttk.Frame(foot, style="Audit.TFrame")
        pages.pack(fill=tk.X, pady=(0, 10))
        self.page_var = tk.StringVar()
        self.previous_button = ttk.Button(pages, text="< Zurück", command=lambda: self._change_page(-1), style="Audit.TButton")
        self.previous_button.pack(side=tk.LEFT)
        ttk.Label(pages, textvariable=self.page_var, style="Audit.TLabel").pack(side=tk.LEFT, padx=10)
        self.next_button = ttk.Button(pages, text="Weiter >", command=lambda: self._change_page(1), style="Audit.TButton")
        self.next_button.pack(side=tk.LEFT)
        self.preview_button = ttk.Button(pages, text="Foto in Vorschau öffnen", command=self._preview, style="Audit.TButton")
        self.preview_button.pack(side=tk.RIGHT)
        self.status_var = tk.StringVar(value="Der Bericht liest vorhandene Analysedaten. Es werden keine Fotos neu analysiert.")
        export_row = ttk.Frame(foot, style="Audit.TFrame")
        export_row.pack(fill=tk.X)
        export_row.columnconfigure(0, weight=1)
        status = ttk.Label(export_row, textvariable=self.status_var, style="Audit.TLabel", wraplength=630, width=1)
        status.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Button(export_row, text="HTML exportieren", command=lambda: self._export("html"), style="Audit.TButton").grid(row=0, column=1, padx=(0, 8))
        ttk.Button(export_row, text="CSV exportieren", command=lambda: self._export("csv"), style="Audit.TButton").grid(row=0, column=2)
        export_row.bind("<Configure>", lambda event: status.configure(wraplength=max(200, event.width-290)))
        self.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._render_page(initial_index)

    def _schedule_search(self, *_):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(180, self._apply_filters)

    def _escape_search(self, _event=None):
        if self.search_var.get():
            self.search_var.set("")
        else:
            self.destroy()
        return "break"

    def _apply_filters(self, _event=None):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
            self._search_job = None
        search = self.search_var.get().strip().casefold()
        mode = self.filter_var.get()
        self._filtered = [audit for audit in self.audits if
            (mode != "Im Album" or audit.selected) and
            (mode != "Ausgelassen" or not audit.selected) and
            (mode != "Prüfhinweise" or audit.needs_review) and
            (mode != "Manuelle Vorgaben" or audit.manual_decision != "auto") and
            (not search or search in self._searchable[audit.photo_index])]
        self._page = 0
        self._render_page()

    def _change_page(self, delta):
        self._page = max(0, min(self._page + delta, max(0, (len(self._filtered)-1)//PAGE_SIZE)))
        self._render_page()

    def _render_page(self, initial_index=None):
        if initial_index is not None:
            positions = [n for n, audit in enumerate(self._filtered) if audit.photo_index == initial_index]
            if positions:
                self._page = positions[0] // PAGE_SIZE
        self.table.delete(*self.table.get_children())
        start = self._page * PAGE_SIZE
        visible = self._filtered[start:start+PAGE_SIZE]
        for audit in visible:
            self.table.insert("", tk.END, iid=str(audit.photo_index), values=(
                "Im Album" if audit.selected else "Ausgelassen", audit.filename,
                audit.primary_reasons[0] if audit.primary_reasons else "Unbekannt"))
        total = len(self._filtered)
        self.page_var.set(f"{start+1 if total else 0}-{min(start+PAGE_SIZE, total)} von {total}")
        self.previous_button.configure(state=tk.NORMAL if self._page else tk.DISABLED)
        self.next_button.configure(state=tk.NORMAL if start+PAGE_SIZE < total else tk.DISABLED)
        self.preview_button.configure(state=tk.NORMAL if visible else tk.DISABLED)
        if visible:
            selected = str(initial_index) if any(a.photo_index == initial_index for a in visible) else str(visible[0].photo_index)
            self.table.selection_set(selected)
            self.table.see(selected)
            self._select()
        else:
            self.detail.title_var.set("Keine passenden Bilder")
            self.detail.status_var.set("Suchbegriff ändern oder einen anderen Filter wählen.")
            self.detail.text.configure(state=tk.NORMAL)
            self.detail.text.delete("1.0", tk.END)
            self.detail.text.configure(state=tk.DISABLED)

    def _select(self, _event=None):
        selected = self.table.selection()
        if selected:
            self.detail.show(self._by_index[int(selected[0])])

    def _preview(self):
        selected = self.table.selection()
        if selected:
            index = int(selected[0])
            self.destroy()
            self.review._open_review_pool([index], "Prüfbericht: " + self.photos[index].filename)
            self.review.lift()

    def _export(self, kind):
        path = filedialog.asksaveasfilename(parent=self, title="Prüfbericht exportieren",
            initialdir=str(self.review.output_dir), initialfile="pruefbericht." + kind,
            defaultextension="." + kind, filetypes=[("HTML-Bericht" if kind == "html" else "CSV-Tabelle", "*." + kind)])
        if not path:
            return
        try:
            writer = write_audit_report if kind == "html" else write_audit_csv
            writer(self.photos, Path(path), kept=self.kept, project_name=self.project_name)
        except Exception as exc:
            messagebox.showerror("Prüfbericht konnte nicht exportiert werden", str(exc), parent=self)
            return
        self.status_var.set("Gespeichert: " + Path(path).name + " (gesamter Bericht)")

    def destroy(self):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
            self._search_job = None
        super().destroy()


def open_audit_report(review, initial_index=None):
    return AuditReportWindow(review, initial_index=initial_index)
