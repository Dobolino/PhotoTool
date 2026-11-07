"""Focused main workspace and an optional, grouped settings sheet.

This module builds native Tk views only; the application owns project state and
analysis. All controls use the application's existing variables and actions.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path


def text(app, de: str, en: str) -> str:
    return en if getattr(app.app_settings, "language", "de") == "en" else de


def label(app, parent, de, en, *, size=12, bold=False, muted=False, **kwargs):
    from . import ui_widgets
    widget = tk.Label(
        parent, text=text(app, de, en), bg=parent.cget("background"),
        fg=app._workspace_colors["muted" if muted else "ink"],
        font=(ui_widgets.FONT_UI, size, "bold" if bold else "normal"),
        anchor="w", justify="left", **kwargs,
    )
    app._workspace_texts.append((widget, de, en))
    return widget


def button(app, parent, de, en, command, *, primary=False):
    widget = ttk.Button(parent, text=text(app, de, en), command=command,
                        style="Start.TButton" if primary else "Browse.TButton")
    app._workspace_texts.append((widget, de, en))
    return widget


def card(app, parent, *, padding=22):
    c = app._workspace_colors
    outer = tk.Frame(parent, bg=c["surface"], highlightbackground=c["line"], highlightthickness=1)
    inner = tk.Frame(outer, bg=c["surface"], padx=padding, pady=padding)
    inner.pack(fill="both", expand=True)
    outer.inner = inner
    return outer


def build_workspace(app, colors, translate):
    from .travel_profiles import profile_choices
    c = colors
    app._workspace_colors = c
    app._workspace_texts = []
    app._settings_sheet = None
    app._settings_tabs = {}
    app._view_mode = "setup"
    app._workflow_labels = []  # No passive controls masquerading as navigation.
    app._help_tips = []
    app._adv_checks = []
    app._toggle_rows = []
    app._cap_labels = []
    app._ui_labels = {}

    root = tk.Frame(app, bg=c["bg"])
    root.pack(fill="both", expand=True)
    footer = tk.Frame(root, bg=c["bg"], pady=18)
    footer.pack(side="bottom", fill="x")
    footer_center = tk.Frame(footer, bg=c["bg"])
    footer_center.pack()
    app._footer = footer
    app._footer_actions_host = footer_center

    host = tk.Frame(root, bg=c["bg"])
    host.pack(fill="both", expand=True)
    app._body_host = host
    canvas = tk.Canvas(host, bg=c["bg"], highlightthickness=0)
    app._body_canvas = canvas
    scrollbar = ttk.Scrollbar(host, command=canvas.yview)
    app._body_scroll = scrollbar
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    content = tk.Frame(canvas, bg=c["bg"], pady=24)
    app._content_frame = content
    app._body_win = canvas.create_window((0, 0), window=content, anchor="nw")
    def update_scroll_region(_event=None):
        bounds = canvas.bbox("all")
        canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), bounds[3] if bounds else 0))
        overflow = bool(bounds and bounds[3] - bounds[1] > canvas.winfo_height() + 4)
        if overflow and not scrollbar.winfo_manager():
            scrollbar.pack(side="right", fill="y", before=canvas)
        elif not overflow and scrollbar.winfo_manager():
            scrollbar.pack_forget()
    content.bind("<Configure>", update_scroll_region)

    def fit_content(event):
        scale = float(app.tk.call("tk", "scaling")) / (96 / 72)
        width = min(round(1100 * scale), max(320, event.width - round(48 * scale)))
        canvas.itemconfigure(app._body_win, width=width)
        canvas.coords(app._body_win, (event.width - width) / 2, 0)
        app._content_width = width
        if hasattr(app, "_summary_description"):
            app._summary_description.configure(wraplength=max(260, width - 70))
            app._mode_label.configure(wraplength=max(260, width - round(250 * scale)))
        update_scroll_region()
        if hasattr(app, "_layout_chrome"):
            app._layout_chrome(width)
    canvas.bind("<Configure>", fit_content)

    header = tk.Frame(content, bg=c["bg"])
    header.pack(fill="x", pady=(0, 24))
    titles = tk.Frame(header, bg=c["bg"])
    titles.pack(side="left")
    app._brand_lbl = label(app, titles, "PhotoTool", "PhotoTool", size=26, bold=True)
    app._brand_lbl.pack(anchor="w")
    app._hero_subtitle = label(app, titles, "Deine Reise. Dein Fotobuch.",
                               "Your trip. Your photobook.", size=14, muted=True)
    app._hero_subtitle.pack(anchor="w", pady=(6, 0))
    tools = tk.Frame(header, bg=c["bg"])
    tools.pack(side="right")
    app._project_btn = button(app, tools, "Projekte", "Projects", app._open_project_manager)
    app._project_btn.pack(side="left", padx=(0, 8))
    app._resume_btn = button(app, tools, "Album fortsetzen", "Resume album", app._open_existing_review)
    app._resume_btn.pack(side="left", padx=(0, 8))
    more = ttk.Menubutton(tools, text=text(app, "Mehr", "More"), style="Browse.TButton")
    more.pack(side="left")
    menu = tk.Menu(more, tearoff=False)
    menu.add_command(label=text(app, "Darstellung & Sprache", "Appearance & language"), command=app._open_settings)
    menu.add_command(label=text(app, "Hilfe", "Help"), command=app._show_help)
    from .update_dialog import open_update_dialog
    menu.add_command(label="Updates", command=lambda: open_update_dialog(app))
    more.configure(menu=menu)
    app._more_menu = menu

    setup = tk.Frame(content, bg=c["bg"])
    app._setup_view = setup
    setup.pack(fill="x")
    plans = tk.Frame(setup, bg=c["bg"])
    plans.pack(fill="x", pady=(0, 16))
    plans.columnconfigure(0, weight=1, uniform="plan")
    plans.columnconfigure(1, weight=1, uniform="plan")
    app._planning_cards = plans
    trip = card(app, plans)
    app._folder_card = trip

    top = tk.Frame(trip.inner, bg=c["surface"])
    top.pack(fill="x", pady=(0, 14))
    label(app, top, "1  Deine Reisefotos", "1  Your travel photos", size=18, bold=True).pack(side="left")
    app._project_name_var = tk.StringVar(value=text(app, "Neue Reise", "New trip"))
    tk.Label(top, textvariable=app._project_name_var, bg=c["surface"], fg=c["muted"],
             font=(app._font_family, 12)).pack(side="right")
    locations = tk.Frame(trip.inner, bg=c["surface"])
    locations.pack(fill="x")
    app._location_labels = []
    for var, title_de, title_en, command in (
        (app.input_var, "Originalfotos", "Original photos", app._pick_input),
        (app.output_var, "Dein Projektordner", "Your project folder", app._pick_output),
    ):
        cell = tk.Frame(locations, bg=c["surface"])
        cell.pack(fill="x", pady=(0, 15))
        details = tk.Frame(cell, bg=c["surface"])
        details.pack(side="left", fill="x", expand=True, padx=(0, 8))
        label(app, details, title_de, title_en, muted=True).pack(anchor="w")
        path_label = tk.Label(details, bg=c["surface"], fg=c["ink"], font=(app._font_family, 14, "bold"),
                              anchor="w", justify="left", wraplength=270)
        path_label.pack(fill="x", pady=(5, 0))
        app._location_labels.append((path_label, var))
        button(app, cell, "Wählen", "Choose", command).pack(side="right")
    app._found_badge = tk.Label(trip.inner, textvariable=app.found_var, bg=c["surface"], fg=c["accent"],
                               font=(app._font_family, 12))
    app._found_badge.pack(anchor="w", pady=(14, 0))
    trip_tools = tk.Frame(trip.inner, bg=c["surface"])
    trip_tools.pack(fill="x", pady=(10, 0))
    app._workflow_tools_host = trip_tools
    app.map_btn = button(app, trip_tools, "Reiseroute", "Route", app._open_map_preview)
    app.map_btn.pack(side="left", padx=(0, 8))
    app._relink_btn = button(app, trip_tools, "Originale finden", "Locate originals", app._open_source_relink)
    app._relink_btn.pack(side="left")

    album = card(app, plans)
    app._settings_card = album

    label(app, album.inner, "2  Deine Auswahl", "2  Your selection", size=18, bold=True).pack(anchor="w", pady=(0, 14))
    row = tk.Frame(album.inner, bg=c["surface"])
    row.pack(fill="x")
    app._album_tools_host = row
    app._profile_choices = profile_choices(getattr(app.app_settings, "language", "de"))
    profile = tk.Frame(row, bg=c["surface"])
    profile.pack(fill="x", expand=True, pady=(0, 14))
    label(app, profile, "Was für eine Reise war es?", "What kind of trip was it?", muted=True).pack(anchor="w", pady=(0, 6))
    app._profile_combo = ttk.Combobox(profile, state="readonly", width=25,
                                    values=[name for _, name in app._profile_choices])
    app._profile_combo.pack(fill="x")
    app._profile_combo.current(0)
    app._profile_combo.bind("<<ComboboxSelected>>", app._apply_selected_profile)
    target = tk.Frame(row, bg=c["surface"])
    target.pack(fill="x")
    app._target_lbl = label(app, target, "Wie viele Fotos sollen bleiben?", "How many photos should remain?", muted=True)
    app._target_lbl.pack(side="left", padx=(0, 12))
    app._target_spin = ttk.Spinbox(target, from_=1, to=2000, textvariable=app.target_var, width=8,
                                  font=(app._font_family, 15, "bold"))
    app._target_spin.pack(side="right")
    button(app, album.inner, "Seitenbudget planen", "Plan page budget", lambda: app._open_selection_settings("variety")).pack(anchor="w", pady=(10, 0))
    app._budget_hint_var = tk.StringVar()
    tk.Label(album.inner, textvariable=app._budget_hint_var, bg=c["surface"], fg=c["muted"],
             font=(app._font_family, 12), anchor="w", wraplength=450).pack(fill="x", pady=(10, 0))
    app._selection_summary_var = tk.StringVar()
    tk.Label(album.inner, textvariable=app._selection_summary_var, bg=c["surface"], fg=c["muted"],
             font=(app._font_family, 12), anchor="w", wraplength=450).pack(fill="x", pady=(10, 0))
    app.advanced_toggle = button(app, album.inner, "Auswahl anpassen", "Customize selection", app._toggle_advanced)
    app.advanced_toggle.pack(anchor="w", pady=(12, 0))

    def fit_planning_cards(event):
        scale = float(app.tk.call("tk", "scaling")) / (96 / 72)
        wide = event.width >= round(900 * scale)
        trip.grid_forget()
        album.grid_forget()
        trip.grid(row=0, column=0, columnspan=1 if wide else 2, sticky="nsew", padx=(0, 9) if wide else 0)
        album.grid(row=0 if wide else 1, column=1 if wide else 0, columnspan=1 if wide else 2,
                   sticky="nsew", padx=(9, 0) if wide else 0, pady=(0, 0) if wide else (16, 0))
    plans.bind("<Configure>", fit_planning_cards)

    summary = card(app, setup)
    summary.pack(fill="x", pady=(0, 8))
    app._mode_title_var = tk.StringVar()
    app._mode_description_var = tk.StringVar()
    mode_heading = tk.Frame(summary.inner, bg=c["surface"])
    mode_heading.pack(fill="x")
    button(app, mode_heading, "KI optional", "Optional AI", lambda: app._open_selection_settings("ai")).pack(side="right", padx=(16, 0))
    app._mode_label = tk.Label(mode_heading, textvariable=app._mode_title_var, bg=c["surface"],
                               fg=c["ink"], font=(app._font_family, 16, "bold"), anchor="w", justify="left", wraplength=760)
    app._mode_label.pack(side="left", fill="x", expand=True)
    app._summary_description = tk.Label(summary.inner, textvariable=app._mode_description_var,
                                        bg=c["surface"], fg=c["muted"], font=(app._font_family, 12),
                                        anchor="w", justify="left", wraplength=980)
    app._summary_description.pack(fill="x", pady=(8, 0))
    app._result_note_var = tk.StringVar()
    app._result_note_label = tk.Label(summary.inner, textvariable=app._result_note_var, bg=c["surface"], fg=c["accent"],
             font=(app._font_family, 12, "bold"), anchor="w", justify="left", wraplength=980)
    app._result_note_var.trace_add("write", lambda *_: app._result_note_label.pack(fill="x", pady=(12, 0)) if app._result_note_var.get() else app._result_note_label.pack_forget())

    analysis = tk.Frame(content, bg=c["bg"])
    app._analysis_view = analysis
    label(app, analysis, "Deine Reise wird sortiert", "Organizing your trip", size=24, bold=True).pack(anchor="w", pady=(12, 8))
    app._analysis_mode_var = tk.StringVar()
    tk.Label(analysis, textvariable=app._analysis_mode_var, bg=c["bg"], fg=c["muted"],
             font=(app._font_family, 13), anchor="w").pack(fill="x", pady=(0, 28))
    app.phase_var = tk.StringVar()
    tk.Label(analysis, textvariable=app.phase_var, bg=c["bg"], fg=c["ink"], font=(app._font_family, 25, "bold"),
             anchor="w", wraplength=980).pack(fill="x", pady=(0, 14))
    app._percent_var = tk.StringVar(value="0 %")
    tk.Label(analysis, textvariable=app._percent_var, bg=c["bg"], fg=c["accent"],
             font=(app._font_family, 20, "bold")).pack(anchor="e", pady=(0, 6))
    app.progress = ttk.Progressbar(analysis, maximum=100, mode="determinate", style="Analysis.Horizontal.TProgressbar")
    app.progress.pack(fill="x", pady=(0, 22))
    label(app, analysis, "Du kannst die Analyse abbrechen. Deine Originale bleiben erhalten.",
          "You can cancel the analysis. Your original photographs are preserved.", muted=True).pack(anchor="w")
    app.next_step_var = tk.StringVar()
    app.status_var = tk.StringVar(value=translate("loading_modules"))
    app._phase_box = tk.Frame(analysis, bg=c["bg"])
    app._phase_inner = tk.Frame(app._phase_box, bg=c["surface"])
    app._phase_inner.pack(fill="x")
    app._details_toggle = button(app, analysis, "Technische Details anzeigen", "Show technical details", app._toggle_log)
    app._details_toggle.pack(anchor="w", pady=(20, 0))
    app._log_host = tk.Frame(analysis, bg=c["bg"])
    app._log_host.pack(fill="both", expand=True)
    app._log_frame = tk.Frame(app._log_host, bg=c["surface"])
    app.log = tk.Text(app._log_frame, height=8, wrap="word", state="disabled", bg=c["log_bg"], fg=c["log_fg"],
                      font=("Consolas" if __import__("sys").platform == "win32" else "Courier", 11),
                      relief="flat", padx=14, pady=14)
    app.log.pack(side="left", fill="both", expand=True)
    app._log_scroll = ttk.Scrollbar(app._log_frame, command=app.log.yview)
    app._log_scroll.pack(side="right", fill="y")
    app.log.configure(yscrollcommand=app._log_scroll.set)

    app._footer_hint = label(app, footer_center, "Originale bleiben erhalten.", "Original photographs are preserved.", muted=True)
    app._footer_hint.pack(side="left", padx=(0, 28))
    app.review_btn = button(app, footer_center, "Auswahl prüfen", "Review selection", app._open_review)
    app.review_btn.pack(side="left", padx=(0, 12))
    app.start_btn = button(app, footer_center, "Lokale Auswahl erstellen", "Create local selection", app._start, primary=True)
    app.start_btn.pack(side="left")
    app.cancel_btn = button(app, footer_center, "Analyse abbrechen", "Cancel analysis", app._cancel)
    app._selection_action_widgets = (app._footer_hint, app.review_btn, app.start_btn)
    app._setup_controls = (app._project_btn, app._resume_btn)

    def layout_chrome(width):
        titles.pack_forget()
        tools.pack_forget()
        if titles.winfo_reqwidth() + tools.winfo_reqwidth() + 24 > width:
            titles.pack(anchor="w")
            tools.pack(anchor="w", pady=(14, 0))
        else:
            titles.pack(side="left")
            tools.pack(side="right")
        gutter = max(16, (footer.winfo_width() - width) // 2)
        footer_center.pack_configure(fill="x", padx=gutter)
        if app._view_mode != "setup":
            return
        for widget in app._selection_action_widgets:
            widget.pack_forget()
        critical_mode = getattr(app, "_critical_run_mode", False)
        if critical_mode:
            app._footer_hint.configure(wraplength=max(260, width))
            app._footer_hint.pack(fill="x", pady=(0, 8))
        action_width = app.start_btn.winfo_reqwidth() + app.review_btn.winfo_reqwidth() + 16
        if action_width > width:
            app.start_btn.pack(fill="x")
            app.review_btn.pack(fill="x", pady=(8, 0))
        else:
            app.start_btn.pack(side="right")
            app.review_btn.pack(side="right", padx=(0, 12))
            if not critical_mode and action_width + app._footer_hint.winfo_reqwidth() + 28 <= width:
                app._footer_hint.pack(side="left")
    app._layout_chrome = layout_chrome

    for variable in (app.input_var, app.output_var, app.target_var, app.max_per_day_var, app.max_per_chapter_var,
                     app.ai_provider_var, app.dry_run_var, app.found_var, app.profile_var, app.cost_var):
        variable.trace_add("write", lambda *_: app._refresh_run_summary())
    app.book_pages_var.trace_add("write", app._refresh_page_budget)
    app.photos_per_page_var.trace_add("write", app._refresh_page_budget)
    app.reserved_pages_var.trace_add("write", app._refresh_page_budget)
    app.target_var.trace_add("write", app._refresh_cost_estimate)
    app.ai_provider_var.trace_add("write", app._refresh_cost_estimate)
    app.output_var.trace_add("write", app._sync_project_actions)
    app._apply_selected_profile()
    for name in ("target_var", "geocode_var", "faces_var", "bursts_var", "aside_var", "finger_var",
                 "accidental_var", "weak_night_var", "content_var", "aesthetic_var", "video_var",
                 "timezone_offset_var", "coverage_var", "coverage_intensity_var", "people_var",
                 "people_intensity_var", "map_preview_var", "ai_provider_var", "max_per_day_var",
                 "max_per_chapter_var", "book_pages_var", "photos_per_page_var", "reserved_pages_var",
                 "storytelling_var", "dry_run_var"):
        getattr(app, name).trace_add("write", app._mark_profile_custom)
    app._sync_project_actions()
    app._refresh_page_budget()
    app._refresh_run_summary()
    app._install_body_wheel()
    app.bind("<Control-o>", lambda _e: app._open_project_manager())
    app.bind("<Control-Return>", lambda _e: app._start())
    app.bind("<F1>", lambda _e: app._show_help())


def open_settings_sheet(app, section="quality"):
    """Show settings in a bounded, scrollable sheet rather than expanding setup."""
    from .ui_widgets import HelpTip
    c = app._workspace_colors
    if app._settings_sheet is None:
        sheet = tk.Toplevel(app)
        sheet.withdraw()
        app._settings_sheet = sheet
        sheet.configure(bg=c["bg"])
        sheet.transient(app)
        sheet.title(text(app, "Auswahl anpassen", "Customize selection"))
        header = tk.Frame(sheet, bg=c["bg"], padx=24, pady=20)
        header.pack(fill="x")
        label(app, header, "So soll deine Auswahl aussehen", "Make the selection yours", size=20, bold=True).pack(anchor="w")
        label(app, header, "Änderungen gelten für den nächsten Lauf.", "Changes apply to the next run.", muted=True).pack(anchor="w", pady=(5, 0))
        footer = tk.Frame(sheet, bg=c["bg"], padx=24, pady=16)
        footer.pack(side="bottom", fill="x")
        app._sheet_mode_var = tk.StringVar()
        tk.Label(footer, textvariable=app._sheet_mode_var, bg=c["bg"], fg=c["accent"],
                 font=(app._font_family, 12, "bold"), anchor="w", wraplength=540).pack(side="left", fill="x", expand=True)
        button(app, footer, "Fertig", "Done", app._close_selection_settings, primary=True).pack(side="right", padx=(16, 0))
        notebook = ttk.Notebook(sheet)
        app._settings_notebook = notebook
        notebook.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        app._settings_scroll = {}

        def tab(key, de, en):
            frame = tk.Frame(notebook, bg=c["surface"])
            notebook.add(frame, text=text(app, de, en))
            scroll = ttk.Scrollbar(frame, orient="vertical")
            scroll.pack(side="right", fill="y")
            canvas = tk.Canvas(frame, bg=c["surface"], highlightthickness=0, yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll.configure(command=canvas.yview)
            inner = tk.Frame(canvas, bg=c["surface"], padx=22, pady=20)
            window = canvas.create_window((0, 0), window=inner, anchor="nw")
            inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
            app._settings_tabs[key] = frame
            app._settings_scroll[str(frame)] = canvas
            return inner

        def check(parent, variable, de, en, help_key=None):
            row = tk.Frame(parent, bg=c["surface"])
            row.pack(fill="x", pady=6)
            widget = ttk.Checkbutton(row, text=text(app, de, en), variable=variable,
                                     command=app._sync_dependent_controls)
            widget.pack(side="left")
            app._workspace_texts.append((widget, de, en))
            if help_key:
                tip = HelpTip(row, help_key, c, get_text=app._translate)
                tip.pack(side="left", padx=(6, 0))
                app._help_tips.append(tip)
            return widget

        def heading(parent, de, en):
            label(app, parent, de, en, size=15, bold=True).pack(anchor="w", pady=(14, 9))

        quality = tab("quality", "Bildqualität", "Photo quality")
        label(app, quality, "Technische Hilfe bei der Vorauswahl. Du entscheidest beim Prüfen.",
              "Technical help with the first selection. You decide during review.", muted=True, wraplength=650).pack(fill="x", pady=(0, 10))
        for variable, de, en, help_key in (
            (app.faces_var, "Gesichter und geschlossene Augen prüfen", "Check faces and closed eyes", "help_opt_faces"),
            (app.bursts_var, "Aus ähnlichen Serien die besten Bilder behalten", "Keep the best pictures from similar bursts", "help_opt_bursts"),
            (app.aside_var, "Screenshots und Dokumente separat sammeln", "Collect screenshots and documents separately", "help_opt_aside"),
            (app.accidental_var, "Mögliche Fehlaufnahmen aussortieren", "Exclude likely accidental photographs", "help_opt_accidental"),
            (app.weak_night_var, "Schwache Nachtaufnahmen aussortieren", "Exclude poor night photographs", "help_opt_weak_night"),
            (app.finger_var, "Finger vor der Linse erkennen", "Detect fingers covering the lens", "help_opt_finger"),
            (app.aesthetic_var, "Bildwirkung bewerten", "Assess visual appeal", "help_opt_aesthetic"),
            (app.video_var, "Standbilder aus Videos hinzufügen", "Include still images from videos", "help_opt_video"),
        ):
            check(quality, variable, de, en, help_key)
        heading(quality, "Orte und Aufnahmezeit", "Locations and capture time")
        check(quality, app.geocode_var, "Ortsnamen online ermitteln", "Look up place names online", "help_opt_geocode")
        tz = tk.Frame(quality, bg=c["surface"])
        tz.pack(fill="x", pady=(8, 0))
        label(app, tz, "Uhrzeit korrigieren · Stunden", "Correct capture time · hours").pack(side="left")
        app.timezone_spin = ttk.Spinbox(tz, from_=-14, to=14, increment=0.5,
                                        textvariable=app.timezone_offset_var, width=7)
        app.timezone_spin.pack(side="right")

        variety = tab("variety", "Abwechslung", "Variety")
        heading(variety, "Albumgrösse aus Seiten berechnen", "Calculate selection size from pages")
        label(app, variety, "0 Buchseiten bedeutet: Zielanzahl im Hauptfenster selbst wählen.",
              "0 book pages means: choose the target photo count in the main window.", muted=True, wraplength=650).pack(fill="x", pady=(0, 12))
        budget_row = tk.Frame(variety, bg=c["surface"])
        budget_row.pack(fill="x")
        for n, (var, de, en) in enumerate((
            (app.book_pages_var, "Buchseiten", "Book pages"),
            (app.photos_per_page_var, "Fotos je Seite", "Photos per page"),
            (app.reserved_pages_var, "Titel-/Textseiten", "Title/text pages"),
        )):
            cell = tk.Frame(budget_row, bg=c["surface"])
            cell.pack(side="left", fill="x", expand=True, padx=(0, 12) if n < 2 else 0)
            label(app, cell, de, en, muted=True).pack(anchor="w", pady=(0, 5))
            ttk.Entry(cell, textvariable=var, width=12).pack(fill="x")
        heading(variety, "Ausgewogene Reisegeschichte", "A balanced travel story")
        check(variety, app.content_var, "Ähnliche Bilder reduzieren", "Reduce similar photographs", "help_opt_content")
        check(variety, app.coverage_var, "Reisetage ausgewogen berücksichtigen", "Represent travel days evenly", "help_opt_coverage")
        app.coverage_block = tk.Frame(variety, bg=c["surface"])
        app.coverage_block.pack(fill="x", padx=(20, 0), pady=(0, 8))
        app.coverage_label = label(app, app.coverage_block, "Stärke", "Strength", muted=True)
        app.coverage_label.pack(side="left")
        app.coverage_scale = ttk.Scale(app.coverage_block, from_=0.1, to=1, variable=app.coverage_intensity_var,
                                       command=app._on_coverage_scale)
        app.coverage_scale.pack(side="right", fill="x", expand=True, padx=(18, 0))
        check(variety, app.people_var, "Personen gleichmässiger zeigen", "Show people more evenly", "help_opt_people")
        app.people_block = tk.Frame(variety, bg=c["surface"])
        app.people_block.pack(fill="x", padx=(20, 0), pady=(0, 8))
        app.people_label = label(app, app.people_block, "Stärke", "Strength", muted=True)
        app.people_label.pack(side="left")
        app.people_scale = ttk.Scale(app.people_block, from_=0.1, to=1, variable=app.people_intensity_var,
                                     command=app._on_people_scale)
        app.people_scale.pack(side="right", fill="x", expand=True, padx=(18, 0))
        story = tk.Frame(variety, bg=c["surface"])
        story.pack(fill="x", pady=(10, 14))
        label(app, story, "Verschiedene Motive mischen", "Mix different kinds of photographs").pack(side="left")
        ttk.Scale(story, from_=0, to=1, variable=app.storytelling_var).pack(side="right", fill="x", expand=True, padx=(18, 0))
        for var, de, en in ((app.max_per_day_var, "Höchstens Fotos pro Tag · 0 = unbegrenzt", "Maximum photos per day · 0 = unlimited"),
                            (app.max_per_chapter_var, "Höchstens Fotos pro Kapitel · 0 = unbegrenzt", "Maximum photos per chapter · 0 = unlimited")):
            row = tk.Frame(variety, bg=c["surface"])
            row.pack(fill="x", pady=7)
            label(app, row, de, en).pack(side="left")
            ttk.Spinbox(row, from_=0, to=10000, textvariable=var, width=7).pack(side="right")
        label(app, variety, "Geschützte Favoriten haben Vorrang vor diesen Grenzen.",
              "Protected favorites take priority over these limits.", muted=True, wraplength=650).pack(fill="x", pady=(8, 12))
        check(variety, app.map_preview_var, "Kapitel und Reiseroute vor dem Export ansehen", "Preview chapters and route before export", "help_opt_map")

        ai = tab("ai", "KI", "AI")
        app.ai_block = ai
        label(app, ai, "Die lokale Auswahl funktioniert vollständig ohne KI.",
              "The local selection works fully without AI.", size=15, bold=True, wraplength=650).pack(fill="x", pady=(0, 8))
        label(app, ai, "Optional danach mit KI bewerten: Die lokale Analyse wird wiederverwendet, und nur Kandidaten werden an den Anbieter geschickt.",
              "Optionally add AI review later: local analysis is reused and only shortlisted candidates are sent to the provider.",
              muted=True, wraplength=650).pack(fill="x", pady=(0, 20))
        label(app, ai, "Auswahlmodus", "Selection mode", muted=True).pack(anchor="w", pady=(0, 5))
        app._ai_provider_values = app._provider_label_pairs()
        app.ai_provider_combo = ttk.Combobox(ai, state="readonly", values=[name for _, name in app._ai_provider_values])
        app.ai_provider_combo.pack(fill="x")
        app.ai_provider_combo.bind("<<ComboboxSelected>>", app._on_ai_provider_selected)
        app.ai_blurb_var = tk.StringVar()
        app._ai_blurb_lbl = tk.Label(ai, textvariable=app.ai_blurb_var, bg=c["surface"], fg=c["muted"],
                                    font=(app._font_family, 12), wraplength=650, anchor="w", justify="left")
        app._ai_blurb_lbl.pack(fill="x", pady=(12, 18))
        app._key_row = tk.Frame(ai, bg=c["surface"])
        app._api_key_lbl = label(app, app._key_row, "API-Schlüssel", "API key", muted=True)
        app._api_key_lbl.pack(side="left")
        app._api_key_link = ttk.Button(app._key_row, text=text(app, "Schlüssel erstellen", "Create key"),
                                       command=app._open_api_key_url, style="Browse.TButton")
        app._api_key_link.pack(side="right")
        app.api_entry = ttk.Entry(ai, show="•")
        app._ollama_hint_lbl = label(app, ai, "Ollama muss auf diesem Gerät laufen.", "Ollama must be running on this device.", muted=True)
        app._ollama_lbl_row = tk.Frame(ai, bg=c["surface"])
        label(app, app._ollama_lbl_row, "Lokales Vision-Modell", "Local vision model").pack(side="left")
        app.ollama_model_combo = ttk.Combobox(ai, textvariable=app.ollama_model_var, values=app._default_ollama_choices())
        app.ollama_model_entry = app.ollama_model_combo
        app._ollama_row = app._ollama_lbl_row
        app._dry_row = tk.Frame(ai, bg=c["surface"])
        app.dry_run_chk = ttk.Checkbutton(app._dry_row,
                                          text=text(app, "Nur Kosten schätzen · keine fertige Auswahl", "Estimate cost only · no finished selection"),
                                          variable=app.dry_run_var, command=app._sync_dependent_controls)
        app.dry_run_chk.pack(anchor="w")
        tk.Label(ai, textvariable=app.cost_var, bg=c["surface"], fg=c["accent"], font=(app._font_family, 12),
                 anchor="w", wraplength=650).pack(fill="x", pady=(14, 0))

        def wheel(event):
            canvas = app._settings_scroll.get(notebook.select())
            if canvas is not None:
                delta = -1 if getattr(event, "num", 0) == 4 else 1
                if getattr(event, "delta", 0):
                    delta = -1 if event.delta > 0 else 1
                canvas.yview_scroll(delta * 3, "units")
            return "break"
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            sheet.bind(sequence, wheel)
        sheet.bind("<Escape>", lambda _e: app._close_selection_settings())
        sheet.protocol("WM_DELETE_WINDOW", app._close_selection_settings)
    sheet = app._settings_sheet
    scale = float(app.tk.call("tk", "scaling")) / (96 / 72)
    width = min(round(880 * scale), app.winfo_screenwidth() - 48)
    height = min(round(740 * scale), app.winfo_screenheight() - 80)
    sheet.geometry(f"{width}x{height}+{max(0, (app.winfo_screenwidth()-width)//2)}+{max(0,(app.winfo_screenheight()-height)//2)}")
    sheet.minsize(min(round(650 * scale), width), min(round(460 * scale), height))
    app._settings_notebook.select(app._settings_tabs.get(section, app._settings_tabs["quality"]))
    app._advanced_open = True
    app._sync_ai_provider_combo_display()
    app._sync_dependent_controls()
    app._refresh_run_summary()
    sheet.deiconify()
    sheet.lift()
    sheet.grab_set()
    sheet.focus_set()


def refresh_texts(app):
    for widget, de, en in app._workspace_texts:
        if widget.winfo_exists():
            widget.configure(text=text(app, de, en))
    if app._settings_sheet is not None:
        for key, de, en in (("quality", "Bildqualität", "Photo quality"), ("variety", "Abwechslung", "Variety"), ("ai", "KI", "AI")):
            app._settings_notebook.tab(app._settings_tabs[key], text=text(app, de, en))
