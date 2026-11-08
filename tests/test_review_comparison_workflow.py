"""Anchored comparison, explicit selection actions and lifecycle regressions."""
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk

from PIL import Image
import pytest

from photobook_curator.models import BookPlan, Photo, Region
from photobook_curator.review_gui import ReviewWindow


FOLDER = "01_Kyoto/hauptteil"


def photos_for(path):
    photos = []
    for i in range(6):
        image_path = path / f"photo-{i}.jpg"
        if not image_path.exists():
            Image.new("RGB", (420, 280), (30 * i, 100, 160)).save(image_path)
        photos.append(Photo(
            path=image_path, filename=image_path.name, region="Kyoto",
            chapter_folder=FOLDER if i < 3 else None,
            is_selected=i < 3, is_candidate=True,
            book_position=i + 1 if i < 3 else None,
            datetime_taken=datetime(2026, 5, 1) + timedelta(minutes=i),
            technical_score=95 - i, final_score=95 - i,
            burst_group_id=7 if i in (0, 3) else None,
            content_cluster_id=9 if i in (0, 4) else None,
            scene_type="portrait" if i == 5 else "landschaft",
            width=420, height=280,
        ))
    return photos


@pytest.fixture
def pair(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Native Tk display unavailable")
    root.withdraw()
    monkeypatch.setattr(ReviewWindow, "_open_large", lambda self: None)
    plan = BookPlan(regions=[Region("Kyoto", photo_indices=list(range(6)))])
    win = ReviewWindow(root, photos_for(tmp_path), plan, tmp_path)
    win.geometry("1180x820+10+10")
    root.update()
    yield win, root, plan
    for child in list(root.winfo_children()):
        if child.winfo_exists():
            if isinstance(child, ReviewWindow):
                child._close()
            else:
                child.destroy()
    root.destroy()


def compare(win):
    win._open_photo_preview(0, FOLDER)
    win._compare_btn.invoke()
    win.update()
    assert win._comparison_anchor() == 0


def test_pair_has_honest_evidence_stable_scoped_counts_and_no_grid_chrome(pair):
    win, _, _ = pair
    compare(win)
    assert "Serie" in win._current_title.cget("text")
    assert "Albumfoto 1 von 3" in win._slide_status.get()
    assert "Alternative 1 von 3" in win._slide_status.get()
    assert all(not widget.winfo_ismapped() for widget, _ in win._grid_chrome)
    assert win._preview_audit_report_button.winfo_ismapped()
    win._preview_next_btn.invoke()
    win._preview_next_btn.invoke()
    assert win._comparison_anchor() == 0
    assert "Weitere Aufnahmen" in win._current_title.cget("text")
    assert "Keine direkte Ähnlichkeit" in win._current_caption.get()
    assert "Alternative 3 von 3" in win._slide_status.get()
    win._album_back_btn.invoke()
    assert win._slide_indices[win._slide_pos] == 0
    assert win.kept == {0, 1, 2}


def test_add_is_idempotent_keeps_anchor_and_is_one_undo_step(pair):
    win, _, _ = pair
    compare(win)
    before = len(win._history.undo_stack)
    win._compare_add_btn.invoke()
    assert win.kept == {0, 1, 2, 3}
    assert win._comparison_anchor() == 0
    assert len(win._history.undo_stack) == before + 1
    win._compare_add_btn.invoke()
    assert win.kept == {0, 1, 2, 3}
    win._album_back_btn.invoke()
    assert win._slide_indices[win._slide_pos] == 0
    win._undo()
    assert win.kept == {0, 1, 2}
    assert not win.photos[3].review_added
    win._redo()
    assert win.kept == {0, 1, 2, 3}


def test_replace_and_undo_redo_preserve_album_slot_and_original_comparison(pair):
    win, _, _ = pair
    compare(win)
    before = len(win._history.undo_stack)
    win._compare_replace_btn.invoke()
    assert win.kept == {1, 2, 3}
    assert win._comparison_anchor() == 0
    assert win.photos[3].book_position == 1
    assert len(win._history.undo_stack) == before + 1
    win._undo()
    assert win.kept == {0, 1, 2}
    win._redo()
    assert win.kept == {1, 2, 3}
    win._album_back_btn.invoke()
    assert win._slide_indices[win._slide_pos] == 3
    assert win._slide_pos == 0
    win._undo()
    assert win._slide_indices[win._slide_pos] == 0
    win._redo()
    assert win._slide_indices[win._slide_pos] == 3


@pytest.mark.parametrize("protection", ["favorite", "keep"])
def test_protected_anchor_cannot_be_replaced(pair, protection):
    win, _, _ = pair
    if protection == "favorite":
        win.photos[0].is_favorite = True
    else:
        win.photos[0].manual_decision = "keep"
    compare(win)
    before = set(win.kept)
    win._slide_take_alternative()
    assert win.kept == before
    assert "geschützt" in win._preview_feedback_var.get()


def test_rejected_candidate_cannot_be_added_or_used_as_replacement(pair):
    win, _, _ = pair
    win.photos[3].manual_decision = "reject"
    compare(win)
    win._comparison_add_current()
    win._slide_take_alternative()
    assert win.kept == {0, 1, 2}
    assert win.photos[3].manual_decision == "reject"


def test_pause_reopen_restores_original_pair_candidate_and_replacement_slot(pair, tmp_path):
    win, root, plan = pair
    compare(win)
    win._compare_replace_btn.invoke()
    win._preview_next_btn.invoke()
    candidate = win._slide_indices[win._slide_pos]
    win._close()
    resumed = ReviewWindow(root, photos_for(tmp_path), plan, tmp_path)
    resumed.withdraw()
    root.update()
    assert resumed._preview_kind == "variants"
    assert resumed._comparison_anchor() == 0
    assert resumed._slide_indices[resumed._slide_pos] == candidate
    assert resumed.kept == {1, 2, 3}
    resumed._return_to_album_slideshow()
    assert resumed._slide_indices[resumed._slide_pos] == 3
    assert resumed._slide_pos == 0


@pytest.mark.parametrize("scale", [1.0, 1.5])
def test_minimum_window_keeps_selection_actions_visible_and_pair_tabs_work(pair, scale):
    win, _, _ = pair
    initial = float(win.tk.call("tk", "scaling"))
    try:
        win.tk.call("tk", "scaling", (96 / 72) * scale)
        win._setup_style()
        win.geometry("1000x740+10+10")
        compare(win)
        win.update()
        for widget in (win._compare_add_btn, win._compare_replace_btn, win._album_back_btn,
                       win._preview_why_btn, win._preview_undo_btn, win._preview_more):
            assert widget.winfo_ismapped()
            assert widget.winfo_rootx() >= win.winfo_rootx()
            assert widget.winfo_rootx() + widget.winfo_width() <= win.winfo_rootx() + win.winfo_width()
        assert win._comparison_switcher.winfo_ismapped()
        win._anchor_view_btn.invoke()
        win.update()
        assert win._anchor_panel.winfo_ismapped()
        assert not win._current_panel.winfo_ismapped()
        win._candidate_view_btn.invoke()
        win.update()
        assert win._current_panel.winfo_ismapped()
        assert win._comparison_anchor() == 0
    finally:
        win.tk.call("tk", "scaling", initial)


def test_search_in_actual_audit_dialog_does_not_edit_preview_selection(pair):
    from photobook_curator.review_audit_dialog import open_audit_report
    win, _, _ = pair
    compare(win)
    report = open_audit_report(win)
    report.deiconify()
    report.search_entry.focus_force()
    win.update()
    before = set(win.kept)
    assert win._text_input_active()
    win._slide_key_remove()
    win._decision_shortcut("reject", object())
    assert win.kept == before
    report.destroy()
