"""Exercise real Tk widgets and review actions without external services."""

from pathlib import Path
import tkinter as tk

from PIL import Image
import pytest

from photobook_curator.models import Photo, BookPlan, Region
from photobook_curator.review_gui import ReviewWindow
from photobook_curator.selection_draft import save_selection_draft


@pytest.fixture
def window(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    monkeypatch.setattr(ReviewWindow, "_open_large", lambda self: None)
    photos = []
    for n in range(2):
        path = tmp_path / f"{n}.jpg"
        Image.new("RGB", (120, 80), (n * 50, 80, 90)).save(path)
        photos.append(Photo(path=path, filename=path.name, region="Tokyo",
                            chapter_folder="01_Tokyo/hauptteil", is_selected=True,
                            is_candidate=True, width=120, height=80))
    win = ReviewWindow(root, photos, BookPlan(regions=[Region(name="Tokyo", photo_indices=[0, 1])]), tmp_path)
    win.withdraw()
    root.update()
    yield win
    win._close()
    root.destroy()


def test_favorite_blocks_grid_and_slideshow_removal_and_swaps(window):
    win = window
    win._toggle_favorite(0)
    assert win.photos[0].is_favorite
    win._toggle_photo(0, "keep", "01_Tokyo/hauptteil")
    win._grid_swap_alternative(0, "01_Tokyo/hauptteil")
    assert 0 in win.kept
    win._enter_slideshow()
    win._slide_pos = win._slide_indices.index(0)
    win._slide_toggle_current()
    win._slide_key_remove()
    win._alt_idx = 1
    win._slide_take_alternative()
    assert 0 in win.kept
    win._undo()
    assert not win.photos[0].is_favorite
    win._redo()
    assert win.photos[0].is_favorite


def test_move_then_undo_restores_folder_and_selection(window):
    win = window
    win._move_photo_to_folder(0, "02_Lyon/hauptteil")
    assert win.photos[0].chapter_folder == "02_Lyon/hauptteil"
    win._undo()
    assert win.photos[0].chapter_folder == "01_Tokyo/hauptteil"
    win._redo()
    assert win.photos[0].chapter_folder == "02_Lyon/hauptteil"


def test_print_dialog_constructs_and_reports_without_network(window):
    window._print_check()
    dialog = [w for w in window.winfo_children() if isinstance(w, tk.Toplevel)][0]
    dialog.update_idletasks()
    dialog.destroy()
