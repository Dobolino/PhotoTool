"""One packaged brand mark for native windows and the local photo workspace."""
from __future__ import annotations

from importlib.resources import files
from io import BytesIO
import sys


APP_ID = "Dobolino.PhotoTool"
BRAND_ASSETS = frozenset({"phototool.png", "phototool.ico"})


def brand_asset(name: str = "phototool.png"):
    """Resolve installed package data, independently of CWD or the launcher."""
    if name not in BRAND_ASSETS:
        raise ValueError("Unbekannte PhotoTool-Markendatei.")
    return files("photobook_curator").joinpath("assets", name)


def set_windows_app_id() -> bool:
    """Group the Tk and WebView processes under the same Windows app identity."""
    if sys.platform != "win32":
        return False
    import ctypes

    try:
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        return setter(APP_ID) == 0
    except (AttributeError, OSError):
        return False


def _logo_image(master, size: int):
    from PIL import Image, ImageTk

    if type(size) is not int or not 8 <= size <= 512:
        raise ValueError("Ungültige Logogrösse.")
    with Image.open(BytesIO(brand_asset().read_bytes())) as source:
        image = source.convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        try:
            return ImageTk.PhotoImage(image, master=master)
        finally:
            image.close()


def set_window_icon(window) -> None:
    """Keep every Tk image on its owning window, never in a module-wide cache."""
    set_windows_app_id()
    images = tuple(_logo_image(window, size) for size in (256, 64, 32, 16))
    window.iconphoto(True, *images)
    window._phototool_icon_images = images


def make_logo_label(parent, size: int = 48, background: str | None = None):
    """Return an unpacked Tk label with a correctly owned image reference."""
    import tkinter as tk

    image = _logo_image(parent, size)
    options = {"background": background} if background is not None else {}
    label = tk.Label(parent, image=image, borderwidth=0, highlightthickness=0,
                     padx=0, pady=0, **options)
    label._phototool_logo_image = image
    return label
