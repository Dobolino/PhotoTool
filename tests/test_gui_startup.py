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
