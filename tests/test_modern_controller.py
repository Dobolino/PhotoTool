"""The real Tk owner must preserve one session and service native dialogs safely."""
import runpy
import gc
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    import tkinter as tk
    from photobook_curator import modern_review
    from photobook_curator.review_gui import ReviewWindow
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Desktop display unavailable")
    root.withdraw()
    legacy_windows = []
    initialize_review = ReviewWindow.__init__
    def tracked_review(self, *args, **kwargs):
        initialize_review(self, *args, **kwargs)
        legacy_windows.append(self)
    monkeypatch.setattr(ReviewWindow, "__init__", tracked_review)
    processes = []
    class Process:
        pid = 1
        result = None
        def poll(self):
            return self.result
        def terminate(self):
            self.result = 0
        def wait(self, timeout=None):
            return self.result
    def launch(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process
    monkeypatch.setattr(modern_review.subprocess, "Popen", launch)
    monkeypatch.setattr(modern_review.shutil, "which", lambda name: "/unused/browser")
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *args, **kw: pytest.fail(str(args)))
    helper = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging/native_review_smoke.py"))
    photos, plan, output = helper["create_fixture"](tmp_path)
    try:
        yield root, photos, plan, output, processes
    finally:
        # Shut down the real owners before releasing their Tcl objects. Cycles
        # left for a later HTTP worker's automatic GC can finalize Tcl on the
        # wrong thread (especially on Windows).
        for child in list(root.winfo_children()):
            close = getattr(child, "_close", None)
            if close is not None:
                close()
            else:
                child.destroy()
        child = None
        for legacy in legacy_windows:
            if legacy.winfo_exists():
                legacy._close()
            for worker in legacy._loaders:
                worker.join(timeout=2)
                assert not worker.is_alive()
        legacy = None
        legacy_windows.clear()
        root.destroy()
        gc.collect()


def test_owner_reuses_project_and_saves_before_terminating_native_child(desktop):
    from photobook_curator.modern_review import open_modern_review
    from photobook_curator.modern_review_session import ReviewSession
    root, photos, plan, output, processes = desktop
    window = open_modern_review(root, photos, plan, output)
    assert open_modern_review(root, photos, plan, output) is window
    assert len(processes) == 1
    window.session.action({"action": "select", "id": 1, "selected": True})
    window.session.action({"action": "view", "view": {"layout": "B", "theme": "light"}})
    window.session._busy = True
    window._autosave_draft()
    assert window._draft_save_error and processes[0].poll() is None
    window.session._busy = False
    assert window._close()
    assert processes[0].poll() == 0 and window.server._closed
    assert window.session.on_native is None
    restored = ReviewSession(photos, plan, output)
    assert 1 in restored.kept
    assert restored.view["layout"] == "B" and restored.view["theme"] == "light"


def test_source_dialog_is_serviced_while_http_worker_waits_without_tk_deadlock(desktop, monkeypatch):
    from photobook_curator.modern_review import open_modern_review
    root, photos, plan, output, _ = desktop
    window = open_modern_review(root, photos, plan, output)
    original_root = photos[0].path.parent
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(original_root))
    result, errors = [], []
    def choose():
        try:
            result.append(window.session.action({"action": "source_choose"}))
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=choose, daemon=True)
    worker.start()
    deadline = time.monotonic() + 3
    while worker.is_alive() and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    worker.join(.1)
    assert not worker.is_alive() and not errors
    assert result and not result[0].get("cancelled")
    assert window._close()


