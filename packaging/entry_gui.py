"""Einstiegspunkt für das gebündelte GUI-Executable (PyInstaller).

Bewusst schlank gehalten: nur der GUI-Start, damit PyInstaller einen klaren
Entry-Point hat. Fängt Startfehler ab und zeigt sie – im gebündelten
--windowed-Modus gäbe es sonst keinerlei Rückmeldung.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
import json

if not getattr(sys, "frozen", False):
    source_root = str(Path(__file__).resolve().parents[1])
    if source_root not in sys.path:
        sys.path.insert(0, source_root)


def _argument_after(flag: str) -> str:
    position = sys.argv.index(flag)
    if position + 1 >= len(sys.argv):
        raise ValueError(f"Argument fehlt: {flag}")
    return sys.argv[position + 1]


def main() -> int:
    try:
        from photobook_curator.branding import set_windows_app_id

        set_windows_app_id()
        # WebView2 owns this process's main thread. Do not initialize a Tk root
        # before entering its native event loop.
        if "--review-window" in sys.argv:
            from photobook_curator.modern_review import run_native_window

            title = _argument_after("--window-title") if "--window-title" in sys.argv else "PhotoTool – Auswahl prüfen"
            return run_native_window(_argument_after("--review-window"), title=title) or 0
        if "--review-smoke" in sys.argv:
            from native_review_smoke import run

            captures = Path(_argument_after("--review-capture-dir")) if "--review-capture-dir" in sys.argv else None
            return run(Path(_argument_after("--review-smoke")), capture_dir=captures)
        if "--smoke-test" in sys.argv:
            import tkinter as tk
            from photobook_curator import gui, review_gui, updater
            from photobook_curator.geocoding import offline_reverse
            from importlib.resources import files
            import photobook_curator.modern_review
            import photobook_curator.modern_review_session

            for name in ("index.html", "style.css", "app.js"):
                assert files("photobook_curator").joinpath("web_review", name).is_file(), name
            from PIL import Image
            from photobook_curator.branding import brand_asset
            from io import BytesIO

            for name, image_format in (("phototool.png", "PNG"), ("phototool.ico", "ICO")):
                with Image.open(BytesIO(brand_asset(name).read_bytes())) as image:
                    assert image.format == image_format, name
                    image.load()
            if sys.platform == "win32":
                import webview
            root = tk.Tk()
            root.withdraw()
            root.update()
            root.destroy()
            assert offline_reverse(35.6762, 139.6503)["city"] == "Tokyo"
            return 0
        from photobook_curator.gui import main as gui_main

        return gui_main()
    except Exception:  # pragma: no cover - Startdiagnose im Bundle
        err = traceback.format_exc()
        # CI probes must fail promptly rather than waiting behind a modal dialog
        # in a windowed executable. Preserve a machine-readable failure result.
        if "--smoke-test" in sys.argv or "--review-smoke" in sys.argv:
            if "--review-smoke" in sys.argv:
                try:
                    result = Path(_argument_after("--review-smoke"))
                    result.parent.mkdir(parents=True, exist_ok=True)
                    result.write_text(json.dumps({"success": False, "error": err},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            if sys.stderr is not None:
                sys.stderr.write(err)
            return 1
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Fotobuch – Startfehler",
                "Das Programm konnte nicht gestartet werden:\n\n" + err,
            )
        except Exception:
            sys.stderr.write(err)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
