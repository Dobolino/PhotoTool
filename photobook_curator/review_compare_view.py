"""Focused album/alternative preview widgets; state stays in ReviewWindow."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def build_preview(view, colors, font):
    c = colors
    host = view._slide_host
    bg = c.get("slide_stage", c["bg"])
    top = tk.Frame(host, bg=c["bg"])
    top.pack(fill="x", pady=(0, 10))
    view._grid_back_btn = ttk.Button(top, text="Albumübersicht", style="Compare.TButton", command=view._exit_slideshow)
    view._grid_back_btn.pack(side="left")
    view._preview_breadcrumb = tk.StringVar()
    tk.Label(top, textvariable=view._preview_breadcrumb, bg=c["bg"], fg=c["muted"],
             font=(font, 12), anchor="w").pack(side="left", fill="x", expand=True, padx=16)
    ttk.Button(top, text="Pause & speichern", style="Compare.TButton", command=view._close).pack(side="right")
    view._preview_audit_report_button = ttk.Button(top, text="Prüfbericht", style="Compare.TButton", command=view._open_audit_report)
    view._preview_audit_report_button.pack(side="right", padx=(0, 8))

    footer = tk.Frame(host, bg=c["bg"])
    footer.pack(side="bottom", fill="x", pady=(12, 0))
    view._slide_status = tk.StringVar()
    view._slide_caption = tk.StringVar()
    view._slide_notes = tk.StringVar()
    view._preview_feedback_var = tk.StringVar()
    navigation = tk.Frame(footer, bg=c["bg"])
    navigation.pack(fill="x", pady=(0, 10))
    view._preview_prev_btn = ttk.Button(navigation, text="Voriges Albumfoto", style="Compare.TButton", command=view._slide_prev)
    view._preview_prev_btn.pack(side="left")
    count_label = tk.Label(navigation, textvariable=view._slide_status, bg=c["bg"], fg=c["muted"],
                          font=(font, 12), anchor="center", justify="center")
    count_label.pack(side="left", fill="x", expand=True, padx=12)
    view._preview_next_btn = ttk.Button(navigation, text="Nächstes Albumfoto", style="Compare.TButton", command=view._slide_next)
    view._preview_next_btn.pack(side="right")
    navigation.bind("<Configure>", lambda _e: count_label.configure(
        wraplength=max(180, navigation.winfo_width() - view._preview_prev_btn.winfo_reqwidth()
                       - view._preview_next_btn.winfo_reqwidth() - 28)))
    actions = tk.Frame(footer, bg=c["bg"])
    actions.pack(fill="x")
    primary_actions = tk.Frame(actions, bg=c["bg"])
    secondary_actions = tk.Frame(actions, bg=c["bg"])
    primary_actions.pack(side="left")
    secondary_actions.pack(side="right")
    view._album_back_btn = ttk.Button(primary_actions, text="Zurück zum Albumfoto", style="Compare.TButton", command=view._return_to_album_slideshow)
    view._slide_toggle_btn = ttk.Button(primary_actions, text="Aus Album entfernen", style="Compare.TButton", command=view._slide_toggle_current)
    view._slide_toggle_btn.pack(side="left")
    view._compare_btn = ttk.Button(primary_actions, text="Varianten vergleichen", style="ComparePrimary.TButton", command=view._preview_alternatives)
    view._compare_btn.pack(side="left", padx=(10, 0))
    view._compare_add_btn = ttk.Button(primary_actions, text="Zusätzlich aufnehmen", style="Compare.TButton", command=view._comparison_add_current)
    view._compare_replace_btn = ttk.Button(primary_actions, text="Als Ersatz wählen", style="ComparePrimary.TButton", command=view._slide_take_alternative)
    view._preview_more = ttk.Menubutton(secondary_actions, text="Mehr", style="Compare.TMenubutton")
    view._preview_menu = tk.Menu(view._preview_more, tearoff=False, bg=c["surface"], fg=c["ink"],
                                 font=(font, 12))
    view._preview_more.configure(menu=view._preview_menu)
    view._preview_more.pack(side="right")
    view._preview_why_btn = ttk.Button(secondary_actions, text="Warum dieses Bild?", style="Compare.TButton", command=view._explain_current)
    view._preview_why_btn.pack(side="right", padx=(10, 10))
    view._preview_undo_btn = ttk.Button(secondary_actions, text="Rückgängig", style="Compare.TButton", command=view._undo)
    view._preview_undo_btn.pack(side="right", padx=(10, 0))
    view._preview_feedback = tk.Label(footer, textvariable=view._preview_feedback_var, bg=c["bg"], fg=c["accent"],
                                       font=(font, 12), anchor="w", justify="left", wraplength=1120)
    view._preview_feedback.pack(fill="x", pady=(8, 0))

    view._comparison_switcher = tk.Frame(host, bg=c["bg"])
    view._anchor_view_btn = ttk.Button(view._comparison_switcher, text="Albumfoto", style="Compare.TButton",
                                       command=lambda: view._set_comparison_side("anchor"))
    view._anchor_view_btn.pack(side="left", padx=(0, 8))
    view._candidate_view_btn = ttk.Button(view._comparison_switcher, text="Alternative", style="Compare.TButton",
                                          command=lambda: view._set_comparison_side("candidate"))
    view._candidate_view_btn.pack(side="left")
    stage_row = tk.Frame(host, bg=c["bg"])
    stage_row.pack(fill="both", expand=True)
    view._comparison_stage_row = stage_row
    stage_row.columnconfigure(0, weight=1, uniform="preview")
    stage_row.columnconfigure(1, weight=1, uniform="preview")
    stage_row.rowconfigure(0, weight=1)
    for kind in ("anchor", "current"):
        panel = tk.Frame(stage_row, bg=bg, padx=12, pady=10)
        heading = tk.Frame(panel, bg=bg)
        heading.pack(fill="x", pady=(0, 8))
        title = tk.Label(heading, bg=bg, fg=c["ink"], font=(font, 14, "bold"), anchor="w")
        title.pack(side="left", fill="x", expand=True)
        caption = tk.StringVar()
        tk.Label(panel, textvariable=caption, bg=bg, fg=c["muted"], font=(font, 11),
                 anchor="w", justify="left", wraplength=560).pack(side="bottom", fill="x", pady=(8, 0))
        stage = tk.Frame(panel, bg=bg)
        stage.pack(fill="both", expand=True)
        stage.pack_propagate(False)
        image = tk.Label(stage, bg=bg, fg=c["ink"], font=(font, 12), text="Bild wird geladen...")
        image.pack(fill="both", expand=True)
        if kind == "anchor":
            view._anchor_panel, view._anchor_title, view._anchor_caption = panel, title, caption
            view._anchor_stage, view._anchor_image_lbl = stage, image
            ttk.Button(heading, text="Warum?", style="Compare.TButton", command=view._explain_anchor).pack(side="right", padx=(8, 0))
            stage.bind("<Configure>", lambda _e: view._show_anchor_image())
        else:
            view._current_panel, view._current_title, view._current_caption = panel, title, caption
            view._slide_stage, view._slide_image_lbl = stage, image
            panel.grid(row=0, column=0, columnspan=2, sticky="nsew")
            stage.bind("<Configure>", view._on_slide_stage_configure)
            image.bind("<Button-1>", lambda _e: view.focus_set())
            image.bind("<MouseWheel>", view._slide_mousewheel)
    stage_row.bind("<Configure>", lambda _e: view._fit_comparison_panels())

    # Existing filters remain a data contract, not a second preview toolbar.
    view._filter_var = tk.StringVar(value=view._filter_mode)
    view._chapter_var = tk.StringVar(value="")
    view._filter_buttons = []
    view._chapter_combo = ttk.Combobox(host, textvariable=view._chapter_var)
    view._strip_bar = tk.Frame(host, bg=bg)  # No filmstrip competing with the pair.
    view._alt_caption = tk.StringVar()
    view._alt_idx = None

    def fit_actions(_event=None):
        width = actions.winfo_width()
        view._preview_feedback.configure(wraplength=max(260, width))
        wide = primary_actions.winfo_reqwidth() + secondary_actions.winfo_reqwidth() + 24 <= width
        primary_actions.pack_forget()
        secondary_actions.pack_forget()
        if wide:
            primary_actions.pack(side="left")
            secondary_actions.pack(side="right")
        else:
            primary_actions.pack(anchor="w")
            secondary_actions.pack(anchor="e", pady=(8, 0))
    view._fit_preview_actions = fit_actions
    actions.bind("<Configure>", fit_actions)
