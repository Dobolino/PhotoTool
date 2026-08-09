"""Einstellungsdialog: Sprache, Design, Diashow-Optionen."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .i18n import set_language, t
from .settings import (
    AppSettings,
    load_settings,
    save_settings,
    theme_choices,
    theme_colors,
)


def open_settings_dialog(
    master: tk.Misc,
    on_saved: Optional[Callable[[AppSettings], None]] = None,
) -> tk.Toplevel:
    settings = load_settings()
    colors = theme_colors(settings.theme)

    win = tk.Toplevel(master)
    win.title(t("settings_title"))
    win.minsize(420, 360)
    win.configure(bg=colors["bg"])
    win.transient(master)
    try:
        win.grab_set()
    except tk.TclError:
        pass

    frame = ttk.Frame(win, padding=16)
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text=t("settings_title"), font=("Segoe UI Semibold", 12)).pack(
        anchor=tk.W
    )
    ttk.Label(frame, text=t("settings_hint"), wraplength=380).pack(
        anchor=tk.W, pady=(4, 14)
    )

    lang_row = ttk.Frame(frame)
    lang_row.pack(fill=tk.X, pady=4)
    ttk.Label(lang_row, text=t("language")).pack(side=tk.LEFT)
    lang_var = tk.StringVar(value=settings.language)
    lang_box = ttk.Combobox(
        lang_row,
        textvariable=lang_var,
        state="readonly",
        values=("de", "en"),
        width=12,
    )
    lang_box.pack(side=tk.RIGHT)
    # Anzeige freundlicher Labels über Mapping
    lang_labels = {"de": t("lang_de"), "en": t("lang_en")}
    lang_display = tk.StringVar(value=lang_labels.get(settings.language, settings.language))
    lang_box.configure(values=[lang_labels["de"], lang_labels["en"]])
    lang_display.set(lang_labels.get(settings.language, t("lang_de")))
    lang_box.configure(textvariable=lang_display)

    theme_row = ttk.Frame(frame)
    theme_row.pack(fill=tk.X, pady=8)
    ttk.Label(theme_row, text=t("theme")).pack(side=tk.LEFT)
    choices = theme_choices(settings.language)
    id_by_label = {label: tid for tid, label in choices}
    label_by_id = {tid: label for tid, label in choices}
    theme_display = tk.StringVar(
        value=label_by_id.get(settings.theme, choices[0][1] if choices else settings.theme)
    )
    theme_box = ttk.Combobox(
        theme_row,
        textvariable=theme_display,
        state="readonly",
        values=[label for _, label in choices],
        width=22,
    )
    theme_box.pack(side=tk.RIGHT)

    auto_var = tk.BooleanVar(value=settings.slideshow_auto_advance)
    alt_var = tk.BooleanVar(value=settings.slideshow_show_alternative)
    ttk.Checkbutton(frame, text=t("auto_advance"), variable=auto_var).pack(
        anchor=tk.W, pady=(10, 2)
    )
    ttk.Checkbutton(frame, text=t("show_alt"), variable=alt_var).pack(
        anchor=tk.W, pady=2
    )

    # Mini-Vorschau der Farben
    preview = tk.Frame(frame, bg=colors["bg"], highlightthickness=1, highlightbackground=colors["line"])
    preview.pack(fill=tk.X, pady=(16, 8))
    swatch = tk.Frame(preview, bg=colors["accent"], height=28)
    swatch.pack(fill=tk.X)
    tk.Label(
        preview,
        text=theme_display.get(),
        bg=colors["surface"],
        fg=colors["ink"],
        font=("Segoe UI", 9),
        padx=8,
        pady=6,
    ).pack(fill=tk.X)

    def _refresh_preview(*_args) -> None:
        label = theme_display.get()
        tid = id_by_label.get(label, settings.theme)
        c = theme_colors(tid)
        try:
            preview.configure(bg=c["bg"], highlightbackground=c["line"])
            swatch.configure(bg=c["accent"])
            for child in preview.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=c["surface"], fg=c["ink"], text=label)
        except tk.TclError:
            pass

    theme_box.bind("<<ComboboxSelected>>", _refresh_preview)

    def _save() -> None:
        lang_label = lang_display.get()
        language = "en" if lang_label == lang_labels["en"] or lang_label == "en" else "de"
        theme_id = id_by_label.get(theme_display.get(), settings.theme)
        new = AppSettings(
            language=language,
            theme=theme_id,
            slideshow_auto_advance=bool(auto_var.get()),
            slideshow_show_alternative=bool(alt_var.get()),
        ).normalized()
        save_settings(new)
        set_language(new.language)
        messagebox.showinfo(t("settings_title"), t("settings_saved"), parent=win)
        if on_saved:
            on_saved(new)
        win.destroy()

    btns = ttk.Frame(frame)
    btns.pack(fill=tk.X, pady=(16, 0))
    ttk.Button(btns, text=t("save_settings"), command=_save).pack(side=tk.RIGHT)
    ttk.Button(btns, text=t("close"), command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    return win
