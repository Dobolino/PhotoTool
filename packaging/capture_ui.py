"""Capture real native UI states for the Windows CI review artifact.

No images are analyzed, API calls made or user settings read. Progress and the
2,000-photo cost example are explicitly demo data, recorded in metadata.json.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _display_mode():
    """DEVMODEW, including the display/printer union retained as raw bytes."""
    from ctypes import wintypes as w

    class Mode(ctypes.Structure):
        _fields_ = [
            ("device", w.WCHAR * 32), ("spec", w.WORD), ("driver", w.WORD),
            ("size", w.WORD), ("extra", w.WORD), ("fields", w.DWORD),
            ("display_union", ctypes.c_byte * 16), ("color", w.SHORT),
            ("duplex", w.SHORT), ("y_resolution", w.SHORT), ("tt_option", w.SHORT),
            ("collate", w.SHORT), ("form", w.WCHAR * 32), ("log_pixels", w.WORD),
            ("bits", w.DWORD), ("width", w.DWORD), ("height", w.DWORD),
            ("flags", w.DWORD), ("frequency", w.DWORD), ("icm_method", w.DWORD),
            ("icm_intent", w.DWORD), ("media", w.DWORD), ("dither", w.DWORD),
            ("reserved1", w.DWORD), ("reserved2", w.DWORD),
            ("panning_width", w.DWORD), ("panning_height", w.DWORD),
        ]

    mode = Mode()
    mode.size = ctypes.sizeof(Mode)
    return mode


def prepare_display() -> tuple[dict, object | None]:
    info = {"requested_resolution": [1920, 1080], "changed": False}
    if sys.platform != "win32":
        info["reason"] = "Non-Windows local script check; no Windows screenshot claim"
        return info, None
    api = ctypes.windll.user32
    current = _display_mode()
    if not api.EnumDisplaySettingsW(None, -1, ctypes.byref(current)):
        info["reason"] = "Current display mode unavailable; capture actual Tk display"
        return info, None
    info["original_resolution"] = [current.width, current.height]
    info["original_frequency"] = current.frequency
    if (current.width, current.height) == (1920, 1080):
        info["reason"] = "Already 1920x1080"
        return info, None
    index = 0
    while True:
        mode = _display_mode()
        if not api.EnumDisplaySettingsW(None, index, ctypes.byref(mode)):
            break
        index += 1
        if (mode.width, mode.height, mode.bits) != (1920, 1080, current.bits):
            continue
        # Test first; change only this desktop session, never registry defaults.
        tested = api.ChangeDisplaySettingsExW(None, ctypes.byref(mode), None, 2, None)
        info["test_result"] = tested
        if tested != 0:
            continue
        applied = api.ChangeDisplaySettingsExW(None, ctypes.byref(mode), None, 4, None)
        info["apply_result"] = applied
        if applied == 0:
            info["changed"] = True
            info["reason"] = "Supported 1920x1080 mode temporarily applied"
            return info, current
    info["reason"] = "1920x1080 unsupported; actual available maximized layout captured"
    return info, None


def window_geometry(widget, *, native_window=True) -> dict:
    result = {"tk_geometry": widget.winfo_geometry(),
              "tk_client_bbox": [widget.winfo_rootx(), widget.winfo_rooty(),
                                 widget.winfo_rootx() + widget.winfo_width(),
                                 widget.winfo_rooty() + widget.winfo_height()]}
    result["capture_bbox"] = result["tk_client_bbox"]
    if native_window and sys.platform == "win32":
        from ctypes import wintypes as w
        api = ctypes.windll.user32
        api.GetAncestor.argtypes = [w.HWND, w.UINT]
        api.GetAncestor.restype = w.HWND
        hwnd = api.GetAncestor(widget.winfo_id(), 2)
        if hwnd:
            rect = w.RECT()
            # DWM bounds use physical pixels even when Tk is DPI virtualized.
            dwm = ctypes.windll.dwmapi.DwmGetWindowAttribute
            dwm.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
            if dwm(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0:
                result["capture_bbox"] = [rect.left, rect.top, rect.right, rect.bottom]
                result["capture_bbox_source"] = "DWM physical window bounds"
            try:
                api.GetDpiForWindow.argtypes = [w.HWND]
                result["window_dpi"] = int(api.GetDpiForWindow(hwnd))
            except AttributeError:
                pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "windows-ui")
    parser.add_argument("--allow-non-windows", action="store_true",
                        help="Local script check only; metadata records actual platform")
    args = parser.parse_args()
    if sys.platform != "win32" and not args.allow_non_windows:
        parser.error("Native Windows captures require Windows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"platform": platform.platform(), "python": platform.python_version(),
                "native_windows": sys.platform == "win32", "captures": [],
                "source_fields_empty": True, "network_and_analysis_disabled": True,
                "demo_states": ["Anthropic estimate for 2000 synthetic input count",
                                "Simulated analysis progress; no pipeline run"]}
    try:
        metadata["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        metadata["commit"] = "unknown"
    original_mode = None
    app = None
    failed = False
    try:
        metadata["display"], original_mode = prepare_display()
        from PIL import ImageGrab
        from photobook_curator import __version__, settings
        metadata["app_version"] = __version__
        with tempfile.TemporaryDirectory(prefix="PhotoTool-ui-capture-") as isolated:
            with patch.object(settings, "settings_path", lambda: Path(isolated) / "settings.json"), \
                    patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
                                            "GOOGLE_API_KEY": "", "OLLAMA_MODEL": "llava"}):
                from photobook_curator.gui import PhotobookApp
                with patch.object(PhotobookApp, "_warmup_backend", lambda self: None), \
                        patch.object(PhotobookApp, "_update_found_count", lambda self, path: None):
                    app = PhotobookApp()
                    if not app._init_ok:
                        raise RuntimeError("PhotobookApp startup failed")
                    app.input_var.set("")
                    app.output_var.set("")
                    app.api_key_var.set("")
                    app.gemini_key_var.set("")
                    metadata["display"].update({
                        "tk_screen": [app.winfo_screenwidth(), app.winfo_screenheight()],
                        "tk_scaling": float(app.tk.call("tk", "scaling")),
                    })

                    def fail(error):
                        nonlocal failed
                        failed = True
                        metadata["error"] = str(error)
                        metadata["traceback"] = traceback.format_exc()
                        app.destroy()

                    app.report_callback_exception = lambda kind, value, tb: fail(value)

                    def close_dialogs():
                        import tkinter as tk
                        sheet = getattr(app, "_settings_sheet", None)
                        if sheet is not None:
                            sheet.grab_release()
                            sheet.withdraw()
                        for child in list(app.winfo_children()):
                            if isinstance(child, tk.Toplevel) and child is not sheet:
                                child.grab_release()
                                child.destroy()

                    def regular():
                        app.state("normal")
                        width = min(1120, max(900, app.winfo_screenwidth() - 80))
                        height = min(820, max(660, app.winfo_screenheight() - 80))
                        app.geometry(f"{width}x{height}+30+30")
                        app.lift()

                    def maximized():
                        if sys.platform == "win32":
                            app.state("zoomed")
                        else:
                            app.attributes("-zoomed", True)
                        app.lift()

                    def processing_settings():
                        app._open_selection_settings("quality")

                    def anthropic_settings():
                        close_dialogs()
                        app._apply_config_settings({"ai_provider": "anthropic", "ai_review": True,
                                                    "dry_run": True, "target_n": 160})
                        app._found_count = 2000
                        app._refresh_cost_estimate()
                        app._refresh_run_summary()
                        app._open_selection_settings("ai")

                    def cost_main():
                        close_dialogs()
                        app._refresh_cost_estimate()
                        app._refresh_run_summary()

                    def progress_demo():
                        app._apply_config_settings({"ai_provider": "none", "ai_review": False, "dry_run": False})
                        app._refresh_run_summary()
                        app._show_main_view("analysis")
                        app._set_progress("DEMO · Lokale Analyse – 840 von 2000", 0.42, "quality")

                    steps = [("main-regular", regular), ("main-maximized", maximized),
                             ("settings-grouped", processing_settings),
                             ("settings-anthropic-dry-run-demo", anthropic_settings),
                             ("main-anthropic-dry-run-demo", cost_main),
                             ("analysis-progress-demo", progress_demo)]

                    def capture(name):
                        import tkinter as tk
                        if name == "main-maximized" and sys.platform == "win32" and app.state() != "zoomed":
                            raise RuntimeError("Windows maximized state was not reached")
                        visible = [w for w in app.winfo_children()
                                   if isinstance(w, tk.Toplevel) and w.winfo_ismapped()]
                        target = visible[-1] if visible else app
                        geometry = window_geometry(target)
                        screenshot = ImageGrab.grab(bbox=tuple(geometry["capture_bbox"]), all_screens=True)
                        if screenshot.width < 100 or screenshot.height < 100:
                            raise RuntimeError("Native screenshot has no usable window area")
                        extrema = screenshot.convert("RGB").getextrema()
                        if all(low == high for low, high in extrema):
                            raise RuntimeError("Native screenshot is blank")
                        filename = f"{name}.png"
                        screenshot.save(output / filename)
                        item = {"file": filename, "window": geometry,
                                "image_size": [screenshot.width, screenshot.height],
                                "main_state": app.state(), "main_geometry": window_geometry(app),
                                "content_width": getattr(app, "_content_width", None),
                                "ai_provider": app.ai_provider_var.get(),
                                "dry_run": bool(app.dry_run_var.get()),
                                "cost_summary": app.cost_var.get()}
                        if name == "main-maximized":
                            item["requested_maximized_state_achieved"] = app.state() == "zoomed"
                        for attribute in ("_content", "_content_frame", "_workspace", "_cards_host"):
                            widget = getattr(app, attribute, None)
                            if widget is not None and hasattr(widget, "winfo_width"):
                                item.setdefault("content_geometry", {})[attribute] = window_geometry(widget, native_window=False)
                        metadata["captures"].append(item)

                    def advance(index=0):
                        if index == len(steps):
                            close_dialogs()
                            app.destroy()
                            return
                        name, prepare = steps[index]

                        def finish_step():
                            try:
                                capture(name)
                                app.after(150, lambda: advance(index + 1))
                            except Exception as error:
                                fail(error)

                        # Schedule before opening a modal, so a nested wait_window
                        # still permits its screenshot and the scripted close.
                        app.after(900, finish_step)
                        try:
                            prepare()
                        except Exception as error:
                            fail(error)

                    app.after(50000, lambda: fail(TimeoutError("UI capture exceeded 50 seconds")))
                    app.after(700, advance)
                    app.mainloop()
                    if not failed and len(metadata["captures"]) != len(steps):
                        raise RuntimeError("UI capture ended before all requested states were captured")
    except Exception as error:
        failed = True
        metadata["error"] = str(error)
        metadata["traceback"] = traceback.format_exc()
    finally:
        if app is not None:
            try:
                if app.winfo_exists():
                    app.destroy()
            except Exception:
                pass
        if original_mode is not None:
            metadata["display"]["restore_result"] = ctypes.windll.user32.ChangeDisplaySettingsExW(
                None, ctypes.byref(original_mode), None, 0, None)
        metadata["success"] = not failed
        (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"success": not failed, "captures": len(metadata["captures"]),
                      "metadata": str(output / "metadata.json"), "error": metadata.get("error")}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
