"""Tk update dialog; network work runs off the UI thread."""

import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from . import __version__
from .i18n import t
from .updater import RELEASES_URL, check_update, download_update, launch_installer


def open_update_dialog(app) -> None:
    existing = getattr(app, "_update_window", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return
    win = tk.Toplevel(app)
    app._update_window = win
    win.title(t("update_title"))
    win.transient(app)
    win.resizable(False, False)
    body = ttk.Frame(win, padding=20)
    body.pack(fill=tk.BOTH, expand=True)
    ttk.Label(body, text=f"PhotoTool {__version__}").pack(anchor=tk.W)
    status = tk.StringVar(value=t("update_checking"))
    ttk.Label(body, textvariable=status, wraplength=420).pack(anchor=tk.W, pady=12)
    results = queue.Queue()
    available = None

    def background(kind, function):
        def work():
            try:
                results.put((kind, function(), None))
            except Exception as exc:
                results.put((kind, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def install():
        if available is None:
            return
        if app._is_analysis_running():
            messagebox.showinfo(t("update_title"), t("update_busy"), parent=win)
            return
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            webbrowser.open(RELEASES_URL)
            return
        if not messagebox.askyesno(t("update_title"), t("update_confirm"), parent=win):
            return
        button.configure(state=tk.DISABLED)
        status.set(t("update_downloading"))
        background("download", lambda: download_update(available))

    button = ttk.Button(body, text=t("update_install"), command=install, state=tk.DISABLED)
    button.pack(anchor=tk.W)

    def poll():
        nonlocal available
        if not win.winfo_exists():
            return
        try:
            kind, result, error = results.get_nowait()
        except queue.Empty:
            win.after(100, poll)
            return
        if error:
            status.set(t("update_error", error=error))
            if available:
                button.configure(state=tk.NORMAL)
        elif kind == "check":
            available = result
            status.set(t("update_available", version=result.version) if result else t("update_current"))
            if result:
                button.configure(state=tk.NORMAL)
        else:
            # User may have started analysis while the download was running.
            if app._is_analysis_running():
                status.set(t("update_busy"))
                button.configure(state=tk.NORMAL)
            else:
                try:
                    # Save open review drafts before the installer closes the app.
                    for child in list(app.winfo_children()):
                        if hasattr(child, "_autosave_draft"):
                            child._autosave_draft()
                    launch_installer(result)
                    app.destroy()
                    return
                except Exception as exc:
                    status.set(t("update_error", error=str(exc)))
                    button.configure(state=tk.NORMAL)
        win.after(100, poll)

    background("check", check_update)
    win.after(100, poll)
