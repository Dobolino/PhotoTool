"""Fenstergröße und Position – direkt richtig öffnen, ohne Aufziehen."""

from __future__ import annotations

import tkinter as tk
from typing import Optional


def screen_size(win: tk.Misc) -> tuple[int, int]:
    try:
        sw = int(win.winfo_screenwidth())
        sh = int(win.winfo_screenheight())
        return max(800, sw), max(600, sh)
    except tk.TclError:
        return 1280, 800


def place_window(
    win: tk.Misc,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    frac_w: float = 0.62,
    frac_h: float = 0.88,
    min_width: int = 720,
    min_height: int = 560,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    center: bool = True,
    maximize: bool = False,
) -> None:
    """Setzt sinnvolle Startgröße (relativ zum Bildschirm) und zentriert."""
    sw, sh = screen_size(win)
    if maximize:
        try:
            win.state("zoomed")  # type: ignore[attr-defined]
            return
        except tk.TclError:
            pass

    w = int(width if width is not None else sw * frac_w)
    h = int(height if height is not None else sh * frac_h)
    w = max(min_width, w)
    h = max(min_height, h)
    if max_width is not None:
        w = min(w, max_width)
    if max_height is not None:
        h = min(h, max_height)
    # Rand zum Taskleisten-/Dock-Bereich
    w = min(w, sw - 24)
    h = min(h, sh - 48)

    # minsize nicht größer als Bildschirm (kleine Laptops / 1366×768)
    try:
        win.minsize(min(min_width, sw - 40), min(min_height, sh - 60))  # type: ignore[attr-defined]
    except tk.TclError:
        pass

    if center:
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        geo = f"{w}x{h}+{x}+{y}"
    else:
        geo = f"{w}x{h}"
    try:
        win.geometry(geo)  # type: ignore[attr-defined]
    except tk.TclError:
        pass


def fit_dialog(
    win: tk.Misc,
    *,
    min_width: int = 420,
    min_height: int = 320,
    pad: int = 32,
    max_frac_w: float = 0.7,
    max_frac_h: float = 0.85,
) -> None:
    """Dialog an Inhalt anpassen (nach dem Aufbau), mit Deckel."""
    try:
        win.update_idletasks()  # type: ignore[attr-defined]
    except tk.TclError:
        pass
    sw, sh = screen_size(win)
    try:
        req_w = int(win.winfo_reqwidth())  # type: ignore[attr-defined]
        req_h = int(win.winfo_reqheight())  # type: ignore[attr-defined]
    except tk.TclError:
        req_w, req_h = min_width, min_height
    w = max(min_width, req_w + pad)
    h = max(min_height, req_h + pad)
    w = min(w, int(sw * max_frac_w))
    h = min(h, int(sh * max_frac_h))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    try:
        win.minsize(min_width, min_height)  # type: ignore[attr-defined]
        win.geometry(f"{w}x{h}+{x}+{y}")  # type: ignore[attr-defined]
    except tk.TclError:
        pass
