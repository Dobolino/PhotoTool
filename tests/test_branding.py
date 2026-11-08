"""Packaged icon quality and ownership boundaries used by real native windows."""
from io import BytesIO
import tkinter as tk

from PIL import Image
import pytest

from photobook_curator import branding


def test_packaged_mark_and_windows_icon_are_readable_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with Image.open(BytesIO(branding.brand_asset().read_bytes())) as logo:
        assert logo.format == "PNG" and logo.width == logo.height and logo.width >= 256
        assert logo.mode == "RGBA"
        assert logo.getchannel("A").getextrema() == (0, 255)
    with Image.open(BytesIO(branding.brand_asset("phototool.ico").read_bytes())) as icon:
        assert icon.format == "ICO"
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes()
        for size in ((16, 16), (32, 32), (256, 256)):
            frame = icon.ico.getimage(size)
            assert frame.size == size and frame.getbbox() is not None


def test_only_named_brand_assets_are_exposed():
    with pytest.raises(ValueError):
        branding.brand_asset("../../other.ico")


def test_each_tk_window_owns_its_brand_images_without_cross_interpreter_cache():
    try:
        first = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    second = None
    first.withdraw()
    try:
        second = tk.Tk()
        second.withdraw()
        for root in (first, second):
            branding.set_window_icon(root)
            label = branding.make_logo_label(root, size=52, background="#10191f")
            label.pack()
            root.update_idletasks()
            assert label._phototool_logo_image.tk is root.tk
            assert label._phototool_logo_image.width() == 52
            assert all(image.tk is root.tk for image in root._phototool_icon_images)
        assert first._phototool_icon_images[0] is not second._phototool_icon_images[0]
    finally:
        if second is not None:
            second.destroy()
        first.destroy()
