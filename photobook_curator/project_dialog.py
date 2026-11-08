"""Project launcher for reusable travel albums; does not run an analysis."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont
from typing import Callable

from .projects import (PROJECT_FILENAME, TravelProject, create_project,
                       forget_project, load_project, recent_projects)
from .travel_profiles import get_profile, profile_choices
from .ui_widgets import FONT_UI


def show_project_manager(
    parent: tk.Misc, colors: dict[str, str], on_open: Callable[[TravelProject], None],
    current_input: str = "", current_output: str = "", *, language: str = "de",
) -> tk.Toplevel:
    """Open/create one project; callback receives config, never a duplicate draft."""
    en = language == "en"
    def tr(de: str, eng: str) -> str:
        return eng if en else de

    available = {family.lower(): family for family in tkfont.families(parent)}
    font_family = next((available[name.lower()] for name in (FONT_UI, "DejaVu Sans", "Helvetica")
                        if name.lower() in available), tkfont.nametofont("TkDefaultFont").actual("family"))
    c = colors
    bg, surface = c.get("bg", "#111827"), c.get("surface", "#1f2937")
    ink, muted = c.get("ink", "#f9fafb"), c.get("muted", "#9ca3af")
    accent = c.get("accent", "#6d5dfc")
    on_accent = c.get("on_accent", c.get("hero_fg", "#ffffff"))
    primary_bg, primary_ink = c.get("cta", accent), c.get("cta_ink", on_accent)
    window = tk.Toplevel(parent)
    window.title(tr("Reiseprojekte", "Travel projects"))
    window.configure(bg=bg)
    scale = float(parent.tk.call("tk", "scaling")) / (96 / 72)
    width = min(round(1040 * scale), max(320, parent.winfo_screenwidth() - 64))
    height = min(round(740 * scale), max(320, parent.winfo_screenheight() - 88))
    window.geometry(f"{width}x{height}+{max(0, (parent.winfo_screenwidth()-width)//2)}+{max(0, (parent.winfo_screenheight()-height)//2)}")
    window.minsize(min(round(880 * scale), width), min(round(640 * scale), height))
    window.transient(parent)
    style = ttk.Style(window)
    style.configure("Project.TEntry", fieldbackground=c.get("chip_bg", bg), foreground=ink,
                    insertcolor=ink, padding=7, bordercolor=c.get("line", bg),
                    font=(font_family, 11))
    style.configure("Project.TCombobox", fieldbackground=c.get("chip_bg", bg), foreground=ink,
                    background=c.get("chip_bg", bg), arrowcolor=ink, padding=7,
                    bordercolor=c.get("line", bg), font=(font_family, 11))
    style.map("Project.TCombobox", fieldbackground=[("readonly", c.get("chip_bg", bg))],
              foreground=[("readonly", ink)], selectbackground=[("readonly", accent)],
              selectforeground=[("readonly", on_accent)])
    style.configure("Project.Treeview", background=surface, fieldbackground=surface,
                    foreground=ink, rowheight=32, font=(font_family, 10), borderwidth=0)
    style.configure("Project.Treeview.Heading", background=c.get("chip_bg", bg), foreground=ink,
                    font=(font_family, 9, "bold"), padding=7, relief="flat")
    style.map("Project.Treeview", background=[("selected", c.get("accent_soft", surface))],
              foreground=[("selected", ink)])
    style.configure("Project.Vertical.TScrollbar", background=c.get("chip_bg", surface),
                    troughcolor=bg, arrowcolor=muted, bordercolor=c.get("line", bg))

    viewport = tk.Frame(window, bg=bg)
    viewport.pack(fill=tk.BOTH, expand=True)
    canvas = tk.Canvas(viewport, bg=bg, highlightthickness=0)
    scroll = ttk.Scrollbar(viewport, command=canvas.yview, style="Project.Vertical.TScrollbar")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    outer = tk.Frame(canvas, bg=bg, padx=26, pady=22)
    body = canvas.create_window((0, 0), window=outer, anchor="nw")
    window._project_canvas = canvas
    tk.Label(outer, text=tr("Jede Reise. Ein eigenes Album.", "Every trip. Its own album."),
             bg=bg, fg=ink, font=(font_family, 21, "bold"), anchor="w").pack(fill="x")
    intro = tk.Label(outer, text=tr(
        "Projekte merken Ordner und Einstellungen. Deine Bildentscheidungen bleiben im jeweiligen Reiseprojekt.",
        "Projects remember folders and settings. Photo decisions stay in their own travel project."),
        bg=bg, fg=muted, font=(font_family, 10), anchor="w", wraplength=860,
        justify="left")
    intro.pack(fill="x", pady=(6, 20))

    columns = tk.Frame(outer, bg=bg)
    columns.pack(fill="both", expand=True)
    columns.columnconfigure(0, weight=1, uniform="project")
    columns.columnconfigure(1, weight=1, uniform="project")
    columns.rowconfigure(0, weight=1)
    new_card = tk.Frame(columns, bg=surface, padx=20, pady=18,
                        highlightbackground=c.get("line", bg),
                        highlightcolor=c.get("line", bg), highlightthickness=1)
    new_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    recent_card = tk.Frame(columns, bg=surface, padx=20, pady=18,
                           highlightbackground=c.get("line", bg),
                           highlightcolor=c.get("line", bg), highlightthickness=1)
    recent_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    def fit_content(_event=None):
        width = max(1, canvas.winfo_width())
        wide = width >= round(860 * scale)
        new_card.grid_forget()
        recent_card.grid_forget()
        new_card.grid(row=0, column=0, columnspan=1 if wide else 2, sticky="nsew",
                      padx=(0, 10) if wide else 0)
        recent_card.grid(row=0 if wide else 1, column=1 if wide else 0,
                         columnspan=1 if wide else 2, sticky="nsew",
                         padx=(10, 0) if wide else 0, pady=0 if wide else (18, 0))
        intro.configure(wraplength=max(220, width - 52))
        canvas.itemconfigure(body, width=width)

    def fit_scroll_region(_event=None):
        bounds = canvas.bbox("all")
        height = max(canvas.winfo_height(), bounds[3] if bounds else 0)
        canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), height))
        if height > canvas.winfo_height() + 2:
            if not scroll.winfo_manager():
                scroll.pack(side=tk.RIGHT, fill=tk.Y)
        elif scroll.winfo_manager():
            scroll.pack_forget()

    canvas.bind("<Configure>", fit_content)
    outer.bind("<Configure>", fit_scroll_region)

    def wheel(event):
        if isinstance(event.widget, (ttk.Treeview, ttk.Combobox)):
            return
        delta = -1 if getattr(event, "num", 0) == 4 else 1
        if getattr(event, "delta", 0):
            delta = -1 if event.delta > 0 else 1
        canvas.yview_scroll(delta * 3, "units")
        return "break"

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        window.bind(sequence, wheel)

    def title(host, value):
        tk.Label(host, text=value, bg=surface, fg=ink,
                 font=(font_family, 13, "bold"), anchor="w").pack(fill="x", pady=(0, 12))

    def button(host, text, command, primary=False):
        return tk.Button(host, text=text, command=command, relief="flat", bd=0,
                         bg=c.get("cta", accent) if primary else c.get("chip_bg", bg),
                         fg=primary_ink if primary else ink,
                         activebackground=c.get("cta_hover", primary_bg) if primary else c.get("accent_soft", surface),
                         activeforeground=primary_ink if primary else ink,
                         font=(font_family, 10, "bold"), padx=14, pady=9, cursor="hand2",
                         highlightbackground=c.get("line", bg), highlightcolor=accent,
                         highlightthickness=1)

    title(new_card, tr("Neue Reise anlegen", "Create a new trip"))
    name = tk.StringVar(value=tr("Meine Reise", "My trip"))
    source = tk.StringVar(value=current_input)
    output = tk.StringVar(value=current_output)
    choices = profile_choices(language)
    profile_label = tk.StringVar(value=choices[0][1])
    profile_by_label = {label: pid for pid, label in choices}

    def entry(label, variable, browse=False):
        tk.Label(new_card, text=label, bg=surface, fg=muted, font=(font_family, 10),
                 anchor="w").pack(fill="x", pady=(9, 4))
        row = tk.Frame(new_card, bg=surface)
        row.pack(fill="x")
        field = ttk.Entry(row, textvariable=variable, style="Project.TEntry")
        field.pack(side="left", fill="x", expand=True, ipady=4)
        if browse:
            def choose():
                value = filedialog.askdirectory(parent=window, title=label,
                                                initialdir=variable.get() or str(Path.home()))
                if value:
                    variable.set(value)
            button(row, "...", choose).pack(side="right", padx=(6, 0))
        return field

    name_field = entry(tr("Reisename", "Trip name"), name)
    entry(tr("Originalfotos", "Original photographs"), source, True)
    entry(tr("Projekt- und Ausgabeordner", "Project and output folder"), output, True)
    tk.Label(new_card, text=tr("Reiseprofil · jederzeit anpassbar", "Travel profile · adjustable anytime"),
             bg=surface, fg=muted, font=(font_family, 10), anchor="w").pack(fill="x", pady=(12, 4))
    selector = ttk.Combobox(new_card, textvariable=profile_label,
                            values=[label for _id, label in choices], state="readonly", style="Project.TCombobox")
    selector.pack(fill="x", ipady=4)
    description = tk.StringVar()
    tk.Label(new_card, textvariable=description, bg=surface, fg=muted,
             font=(font_family, 9), wraplength=350, justify="left", anchor="nw").pack(
        fill="x", pady=(7, 14))

    def describe(_event=None):
        description.set(get_profile(profile_by_label[profile_label.get()]).description(language))
    selector.bind("<<ComboboxSelected>>", describe)
    describe()

    def activate(project):
        try:
            on_open(project)
        except Exception as exc:
            messagebox.showerror(tr("Projekt nicht geöffnet", "Project not opened"), str(exc), parent=window)
            return
        window.destroy()

    def create():
        if not source.get().strip() or not output.get().strip():
            messagebox.showerror(tr("Ordner fehlen", "Folders missing"), tr(
                "Bitte Originalfotos und einen separaten Projektordner wählen.",
                "Choose original photographs and a separate project folder."), parent=window)
            return
        try:
            project = create_project(name.get(), Path(source.get()), Path(output.get()),
                                     profile_id=profile_by_label[profile_label.get()])
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr("Projekt nicht angelegt", "Project not created"), str(exc), parent=window)
            return
        activate(project)

    button(new_card, tr("Projekt anlegen", "Create project"), create, True).pack(fill="x", pady=(2, 0))

    title(recent_card, tr("Reise fortsetzen", "Continue a trip"))
    tk.Label(recent_card, text=tr("Auswahl und Zwischenstand werden beim Öffnen übernommen.",
                                  "Opening restores the selection and saved progress."),
             bg=surface, fg=muted, font=(font_family, 9), wraplength=340, justify="left",
             anchor="w").pack(fill="x", pady=(0, 12))
    tree = ttk.Treeview(recent_card, columns=("updated",), show="tree headings", height=8, selectmode="browse", style="Project.Treeview")
    tree.heading("#0", text=tr("Reise", "Trip"))
    tree.heading("updated", text=tr("Zuletzt verwendet", "Last used"))
    tree.column("#0", width=165, minwidth=100)
    tree.column("updated", width=115, minwidth=95, stretch=False)
    tree.pack(fill="both", expand=True)
    records: dict[str, dict] = {}
    hint = tk.StringVar()
    tk.Label(recent_card, textvariable=hint, bg=surface, fg=muted, wraplength=340,
             justify="left", font=(font_family, 9), anchor="w").pack(fill="x", pady=(8, 10))

    def refresh():
        tree.delete(*tree.get_children())
        records.clear()
        for i, record in enumerate(recent_projects()):
            key = str(i)
            records[key] = record
            label = record["name"] + ("" if record["exists"] else tr(" · nicht gefunden", " · missing"))
            tree.insert("", "end", iid=key, text=label,
                        values=(record["updated_at"][:16].replace("T", " "),))
        hint.set(tr("Noch keine Projekte. Lege links deine erste Reise an.",
                    "No recent projects. Create your first trip on the left.") if not records else "")

    def selected_record():
        selected = tree.selection()
        return records.get(selected[0]) if selected else None

    def open_recent(_event=None):
        record = selected_record()
        if not record:
            return
        try:
            project = load_project(Path(record["path"]))
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr("Projekt nicht gefunden", "Project not found"), str(exc), parent=window)
            return
        activate(project)

    def browse_project():
        value = filedialog.askopenfilename(parent=window,
            title=tr("Reiseprojekt öffnen", "Open a travel project"),
            filetypes=[(tr("PhotoTool-Projekt", "PhotoTool project"), PROJECT_FILENAME),
                       ("JSON", "*.json")])
        if value:
            try:
                project = load_project(Path(value))
            except (OSError, ValueError) as exc:
                messagebox.showerror(tr("Projekt nicht geöffnet", "Project not opened"), str(exc), parent=window)
                return
            activate(project)

    def forget():
        record = selected_record()
        if record:
            try:
                forget_project(Path(record["path"]))
            except OSError as exc:
                messagebox.showerror(tr("Liste nicht gespeichert", "List not saved"), str(exc), parent=window)
                return
            refresh()

    tree.bind("<Double-1>", open_recent)
    tree.bind("<Return>", open_recent)
    tree.bind("<<TreeviewSelect>>", lambda _e: hint.set(
        (selected_record() or {}).get("path", "")))
    actions = tk.Frame(recent_card, bg=surface)
    actions.pack(fill="x", pady=(0, 8))
    button(actions, tr("Fortsetzen", "Continue"), open_recent, True).pack(side="left")
    button(actions, tr("Aus Liste entfernen", "Remove from list"), forget).pack(side="right")
    button(recent_card, tr("Projektdatei öffnen...", "Open project file..."), browse_project).pack(fill="x")
    refresh()
    window.bind("<Escape>", lambda _e: window.destroy())
    name_field.focus_set()
    return window
