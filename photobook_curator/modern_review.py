"""Local, authenticated photo workspace and native desktop window.

The Python application keeps the project state. Its WebView receives only a
random loopback URL and photo IDs; it never receives arbitrary file access.
"""
from __future__ import annotations

from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit


MAX_BODY = 64 * 1024
IMAGE_EDGES = frozenset({160, 320, 800, 1600, 2000})
ASSETS = {"": ("index.html", "text/html; charset=utf-8"),
          "index.html": ("index.html", "text/html; charset=utf-8"),
          "app.js": ("app.js", "text/javascript; charset=utf-8"),
          "style.css": ("style.css", "text/css; charset=utf-8")}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
REPORT_CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
              "style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; "
              "base-uri 'none'; form-action 'none'")


class ReviewServer:
    """An ephemeral server that can read only the supplied project's photos."""
    def __init__(self, session):
        self.session = session
        self.token = secrets.token_urlsafe(32)
        self.url = ""
        self.origin = ""
        self.last_seen = 0.0
        self._server = None
        self._thread = None
        self._cache: OrderedDict[tuple, bytes] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._decoders = threading.BoundedSemaphore(4)
        self._closed = False

    def start(self) -> str:
        if self._closed:
            raise RuntimeError("Die Vorschau wurde bereits geschlossen.")
        if self._server is not None:
            return self.url
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, *_):
                pass  # Never put the private session token or source names in logs.

            def send(self, status, body=b"", content_type="application/json; charset=utf-8",
                     *, report=False, cache=False, attachment=False):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                    self.send_header("Content-Security-Policy", REPORT_CSP if report else CSP)
                    self.send_header("Cache-Control", "private, max-age=3600" if cache else "no-store")
                    if attachment:
                        self.send_header("Content-Disposition", 'attachment; filename="selection_audit.csv"')
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    self.close_connection = True

            def error(self, status, message, state=None):
                data = {"error": message}
                if state is not None:
                    data["state"] = state
                self.send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"))

            def route(self):
                expected_host = owner.origin.removeprefix("http://")
                if self.headers.get("Host") != expected_host:
                    self.error(403, "Ungültiger Vorschau-Host.")
                    return None
                parsed = urlsplit(self.path)
                prefix = "/" + owner.token + "/"
                if not parsed.path.startswith(prefix):
                    self.error(404, "Diese Vorschau ist nicht verfügbar.")
                    return None
                return parsed.path[len(prefix):], parsed.query

            def do_GET(self):
                route = self.route()
                if route is None:
                    return
                path, query = route
                try:
                    if path in ASSETS:
                        asset, mime = ASSETS[path]
                        data = files("photobook_curator").joinpath("web_review", asset).read_bytes()
                        self.send(200, data, mime)
                    elif path == "api/state":
                        data = owner.session.snapshot()
                        owner.last_seen = time.monotonic()
                        self.send(200, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"))
                    elif re.fullmatch(r"image/\d+", path):
                        index = int(path.split("/")[1])
                        values = parse_qs(query).get("edge", ["160"])
                        if len(values) != 1 or not values[0].isdigit() or int(values[0]) not in IMAGE_EDGES:
                            self.error(400, "Ungültige Vorschaugrösse.")
                            return
                        photo = owner.session.image_photo(index)
                        data = owner._image(photo.path, int(values[0]))
                        self.send(200, data, "image/jpeg", cache=True)
                    elif path in {"report.html", "report.csv"}:
                        suffix = "html" if path.endswith("html") else "csv"
                        source = owner.session.output_dir / ("selection_audit." + suffix)
                        data = source.read_bytes()
                        self.send(200, data, "text/html; charset=utf-8" if suffix == "html"
                                  else "text/csv; charset=utf-8", report=True, attachment=suffix == "csv")
                    else:
                        self.error(404, "Nicht gefunden.")
                except (ValueError, IndexError) as exc:
                    self.error(getattr(exc, "status", 400), str(exc), getattr(exc, "state", None))
                except FileNotFoundError:
                    self.error(404, "Die Datei ist nicht verfügbar. Originale gegebenenfalls neu verknüpfen.")
                except TimeoutError:
                    self.error(503, "Die Bildvorschau wird geladen. Bitte erneut versuchen.")
                except (OSError, RuntimeError) as exc:
                    self.error(500, str(exc))

            def do_POST(self):
                route = self.route()
                if route is None:
                    self.close_connection = True
                    return
                if route[0] != "api/action" or route[1]:
                    self.error(404, "Nicht gefunden.")
                    self.close_connection = True
                    return
                if self.headers.get("Origin") != owner.origin:
                    self.error(403, "Diese Aktion muss aus der lokalen Vorschau kommen.")
                    self.close_connection = True
                    return
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                    self.error(415, "JSON erforderlich.")
                    self.close_connection = True
                    return
                raw_length = self.headers.get("Content-Length", "")
                if self.headers.get("Transfer-Encoding") or not raw_length.isdigit():
                    self.error(400, "Ungültige Anfragegrösse.")
                    self.close_connection = True
                    return
                size = int(raw_length)
                if size > MAX_BODY:
                    self.error(413, "Die Anfrage ist zu gross.")
                    self.close_connection = True
                    return
                try:
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ValueError("Unvollständige Anfrage.")
                    data = json.loads(raw.decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError("Die Anfrage muss ein Objekt sein.")
                    result = owner.session.action(data)
                    owner.last_seen = time.monotonic()
                    self.send(200, json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8"))
                except (ValueError, UnicodeError, RecursionError) as exc:
                    self.error(getattr(exc, "status", 400), str(exc), getattr(exc, "state", None))
                except (OSError, RuntimeError) as exc:
                    self.error(500, str(exc))

            def do_OPTIONS(self):
                self.error(403, "Nur lokale Vorschauaktionen sind erlaubt.")

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

        self._server = Server(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self._server.server_port}"
        self.url = self.origin + "/" + self.token + "/"
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": .1}, daemon=True, name="PhotoTool-review")
        self._thread.start()
        return self.url

    def _image(self, path: Path, edge: int) -> bytes:
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns, edge)
        with self._cache_lock:
            data = self._cache.get(key)
            if data is not None:
                self._cache.move_to_end(key)
                return data
        if not self._decoders.acquire(timeout=3):
            raise TimeoutError("Bilddecoder sind beschäftigt.")
        try:
            from .utils import load_image_scaled, load_thumb_cached
            image = load_thumb_cached(path, edge) if edge <= 320 else load_image_scaled(path, edge)
            try:
                output = BytesIO()
                image.convert("RGB").save(output, "JPEG", quality=88 if edge > 320 else 82)
                data = output.getvalue()
            finally:
                image.close()
            with self._cache_lock:
                self._cache[key] = data
                self._cache.move_to_end(key)
                while len(self._cache) > 128 or sum(len(value) for value in self._cache.values()) > 24 * 1024 * 1024:
                    self._cache.popitem(last=False)
            return data
        finally:
            self._decoders.release()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._cache_lock:
            self._cache.clear()


def _validate_window_url(url: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.username or parsed.password or parsed.fragment or parsed.query
            or not re.fullmatch(r"/[A-Za-z0-9_-]{32,}/", parsed.path)):
        raise ValueError("Das Vorschaufenster darf nur die lokale PhotoTool-Sitzung öffnen.")


def run_native_window(url: str, title: str = "PhotoTool · Auswahl prüfen", *,
                      smoke_result: Path | None = None, capture_dir: Path | None = None) -> int:
    """Own main-thread WebView2 event loop, isolated from the Tk analysis window."""
    _validate_window_url(url)
    import http.client
    import webview
    parsed = urlsplit(url)
    origin = f"http://127.0.0.1:{parsed.port}"

    class LocalAPIError(RuntimeError):
        def __init__(self, status, payload):
            self.status = status
            self.state = payload.get("state", {})
            super().__init__(payload.get("error", "Die lokale Sitzung hat die Anfrage abgelehnt."))

    def request(path, payload=None):
        # This is our validated loopback server, not an outgoing/proxied request.
        connection = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=3)
        try:
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            connection.request("GET" if payload is None else "POST", parsed.path + path,
                               body=body, headers={"Origin": origin, "Content-Type": "application/json"})
            response = connection.getresponse()
            value = json.loads(response.read().decode("utf-8"))
            if response.status != 200:
                raise LocalAPIError(response.status, value)
            return value
        finally:
            connection.close()

    width, height = 1400, 940
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
            width, height = min(width, rect.right - rect.left - 32), min(height, rect.bottom - rect.top - 48)
    width, height = max(640, width), max(480, height)
    window = webview.create_window(title[:140], url=url, width=width, height=height,
        min_size=(min(980, width), min(680, height)), background_color="#10191f", resizable=True,
        maximized=sys.platform == "win32")
    outcome = {"success": False, "error": "Die Oberfläche wurde nicht geladen."}

    def show_notice(message):
        try:
            window.run_js("(() => { const el=document.getElementById('notice'); if(el) {"
                          "el.hidden=false; el.textContent=" + json.dumps(message) + "; } })();")
        except Exception:
            pass

    allow_close, closing = threading.Event(), threading.Event()

    def close_worker():
        try:
            state = request("api/state")
            if state.get("busy"):
                show_notice("Ein Vorgang läuft noch. Bitte zuerst abschließen und danach das Fenster schließen.")
                return
            # A ready frontend owns pending choices/navigation and must flush them
            # itself. Only an uninitialized page can close directly without a queue.
            try:
                window.run_js("""(() => {
                  if(document.documentElement.dataset.appReady==='true') {
                    try { Promise.resolve(window.PhotoToolReview?.close()).catch(()=>{}); }
                    catch(_) { /* Keep this ready page open if its close fails. */ }
                  } else {
                    fetch(CLOSE_URL, {method:'POST', headers:{'Content-Type':'application/json'},
                      body:JSON.stringify({action:'close'})}).catch(()=>{});
                  }
                })();""".replace("CLOSE_URL", json.dumps(url + "api/action")))
            except Exception:
                pass
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = request("api/state")
                if state.get("close_requested"):
                    allow_close.set()
                    window.destroy()
                    return
                if state.get("busy"):
                    show_notice("Ein Vorgang läuft noch. Bitte warte bis zum Abschluss.")
                    return
                time.sleep(.1)
            # A native dispatch error cannot prove that the page has no pending
            # choices. Never bypass its queue from Python, even after a timeout.
            show_notice("Das Fenster bleibt geöffnet, weil noch nicht alle Änderungen gespeichert sind. "
                        "Bitte den Hinweis prüfen und erneut schließen.")
        except (ConnectionRefusedError, ConnectionResetError, http.client.RemoteDisconnected):
            # The owning process has already closed its session.
            allow_close.set()
            window.destroy()
        except Exception as exc:
            show_notice("Das Fenster bleibt geöffnet, weil Speichern noch nicht bestätigt wurde: " + str(exc))
        finally:
            closing.clear()

    def on_closing():
        if allow_close.is_set():
            return True
        if not closing.is_set():
            closing.set()
            threading.Thread(target=close_worker, name="PhotoTool-close", daemon=True).start()
        return False

    window.events.closing += on_closing

    def show_loaded_layout(layout, deadline):
        # evaluate_js wraps code in eval(), which our strict CSP intentionally blocks.
        # run_js executes a raw WebView2 script. Its real DOM event changes server
        # state only after both app startup and an actual photo decode succeeded.
        target = json.dumps(layout)
        script = """(() => {
          const target=TARGET;
          const images=Array.from(document.querySelectorAll('.large-image'));
          const root=document.documentElement;
          const button=document.querySelector('[data-layout="'+target+'"]');
          if(root.dataset.appReady==='true' && button && images.length &&
             images.every(image=>image.complete && image.naturalWidth>0) &&
             root.dataset.nativeSmokeLayout!==target) {
            root.dataset.nativeSmokeLayout=target;
            button.click();
          }
        })();""".replace("TARGET", target)
        while time.monotonic() < deadline:
            try:
                window.run_js(script)
                state = request("api/state")
                if state.get("view", {}).get("layout") == layout:
                    return state
            except Exception:
                pass
            time.sleep(.15)
        raise RuntimeError("Die echte Fotooberfläche wurde nicht startbereit: " + layout)

    def probe():
        try:
            deadline = time.monotonic() + 45
            initial = request("api/state")
            state = show_loaded_layout("B" if initial.get("view", {}).get("layout") == "A" else "A", deadline)
            info = {"title": title, "photo_count": len(state.get("photos", [])),
                    "ready": True, "image_ready": True, "theme": state.get("view", {}).get("theme")}
            if not info["photo_count"]:
                raise RuntimeError("Die Oberfläche enthält keine echten Testfotos.")
            outcome.update(success=True, frontend=info)
            outcome.pop("error", None)
            if capture_dir is not None:
                from PIL import ImageGrab
                capture_dir.mkdir(parents=True, exist_ok=True)
                for layout in ("A", "B", "C"):
                    show_loaded_layout(layout, time.monotonic() + 15)
                    time.sleep(.7)
                    ImageGrab.grab().save(capture_dir / f"modern-review-{layout}.png")
                outcome["captures"] = [f"modern-review-{layout}.png" for layout in ("A", "B", "C")]
        except Exception as exc:
            outcome.update(success=False, error=str(exc))
        finally:
            if smoke_result is not None:
                smoke_result.parent.mkdir(parents=True, exist_ok=True)
                smoke_result.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
                if not outcome["success"]:
                    # Keep failure diagnostics available even if the page cannot
                    # run the close handshake. Successful probes use the real X path.
                    allow_close.set()
                window.destroy()

    webview.start(probe if smoke_result is not None else None,
                  gui="edgechromium" if sys.platform == "win32" else None,
                  debug=False, private_mode=True)
    if smoke_result is not None:
        try:
            closed = bool(request("api/state").get("close_requested"))
            outcome["native_close_verified"] = closed
            if outcome["success"] and not closed:
                outcome.update(success=False, error="Das native Fenster wurde ohne Speicherbestätigung geschlossen.")
        except Exception as exc:
            outcome.update(success=False, native_close_verified=False, error=str(exc))
        smoke_result.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if smoke_result is None or outcome["success"] else 1


def open_modern_review(master, photos, plan, output_dir, on_saved=None):
    """Tk owns lifecycle/save guarantees; the native child owns the web window."""
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from .modern_review_session import ReviewSession

    output_dir = Path(output_dir).resolve()
    for child in master.winfo_children():
        child_output = getattr(child, "_modern_output_dir", getattr(child, "output_dir", None))
        if (child_output is not None and Path(child_output).resolve() == output_dir
                and callable(getattr(child, "_autosave_draft", None))):
            focus = getattr(child, "_focus_native", None)
            if focus is not None:
                focus()
            else:
                child.lift()
                child.focus_force()
            return child

    class ReviewHandle(tk.Toplevel):
        def __init__(self):
            super().__init__(master)
            self.withdraw()
            self._modern_output_dir = output_dir
            self._draft_save_error = None
            self._stopped = False
            self._native_requests = queue.Queue()
            self._monitor_job = None
            self._profile_dir = None
            self._last_revision = -1
            self._started_at = time.monotonic()
            self.session = ReviewSession(photos, plan, output_dir, on_native=self._native_action)
            self.photos = self.session.photos
            self.output_dir = output_dir
            self.server = ReviewServer(self.session)
            try:
                url = self.server.start()
                title = "PhotoTool · " + self.session.snapshot()["project"]["name"]
                self._process = self._launch(url, title)
            except Exception:
                self.server.close()
                self.destroy()
                raise
            self.bind("<Destroy>", self._on_destroy, add="+")
            self._monitor_job = self.after(80, self._monitor)

        @property
        def kept(self):
            return self.session.kept

        def _launch(self, url, title):
            if sys.platform == "win32":
                command = ([sys.executable] if getattr(sys, "frozen", False) else
                           [sys.executable, str(Path(__file__).resolve().parent.parent / "packaging" / "entry_gui.py")])
                command += ["--review-window", url, "--window-title", title]
            else:
                browser = next((shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome")
                                if shutil.which(name)), None)
                if not browser:
                    raise RuntimeError("Für die Vorschau wird Chromium oder Chrome benötigt.")
                self._profile_dir = Path(tempfile.mkdtemp(prefix="PhotoTool-view-"))
                command = [browser, "--app=" + url, "--user-data-dir=" + str(self._profile_dir),
                           "--no-first-run", "--disable-default-apps", "--class=PhotoToolReview"]
            return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def _focus_native(self):
            if sys.platform == "win32" and self._process.poll() is None:
                import ctypes
                from ctypes import wintypes
                api = ctypes.windll.user32
                callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                def visit(hwnd, _):
                    pid = wintypes.DWORD()
                    api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == self._process.pid and api.IsWindowVisible(hwnd):
                        api.ShowWindow(hwnd, 9)
                        api.SetForegroundWindow(hwnd)
                        return False
                    return True
                api.EnumWindows(callback_type(visit), 0)

        def _native_action(self, name, payload):
            event, result = threading.Event(), {}
            self._native_requests.put((name, payload, event, result))
            if not event.wait(600):
                raise OSError("Der Dateidialog wurde nicht beantwortet.")
            if "error" in result:
                raise OSError(result["error"])
            return result.get("value")

        def _drain_native(self):
            while not self._native_requests.empty():
                name, payload, event, result = self._native_requests.get_nowait()
                try:
                    if name == "choose_source":
                        master.lift()
                        result["value"] = filedialog.askdirectory(title="Neuen Originalordner wählen", parent=master) or ""
                        self._focus_native()
                    elif name == "open_folder":
                        which = payload.get("which", "selected")
                        if which not in {"selected", "project"}:
                            raise ValueError("Unbekannter Ausgabeordner.")
                        folder = output_dir / "selected" if which == "selected" else output_dir
                        if sys.platform == "win32":
                            os.startfile(str(folder))
                        else:
                            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        result["value"] = True
                    elif name == "advanced_tools":
                        tool = payload.get("tool", "all")
                        if tool not in {"all", "print", "motifs", "chapters", "rebuild"}:
                            raise ValueError("Unbekanntes Werkzeug.")
                        self.after(220, lambda chosen=tool: self._open_advanced(chosen))
                        result["value"] = {"switching": True}
                    else:
                        raise ValueError("Unbekannte Desktopaktion.")
                except Exception as exc:
                    result["error"] = str(exc)
                finally:
                    event.set()

        def _monitor(self):
            self._monitor_job = None
            if self._stopped:
                return
            self._drain_native()
            if self.session.lock.acquire(blocking=False):
                try:
                    busy = self.session.busy
                    close = self.session.close_requested
                    revision = self.session.revision
                finally:
                    self.session.lock.release()
                if revision != self._last_revision:
                    self._last_revision = revision
                    if on_saved is not None:
                        on_saved()
                if not busy and (close or self._process.poll() is not None):
                    if self._process.poll() not in (None, 0) and not self.server.last_seen:
                        messagebox.showerror("Vorschau konnte nicht starten",
                            "Bitte PhotoTool mit dem aktuellen Installer erneut installieren. "
                            "Die moderne Vorschau benötigt die Microsoft Edge WebView2-Laufzeit.", parent=master)
                    self._close()
                    return
                if not self.server.last_seen and time.monotonic() - self._started_at > 65:
                    messagebox.showerror("Vorschau nicht startbereit",
                        "Die Fotooberfläche konnte nicht geladen werden. Bitte PhotoTool erneut öffnen "
                        "oder den aktuellen Installer ausführen.", parent=master)
                    self._close()
                    return
            self._monitor_job = self.after(120, self._monitor)

        def _open_advanced(self, tool):
            from copy import deepcopy
            from tkinter import ttk
            from .review_gui import open_review
            view = deepcopy(self.session.view)
            current_plan = self.session.plan
            if not self._close():
                return
            win = open_review(master, photos, current_plan, output_dir, on_saved=on_saved, legacy=True)
            win.title("PhotoTool · Weitere Werkzeuge")
            bar = ttk.Frame(win, padding=(12, 6))
            children = [child for child in win.winfo_children() if child is not bar]
            bar.pack(fill=tk.X, before=children[0] if children else None)
            ttk.Label(bar, text="Weitere Werkzeuge").pack(side=tk.LEFT)
            def back():
                win._autosave_draft()
                if win._draft_save_error:
                    messagebox.showerror("Zwischenstand nicht gespeichert", win._draft_save_error, parent=win)
                    return
                current_photos, current_plan = win.photos, win.plan
                win._close()
                if win.winfo_exists():
                    # The classic window stays open when its final autosave
                    # fails. Keep it the sole writer of this project.
                    return
                modern = open_modern_review(master, current_photos, current_plan, output_dir, on_saved=on_saved)
                modern.session.action({"action": "view", "view": view})
            ttk.Button(bar, text="Zur neuen Vorschau", command=back).pack(side=tk.RIGHT)
            callback = {"print": win._print_check, "motifs": win._open_insights}.get(tool)
            if callback is not None:
                win.after(180, callback)

        def _autosave_draft(self):
            try:
                if self.session.busy:
                    raise OSError("Eine Ausgabe oder Ortsprüfung läuft noch. Bitte zuerst abschliessen.")
                self.session.save()
                self._draft_save_error = None
            except Exception as exc:
                self._draft_save_error = str(exc)

        def _close(self):
            self._autosave_draft()
            if self._draft_save_error:
                messagebox.showerror("Zwischenstand nicht gespeichert", self._draft_save_error, parent=master)
                return False
            try:
                self.session.close()
            except Exception as exc:
                messagebox.showerror("Vorschau wird noch benötigt", str(exc), parent=master)
                return False
            self._cleanup()
            self.destroy()
            return True

        def _cleanup(self):
            if self._stopped:
                return
            self._stopped = True
            if self._monitor_job is not None:
                self.after_cancel(self._monitor_job)
            while not self._native_requests.empty():
                _, _, event, result = self._native_requests.get_nowait()
                result["error"] = "Vorschau geschlossen."
                event.set()
            # Do not let the metadata/server object retain a bound Tk callback
            # after its owner closes. A later worker-side GC must never become
            # responsible for finalizing this window's Tcl interpreter.
            self.session.on_native = None
            process = getattr(self, "_process", None)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            self.server.close()
            if self._profile_dir is not None:
                shutil.rmtree(self._profile_dir, ignore_errors=True)

        def _on_destroy(self, event):
            if event.widget is self:
                self._cleanup()

    return ReviewHandle()