@pytest.mark.parametrize("tool", ["all", "print"])
def test_advanced_tools_return_to_current_repaired_project_and_preserve_view(desktop, monkeypatch, tool):
    """Exercise real Tk tools and their real close method, not a facade stub."""
    from tkinter import ttk
    from photobook_curator.modern_review import open_modern_review
    from photobook_curator.review_gui import ReviewWindow
    from photobook_curator.selection_draft import load_selection_draft
    from photobook_curator.i18n import t

    root, photos, original_plan, output, processes = desktop
    errors = []
    root.report_callback_exception = lambda kind, error, tb: errors.append(error)
    monkeypatch.setattr(ReviewWindow, "_open_large", lambda self: None)
    photos[0].gps_lat, photos[0].gps_lon = 34.6851, 135.8048  # Nara, not the old Kyoto label
    photos[4].gps_lat, photos[4].gps_lon = 35.6762, 139.6503
    window = open_modern_review(root, photos, original_plan, output)

    def pump_until(predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert predicate(), "The native tool transition did not complete"
        assert not errors

    preview = window.session.action({"action": "location_preview", "online": False})
    job_id = preview["job"]["id"]
    pump_until(lambda: not window.session.busy)
    job = window.session.action({"action": "job", "job_id": job_id})["job"]
    assert job["status"] == "done"
    window.session.action({"action": "location_apply", "preview_id": job["result"]["preview_id"]})
    repaired_plan = window.session.plan
    assert repaired_plan is not original_plan and photos[0].region == "Nara"
    window.session.action({"action": "decision", "id": 1, "decision": "keep", "reason": "Erinnerung"})
    window.session.action({"action": "favorite", "id": 0, "value": True})
    chapter = window.session.snapshot()["photos"][0]["chapter"]
    window.session.action({"action": "view", "view": {
        "layout": "C", "theme": "light", "filter": "all", "chapter": chapter,
        "focus": 1, "anchor": 0, "export_layout": "flat"}})
    expected_view = {key: window.session.view[key] for key in
                     ("layout", "theme", "filter", "chapter", "focus", "anchor", "export_layout")}
    expected_kept = set(window.session.kept)

    window._open_advanced(tool)
    classic = next(child for child in root.winfo_children() if isinstance(child, ReviewWindow))
    assert classic.plan is repaired_plan
    assert classic.photos[0].region == "Nara"
    assert classic.kept == expected_kept
    assert classic.photos[0].is_favorite and classic.photos[1].decision_reason == "Erinnerung"
    assert processes[0].poll() == 0 and window.server._closed
    assert open_modern_review(root, photos, repaired_plan, output) is classic
    assert len(processes) == 1  # Reopening from the main window reuses the tool owner.
    if tool == "print":
        pump_until(lambda: any(getattr(child, "title", lambda: "")() == t("print_check")
                               for child in classic.winfo_children()))

    # A decision made in the real tool window must reach the reopened workspace.
    classic._set_decision(2, "keep", "Aus weiteren Werkzeugen")
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    back = next(child for child in descendants(classic)
                if isinstance(child, ttk.Button) and child.cget("text") == "Zur neuen Vorschau")
    back.invoke()
    pump_until(lambda: any(getattr(child, "_modern_output_dir", None) == output.resolve()
                           for child in root.winfo_children()))
    modern = next(child for child in root.winfo_children()
                  if getattr(child, "_modern_output_dir", None) == output.resolve())
    assert not classic.winfo_exists()  # real _close() returns None after destroying the tool window
    assert modern.session.plan is repaired_plan
    assert modern.kept == expected_kept | {2}
    assert modern.photos[2].manual_decision == "keep"
    assert modern.photos[2].decision_reason == "Aus weiteren Werkzeugen"
    assert modern.photos[0].region == "Nara" and modern.photos[0].is_favorite
    assert {key: modern.session.view[key] for key in expected_view} == expected_view
    assert len(processes) == 2
    draft = load_selection_draft(output)
    assert draft["review_state"]["modern_review"]["layout"] == "C"
    assert modern._close()


def test_failed_real_tool_close_does_not_create_a_second_project_owner(desktop, monkeypatch):
    from tkinter import ttk
    from photobook_curator.modern_review import open_modern_review
    from photobook_curator.review_gui import ReviewWindow
    root, photos, plan, output, processes = desktop
    monkeypatch.setattr(ReviewWindow, "_open_large", lambda self: None)
    errors = []
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *args, **kwargs: errors.append(args))
    window = open_modern_review(root, photos, plan, output)
    window._open_advanced("all")
    classic = next(child for child in root.winfo_children() if isinstance(child, ReviewWindow))
    save, saves = classic._autosave_draft, []
    def fail_on_close():
        saves.append(True)
        if len(saves) == 2:
            classic._draft_save_error = "Speicherort vorübergehend nicht verfügbar"
        else:
            save()
    monkeypatch.setattr(classic, "_autosave_draft", fail_on_close)
    back = next(button for frame in classic.winfo_children() for button in frame.winfo_children()
                if isinstance(button, ttk.Button) and button.cget("text") == "Zur neuen Vorschau")
    back.invoke()
    assert errors and classic.winfo_exists()
    assert len(processes) == 1, "An unsuccessful close must not launch another writer for the same project"
