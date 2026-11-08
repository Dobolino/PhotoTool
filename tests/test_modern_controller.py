"""The real Tk owner must preserve one session and service native dialogs safely."""
import runpy
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    import tkinter as tk
    from photobook_curator import modern_review
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Desktop display unavailable")
    root.withdraw()
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
    yield root, photos, plan, output, processes
    root.destroy()


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
