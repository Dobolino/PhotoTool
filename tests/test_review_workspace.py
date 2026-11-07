"""Review workspace actions persist intent and expose explainable worklists."""
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk

from PIL import Image
import pytest

from photobook_curator.models import Photo, BookPlan, Region
from photobook_curator.review_gui import ReviewWindow
from photobook_curator.selection_draft import load_selection_draft
from photobook_curator.review_insights import build_motif_groups
from photobook_curator.review_workspace import open_review_assistant


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable')
    root.withdraw()
    monkeypatch.setattr(ReviewWindow, '_open_large', lambda self: None)
    photos = []
    for n in range(6):
        path = tmp_path / f'photo-{n}.jpg'
        Image.new('RGB', (320, 210), (40+n*20, 90, 140)).save(path)
        photos.append(Photo(path=path, filename=path.name, region='Coast',
            chapter_folder='01_Coast/hauptteil' if n < 3 else None,
            datetime_taken=datetime(2026, 7, 1) + timedelta(minutes=n),
            is_selected=n < 3, is_candidate=True, final_score=90-n,
            technical_score=90-n, burst_group_id=1 if n < 4 else None,
            bad_face=n == 0, scene_type='landschaft', width=320, height=210))
    win = ReviewWindow(root, photos, BookPlan(regions=[Region('Coast', photo_indices=list(range(6)))]), tmp_path)
    win.withdraw()
    root.update()
    yield win
    win._close()
    root.destroy()


def test_durable_decisions_persist_and_undo_as_one_action(workspace):
    win = workspace
    win._set_decision(0, 'reject', 'Unscharf und ohne Erinnerungswert')
    assert 0 not in win.kept and win.photos[0].manual_decision == 'reject'
    draft = load_selection_draft(win.output_dir)
    assert draft and 'reject' in str(draft)
    win._toggle_photo(0, 'keep', win._grid_folder)
    assert 0 not in win.kept  # permanent reject blocks accidental addition
    win._undo()
    assert 0 in win.kept and win.photos[0].manual_decision == 'auto'
    win._set_decision(0, 'keep')
    win._toggle_photo(0, 'keep', win._grid_folder)
    assert 0 in win.kept
    win._set_decision(0, 'auto')
    win._toggle_photo(0, 'keep', win._grid_folder)
    assert 0 not in win.kept


def test_filters_and_search_do_not_change_selection(workspace):
    win = workspace
    before = set(win.kept)
    win._set_workspace_filter('candidates')
    indices = {h['idx'] for h in win._hit_tiles if h['kind'] == 'photo'}
    assert indices == {3, 4, 5}
    win._search_var.set('photo-5')
    win._apply_search()
    assert {h['idx'] for h in win._hit_tiles if h['kind'] == 'photo'} == {5}
    assert win.kept == before
    win._set_workspace_filter('kept')
    win._search_var.set('')
    win._apply_search()
    assert {h['idx'] for h in win._hit_tiles if h['kind'] == 'photo'} == before


def test_motif_recommendation_preserves_protected_images_and_is_undoable(workspace):
    win = workspace
    group = build_motif_groups(win.photos)[0]
    win._toggle_favorite(0)
    before = set(win.kept)
    win._apply_motif_recommendation(group)
    assert 0 in win.kept
    assert set(group.recommended_indices).issubset(win.kept)
    for i in group.indices:
        if i not in group.recommended_indices and i != 0:
            assert win.photos[i].manual_decision == 'reject'
    win._undo()
    assert win.kept == before


def test_assistant_constructs_queue_motifs_and_story_tabs(workspace):
    win = open_review_assistant(workspace)
    notebook = next(child for child in win.winfo_children() if isinstance(child, __import__('tkinter.ttk', fromlist=['Notebook']).Notebook))
    assert len(notebook.tabs()) == 3
    win.update_idletasks()
    win.destroy()


def test_typing_in_search_does_not_remove_current_preview_photo(workspace):
    win = workspace
    win._enter_slideshow()
    win._slide_pos = win._slide_indices.index(0)
    win.deiconify()
    win.geometry('1120x760+80+80')
    win.lift()
    win.update()
    win._search_entry.focus_force()
    win.update()
    before = set(win.kept)
    assert win._text_input_active()
    win._slide_key_remove()
    win._decision_shortcut('reject', object())
    assert win.kept == before


def test_search_and_filter_restore_when_review_resumes(workspace):
    win = workspace
    win._set_workspace_filter('candidates')
    win._search_var.set('photo-5')
    win._apply_search()
    win._autosave_draft()
    state = load_selection_draft(win.output_dir)['review_state']
    assert state['filter'] == 'candidates'
    assert state['search'] == 'photo-5'
    assert state['page'] == 0


def test_assistant_actions_remain_visible_at_minimum_size(workspace):
    from tkinter import ttk
    workspace.deiconify()
    workspace.update()
    win = open_review_assistant(workspace)
    win.geometry('760x500+100+100')
    win.update()
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    notebook = next(w for w in win.winfo_children() if isinstance(w, ttk.Notebook))
    for tab in notebook.tabs():
        notebook.select(tab)
        win.update()
        for button in descendants(win.nametowidget(tab)):
            if isinstance(button, ttk.Button):
                assert button.winfo_height() >= 28
                assert button.winfo_rooty() + button.winfo_height() <= win.winfo_rooty() + win.winfo_height()
    win.destroy()
