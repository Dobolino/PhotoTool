"""GUI soll ohne schwere Backend-Imports startbar sein."""

from __future__ import annotations

import ast
from pathlib import Path


def test_gui_does_not_import_pipeline_at_module_level() -> None:
    src = Path("photobook_curator/gui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not (
                node.module.endswith("pipeline") or node.module == "pipeline"
            ), "pipeline darf nicht top-level importiert werden (nur unter TYPE_CHECKING)"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "pipeline" not in alias.name


def test_classify_console_chunk_detects_tqdm() -> None:
    from photobook_curator.gui import ConsoleQueueWriter, classify_console_chunk

    assert classify_console_chunk("hello", "line") == "line"
    assert classify_console_chunk("x", "status") == "status"
    assert (
        classify_console_chunk(
            "Technische Analyse:  36%|██ | 958/2618 [02:30<04:20, 6.37img/s]",
            "line",
        )
        == "status"
    )
    assert (
        classify_console_chunk(
            "Dokumente/Screenshots: 30%|▎| 780/2618 [01:00<08:55, 3.43img/s]",
            "line",
        )
        == "status"
    )

    import queue

    q: queue.Queue = queue.Queue()
    w = ConsoleQueueWriter(q, None)
    assert w.isatty() is True
    w.write("Technische Analyse: 10%| | 1/10 [00:01<00:09, 1.0img/s]\n")
    mode, _text = q.get_nowait()
    assert mode == "status"


def test_close_prompt_when_analysis_running() -> None:
    from photobook_curator.gui import PhotobookApp

    class AliveWorker:
        def is_alive(self) -> bool:
            return True

    class DeadWorker:
        def is_alive(self) -> bool:
            return False

    app = object.__new__(PhotobookApp)
    app._worker = AliveWorker()
    assert app._is_analysis_running() is True
    app._worker = DeadWorker()
    assert app._is_analysis_running() is False
    app._worker = None
    assert app._is_analysis_running() is False


def test_main_window_has_body_mousewheel_scroll() -> None:
    src = Path("photobook_curator/gui.py").read_text(encoding="utf-8")
    assert "_install_body_wheel" in src
    assert "_on_body_mousewheel" in src
    assert "_pointer_over_main_scroll_area" in src
    assert 'bind_all("<MouseWheel>"' in src
    assert "_body_canvas" in src


def test_gui_module_imports_without_cv2(monkeypatch) -> None:
    """Import von gui darf cv2/mediapipe nicht voraussetzen."""
    import importlib
    import sys

    blocked = {"cv2", "mediapipe", "sklearn"}
    real_import = __import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked or name in blocked:
            raise ImportError(f"blocked heavy import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    for key in list(sys.modules):
        if key == "photobook_curator.gui" or key.startswith("photobook_curator.pipeline"):
            sys.modules.pop(key, None)

    monkeypatch.setattr("builtins.__import__", guarded)
    mod = importlib.import_module("photobook_curator.gui")
    assert hasattr(mod, "PhotobookApp")
    assert hasattr(mod, "main")
