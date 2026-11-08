"""Native location repair is preview-first, asynchronous and durable before apply."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk

import pytest

from photobook_curator.models import Photo
from photobook_curator.review_export import plan_from_photos, load_photos_from_csv
from photobook_curator.review_history import ReviewHistory
from photobook_curator.review_location_dialog import open_location_repair
from photobook_curator.selection_draft import load_selection_draft


class Owner(tk.Toplevel):
    def __init__(self, root, output_dir):
        super().__init__(root)
        self.output_dir = output_dir
        at = datetime(2026, 4, 10, 10)
        self.photos = [
            Photo(path=output_dir/'tokyo.jpg', filename='tokyo.jpg', gps_lat=35.6762, gps_lon=139.6503,
                  datetime_taken=at, region='Old city', chapter_folder='01_Old/hauptteil',
                  chapter_type='Hauptteil', is_selected=True, is_favorite=True, manual_decision='keep',
                  decision_reason='Erstes Bild der Reise', book_position=1, flags=['my_custom_flag']),
            Photo(path=output_dir/'nearby.jpg', filename='nearby.jpg', datetime_taken=at+timedelta(hours=1),
                  region='Old city', chapter_folder='01_Old/hauptteil', chapter_type='Hauptteil',
                  is_selected=True, book_position=2, flags=['my_custom_flag']),
            Photo(path=output_dir/'far.jpg', filename='far.jpg', datetime_taken=at+timedelta(days=9),
                  region='Old city', manual_decision='reject', decision_reason='Nicht fürs Album'),
        ]
        self.kept = {0, 1}
        self.plan = plan_from_photos(self.photos)
        self._history = ReviewHistory(self.photos)
        self._known_folders = ['01_Old/hauptteil']
        self.refreshes = self.saves = 0
        self.feedback = ''

    def _review_view_state(self):
        return {'filter': 'kept', 'photo': str(self.photos[1].path)}

    def _refresh_review_edit(self):
        self.refreshes += 1

    def _autosave_draft(self):
        self.saves += 1

    def _flash_status(self, text):
        self.feedback = text


@pytest.fixture
def owner(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable')
    root.withdraw()
    monkeypatch.setattr('PIL.Image.open', lambda *_a, **_kw: pytest.fail('Location repair opened photo pixels'))
    monkeypatch.setattr('photobook_curator.geocoding.Nominatim', lambda **_kw: pytest.fail('Offline mode opened an online geocoder'))
    owner = Owner(root, tmp_path)
    owner.geometry('1100x760+40+40')
    root.update()
    yield owner
    root.destroy()


def pump_until(win, predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        win.update()
        time.sleep(.005)
    assert predicate()


def selection_signature(photos):
    return [(p.path, p.is_selected, p.is_favorite, p.manual_decision, p.decision_reason,
             p.book_position, p.final_score, deepcopy(p.selection_trace)) for p in photos]


def test_offline_preview_is_modal_async_and_does_not_mutate_originals(owner, monkeypatch):
    import photobook_curator.review_location_dialog as module
    original = deepcopy(owner.photos)
    actual_preview = module.preview_location_repair
    calls = []

    def wrapped(photos, cache, max_hours):
        calls.append((threading.get_ident(), cache.enabled, max_hours))
        return actual_preview(photos, cache, max_hours=max_hours)

    monkeypatch.setattr(module, 'preview_location_repair', wrapped)
    dialog = open_location_repair(owner)
    assert owner.grab_current() == dialog
    assert not dialog.online_var.get()
    dialog._start_preview()
    assert dialog._busy
    assert str(dialog.apply_btn['state']) == 'disabled'
    pump_until(dialog, lambda: not dialog._busy)
    assert dialog.preview is not None
    assert calls[0] == (calls[0][0], False, 6.0)
    assert calls[0][0] != threading.get_ident()
    assert owner.photos == original
    assert dialog.preview.photos[0].region == 'Tokyo'
    assert dialog.preview.photos[1].region == 'Tokyo'
    assert dialog.preview.photos[2].region == 'Unbestimmt'
    assert dialog.preview.unresolved_count == 1
    dialog.filter_var.set('Nur Ungeklärte')
    dialog._filter_rows()
    assert dialog.table.get_children() == ('2',)
    assert 'Kein GPS-Anker' in dialog.detail_var.get()
    dialog.destroy()
    assert owner.grab_current() is None


def test_apply_persists_before_mutating_and_keeps_photo_decisions(owner, monkeypatch):
    import photobook_curator.review_location_dialog as module
    before = selection_signature(owner.photos)
    history = owner._history
    actual_persist = module.persist_location_repair
    calls = []

    def persist(*args, **kwargs):
        assert owner.photos[0].region == 'Old city'
        actual_persist(*args, **kwargs)
        calls.append('saved')

    actual_apply = module.apply_location_repair

    def apply(photos, preview):
        assert calls == ['saved']
        actual_apply(photos, preview)
        calls.append('applied')

    monkeypatch.setattr(module, 'persist_location_repair', persist)
    monkeypatch.setattr(module, 'apply_location_repair', apply)
    dialog = open_location_repair(owner)
    dialog._start_preview()
    pump_until(dialog, lambda: not dialog._busy)
    dialog._apply()
    assert calls == ['saved', 'applied']
    assert owner.photos[0].region == 'Tokyo'
    assert selection_signature(owner.photos) == before
    assert all('my_custom_flag' in photo.flags for photo in owner.photos[:2])
    assert owner.kept == {0, 1}
    assert owner._history is not history and not owner._history.undo_stack
    assert owner.refreshes == owner.saves == 1
    saved = load_photos_from_csv(owner.output_dir/'photos_analysis.csv')
    assert saved[0].region == 'Tokyo'
    assert selection_signature(saved) == before
    assert load_selection_draft(owner.output_dir)['review_state']['filter'] == 'kept'


def test_failed_persistence_keeps_live_photos_and_history_unchanged(owner, monkeypatch):
    original = deepcopy(owner.photos)
    history = owner._history
    errors = []
    monkeypatch.setattr('photobook_curator.review_location_dialog.persist_location_repair',
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError('disk full')))
    monkeypatch.setattr('photobook_curator.review_location_dialog.messagebox.showerror', lambda *args, **_kw: errors.append(args))
    dialog = open_location_repair(owner)
    dialog._start_preview()
    pump_until(dialog, lambda: not dialog._busy)
    dialog._apply()
    assert owner.photos == original and owner._history is history
    assert not owner.refreshes and not owner.saves
    assert dialog.winfo_exists() and errors
    dialog.destroy()


def test_changed_options_invalidate_preview_and_require_another_check(owner):
    dialog = open_location_repair(owner)
    dialog._start_preview()
    pump_until(dialog, lambda: not dialog._busy)
    assert str(dialog.apply_btn['state']) == 'normal'
    dialog.hours_var.set('3')
    assert dialog.preview is None
    assert str(dialog.apply_btn['state']) == 'disabled'
    dialog._apply()
    assert owner.photos[0].region == 'Old city'
    dialog.destroy()


def test_online_lookup_requires_opt_in_and_runs_in_worker(owner, monkeypatch):
    import photobook_curator.review_location_dialog as module
    modes = []

    class FakeCache:
        def __init__(self, path, *, enabled, stop):
            modes.append((enabled, threading.get_ident()))
            self.enabled = enabled

        def reverse(self, *_args):
            return {'city': 'Tokyo', 'country': 'Japan', 'region_admin': 'Tokyo', 'raw_display': 'Tokyo, Japan'}

        def save(self):
            pass

    monkeypatch.setattr(module, '_CancellableCache', FakeCache)
    dialog = open_location_repair(owner)
    dialog.online_var.set(True)
    dialog._start_preview()
    pump_until(dialog, lambda: not dialog._busy)
    assert modes[0][0] is True and modes[0][1] != threading.get_ident()
    assert dialog.preview.photos[0].location_evidence['source'] == 'gps_online'
    dialog.destroy()


def test_close_cancels_worker_without_late_ui_or_photo_changes(owner, monkeypatch):
    import photobook_curator.review_location_dialog as module
    completed = threading.Event()
    original = deepcopy(owner.photos)

    def blocked(_photos, cache, **_kwargs):
        cache._stop.wait(2)
        completed.set()
        raise module._CancelledPreview()

    monkeypatch.setattr(module, 'preview_location_repair', blocked)
    dialog = open_location_repair(owner)
    dialog._start_preview()
    dialog.destroy()
    assert completed.wait(1)
    owner.update()
    assert owner.photos == original
    assert owner.grab_current() is None


@pytest.mark.parametrize("scaling", [None, 2.0, 2.5])
def test_actions_remain_visible_at_minimum_size(owner, monkeypatch, request, scaling):
    if scaling is not None:
        import tkinter.font as tkfont
        previous_scaling = owner.tk.call("tk", "scaling")
        request.addfinalizer(lambda: owner.tk.call("tk", "scaling", previous_scaling))
        owner.tk.call("tk", "scaling", scaling)
        available = {name.casefold(): name for name in tkfont.families(owner)}
        for candidate in ("Segoe UI", "DejaVu Sans", "Nimbus Sans L", "Helvetica"):
            if candidate.casefold() in available:
                monkeypatch.setattr("photobook_curator.review_gui.FONT_UI", available[candidate.casefold()])
                break
    dialog = open_location_repair(owner)
    dialog.geometry('800x600+80+80')
    dialog._start_preview()
    pump_until(dialog, lambda: not dialog._busy)
    dialog.update()

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    for widget in descendants(dialog):
        if isinstance(widget, ttk.Button):
            assert widget.winfo_height() >= 26
            assert widget.winfo_rooty()+widget.winfo_height() <= dialog.winfo_rooty()+dialog.winfo_height()
            assert widget.winfo_rootx()+widget.winfo_width() <= dialog.winfo_rootx()+dialog.winfo_width()
    assert dialog.table.winfo_height() >= 100
    assert dialog._detail_text.winfo_height() >= 65
    assert dialog.notebook.select() == str(dialog.results_page)
    dialog.notebook.select(0)
    dialog.update()
    assert dialog.online_check.winfo_viewable()
    assert dialog.hours_combo.winfo_viewable()
    assert dialog.apply_btn.winfo_rooty()+dialog.apply_btn.winfo_height() <= dialog.winfo_rooty()+dialog.winfo_height()
    dialog.destroy()


def test_matching_labels_can_save_missing_location_evidence(owner):
    owner.photos[0].region = owner.photos[0].place_label = 'Tokyo'
    owner.photos[0].country = 'Japan'
    owner.photos[0].chapter_folder = '01_Tokyo/hauptteil'
    assert not owner.photos[0].location_evidence
    dialog = open_location_repair(owner)
    dialog._start_preview()
    pump_until(dialog, lambda: not dialog._busy)
    assert any(change.index == 0 for change in dialog.preview.changes)
    assert str(dialog.apply_btn['state']) == 'normal'
    dialog._apply()
    assert owner.photos[0].location_evidence['source'] == 'gps_offline'
