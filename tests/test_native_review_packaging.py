"""Internal native-window dispatch and real fixture lifecycle checks."""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_window_child_dispatch_does_not_start_the_tk_application(monkeypatch):
    entry = runpy.run_path(str(ROOT / "packaging" / "entry_gui.py"))
    calls = []
    monkeypatch.setitem(sys.modules, "photobook_curator.modern_review", SimpleNamespace(
        run_native_window=lambda url, **kw: calls.append((url, kw))))
    monkeypatch.setattr(sys, "argv", ["Fotobuch.exe", "--review-window",
        "http://127.0.0.1:8123/session/", "--window-title", "Meine Reise"])
    assert entry["main"]() == 0
    assert calls == [("http://127.0.0.1:8123/session/", {"title": "Meine Reise"})]


def test_native_smoke_arguments_support_paths_with_spaces(monkeypatch, tmp_path):
    entry = runpy.run_path(str(ROOT / "packaging" / "entry_gui.py"))
    calls = []
    monkeypatch.setitem(sys.modules, "native_review_smoke", SimpleNamespace(
        run=lambda result, **kw: calls.append((result, kw)) or 0))
    result = tmp_path / "result with spaces.json"
    captures = tmp_path / "screen shots"
    monkeypatch.setattr(sys, "argv", ["Fotobuch.exe", "--review-smoke", str(result),
                                     "--review-capture-dir", str(captures)])
    assert entry["main"]() == 0
    assert calls == [(result, {"capture_dir": captures})]


def test_native_probe_failure_returns_diagnostics_without_a_modal(monkeypatch, tmp_path):
    entry = runpy.run_path(str(ROOT / "packaging" / "entry_gui.py"))
    def fail(*args, **kwargs):
        raise RuntimeError("native render did not become ready")
    monkeypatch.setitem(sys.modules, "native_review_smoke", SimpleNamespace(run=fail))
    monkeypatch.setitem(sys.modules, "tkinter", None)
    result = tmp_path / "native failed.json"
    monkeypatch.setattr(sys, "argv", ["Fotobuch.exe", "--review-smoke", str(result)])
    assert entry["main"]() == 1
    payload = json.loads(result.read_text())
    assert payload["success"] is False
    assert "native render did not become ready" in payload["error"]


def test_native_fixture_is_real_local_images_with_explicit_synthetic_evidence(tmp_path):
    helper = runpy.run_path(str(ROOT / "packaging" / "native_review_smoke.py"))
    photos, plan, output = helper["create_fixture"](tmp_path)
    assert len(photos) == 8 and sum(p.is_selected for p in photos) == 3
    assert {p.region for p in photos} == {"Kyoto", "Tokyo"}
    assert all(p.path.is_file() and p.width == 1200 and p.height == 800 for p in photos)
    assert all(p.selection_trace["context"]["synthetic_native_window_test"] for p in photos)
    assert all(p.selection_trace["status"] != "pending" for p in photos)
    assert (output / "photos_analysis.csv").is_file()
    assert len(plan.regions) == 2


@pytest.mark.parametrize("render_ok", [True, False])
def test_native_smoke_closes_the_session_server_on_success_and_render_failure(monkeypatch, tmp_path, render_ok):
    helper = runpy.run_path(str(ROOT / "packaging" / "native_review_smoke.py"))
    events = []
    class Session:
        def __init__(self, *args):
            events.append("session")
        def action(self, payload):
            events.append(payload["action"])
    class Server:
        def __init__(self, session):
            pass
        def start(self):
            events.append("start")
            return "http://127.0.0.1:8123/session/"
        def close(self):
            events.append("close")
    def native(url, **kwargs):
        events.append("native")
        kwargs["smoke_result"].write_text(json.dumps({"success": render_ok}))
    monkeypatch.setitem(sys.modules, "photobook_curator.modern_review", SimpleNamespace(
        ReviewServer=Server, run_native_window=native))
    monkeypatch.setitem(sys.modules, "photobook_curator.modern_review_session", SimpleNamespace(ReviewSession=Session))
    result = tmp_path / "native.json"
    if render_ok:
        assert helper["run"](result) == 0
    else:
        with pytest.raises(RuntimeError, match="successful render"):
            helper["run"](result)
    assert events == ["session", "start", "native", "save", "close"]


