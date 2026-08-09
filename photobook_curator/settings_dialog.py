"""Einstellungsdialog: Sprache, Design, Diashow-Optionen (Nacht-UI, genug Padding)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .i18n import set_language, t
from .settings import (
    AppSettings,
    load_settings,
    save_settings,
    theme_choices,
    theme_colors,
)
from .ui_widgets import AnAusToggle, PaddedButton, card, section_header


def open_settings_dialog(
    master: tk.Misc,
    on_saved: Optional[Callable[[AppSettings], None]] = None,
) -> tk.Toplevel:
    settings = load_settings()
    colors = theme_colors(settings.theme)

    win = tk.Toplevel(master)
    win.title(t("settings_title"))
    win.minsize(460, 420)
    win.geometry("500x460")
    win.configure(bg=colors["bg"])
    win.transient(master)
    try:
        win.grab_set()
    except tk.TclError:
        pass

    outer = tk.Frame(win, bg=colors["bg"], padx=22, pady=18)
    outer.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        outer,
        text=t("settings_title"),
        bg=colors["bg"],
        fg=colors["ink"],
        font=("Segoe UI Semibold", 16),
        anchor=tk.W,
    ).pack(anchor=tk.W)
    tk.Label(
        outer,
        text=t("settings_hint"),
        bg=colors["bg"],
        fg=colors["muted"],
        font=("Segoe UI", 9),
        wraplength=440,
        justify=tk.LEFT,
        anchor=tk.W,
    ).pack(anchor=tk.W, pady=(6, 16))

    panel = card(outer, colors)
    panel.pack(fill=tk.BOTH, expand=True)
    frame = panel._inner  # type: ignore[attr-defined]

    # Sprache
    section_header(frame, t("language"), {**colors, "bg": colors["surface"]})
    lang_labels = {"de": t("lang_de"), "en": t("lang_en")}
    lang_display = tk.StringVar(value=lang_labels.get(settings.language, t("lang_de")))
    lang_box = ttk.Combobox(
        frame,
        textvariable=lang_display,
        state="readonly",
        values=[lang_labels["de"], lang_labels["en"]],
        width=28,
    )
    lang_box.pack(anchor=tk.W, pady=(0, 14), ipady=4)

    # Design
    section_header(frame, t("theme"), {**colors, "bg": colors["surface"]})
    choices = theme_choices(settings.language)
    id_by_label = {label: tid for tid, label in choices}
    label_by_id = {tid: label for tid, label in choices}
    theme_display = tk.StringVar(
        value=label_by_id.get(settings.theme, choices[0][1] if choices else settings.theme)
    )
    theme_box = ttk.Combobox(
        frame,
        textvariable=theme_display,
        state="readonly",
        values=[label for _, label in choices],
        width=28,
    )
    theme_box.pack(anchor=tk.W, pady=(0, 8), ipady=4)

    preview = tk.Frame(
        frame,
        bg=colors["bg"],
        highlightthickness=1,
        highlightbackground=colors["line"],
    )
    preview.pack(fill=tk.X, pady=(0, 16))
    swatch = tk.Frame(preview, bg=colors["accent"], height=32)
    swatch.pack(fill=tk.X)
    preview_lbl = tk.Label(
        preview,
        text=theme_display.get(),
        bg=colors["surface"],
        fg=colors["ink"],
        font=("Segoe UI", 9),
        padx=12,
        pady=8,
        anchor=tk.W,
    )
    preview_lbl.pack(fill=tk.X)

    def _refresh_preview(*_args) -> None:
        label = theme_display.get()
        tid = id_by_label.get(label, settings.theme)
        c = theme_colors(tid)
        try:
            preview.configure(bg=c["bg"], highlightbackground=c["line"])
            swatch.configure(bg=c["accent"])
            preview_lbl.configure(bg=c["surface"], fg=c["ink"], text=label)
        except tk.TclError:
            pass

    theme_box.bind("<<ComboboxSelected>>", _refresh_preview)

    # Diashow-Optionen als An/Aus
    auto_var = tk.BooleanVar(value=settings.slideshow_auto_advance)
    alt_var = tk.BooleanVar(value=settings.slideshow_show_alternative)
    toggles: list[AnAusToggle] = []
    for label_key, var in (
        ("auto_advance", auto_var),
        ("show_alt", alt_var),
    ):
        row = tk.Frame(frame, bg=colors["surface"])
        row.pack(fill=tk.X, pady=8)
        tk.Label(
            row,
            text=t(label_key),
            bg=colors["surface"],
            fg=colors["ink"],
            font=("Segoe UI", 10),
            anchor=tk.W,
            wraplength=280,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        tog = AnAusToggle(
            row,
            var,
            colors,
            on_text=t("toggle_on"),
            off_text=t("toggle_off"),
        )
        tog.pack(side=tk.RIGHT)
        toggles.append(tog)

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
        if on_saved:
            on_saved(new)
        win.destroy()

    btns = tk.Frame(outer, bg=colors["bg"])
    btns.pack(fill=tk.X, pady=(16, 0))
    PaddedButton(
        btns,
        t("save_settings"),
        colors,
        command=_save,
        primary=True,
        padx=18,
        pady=11,
    ).pack(side=tk.RIGHT)
    PaddedButton(
        btns,
        t("close"),
        colors,
        command=win.destroy,
        padx=18,
        pady=11,
    ).pack(side=tk.RIGHT, padx=(0, 10))

    return win
