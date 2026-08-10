"""GUI-Start soll bei Fehlern keinen leeren Grau-Schirm hinterlassen."""

from __future__ import annotations

import ast
from pathlib import Path


def test_gui_has_boot_and_init_failure_ui() -> None:
    src = Path("photobook_curator/gui.py").read_text(encoding="utf-8")
    assert "_show_init_failure" in src
    assert "Fotobuch wird geladen" in src
    assert "_FALLBACK_COLORS" in src
    tree = ast.parse(src)
    names = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_init_app" in names
    assert "_show_init_failure" in names