def test_native_probe_uses_raw_scripts_and_real_transport_without_eval(monkeypatch, tmp_path):
    import re
    import threading
    from PIL import Image, ImageGrab
    from photobook_curator import modern_review
    from photobook_curator.modern_review_session import ReviewSession

    helper = runpy.run_path(str(ROOT / "packaging" / "native_review_smoke.py"))
    session = ReviewSession(*helper["create_fixture"](tmp_path))
    server = modern_review.ReviewServer(session)
    layouts = []
    closed = threading.Event()
    class ClosingEvent:
        def __iadd__(self, handler):
            self.handler = handler
            return self
    class Window:
        # Deliberately no evaluate_js: CSP must stay strict even in the native probe.
        events = SimpleNamespace(closing=ClosingEvent())
        def run_js(self, script):
            if "window.PhotoToolReview?.close()" in script:
                session.action({"action": "close"})
                return
            assert "root.dataset.appReady==='true'" in script
            assert "image.complete && image.naturalWidth>0" in script
            layout = re.search(r'const target="([ABC])"', script)[1]
            layouts.append(layout)
            session.action({"action": "view", "view": {"layout": layout}})
        def destroy(self):
            if self.events.closing.handler():
                layouts.append("destroy")
                closed.set()
    def start(callback, **kwargs):
        callback()
        assert closed.wait(3), "native probe did not complete its real close handshake"
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(
        create_window=lambda *args, **kwargs: Window(), start=start))
    monkeypatch.setattr(modern_review, "time", SimpleNamespace(monotonic=__import__("time").monotonic,
                                                             sleep=lambda seconds: None))
    monkeypatch.setattr(ImageGrab, "grab", lambda: Image.new("RGB", (40, 30)))
    result = tmp_path / "result.json"
    captures = tmp_path / "captures"
    try:
        assert modern_review.run_native_window(server.start(), smoke_result=result,
                                               capture_dir=captures) == 0
        payload = json.loads(result.read_text())
        assert payload["success"] and payload["frontend"]["image_ready"]
        assert payload["native_close_verified"]
        assert payload["frontend"]["photo_count"] == 8
        assert payload["frontend"]["theme"] == "dark"
        assert layouts == ["B", "A", "B", "C", "destroy"]
        assert all((captures / name).is_file() for name in payload["captures"])
    finally:
        server.close()


@pytest.mark.parametrize("busy", [False, True])
def test_native_x_close_flushes_choices_and_does_not_interrupt_busy_jobs(monkeypatch, tmp_path, busy):
    import threading
    from photobook_curator import modern_review
    from photobook_curator.modern_review_session import ReviewSession

    helper = runpy.run_path(str(ROOT / "packaging" / "native_review_smoke.py"))
    session = ReviewSession(*helper["create_fixture"](tmp_path))
    session._busy = busy
    server = modern_review.ReviewServer(session)
    completed = threading.Event()
    calls = []
    class ClosingEvent:
        def __iadd__(self, handler):
            self.handler = handler
            return self
    class Window:
        events = SimpleNamespace(closing=ClosingEvent())
        def run_js(self, script):
            if "window.PhotoToolReview?.close()" in script:
                calls.append("frontend-close")
                # Model a choice and navigation still queued in the real frontend.
                session.action({"action": "select", "id": 1, "selected": True})
                session.action({"action": "view", "view": {"layout": "B"}})
                session.action({"action": "close"})
            else:
                assert "notice" in script
                calls.append("notice")
                completed.set()
        def destroy(self):
            assert self.events.closing.handler() is True
            calls.append("destroy")
            completed.set()
    window = Window()
    def start(callback, **kwargs):
        assert callback is None
        assert window.events.closing.handler() is False
        assert completed.wait(3), "native close worker did not finish"
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(
        create_window=lambda *args, **kwargs: window, start=start))
    try:
        assert modern_review.run_native_window(server.start()) == 0
        if busy:
            assert calls == ["notice"] and not session.close_requested
        else:
            assert calls == ["frontend-close", "destroy"]
            assert session.close_requested and 1 in session.kept
            assert session.view["layout"] == "B"
    finally:
        server.close()


@pytest.mark.parametrize("page", ["ready-save-failed", "uninitialized", "dispatch-failed"])
def test_native_close_timeout_never_bypasses_a_ready_frontend_queue(monkeypatch, tmp_path, page):
    import itertools
    import threading
    from photobook_curator import modern_review
    from photobook_curator.modern_review_session import ReviewSession

    helper = runpy.run_path(str(ROOT / "packaging" / "native_review_smoke.py"))
    session = ReviewSession(*helper["create_fixture"](tmp_path))
    server = modern_review.ReviewServer(session)
    completed = threading.Event()
    calls = []
    class ClosingEvent:
        def __iadd__(self, handler):
            self.handler = handler
            return self
    class Window:
        events = SimpleNamespace(closing=ClosingEvent())
        def run_js(self, script):
            if "window.PhotoToolReview?.close()" in script:
                calls.append("dispatch")
                assert "if(document.documentElement.dataset.appReady==='true')" in script
                assert "else {\n                    fetch(" in script
                assert server.url + "api/action" in script
                if page == "dispatch-failed":
                    raise RuntimeError("WebView is not initialized")
                if page == "uninitialized":
                    # The page's conditional fallback has no editable state yet.
                    session.action({"action": "close"})
                # A ready page with a failed view save deliberately sends no close.
            else:
                assert "notice" in script
                calls.append("notice")
                completed.set()
        def destroy(self):
            assert self.events.closing.handler() is True
            calls.append("destroy")
            completed.set()
    window = Window()
    def start(callback, **kwargs):
        assert window.events.closing.handler() is False
        assert completed.wait(3), "native close worker did not finish"
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(
        create_window=lambda *args, **kwargs: window, start=start))
    ticks = itertools.count()
    monkeypatch.setattr(modern_review, "time", SimpleNamespace(monotonic=lambda: next(ticks),
                                                             sleep=lambda seconds: None))
    try:
        assert modern_review.run_native_window(server.start()) == 0
        if page in {"ready-save-failed", "dispatch-failed"}:
            assert calls == ["dispatch", "notice"]
            assert not session.close_requested
        else:
            assert calls == ["dispatch", "destroy"] and session.close_requested
    finally:
        server.close()
