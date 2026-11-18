"""Einfache, optisch aufgeräumte Desktop-Oberfläche für den Photobook Curator."""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pipeline import PipelineConfig

from .phases import PHASE_STEPS, initial_phase_status, match_step_id

# Fallback-Palette (Nacht-UI, falls Settings/Theme nicht laden)
_FALLBACK_COLORS = {
    "bg": "#12141C",
    "surface": "#1C2030",
    "ink": "#E8EAF2",
    "muted": "#9AA3B5",
    "line": "#2C3348",
    "accent": "#7B6CFF",
    "accent_hover": "#6958F0",
    "accent_soft": "#2A2750",
    "danger": "#C45C5C",
    "reject": "#C45C5C",
    "keep_border": "#7B6CFF",
    "reject_border": "#3A4158",
    "log_bg": "#0E1018",
    "log_fg": "#C5CAD8",
    "phase_pending_bg": "#2A3145",
    "phase_pending_fg": "#9AA3B5",
    "phase_run_bg": "#C47A3A",
    "phase_run_fg": "#FFF8F0",
    "phase_done_bg": "#7B6CFF",
    "phase_done_fg": "#FFFFFF",
    "phase_skip_bg": "#242A3A",
    "phase_skip_fg": "#7A8296",
    "hero_fg": "#FFFFFF",
    "hero_muted": "#C8C4FF",
    "slide_stage": "#0E1018",
    "slide_fg": "#E8EAF2",
    "thumb_pad": "#242A3A",
    "chip_bg": "#262C40",
    "map_canvas": "#161A28",
}

try:
    from .i18n import sync_language_from_settings, t
    from .settings import load_settings, theme_colors

    COLORS = {**_FALLBACK_COLORS, **theme_colors()}
except Exception:  # pragma: no cover - Notfallstart
    def sync_language_from_settings() -> str:  # type: ignore
        return "de"

    def t(key: str, **kwargs: Any) -> str:  # type: ignore
        return {
            "app_title": "Fotobuch-Auswahl",
            "brand": "Fotobuch",
            "help": "Hilfe",
            "settings": "Darstellung & Sprache",
            "photos_folder": "Fotos-Ordner",
            "output_folder": "Ausgabe-Ordner",
            "browse": "Durchsuchen",
            "options_box": "  Einstellungen  ",
            "target_count": "Zielanzahl Bilder",
            "more_options": "Weitere Optionen ▸",
            "more_options_open": "Weitere Optionen ▾",
            "start": "Auswahl starten",
            "cancel": "Abbrechen",
            "review": "Auswahl prüfen / fortsetzen",
            "map": "Karte",
            "next_pick_folders": "Nächster Schritt: Ordner wählen…",
            "loading_modules": "Lade Erkennungsmodule…",
            "steps_hint": "Schritte (orange = läuft, grün = fertig)",
            "log": "Verlauf",
            "close": "Schließen",
            "opt_geocode": "Ortsnamen per Internet",
            "opt_faces": "Gesichtserkennung / Augen zu",
            "opt_bursts": "Serien/Bursts (beste 1–2)",
            "opt_aside": "Dokumente & Screenshots separat",
            "opt_accidental": "Fehlaufnahmen aussortieren",
            "opt_weak_night": "Schwache Nachtaufnahmen entfernen",
            "opt_finger": "Finger vor der Linse aussortieren",
            "opt_content": "Ähnliche Motive clustern",
            "opt_aesthetic": "Lokale Ästhetik (ohne API)",
            "opt_video": "Video-/Live-Photo-Standbilder",
            "opt_timezone": "Zeitzone korrigieren (Stunden)",
            "opt_coverage": "Tages-Abdeckung",
            "opt_people": "Personen-Balance",
            "opt_map": "Kapitel-/Karten-Vorschau vor Export",
            "opt_ai": "KI-Bewertung",
            "opt_dry": "Nur Kosten schätzen",
            "ai_provider": "KI wählen",
            "ai_section": "KI-Bewertung",
            "ai_provider_none": "Keine KI (nur lokal)",
            "ai_provider_gemini": "Google Gemini 1.5 Flash (Gratis)",
            "ai_provider_anthropic": "Anthropic Claude (kostenpflichtig)",
            "ai_provider_ollama": "Ollama lokal (Gratis, GPU)",
            "ai_api_key": "API-Key",
            "ai_api_key_gemini": "Gemini API-Key",
            "ai_api_key_anthropic": "Anthropic API-Key",
            "ai_key_link": "API-Key erstellen…",
            "ai_ollama_hint": "Vision-Modell wählen (z. B. llava).",
            "ai_ollama_model": "Ollama-Modell",
            "help_tip_title": "Erklärung",
            "help_tip_close": "Schließen",
            "ai_blurb_none": "100 % lokal & schnell – OpenCV / MediaPipe / pHash.",
            "ai_blurb_gemini": "Gratis (Free Tier, ~1500 Bilder/Tag) – gut für Ästhetik & Motive.",
            "ai_blurb_anthropic": "Pay-per-Use – höchste Präzision bei Komposition & Stimmung.",
            "ai_blurb_ollama": "Lokal & offline – braucht starke GPU, oft langsamer.",
            "help_title": "Hilfe – Fotobuch",
            "help_body": "Kurzanleitung – siehe START.md. Optionen: ? neben jeder Einstellung.",
        }.get(key, key)

    def load_settings():  # type: ignore
        class _S:
            language = "de"
            theme = "forest"
            slideshow_auto_advance = False
            slideshow_show_alternative = True

        return _S()

    def theme_colors(theme_id=None):  # type: ignore
        return dict(_FALLBACK_COLORS)

    COLORS = dict(_FALLBACK_COLORS)

PHASE_STYLE = {
    "pending": ("phase_pending_bg", "phase_pending_fg"),
    "running": ("phase_run_bg", "phase_run_fg"),
    "done": ("phase_done_bg", "phase_done_fg"),
    "skipped": ("phase_skip_bg", "phase_skip_fg"),
}

# tqdm-Zeilen (auch wenn ohne \r als normale Zeile kommen)
_PROGRESS_LINE_RE = re.compile(
    r"(\d+%|\d+/\d+.*(img/s|it/s)|%\||\|█|Technische Analyse:|Dokumente/Screenshots:|"
    r"Gesichter|Gesichtsqualität|pHash|Duplikate|Serien/Bursts|Finger-Check|"
    r"Personen-Cluster|Reverse Geocoding|AI-Review|Scan & EXIF)"
)


def classify_console_chunk(text: str, mode: str) -> str:
    """Unterscheidet feste Log-Zeilen von ersetzbarem Fortschritt (tqdm)."""
    if mode == "status":
        return "status"
    t = text.strip()
    if not t:
        return "line"
    if _PROGRESS_LINE_RE.search(t):
        return "status"
    return "line"


class ConsoleQueueWriter:
    """Leitet stdout/stderr in die GUI-Queue; täuscht TTY vor, damit tqdm \\r nutzt."""

    def __init__(self, q: queue.Queue, original) -> None:
        self.q = q
        self.original = original
        self._buf = ""
        self.encoding = getattr(original, "encoding", "utf-8") or "utf-8"

    def isatty(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def fileno(self) -> int:
        raise OSError("no fileno for GUI console writer")

    def write(self, s: str) -> int:
        if self.original:
            try:
                self.original.write(s)
            except Exception:
                pass
        self._buf += s
        # Segmente an \n (feste Zeile) und \r (tqdm-Zwischenstand) trennen.
        while True:
            nl = self._buf.find("\n")
            cr = self._buf.find("\r")
            if nl == -1 and cr == -1:
                break
            if cr == -1 or (nl != -1 and nl < cr):
                idx, mode = nl, "line"
            else:
                idx, mode = cr, "status"
            seg = self._buf[:idx].strip("\r")
            self._buf = self._buf[idx + 1 :]
            if seg.strip():
                mode = classify_console_chunk(seg, mode)
                self.q.put((mode, seg))
        return len(s)

    def flush(self) -> None:
        if self.original:
            try:
                self.original.flush()
            except Exception:
                pass


class PhotobookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        from .window_layout import place_window

        # Sofort sichtbar: verhindert „totales Leeren Fenster“ bei späteren Fehlern
        self.title("Fotobuch-Auswahl")
        self.configure(bg=_FALLBACK_COLORS["bg"])
        # Groß genug für Karten + Aktionsleiste – kein manuelles Aufziehen nötig
        place_window(
            self,
            frac_w=0.58,
            frac_h=0.90,
            min_width=900,
            min_height=780,
            width=980,
            height=860,
        )
        self._boot_lbl = tk.Label(
            self,
            text="Fotobuch wird geladen…",
            bg=_FALLBACK_COLORS["bg"],
            fg=_FALLBACK_COLORS["ink"],
            font=("Segoe UI", 13),
            padx=28,
            pady=28,
        )
        self._boot_lbl.pack(expand=True)
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

        self._init_ok = False
        try:
            self._init_app()
            self._init_ok = True
            # Nach UI-Aufbau nochmals zentriert platzieren (Taskleiste/DPI)
            place_window(
                self,
                frac_w=0.58,
                frac_h=0.90,
                min_width=900,
                min_height=780,
                width=980,
                height=860,
            )
        except Exception:
            self._show_init_failure()

    def _init_app(self) -> None:
        sync_language_from_settings()
        self.app_settings = load_settings()
        global COLORS
        COLORS = {**_FALLBACK_COLORS, **theme_colors(self.app_settings.theme)}
        self.title(t("app_title"))
        self.configure(bg=COLORS["bg"])
        self._set_icon()
        self._advanced_open = False
        self._ui_labels: dict[str, Any] = {}

        self.found_var = tk.StringVar(value="")
        self.cost_var = tk.StringVar(value="")
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.target_var = tk.IntVar(value=80)
        self.geocode_var = tk.BooleanVar(value=True)
        self.faces_var = tk.BooleanVar(value=True)
        self.bursts_var = tk.BooleanVar(value=True)
        self.aside_var = tk.BooleanVar(value=True)
        self.finger_var = tk.BooleanVar(value=False)
        self.accidental_var = tk.BooleanVar(value=True)
        self.weak_night_var = tk.BooleanVar(value=True)
        self.content_var = tk.BooleanVar(value=True)
        self.aesthetic_var = tk.BooleanVar(value=True)
        self.video_var = tk.BooleanVar(value=False)
        self.timezone_offset_var = tk.DoubleVar(value=0.0)
        self.coverage_var = tk.BooleanVar(value=False)
        self.coverage_intensity_var = tk.DoubleVar(value=0.5)
        self.people_var = tk.BooleanVar(value=False)
        self.people_intensity_var = tk.DoubleVar(value=0.5)
        self.map_preview_var = tk.BooleanVar(value=False)
        self.ai_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.ai_provider_var = tk.StringVar(value="none")
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.gemini_key_var = tk.StringVar(
            value=os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )
        self.ollama_model_var = tk.StringVar(
            value=os.environ.get("OLLAMA_MODEL", "llava")
        )
        self._found_count = 0
        self._last_ai_cost: dict[str, Any] | None = None
        self._candidate_factor = 4.0

        self._log_queue: queue.Queue = queue.Queue()
        self._progress_queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._body_wheel_bound = False
        self._body_canvas: tk.Canvas | None = None
        self._body_host: ttk.Frame | None = None
        self._body_scroll = None
        self._log_scroll = None
        self._status_shown = False       # tqdm-Zwischenstand als eine ersetzbare Zeile
        self._status_mark = "log_status"
        self._pending_status: str | None = None
        self._last_status_paint = 0.0
        self._phase_status: dict[str, str] = {
            s.id: "pending" for s in PHASE_STEPS
        }
        self._phase_labels: dict[str, tk.Label] = {}
        self._worker: threading.Thread | None = None
        self._last_photos = None
        self._last_plan = None
        self._last_order = None
        self._last_output: Path | None = None
        self._pipeline_ready = False
        self._pipeline_error: str | None = None
        self._setup_style()
        # Boot-Hinweis entfernen, dann echte UI
        try:
            if getattr(self, "_boot_lbl", None) is not None:
                self._boot_lbl.destroy()
                self._boot_lbl = None
        except tk.TclError:
            pass
        self._build()
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.after(100, self._drain_queues)
        # Schwere Module (OpenCV/MediaPipe) erst NACH dem Fenster laden,
        # sonst wirkt der Start wie ein leeres schwarzes Konsolenfenster.
        self.after(200, self._warmup_backend)

    def _show_init_failure(self) -> None:
        """Fehlertext im Fenster – nicht nur leeres Grau."""
        err = traceback.format_exc()
        try:
            log = Path(__file__).resolve().parent.parent / "fehler_beim_start.txt"
            log.write_text(err, encoding="utf-8")
        except Exception:
            pass
        try:
            print(err, file=sys.stderr)
        except Exception:
            pass
        try:
            for child in list(self.winfo_children()):
                child.destroy()
        except Exception:
            pass
        c = _FALLBACK_COLORS
        self.configure(bg=c["bg"])
        box = tk.Frame(self, bg=c["bg"], padx=24, pady=24)
        box.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            box,
            text="Startfehler – Oberfläche konnte nicht geladen werden",
            bg=c["bg"],
            fg=c["danger"],
            font=("Segoe UI Semibold", 12),
            anchor=tk.W,
        ).pack(fill=tk.X)
        tk.Label(
            box,
            text="Details stehen in fehler_beim_start.txt und start_log.txt",
            bg=c["bg"],
            fg=c["muted"],
            font=("Segoe UI", 10),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 10))
        txt = tk.Text(box, height=18, wrap=tk.WORD, bg=c["surface"], fg=c["ink"], padx=10, pady=10)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", err)
        txt.configure(state=tk.DISABLED)

    def _is_analysis_running(self) -> bool:
        return bool(self._worker and self._worker.is_alive())

    def _on_close_request(self) -> None:
        """Beim Schließen nachfragen, wenn gerade eine Analyse läuft."""
        if self._is_analysis_running():
            ok = messagebox.askyesno(
                "Analyse läuft noch",
                "Es läuft gerade eine Analyse.\n\n"
                "Wirklich schließen?\n"
                "Der aktuelle Lauf wird abgebrochen – bisherige Zwischenstände "
                "werden nicht als fertige Auswahl gespeichert.",
                icon=messagebox.WARNING,
                default=messagebox.NO,
                parent=self,
            )
            if not ok:
                return
            self._cancel_event.set()
            try:
                self.status_var.set("Wird geschlossen…")
            except tk.TclError:
                pass
        self._unbind_body_wheel()
        self.destroy()

    def _install_body_wheel(self) -> None:
        """Mausrad scrollt den Hauptinhalt (wie im Review-Fenster)."""
        if self._body_canvas is None:
            return
        # Immer neu binden: Review macht unbind_all und entfernt sonst unsere Handler
        self.bind_all("<MouseWheel>", self._on_body_mousewheel)
        self.bind_all("<Button-4>", self._on_body_linux_scroll_up)
        self.bind_all("<Button-5>", self._on_body_linux_scroll_down)
        self.bind("<FocusIn>", self._on_main_focus_in)
        self._body_wheel_bound = True

    def _unbind_body_wheel(self) -> None:
        if not self._body_wheel_bound:
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.unbind_all(seq)
            except Exception:
                pass
        self._body_wheel_bound = False

    def _on_main_focus_in(self, _event=None) -> None:
        # Nach Review-Fenster (unbind_all) Wheel wiederherstellen
        if self._body_canvas is not None:
            self._install_body_wheel()

    def _pointer_over_main_scroll_area(self) -> bool:
        """True, wenn Maus über dem scrollbaren Formular liegt – nicht über dem Log."""
        try:
            if not self.winfo_exists() or self._body_canvas is None:
                return False
            widget = self.winfo_containing(*self.winfo_pointerxy())
            w = widget
            while w is not None:
                if w is getattr(self, "log", None) or w is self._log_scroll:
                    return False
                if w in (self._body_canvas, self._body_host, self._body_scroll):
                    return True
                w = getattr(w, "master", None)
            return False
        except tk.TclError:
            return False

    def _scroll_body_units(self, units: int) -> None:
        if self._body_canvas is None:
            return
        try:
            self._body_canvas.yview_scroll(units, "units")
        except tk.TclError:
            pass

    def _on_body_mousewheel(self, event) -> str | None:
        if not self._pointer_over_main_scroll_area():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return None
        steps = -1 if delta > 0 else 1
        if abs(delta) >= 120:
            steps = int(-1 * (delta / 120))
        self._scroll_body_units(max(-8, min(8, steps * 3)))
        return "break"

    def _on_body_linux_scroll_up(self, _event=None) -> str | None:
        if self._pointer_over_main_scroll_area():
            self._scroll_body_units(-3)
            return "break"
        return None

    def _on_body_linux_scroll_down(self, _event=None) -> str | None:
        if self._pointer_over_main_scroll_area():
            self._scroll_body_units(3)
            return "break"
        return None

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        font_ui = ("Segoe UI", 10)
        c = COLORS
        entry_bg = c.get("chip_bg", c["surface"])

        style.configure("App.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["surface"])
        style.configure(
            "Card.TLabelframe",
            background=c["surface"],
            foreground=c["ink"],
            bordercolor=c["line"],
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=c["surface"],
            foreground=c["muted"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Title.TLabel",
            background=c["bg"],
            foreground=c["ink"],
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "Sub.TLabel",
            background=c["bg"],
            foreground=c["muted"],
            font=font_ui,
        )
        style.configure(
            "Field.TLabel",
            background=c["surface"],
            foreground=c["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Body.TLabel",
            background=c["surface"],
            foreground=c["ink"],
            font=font_ui,
        )
        style.configure("Hero.TFrame", background=c["bg"])
        style.configure(
            "HeroTitle.TLabel",
            background=c["bg"],
            foreground=c["ink"],
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "Browse.TButton",
            font=font_ui,
            padding=(14, 9),
            background=c.get("chip_bg", c["surface"]),
            foreground=c["ink"],
        )
        style.map(
            "Browse.TButton",
            background=[("active", c["line"]), ("disabled", c["line"])],
            foreground=[("disabled", c["muted"])],
        )
        style.configure(
            "Start.TButton",
            font=("Segoe UI Semibold", 11),
            padding=(20, 12),
            background=c["accent"],
            foreground=c.get("hero_fg", "#FFFFFF"),
        )
        style.map(
            "Start.TButton",
            background=[("active", c["accent_hover"]), ("disabled", c["line"])],
            foreground=[("disabled", c["muted"])],
        )
        style.configure(
            "TCheckbutton",
            background=c["surface"],
            foreground=c["ink"],
            font=font_ui,
            focuscolor=c["surface"],
        )
        style.map("TCheckbutton", background=[("active", c["surface"])])
        style.configure(
            "TEntry",
            fieldbackground=entry_bg,
            foreground=c["ink"],
            insertcolor=c["ink"],
            padding=10,
            bordercolor=c["line"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=entry_bg,
            background=entry_bg,
            foreground=c["ink"],
            insertcolor=c["ink"],
            padding=10,
            bordercolor=c["line"],
            arrowsize=14,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", entry_bg), ("disabled", c["line"])],
            foreground=[("disabled", c["muted"])],
            background=[("readonly", entry_bg), ("active", entry_bg)],
        )
        style.configure(
            "AI.TCombobox",
            fieldbackground=entry_bg,
            background=entry_bg,
            foreground=c["ink"],
            insertcolor=c["ink"],
            padding=(12, 11),
            bordercolor=c["accent"],
            arrowsize=16,
        )
        style.map(
            "AI.TCombobox",
            fieldbackground=[("readonly", entry_bg)],
            foreground=[("readonly", c["ink"])],
            background=[("readonly", entry_bg), ("active", c.get("accent_soft", entry_bg))],
        )
        try:
            self.option_add("*TCombobox*Listbox.background", entry_bg)
            self.option_add("*TCombobox*Listbox.foreground", c["ink"])
            self.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
            self.option_add("*TCombobox*Listbox.selectForeground", c.get("hero_fg", "#FFFFFF"))
            self.option_add("*TCombobox*Listbox.font", font_ui)
        except tk.TclError:
            pass
        style.configure(
            "TSpinbox",
            fieldbackground=entry_bg,
            foreground=c["ink"],
            insertcolor=c["ink"],
            padding=8,
            bordercolor=c["line"],
        )
        style.configure(
            "Next.TLabel",
            background=c["bg"],
            foreground=c["accent"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Help.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 9),
            background=c.get("chip_bg", c["surface"]),
            foreground=c["ink"],
        )
        style.map(
            "Help.TButton",
            background=[("active", c["line"])],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=c.get("chip_bg", c["surface"]),
            background=c["accent"],
            bordercolor=c["line"],
            lightcolor=c["accent"],
            darkcolor=c["accent"],
        )

    def _build(self) -> None:
        from .ui_widgets import (
            AnAusToggle,
            HelpTip,
            PaddedButton,
            card,
            pill_badge,
            section_header,
            soft_banner,
        )

        c = COLORS
        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True)

        # Akzentlinie oben
        tk.Frame(root, bg=c["accent"], height=3).pack(fill=tk.X)

        header = tk.Frame(root, bg=c["bg"], padx=22, pady=16)
        header.pack(fill=tk.X)
        self._brand_lbl = tk.Label(
            header,
            text=t("brand"),
            bg=c["bg"],
            fg=c["ink"],
            font=("Segoe UI Semibold", 22),
        )
        self._brand_lbl.pack(side=tk.LEFT)
        # PaddedButton statt ttk – vermeidet gequetschten Text in Kacheln
        self._settings_btn = PaddedButton(
            header, t("settings"), c, command=self._open_settings, padx=14, pady=9
        )
        self._settings_btn.pack(side=tk.RIGHT)
        self._help_btn = PaddedButton(
            header, t("help"), c, command=self._show_help, padx=14, pady=9
        )
        self._help_btn.pack(side=tk.RIGHT, padx=(0, 10))

        # Scrollbarer Inhalt (Mausrad → _install_body_wheel)
        body_host = ttk.Frame(root, style="App.TFrame")
        body_host.pack(fill=tk.BOTH, expand=True)
        self._body_host = body_host
        canvas = tk.Canvas(body_host, bg=c["bg"], highlightthickness=0)
        self._body_canvas = canvas
        scroll = ttk.Scrollbar(body_host, orient=tk.VERTICAL, command=canvas.yview)
        self._body_scroll = scroll
        body = ttk.Frame(canvas, style="App.TFrame", padding=(22, 4, 22, 12))
        body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        self._body_win = canvas.create_window((0, 0), window=body, anchor=tk.NW)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(self._body_win, width=e.width),
        )

        self._tip_banner = soft_banner(body, t("tip_resume"), c)
        self._tip_banner.pack(fill=tk.X, pady=(0, 14))

        # —— ORDNER ——
        section_header(body, t("folders_box"), c)
        folder_card = card(body, c)
        folder_card.pack(fill=tk.X)
        folder_inner = folder_card._inner  # type: ignore[attr-defined]

        self._input_title = self._folder_row(
            folder_inner, t("photos_folder"), "", self.input_var, self._pick_input
        )
        self._found_badge = pill_badge(folder_inner, "", c)
        self._found_badge.pack(anchor=tk.W, pady=(8, 0))
        self._found_badge.pack_forget()
        self.found_var.trace_add("write", lambda *_: self._sync_found_badge())

        tk.Frame(folder_inner, bg=c["line"], height=1).pack(fill=tk.X, pady=14)
        self._output_title = self._folder_row(
            folder_inner, t("output_folder"), "", self.output_var, self._pick_output
        )

        # —— EINSTELLUNGEN ——
        section_header(body, t("options_box"), c)
        settings_card = card(body, c)
        settings_card.pack(fill=tk.X, pady=(0, 4))
        settings = settings_card._inner  # type: ignore[attr-defined]
        self._options_box = settings

        target_row = tk.Frame(settings, bg=c["surface"])
        target_row.pack(fill=tk.X)
        self._target_lbl = tk.Label(
            target_row,
            text=t("target_count"),
            bg=c["surface"],
            fg=c["ink"],
            font=("Segoe UI", 10),
            anchor=tk.W,
        )
        self._target_lbl.pack(side=tk.LEFT)
        self._help_tips: list[HelpTip] = []
        tip = HelpTip(target_row, "help_target_count", c, get_text=t)
        tip.pack(side=tk.LEFT, padx=(4, 0))
        self._help_tips.append(tip)
        spin = ttk.Spinbox(
            settings,
            from_=10,
            to=500,
            textvariable=self.target_var,
            width=8,
            command=self._refresh_cost_estimate,
        )
        spin.pack(anchor=tk.W, pady=(6, 4))
        try:
            self.target_var.trace_add("write", lambda *_: self._refresh_cost_estimate())
            self.ai_var.trace_add("write", lambda *_: self._refresh_cost_estimate())
            self.ai_provider_var.trace_add("write", lambda *_: self._refresh_cost_estimate())
        except Exception:
            pass
        tk.Label(
            settings,
            textvariable=self.cost_var,
            bg=c["surface"],
            fg=c["muted"],
            font=("Segoe UI", 9),
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 10))

        self._core_checks: list[tuple[Any, str]] = []
        self._toggle_rows: list[tuple[tk.Label, AnAusToggle, str]] = []
        for key, long_key, var in (
            ("opt_geocode", "opt_geocode_long", self.geocode_var),
            ("opt_faces", "opt_faces_long", self.faces_var),
            ("opt_bursts", "opt_bursts", self.bursts_var),
            ("opt_aside", "opt_aside", self.aside_var),
            ("opt_accidental", "opt_accidental", self.accidental_var),
            ("opt_weak_night", "opt_weak_night", self.weak_night_var),
            ("opt_content", "opt_content", self.content_var),
            ("opt_aesthetic", "opt_aesthetic", self.aesthetic_var),
        ):
            row = tk.Frame(settings, bg=c["surface"])
            row.pack(fill=tk.X, pady=6)
            lbl = tk.Label(
                row,
                text=t(long_key),
                bg=c["surface"],
                fg=c["ink"],
                font=("Segoe UI", 10),
                anchor=tk.W,
            )
            lbl.pack(side=tk.LEFT)
            tip = HelpTip(row, f"help_{key}", c, get_text=t)
            tip.pack(side=tk.LEFT, padx=(4, 8))
            self._help_tips.append(tip)
            spacer = tk.Frame(row, bg=c["surface"])
            spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tog = AnAusToggle(
                row,
                var,
                c,
                command=self._sync_dependent_controls,
                on_text=t("toggle_on"),
                off_text=t("toggle_off"),
            )
            tog.pack(side=tk.RIGHT)
            self._toggle_rows.append((lbl, tog, long_key))
            self._core_checks.append((tog, key))

        tz_row = tk.Frame(settings, bg=c["surface"])
        tz_row.pack(fill=tk.X, pady=6)
        self._tz_lbl = tk.Label(
            tz_row,
            text=t("opt_timezone"),
            bg=c["surface"],
            fg=c["ink"],
            font=("Segoe UI", 10),
            anchor=tk.W,
        )
        self._tz_lbl.pack(side=tk.LEFT)
        tip = HelpTip(tz_row, "help_opt_timezone", c, get_text=t)
        tip.pack(side=tk.LEFT, padx=(4, 8))
        self._help_tips.append(tip)
        spacer = tk.Frame(tz_row, bg=c["surface"])
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.timezone_spin = ttk.Spinbox(
            tz_row,
            from_=-14,
            to=14,
            increment=0.5,
            textvariable=self.timezone_offset_var,
            width=6,
        )
        self.timezone_spin.pack(side=tk.RIGHT)
        opt_row = ttk.Frame(settings, style="Card.TFrame")
        opt_row.pack(fill=tk.X, pady=(12, 0))
        self.advanced_toggle = ttk.Button(
            opt_row,
            text=t("more_options"),
            style="Help.TButton",
            command=self._toggle_advanced,
        )
        self.advanced_toggle.pack(side=tk.LEFT)

        self.advanced_frame = ttk.Frame(settings, style="Card.TFrame")
        self._adv_checks: list[tuple[ttk.Checkbutton, str]] = []
        for key, var in (
            ("opt_video", self.video_var),
            ("opt_finger", self.finger_var),
            ("opt_coverage", self.coverage_var),
            ("opt_people", self.people_var),
            ("opt_map", self.map_preview_var),
        ):
            row = ttk.Frame(self.advanced_frame, style="Card.TFrame")
            row.pack(fill=tk.X, pady=3)
            chk = ttk.Checkbutton(
                row,
                text=t(key),
                variable=var,
                command=self._sync_dependent_controls,
            )
            chk.pack(side=tk.LEFT)
            tip = HelpTip(row, f"help_{key}", c, get_text=t)
            tip.pack(side=tk.LEFT, padx=(6, 0))
            self._help_tips.append(tip)
            self._adv_checks.append((chk, key))

        self.coverage_block = ttk.Frame(self.advanced_frame, style="Card.TFrame")
        cov_row = ttk.Frame(self.coverage_block, style="Card.TFrame")
        cov_row.pack(fill=tk.X, pady=(8, 0))
        self._coverage_strength_lbl = ttk.Label(
            cov_row, text=t("coverage_strength"), style="Field.TLabel"
        )
        self._coverage_strength_lbl.pack(side=tk.LEFT)
        self.coverage_label = ttk.Label(cov_row, text="50%", style="Field.TLabel")
        self.coverage_label.pack(side=tk.RIGHT)
        self.coverage_scale = ttk.Scale(
            self.coverage_block,
            from_=0.1,
            to=1.0,
            variable=self.coverage_intensity_var,
            command=self._on_coverage_scale,
        )
        self.coverage_scale.pack(fill=tk.X, pady=(4, 0))

        self.people_block = ttk.Frame(self.advanced_frame, style="Card.TFrame")
        people_row = ttk.Frame(self.people_block, style="Card.TFrame")
        people_row.pack(fill=tk.X, pady=(8, 0))
        self._people_strength_lbl = ttk.Label(
            people_row, text=t("people_strength"), style="Field.TLabel"
        )
        self._people_strength_lbl.pack(side=tk.LEFT)
        self.people_label = ttk.Label(people_row, text="50%", style="Field.TLabel")
        self.people_label.pack(side=tk.RIGHT)
        self.people_scale = ttk.Scale(
            self.people_block,
            from_=0.1,
            to=1.0,
            variable=self.people_intensity_var,
            command=self._on_people_scale,
        )
        self.people_scale.pack(fill=tk.X, pady=(4, 0))

        self.ai_block = ttk.Frame(self.advanced_frame, style="Card.TFrame")
        self._ai_section_lbl = ttk.Label(
            self.ai_block, text=t("ai_section"), style="Body.TLabel"
        )
        self._ai_section_lbl.pack(anchor=tk.W, pady=(12, 2))

        prov_row = ttk.Frame(self.ai_block, style="Card.TFrame")
        prov_row.pack(fill=tk.X, pady=(4, 0))
        self._ai_provider_lbl = ttk.Label(
            prov_row, text=t("ai_provider"), style="Field.TLabel"
        )
        self._ai_provider_lbl.pack(side=tk.LEFT)
        tip = HelpTip(prov_row, "help_ai_provider", c, get_text=t)
        tip.pack(side=tk.LEFT, padx=(6, 0))
        self._help_tips.append(tip)

        self._ai_provider_values = self._provider_label_pairs()
        self.ai_provider_combo = ttk.Combobox(
            self.ai_block,
            state="readonly",
            style="AI.TCombobox",
            values=[label for _, label in self._ai_provider_values],
        )
        self.ai_provider_combo.pack(fill=tk.X, pady=(6, 0), ipady=2)
        self._sync_ai_provider_combo_display()
        self.ai_provider_combo.bind("<<ComboboxSelected>>", self._on_ai_provider_selected)

        self.ai_blurb_var = tk.StringVar(value=t("ai_blurb_none"))
        self._ai_blurb_lbl = ttk.Label(
            self.ai_block,
            textvariable=self.ai_blurb_var,
            style="Field.TLabel",
            wraplength=440,
            justify=tk.LEFT,
        )
        self._ai_blurb_lbl.pack(anchor=tk.W, fill=tk.X, pady=(8, 0))

        key_row = ttk.Frame(self.ai_block, style="Card.TFrame")
        self._api_key_lbl = ttk.Label(key_row, text=t("ai_api_key"), style="Field.TLabel")
        self._api_key_lbl.pack(side=tk.LEFT)
        self._api_key_link = ttk.Label(
            key_row,
            text=t("ai_key_link"),
            style="Field.TLabel",
            cursor="hand2",
        )
        self._api_key_link.pack(side=tk.RIGHT)
        self._api_key_link.bind("<Button-1>", self._open_api_key_url)
        self._key_row = key_row
        self.api_entry = ttk.Entry(self.ai_block, show="•")
        self._bind_active_api_entry()

        self._ollama_hint_lbl = ttk.Label(
            self.ai_block, text=t("ai_ollama_hint"), style="Field.TLabel", wraplength=440
        )
        self._ollama_lbl_row = ttk.Frame(self.ai_block, style="Card.TFrame")
        self._ollama_model_lbl = ttk.Label(
            self._ollama_lbl_row, text=t("ai_ollama_model"), style="Field.TLabel"
        )
        self._ollama_model_lbl.pack(side=tk.LEFT)
        tip = HelpTip(self._ollama_lbl_row, "help_ai_ollama_model", c, get_text=t)
        tip.pack(side=tk.LEFT, padx=(6, 0))
        self._help_tips.append(tip)
        self.ollama_model_combo = ttk.Combobox(
            self.ai_block,
            textvariable=self.ollama_model_var,
            style="AI.TCombobox",
            values=list(self._default_ollama_choices()),
        )
        self.ollama_model_entry = self.ollama_model_combo
        self._ollama_row = self._ollama_lbl_row

        dry_row = ttk.Frame(self.ai_block, style="Card.TFrame")
        self.dry_run_chk = ttk.Checkbutton(
            dry_row,
            text=t("opt_dry"),
            variable=self.dry_run_var,
            command=self._sync_dependent_controls,
        )
        self.dry_run_chk.pack(side=tk.LEFT)
        tip = HelpTip(dry_row, "help_opt_dry", c, get_text=t)
        tip.pack(side=tk.LEFT, padx=(6, 0))
        self._help_tips.append(tip)
        self._dry_row = dry_row
        # Ollama-/Key-/Dry-Run-Zeilen werden in _sync_dependent_controls ein-/ausgeblendet

        # Status / Fortschritt
        self.next_step_var = tk.StringVar(value=t("next_pick_folders"))
        ttk.Label(body, textvariable=self.next_step_var, style="Next.TLabel").pack(
            anchor=tk.W, pady=(14, 2)
        )
        self.status_var = tk.StringVar(value=t("loading_modules"))
        ttk.Label(body, textvariable=self.status_var, style="Sub.TLabel").pack(anchor=tk.W)

        prog_row = ttk.Frame(body, style="App.TFrame")
        prog_row.pack(fill=tk.X, pady=(8, 0))
        self.phase_var = tk.StringVar(value="")
        ttk.Label(prog_row, textvariable=self.phase_var, style="Sub.TLabel").pack(anchor=tk.W)
        self.progress = ttk.Progressbar(prog_row, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(4, 0))

        self._phase_box = ttk.LabelFrame(
            body,
            text=f"  {t('steps_hint')}  ",
            style="Card.TLabelframe",
            padding=8,
        )
        self._phase_box.pack(fill=tk.X, pady=(10, 0))
        self._phase_inner = ttk.Frame(self._phase_box, style="Card.TFrame")
        self._phase_inner.pack(fill=tk.X)
        self._build_phase_chips()

        log_frame = ttk.LabelFrame(
            body, text=f"  {t('log')}  ", style="Card.TLabelframe", padding=8
        )
        self._log_frame = log_frame
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        log_row = ttk.Frame(log_frame, style="Card.TFrame")
        log_row.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(
            log_row,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=c["log_bg"],
            fg=c["log_fg"],
            insertbackground=c["log_fg"],
            relief=tk.FLAT,
            font=("Consolas", 9),
            padx=10,
            pady=8,
        )
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._log_scroll = ttk.Scrollbar(log_row, command=self.log.yview)
        self._log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=self._log_scroll.set)

        # Untere Aktionsleiste (immer sichtbar)
        actions = tk.Frame(root, bg=c["surface"], padx=18, pady=14)
        actions.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(root, bg=c["line"], height=1).pack(fill=tk.X, side=tk.BOTTOM)
        self.start_btn = ttk.Button(
            actions, text=t("start"), style="Start.TButton", command=self._start
        )
        self.start_btn.pack(side=tk.RIGHT)
        self.cancel_btn = ttk.Button(
            actions,
            text=t("cancel"),
            style="Browse.TButton",
            command=self._cancel,
            state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(0, 10))
        self.review_btn = ttk.Button(
            actions,
            text=t("review"),
            style="Browse.TButton",
            command=self._open_review,
        )
        self.review_btn.pack(side=tk.RIGHT, padx=(0, 10))
        self.map_btn = ttk.Button(
            actions, text=t("map"), style="Browse.TButton", command=self._open_map_preview
        )
        self.map_btn.pack(side=tk.RIGHT, padx=(0, 10))

        self._sync_dependent_controls()
        self._refresh_cost_estimate()
        self._install_body_wheel()

    def _set_icon(self) -> None:
        """Ersetzt das Standard-Tk-Icon (blaue Feder) durch ein eigenes."""
        try:
            from PIL import Image, ImageDraw, ImageTk

            n = 64
            img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([2, 2, n - 3, n - 3], radius=14, fill="#7B6CFF")
            d.rectangle([14, 18, 50, 46], fill="#E8EAF2")
            d.polygon([(18, 44), (28, 30), (36, 44)], fill="#5C6B8A")
            d.polygon([(32, 44), (40, 34), (48, 44)], fill="#3D4A6B")
            d.ellipse([40, 22, 47, 29], fill="#C8C4FF")
            self._icon_img = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _ui_phase_config(self) -> Any:
        """Leichte Config-Ansicht aus den Checkboxen (für Schritt-Vorschau)."""

        class _Cfg:
            pass

        cfg = _Cfg()
        cfg.enable_document_aside = bool(self.aside_var.get())
        cfg.enable_faces = bool(self.faces_var.get())
        cfg.enable_bursts = bool(self.bursts_var.get())
        cfg.enable_finger_filter = bool(self.finger_var.get())
        cfg.enable_accidental_filter = bool(self.accidental_var.get())
        cfg.enable_weak_night_filter = bool(self.weak_night_var.get())
        cfg.enable_content_clusters = bool(self.content_var.get())
        cfg.enable_local_aesthetic = bool(self.aesthetic_var.get())
        cfg.enable_video_frames = bool(self.video_var.get())
        cfg.enable_map_preview = bool(self.map_preview_var.get())
        cfg.people_balance_intensity = (
            float(self.people_intensity_var.get()) if self.people_var.get() else 0.0
        )
        return cfg

    def _default_ollama_choices(self) -> list[str]:
        from .ai_review import DEFAULT_OLLAMA_MODEL_CHOICES

        return list(DEFAULT_OLLAMA_MODEL_CHOICES)

    def _refresh_ollama_model_choices(self) -> None:
        """Combobox mit installierten Ollama-Modellen + Standard-Vision-Vorschlägen füllen."""
        if not hasattr(self, "ollama_model_combo"):
            return
        from .ai_review import DEFAULT_OLLAMA_MODEL, list_ollama_models

        installed = list_ollama_models()
        choices: list[str] = []
        for name in [*installed, *self._default_ollama_choices()]:
            if name and name not in choices:
                choices.append(name)
        if not choices:
            choices = [DEFAULT_OLLAMA_MODEL]
        self.ollama_model_combo.configure(values=choices)
        current = (self.ollama_model_var.get() or "").strip()
        if current and current not in choices:
            choices = [current, *choices]
            self.ollama_model_combo.configure(values=choices)
        if not current:
            prefer = next((n for n in installed if "llava" in n or "vision" in n), None)
            self.ollama_model_var.set(prefer or choices[0])

    def _provider_label_pairs(self) -> list[tuple[str, str]]:
        return [
            ("none", t("ai_provider_none")),
            ("gemini", t("ai_provider_gemini")),
            ("anthropic", t("ai_provider_anthropic")),
            ("ollama", t("ai_provider_ollama")),
        ]

    def _bind_active_api_entry(self) -> None:
        """API-Key-Feld an den passenden StringVar des Providers binden."""
        if not hasattr(self, "api_entry"):
            return
        provider = self._selected_ai_provider()
        var = self.gemini_key_var if provider == "gemini" else self.api_key_var
        self.api_entry.configure(textvariable=var)

    def _open_api_key_url(self, _event=None) -> None:
        import webbrowser

        from .ai_review import ANTHROPIC_KEY_URL, GEMINI_KEY_URL

        provider = self._selected_ai_provider()
        url = GEMINI_KEY_URL if provider == "gemini" else ANTHROPIC_KEY_URL
        try:
            webbrowser.open(url)
        except Exception:
            messagebox.showinfo("API-Key", url)

    def _sync_ai_provider_combo_display(self) -> None:
        """Combobox-Anzeige an ai_provider_var anpassen."""
        if not hasattr(self, "ai_provider_combo"):
            return
        self._ai_provider_values = self._provider_label_pairs()
        current = self._selected_ai_provider()
        labels = []
        selected = None
        for key, label in self._ai_provider_values:
            labels.append(label)
            if key == current:
                selected = label
        self.ai_provider_combo.configure(values=labels)
        if selected:
            self.ai_provider_combo.set(selected)
        elif labels:
            self.ai_provider_combo.set(labels[0])
            self.ai_provider_var.set(self._ai_provider_values[0][0])

    def _on_ai_provider_selected(self, _event=None) -> None:
        label = self.ai_provider_combo.get()
        for key, lbl in self._ai_provider_values:
            if lbl == label:
                self.ai_provider_var.set(key)
                break
        provider = self._selected_ai_provider()
        self.ai_var.set(provider != "none")
        self._bind_active_api_entry()
        self._sync_dependent_controls()
        self._refresh_cost_estimate()

    def _selected_ai_provider(self) -> str:
        from .ai_review import normalize_ai_provider

        return normalize_ai_provider(self.ai_provider_var.get())

    def _sync_dependent_controls(self) -> None:
        """Regler nur zeigen, wenn die Option an ist; KI-Felder abhängig vom Provider."""
        # Während des UI-Aufbaus können Widgets noch fehlen
        if not hasattr(self, "api_entry") or not hasattr(self, "coverage_scale"):
            return

        def enable(widget, on: bool) -> None:
            try:
                widget.state(["!disabled"] if on else ["disabled"])
            except Exception:
                pass

        provider = self._selected_ai_provider()
        ai_on = provider != "none"
        self.ai_var.set(ai_on)

        # Blöcke nur einblenden, wenn erweiterte Optionen offen sind
        if self._advanced_open:
            if self.coverage_var.get():
                self.coverage_block.pack(fill=tk.X)
            else:
                self.coverage_block.pack_forget()
            if self.people_var.get():
                self.people_block.pack(fill=tk.X)
            else:
                self.people_block.pack_forget()
            # KI-Block immer sichtbar in den erweiterten Optionen
            self.ai_block.pack(fill=tk.X)

        enable(self.ai_provider_combo, True)
        blurb_key = {
            "none": "ai_blurb_none",
            "gemini": "ai_blurb_gemini",
            "anthropic": "ai_blurb_anthropic",
            "ollama": "ai_blurb_ollama",
        }.get(provider, "ai_blurb_none")
        if hasattr(self, "ai_blurb_var"):
            self.ai_blurb_var.set(t(blurb_key))

        use_ollama = provider == "ollama"
        use_gemini = provider == "gemini"
        use_anthropic = provider == "anthropic"
        needs_key = use_gemini or use_anthropic

        if hasattr(self, "_api_key_lbl"):
            if needs_key:
                key_label = t("ai_api_key_gemini") if use_gemini else t("ai_api_key_anthropic")
                self._api_key_lbl.configure(text=key_label)
                self._key_row.pack(fill=tk.X, pady=(8, 0))
                self.api_entry.pack(fill=tk.X, pady=(4, 0))
                enable(self.api_entry, True)
                self._bind_active_api_entry()
            else:
                self._key_row.pack_forget()
                self.api_entry.pack_forget()

        if hasattr(self, "_ollama_row"):
            if use_ollama:
                self._refresh_ollama_model_choices()
                self._ollama_hint_lbl.pack(anchor=tk.W, fill=tk.X, pady=(10, 0))
                self._ollama_lbl_row.pack(fill=tk.X, pady=(6, 0))
                self.ollama_model_combo.pack(fill=tk.X, pady=(4, 0), ipady=2)
                enable(self.ollama_model_combo, True)
            else:
                self._ollama_hint_lbl.pack_forget()
                self._ollama_lbl_row.pack_forget()
                self.ollama_model_combo.pack_forget()

        if hasattr(self, "dry_run_chk"):
            # Dry-Run vor allem für Anthropic sinnvoll; bei Gemini optional zum Testen
            show_dry = use_anthropic or use_gemini
            if show_dry:
                self._dry_row.pack(fill=tk.X, pady=(8, 0))
                enable(self.dry_run_chk, True)
            else:
                self._dry_row.pack_forget()
                self.dry_run_var.set(False)

        enable(self.coverage_scale, bool(self.coverage_var.get()))
        enable(self.people_scale, bool(self.people_var.get()))
        # Schritt-Tafel vor dem Start an Optionen anpassen
        if hasattr(self, "_phase_inner") and not self._is_analysis_running():
            self._reset_phase_board(self._ui_phase_config())

    def _folder_row(
        self,
        parent: tk.Misc,
        title: str,
        hint: str,
        var: tk.StringVar,
        command,
    ) -> tk.Label:
        c = COLORS
        title_lbl = tk.Label(
            parent,
            text=title,
            bg=c["surface"],
            fg=c["ink"],
            font=("Segoe UI", 10),
            anchor=tk.W,
        )
        title_lbl.pack(anchor=tk.W)
        if hint:
            tk.Label(
                parent, text=hint, bg=c["surface"], fg=c["muted"], font=("Segoe UI", 9)
            ).pack(anchor=tk.W, pady=(0, 4))
        row = tk.Frame(parent, bg=c["surface"])
        row.pack(fill=tk.X, pady=(6, 0))
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        browse = ttk.Button(
            row, text=t("browse"), style="Browse.TButton", command=command
        )
        browse.pack(side=tk.LEFT, padx=(10, 0))
        title_lbl._browse_btn = browse  # type: ignore[attr-defined]
        return title_lbl

    def _sync_found_badge(self) -> None:
        text = (self.found_var.get() or "").strip()
        try:
            if not text or text == t("found_counting"):
                self._found_badge.pack_forget()
                if text == t("found_counting"):
                    self._found_badge.configure(text=f"  {text}  ")
                    self._found_badge.pack(anchor=tk.W, pady=(8, 0))
                return
            self._found_badge.configure(text=f"  {text}  ")
            if not self._found_badge.winfo_ismapped():
                self._found_badge.pack(anchor=tk.W, pady=(8, 0))
        except tk.TclError:
            pass

    def _open_settings(self) -> None:
        from .settings_dialog import open_settings_dialog

        open_settings_dialog(self, on_saved=self._on_settings_saved)

    def _on_settings_saved(self, settings) -> None:
        self.app_settings = settings
        global COLORS
        COLORS = {**_FALLBACK_COLORS, **theme_colors(settings.theme)}
        self.configure(bg=COLORS["bg"])
        self._setup_style()
        self._apply_ui_language()
        try:
            self.log.configure(
                bg=COLORS["log_bg"],
                fg=COLORS["log_fg"],
                insertbackground=COLORS["log_fg"],
            )
        except tk.TclError:
            pass
        self._build_phase_chips()
        messagebox.showinfo(
            t("settings_title"),
            f"{t('settings_saved')}\n\n{t('settings_restart_hint')}",
            parent=self,
        )

    def _apply_ui_language(self) -> None:
        """Aktualisiert sichtbare Haupttexte nach Sprachwechsel."""
        try:
            self.title(t("app_title"))
            self._brand_lbl.configure(text=t("brand"))
            self._target_lbl.configure(text=t("target_count"))
            self._phase_box.configure(text=f"  {t('steps_hint')}  ")
            self._log_frame.configure(text=f"  {t('log')}  ")
            self.start_btn.configure(text=t("start"))
            self.cancel_btn.configure(text=t("cancel"))
            self.review_btn.configure(text=t("review"))
            self.map_btn.configure(text=t("map"))
            self._settings_btn.configure(text=t("settings"))
            self._help_btn.configure(text=t("help"))
            self.advanced_toggle.configure(
                text=t("more_options_open") if self._advanced_open else t("more_options")
            )
            self._input_title.configure(text=t("photos_folder"))
            self._output_title.configure(text=t("output_folder"))
            for lbl in (self._input_title, self._output_title):
                btn = getattr(lbl, "_browse_btn", None)
                if btn is not None:
                    btn.configure(text=t("browse"))
            for lbl, tog, key in getattr(self, "_toggle_rows", []):
                lbl.configure(text=t(key))
                tog.set_labels(t("toggle_on"), t("toggle_off"))
            if getattr(self, "_tz_lbl", None) is not None:
                self._tz_lbl.configure(text=t("opt_timezone"))
            for chk, key in self._adv_checks:
                chk.configure(text=t(key))
            if getattr(self, "_coverage_strength_lbl", None) is not None:
                self._coverage_strength_lbl.configure(text=t("coverage_strength"))
            if getattr(self, "_people_strength_lbl", None) is not None:
                self._people_strength_lbl.configure(text=t("people_strength"))
            if getattr(self, "_ai_section_lbl", None) is not None:
                self._ai_section_lbl.configure(text=t("ai_section"))
            if getattr(self, "_ai_provider_lbl", None) is not None:
                self._ai_provider_lbl.configure(text=t("ai_provider"))
                self._sync_ai_provider_combo_display()
            if getattr(self, "_api_key_link", None) is not None:
                self._api_key_link.configure(text=t("ai_key_link"))
            if getattr(self, "dry_run_chk", None) is not None:
                self.dry_run_chk.configure(text=t("opt_dry"))
            if getattr(self, "_ollama_hint_lbl", None) is not None:
                self._ollama_hint_lbl.configure(text=t("ai_ollama_hint"))
            if getattr(self, "_ollama_model_lbl", None) is not None:
                self._ollama_model_lbl.configure(text=t("ai_ollama_model"))
            self._sync_dependent_controls()
            self._refresh_cost_estimate()
            # Hilfe-Popups nutzen get_text=t → nächster Klick auf ? ist in neuer Sprache
            for tip in getattr(self, "_help_tips", []):
                try:
                    tip._close()
                except Exception:
                    pass
            tip_banner = getattr(self, "_tip_banner", None)
            if tip_banner is not None:
                for child in tip_banner.winfo_children():
                    if isinstance(child, tk.Label):
                        child.configure(text=t("tip_resume"))
            if self._found_count:
                self.found_var.set(t("found_photos", n=self._found_count))
            elif self.found_var.get():
                # leerer/fehlgeschlagener Ordner neu beschriften
                cur = self.found_var.get()
                if "gefunden" in cur.lower() or "found" in cur.lower() or "Keine" in cur:
                    self.found_var.set(t("found_none"))
            if not self._is_analysis_running() and self.status_var.get() in (
                "Lade Erkennungsmodule…",
                "Loading detection modules…",
                t("loading_modules"),
            ):
                self.status_var.set(t("loading_modules"))
        except tk.TclError:
            pass

    def _on_coverage_scale(self, _value=None) -> None:
        pct = int(round(float(self.coverage_intensity_var.get()) * 100))
        self.coverage_label.configure(text=f"{pct}%")

    def _on_people_scale(self, _value=None) -> None:
        pct = int(round(float(self.people_intensity_var.get()) * 100))
        self.people_label.configure(text=f"{pct}%")

    def _warmup_backend(self) -> None:
        """Lädt Pipeline-Abhängigkeiten im Hintergrund, Fenster bleibt bedienbar."""

        def worker() -> None:
            try:
                from . import pipeline as _pipeline  # noqa: F401

                self._pipeline_ready = True
                self.after(0, lambda: self.status_var.set("Bereit"))
                self.after(0, lambda: self._append_log("Erkennungsmodule geladen."))
            except Exception:
                self._pipeline_error = traceback.format_exc()
                self.after(0, lambda: self.status_var.set("Module fehlgeschlagen"))
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Module fehlen",
                        "Die Erkennungsmodule konnten nicht geladen werden.\n\n"
                        "Oft hilft: „Fotobuch starten.bat“ erneut ausführen "
                        "(repariert eine unvollständige Installation).\n\n"
                        + (self._pipeline_error or "")[-1500:],
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_pipeline(self):
        if self._pipeline_error:
            raise RuntimeError(
                "Erkennungsmodule konnten nicht geladen werden.\n"
                + self._pipeline_error[-1200:]
            )
        from .pipeline import PipelineCancelled, PipelineConfig, run_pipeline

        self._pipeline_ready = True
        return PipelineCancelled, PipelineConfig, run_pipeline

    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="Fotos-Ordner wählen")
        if path:
            self.input_var.set(path)
            self._update_found_count(path)

    def _update_found_count(self, path: str) -> None:
        """Zeigt sofort, wie viele Bilder im Ordner liegen (Zielanzahl realistisch setzen)."""
        self.found_var.set(t("found_counting"))

        def worker() -> None:
            try:
                from .scan import find_images

                n = len(find_images(Path(path)))
                msg = t("found_photos", n=n) if n else t("found_none")
            except Exception:
                n = 0
                msg = ""
            self.after(0, lambda: self._set_found_count(n, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _set_found_count(self, n: int, msg: str) -> None:
        self._found_count = int(n or 0)
        self.found_var.set(msg)
        self._refresh_cost_estimate()

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Ausgabe-Ordner wählen")
        if path:
            self.output_var.set(path)

    def _refresh_cost_estimate(self, *_args) -> None:
        """Dauerhafte KI-Kostenschätzung + Vergleich zum letzten gemessenen Lauf."""
        try:
            from .ai_review import (
                ESTIMATED_COST_PER_IMAGE_USD,
                estimate_candidate_count,
                estimate_cost,
            )

            provider = self._selected_ai_provider()
            if provider == "none":
                self.cost_var.set("KI: aus (nur lokale Heuristik, $0)")
                return
            try:
                target = int(self.target_var.get())
            except (TypeError, ValueError, tk.TclError):
                target = 80
            n_cand = estimate_candidate_count(
                target, self._found_count, self._candidate_factor
            )
            est = estimate_cost(n_cand, provider=provider)
            if provider == "gemini":
                line = (
                    f"KI: Gemini Free Tier · ca. {int(est['candidates'])} Kandidaten · "
                    f"$0 (Limit ~1500/Tag)"
                )
            elif provider == "ollama":
                line = (
                    f"KI: Ollama lokal · ca. {int(est['candidates'])} Kandidaten · $0"
                )
            else:
                line = (
                    f"KI-Schätzung: ~${est['usd_total_estimate']:.2f} "
                    f"(ca. {int(est['candidates'])} Kandidaten × "
                    f"${ESTIMATED_COST_PER_IMAGE_USD:.3f})"
                )
            if self._last_ai_cost:
                last_n = int(self._last_ai_cost.get("candidates") or 0)
                last_usd = float(self._last_ai_cost.get("usd_total_estimate") or 0)
                kind = "Dry-Run" if self._last_ai_cost.get("dry_run") else "letzter Lauf"
                line += f"  ·  Vergleich ({kind}): ${last_usd:.2f} bei {last_n} Bildern"
            self.cost_var.set(line)
        except Exception:
            self.cost_var.set("KI-Schätzung: –")

    def _remember_ai_cost(self, result: dict) -> None:
        ai = result.get("ai") or {}
        if not ai:
            return
        if "usd_total_estimate" not in ai and "candidates" not in ai:
            return
        self._last_ai_cost = {
            "candidates": float(ai.get("candidates") or 0),
            "usd_total_estimate": float(ai.get("usd_total_estimate") or 0),
            "dry_run": bool(result.get("dry_run") or ai.get("dry_run")),
        }
        self._refresh_cost_estimate()

    def _show_text_window(self, title: str, body: str) -> None:
        from .window_layout import place_window

        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        win.configure(bg=COLORS["bg"])
        place_window(
            win,
            width=560,
            height=560,
            min_width=480,
            min_height=420,
            frac_w=0.45,
            frac_h=0.7,
        )
        frm = ttk.Frame(win, style="App.TFrame", padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(
            frm,
            wrap=tk.WORD,
            height=22,
            bg=COLORS["surface"],
            fg=COLORS["ink"],
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            padx=10,
            pady=10,
        )
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frm, command=txt.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        txt.configure(yscrollcommand=scroll.set)
        txt.insert("1.0", body)
        txt.configure(state=tk.DISABLED)
        ttk.Button(win, text=t("close"), command=win.destroy).pack(pady=(0, 10))

    def _show_help(self) -> None:
        self._show_text_window(t("help_title"), t("help_body"))

    def _set_next_step(self, text: str) -> None:
        self.next_step_var.set(text)

    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self.advanced_frame.pack(fill=tk.X, pady=(6, 0))
            self.advanced_toggle.configure(text=t("more_options_open"))
            self._sync_dependent_controls()
        else:
            self.advanced_frame.pack_forget()
            self.advanced_toggle.configure(text=t("more_options"))

    def _build_phase_chips(self) -> None:
        for child in self._phase_inner.winfo_children():
            child.destroy()
        self._phase_labels.clear()
        cols = 8
        for i, step in enumerate(PHASE_STEPS):
            status = self._phase_status.get(step.id, "pending")
            bg_key, fg_key = PHASE_STYLE.get(status, PHASE_STYLE["pending"])
            lbl = tk.Label(
                self._phase_inner,
                text=step.label,
                bg=COLORS[bg_key],
                fg=COLORS[fg_key],
                font=("Segoe UI", 8),
                padx=3,
                pady=2,
            )
            lbl.grid(row=i // cols, column=i % cols, padx=2, pady=2, sticky="ew")
            self._phase_labels[step.id] = lbl
        for c in range(cols):
            self._phase_inner.grid_columnconfigure(c, weight=1)

    def _reset_phase_board(self, cfg: Any) -> None:
        self._phase_status = initial_phase_status(cfg)
        self._build_phase_chips()

    def _paint_phase_chip(self, step_id: str) -> None:
        lbl = self._phase_labels.get(step_id)
        if lbl is None:
            return
        status = self._phase_status.get(step_id, "pending")
        bg_key, fg_key = PHASE_STYLE.get(status, PHASE_STYLE["pending"])
        try:
            lbl.configure(bg=COLORS[bg_key], fg=COLORS[fg_key])
        except tk.TclError:
            pass

    def _apply_phase_progress(self, label: str, step_id: str | None) -> None:
        """Orange = aktueller Schritt, Grün = bereits erledigt."""
        sid = step_id or match_step_id(label)
        if not sid:
            return
        if sid == "done" or (label or "").lower().startswith("fertig"):
            is_dry = "dry" in (label or "").lower()
            for step in PHASE_STEPS:
                st = self._phase_status.get(step.id)
                if st == "running":
                    self._phase_status[step.id] = "done"
                elif st == "pending":
                    # Dry-Run: Rest übersprungen. Normaler Lauf: fehlende
                    # Fortschritts-Events trotzdem als erledigt zählen.
                    self._phase_status[step.id] = "skipped" if is_dry else "done"
                self._paint_phase_chip(step.id)
            return

        seen = False
        for step in PHASE_STEPS:
            cur = self._phase_status.get(step.id, "pending")
            if step.id == sid:
                seen = True
                if cur == "skipped":
                    continue
                if cur != "done":
                    self._phase_status[step.id] = "running"
                    self._paint_phase_chip(step.id)
                continue
            if cur == "skipped":
                continue
            if not seen and cur in ("pending", "running"):
                self._phase_status[step.id] = "done"
                self._paint_phase_chip(step.id)

    def _append_log(self, text: str) -> None:
        """Feste Log-Zeile (bleibt stehen)."""
        self.log.configure(state=tk.NORMAL)
        if self._status_shown:
            self.log.delete(self._status_mark, tk.END)
            self._status_shown = False
        self.log.insert(tk.END, text + "\n")
        # Lange Läufe: altes Log kürzen, damit das Text-Widget nicht explodiert
        try:
            line_count = int(self.log.index("end-1c").split(".")[0])
            if line_count > 400:
                self.log.delete("1.0", f"{line_count - 300}.0")
        except tk.TclError:
            pass
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _append_status(self, text: str) -> None:
        """Eine ersetzbare Fortschrittszeile – kein Flood mit tausenden Zeilen."""
        self.log.configure(state=tk.NORMAL)
        if self._status_shown:
            self.log.delete(self._status_mark, tk.END)
        else:
            self.log.mark_set(self._status_mark, tk.END)
            self.log.mark_gravity(self._status_mark, tk.LEFT)
        self.log.insert(tk.END, text.rstrip() + "\n")
        self._status_shown = True
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_progress(self, label: str, frac: float, step_id: str | None = None) -> None:
        self.phase_var.set(label)
        self.progress["value"] = max(0, min(100, int(round(frac * 100))))
        self._apply_phase_progress(label, step_id)
        if label and label not in ("Fertig", "Abgebrochen", "Fehler") and not str(
            label
        ).lower().startswith("fertig"):
            self.status_var.set(label)
            self._set_next_step(
                f"Analyse läuft ({label}). Bitte warten – bei vielen Fotos dauert das."
            )

    def _drain_queues(self) -> None:
        """Holt Log/Progress; Fortschritt wird gebündelt (max. ~10×/s, nur letzter Stand)."""
        lines: list[str] = []
        try:
            while True:
                item = self._log_queue.get_nowait()
                if isinstance(item, tuple):
                    mode, text = item
                else:
                    mode, text = "line", str(item)
                mode = classify_console_chunk(str(text), mode)
                if mode == "status":
                    self._pending_status = str(text)
                else:
                    lines.append(str(text))
        except queue.Empty:
            pass

        # Backlog begrenzen, damit nach einem Freeze nicht 2000 Zeilen nachgerendert werden
        for text in lines[-80:]:
            self._append_log(text)

        now = time.monotonic()
        if self._pending_status is not None and (now - self._last_status_paint) >= 0.1:
            self._append_status(self._pending_status)
            self._pending_status = None
            self._last_status_paint = now

        latest: tuple[str, float, str | None] | None = None
        try:
            while True:
                item = self._progress_queue.get_nowait()
                if isinstance(item, tuple) and len(item) >= 2:
                    label = str(item[0])
                    frac = float(item[1])
                    step_id = item[2] if len(item) > 2 else None
                    latest = (label, frac, step_id)
        except queue.Empty:
            pass
        if latest is not None:
            self._set_progress(latest[0], latest[1], latest[2])

        self.after(100, self._drain_queues)

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Läuft bereits", "Bitte warten, die Verarbeitung läuft noch.")
            return

        input_dir = Path(self.input_var.get().strip())
        output_dir = Path(self.output_var.get().strip())
        if not input_dir.is_dir():
            messagebox.showerror("Eingabeordner fehlt", "Bitte einen vorhandenen Fotos-Ordner wählen.")
            return
        if not str(output_dir).strip():
            messagebox.showerror("Ausgabeordner fehlt", "Bitte einen Ausgabe-Ordner wählen.")
            return

        anthropic_key = self.api_key_var.get().strip()
        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        gemini_key = self.gemini_key_var.get().strip()
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key

        ai_provider = self._selected_ai_provider()
        ai_on = ai_provider != "none"
        self.ai_var.set(ai_on)
        ai_model = None
        dry_run = bool(self.dry_run_var.get())
        if ai_on and ai_provider == "ollama":
            ai_model = (self.ollama_model_var.get() or "").strip() or None
            dry_run = False
            from .ai_review import check_ollama_available

            ok, msg = check_ollama_available()
            if not ok:
                messagebox.showerror("Ollama fehlt", msg)
                return
        elif ai_on and ai_provider == "gemini" and not dry_run:
            if not (gemini_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
                messagebox.showerror(
                    "Gemini API-Key fehlt",
                    "Für Gemini brauchst du einen kostenlosen API-Key "
                    "(Link neben dem Feld) oder „Nur Kosten schätzen“.",
                )
                return
        elif ai_on and ai_provider == "anthropic" and not dry_run:
            if not (anthropic_key or os.environ.get("ANTHROPIC_API_KEY")):
                messagebox.showerror(
                    "API-Key fehlt",
                    "Für Anthropic brauchst du einen API-Key,\n"
                    "oder wähle Gemini (Gratis) / Ollama / Keine KI.",
                )
                return

        coverage_intensity = 0.0
        if self.coverage_var.get():
            coverage_intensity = float(self.coverage_intensity_var.get())
        people_balance_intensity = 0.0
        if self.people_var.get():
            people_balance_intensity = float(self.people_intensity_var.get())

        map_preview = bool(self.map_preview_var.get())
        try:
            _cancelled, PipelineConfig, _run_pipeline = self._ensure_pipeline()
        except Exception as exc:
            messagebox.showerror("Module fehlen", str(exc))
            return

        cfg = PipelineConfig(
            input_dir=input_dir.resolve(),
            output_dir=output_dir.resolve(),
            target_n=int(self.target_var.get()),
            geocode=bool(self.geocode_var.get()),
            ai_review=ai_on,
            ai_provider=ai_provider,
            ai_model=ai_model,
            dry_run=dry_run,
            enable_faces=bool(self.faces_var.get()),
            enable_bursts=bool(self.bursts_var.get()),
            enable_document_aside=bool(self.aside_var.get()),
            enable_finger_filter=bool(self.finger_var.get()),
            enable_accidental_filter=bool(self.accidental_var.get()),
            enable_weak_night_filter=bool(self.weak_night_var.get()),
            enable_content_clusters=bool(self.content_var.get()),
            enable_local_aesthetic=bool(self.aesthetic_var.get()),
            enable_video_frames=bool(self.video_var.get()),
            timezone_offset_hours=float(self.timezone_offset_var.get() or 0.0),
            coverage_intensity=coverage_intensity,
            people_balance_intensity=people_balance_intensity,
            enable_map_preview=map_preview,
            skip_export=map_preview,  # Export erst nach Bestätigung in der Vorschau
        )

        self._cancel_event.clear()
        self.start_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.review_btn.configure(state=tk.DISABLED, style="Browse.TButton")
        self.map_btn.configure(state=tk.DISABLED)
        self.status_var.set("Arbeitet…")
        self.phase_var.set("Start…")
        self.progress["value"] = 0
        self._pending_status = None
        self._reset_phase_board(cfg)
        self._set_next_step(
            "Analyse läuft… Bei „Auswahl“ kann es einige Minuten still wirken "
            "(Vielfalt/OneDrive) – Fenster nicht schließen."
        )
        self._append_log("Start…")
        self._worker = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.is_alive():
            self._cancel_event.set()
            self.cancel_btn.configure(state=tk.DISABLED)
            self.status_var.set("Wird abgebrochen…")
            self.phase_var.set("Abbrechen… (stoppt nach dem aktuellen Schritt)")
            self._set_next_step("Abbruch angefordert – warte auf Ende des aktuellen Schritts…")
            self._append_log("Abbruch angefordert…")

    def _run(self, cfg: Any) -> None:
        def on_progress(label: str, frac: float, step_id: str | None = None) -> None:
            self._progress_queue.put((label, frac, step_id))

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = ConsoleQueueWriter(self._log_queue, old_out)  # type: ignore[assignment]
        sys.stderr = ConsoleQueueWriter(self._log_queue, old_err)  # type: ignore[assignment]
        try:
            PipelineCancelled, _, run_pipeline = self._ensure_pipeline()
            result = run_pipeline(
                cfg,
                progress=on_progress,
                cancel_check=self._cancel_event.is_set,
            )
            summary = {
                k: v
                for k, v in result.items()
                if k not in ("photo_objects", "plan", "order")
            }
            self._log_queue.put(f"Fertig: {summary}")
            self._log_queue.put(f"Ergebnisordner: {cfg.output_dir}")
            self._last_photos = result.get("photo_objects")
            self._last_plan = result.get("plan")
            self._last_order = result.get("order")
            self._last_output = result.get("output_dir") or cfg.output_dir
            self._progress_queue.put(("Fertig", 1.0, "done"))
            self.after(0, lambda: self.status_var.set("Fertig"))
            self.after(
                0,
                lambda: self._set_next_step(
                    "Fertig. Nächster Schritt: „Auswahl prüfen“ – Bilder rausnehmen "
                    "oder Alternativen hinzufügen."
                ),
            )
            self.after(0, lambda r=result: self._on_finished(r, cfg))
        except Exception as exc:
            from .pipeline import PipelineCancelled as _Cancelled

            if isinstance(exc, _Cancelled):
                self._log_queue.put("Abgebrochen – es wurden keine Ordner geschrieben.")
                self._progress_queue.put(("Abgebrochen", 0.0))
                self.after(0, lambda: self.status_var.set("Abgebrochen"))
                self.after(
                    0,
                    lambda: self._set_next_step(
                        "Abgebrochen. Du kannst die Optionen anpassen und erneut starten."
                    ),
                )
            else:
                self._log_queue.put(f"Fehler: {exc}")
                self._progress_queue.put(("Fehler", 0.0))
                self.after(0, lambda: self.status_var.set("Fehler"))
                self.after(
                    0,
                    lambda: self._set_next_step(
                        "Fehler aufgetreten – siehe Verlauf. Danach erneut versuchen."
                    ),
                )
                self.after(0, lambda: messagebox.showerror("Fehler", str(exc)))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.after(0, lambda: self.start_btn.configure(state=tk.NORMAL))
            self.after(0, lambda: self.cancel_btn.configure(state=tk.DISABLED))
            # Nächster sinnvoller Schritt: „Auswahl prüfen“ optisch hervorheben
            self.after(
                0,
                lambda: self.review_btn.configure(
                    state=tk.NORMAL, style="Start.TButton"
                ),
            )
            self.after(0, lambda: self.map_btn.configure(state=tk.NORMAL))

    def _on_finished(self, result: dict, cfg: Any) -> None:
        self._remember_ai_cost(result)
        if result.get("dry_run"):
            ai = result.get("ai") or {}
            usd = float(ai.get("usd_total_estimate") or 0)
            n = int(ai.get("candidates") or 0)
            self._set_next_step(
                f"Kostenschätzung fertig (~${usd:.2f} / {n} Kandidaten). "
                "Für echten Lauf „Nur Kosten schätzen“ aus und erneut starten."
            )
            messagebox.showinfo(
                "Dry-Run",
                f"Kostenschätzung fertig:\n\n"
                f"~ ${usd:.2f} für {n} Kandidatenbilder.\n\n"
                "Der Betrag bleibt unter der Zielanzahl sichtbar zum Vergleichen.\n"
                "Für den echten Lauf: „Nur Kosten schätzen“ aus → erneut starten.",
            )
            return

        if cfg.enable_map_preview and not result.get("exported"):
            from .map_preview import open_map_preview

            self._set_next_step(
                "Nächster Schritt: Kapitel-/Karten-Vorschau bestätigen, danach „Auswahl prüfen“."
            )
            open_map_preview(
                self,
                result.get("photo_objects") or [],
                result.get("plan"),
                cfg.output_dir,
                order=result.get("order"),
                await_export=True,
                on_confirm=lambda: self._confirm_export_after_preview(result, cfg),
                on_cancel=lambda: self._cancel_export_after_preview(cfg),
            )
            return

        self._set_next_step(
            "Fertig. Nächster Schritt: „Auswahl prüfen“ klicken (oder im Dialog bestätigen)."
        )
        self._ask_open_review(cfg)

    def _confirm_export_after_preview(self, result: dict, cfg: PipelineConfig) -> None:
        from .pipeline import export_book_outputs

        photos = result.get("photo_objects") or self._last_photos
        plan = result.get("plan") or self._last_plan
        order = result.get("order") or self._last_order
        if photos is None or plan is None or order is None:
            messagebox.showerror("Export", "Keine Auswahl zum Exportieren vorhanden.")
            return
        try:
            export_book_outputs(
                photos,
                plan,
                order,
                cfg.output_dir,
                write_map=True,
            )
            self._append_log(f"Export fertig: {cfg.output_dir}")
            self.status_var.set("Exportiert")
        except Exception as exc:
            messagebox.showerror("Export", str(exc))
            return
        self._ask_open_review(cfg)

    def _cancel_export_after_preview(self, cfg: PipelineConfig) -> None:
        self._append_log("Export abgebrochen (Kapitel-Vorschau).")
        self.status_var.set("Export abgebrochen")
        messagebox.showinfo(
            "Abgebrochen",
            "Es wurden keine Ordner kopiert.\n"
            f"Analyse-CSV liegt ggf. unter:\n{cfg.output_dir / 'photos_analysis.csv'}",
        )

    def _ask_open_review(self, cfg: PipelineConfig) -> None:
        self._set_next_step(
            "Nächster Schritt: „Auswahl prüfen“ – Thumbnails durchgehen, dann speichern."
        )
        open_review = messagebox.askyesno(
            "Fertig – nächster Schritt",
            f"Auswahl erstellt in:\n{cfg.output_dir}\n\n"
            "Nächster Schritt: Auswahl prüfen.\n"
            "Bilder als Vorschau ansehen und einzelne rausnehmen oder hinzufügen?",
        )
        if open_review:
            self._open_review()
        else:
            self._set_next_step(
                "Auswahl liegt bereit. Später „Auswahl prüfen“ klicken "
                "(braucht photos_analysis.csv im Ausgabeordner)."
            )

    def _open_map_preview(self) -> None:
        from .map_preview import open_map_preview
        from .review_export import load_photos_from_csv, plan_from_photos

        photos = self._last_photos
        plan = self._last_plan
        order = self._last_order
        output_dir = self._last_output

        if photos is None or plan is None:
            out = Path(self.output_var.get().strip() or "")
            csv_path = out / "photos_analysis.csv"
            if not csv_path.is_file():
                messagebox.showinfo(
                    "Keine Auswahl",
                    "Bitte zuerst „Auswahl starten“, oder einen Ausgabeordner mit "
                    "photos_analysis.csv wählen.",
                )
                return
            try:
                photos = load_photos_from_csv(csv_path)
                plan = plan_from_photos(photos)
                output_dir = out
                self._last_photos = photos
                self._last_plan = plan
                self._last_output = output_dir
            except Exception as exc:
                messagebox.showerror("Laden fehlgeschlagen", str(exc))
                return

        open_map_preview(
            self,
            photos,
            plan,
            Path(output_dir),
            order=order,
            await_export=False,
        )

    def _open_review(self) -> None:
        from .review_export import (
            analysis_has_ai_scores,
            load_photos_from_csv,
            plan_from_photos,
            rebuild_selection_from_analysis,
        )
        from .review_gui import open_review
        from .selection_draft import draft_exists
        from .output import write_csv

        if self._is_analysis_running():
            messagebox.showinfo(
                "Noch nicht fertig",
                "Die Analyse läuft noch (gerade oft die Auswahl/Vielfalt).\n"
                "Bitte warten, bis „Fertig“ erscheint – dann erst prüfen.\n\n"
                "Tipp: Bei OneDrive kann dieser Schritt mehrere Minuten "
                "ohne großen Fortschritt wirken, arbeitet aber weiter.",
                parent=self,
            )
            return

        photos = self._last_photos
        plan = self._last_plan
        output_dir = self._last_output

        out = Path(self.output_var.get().strip() or (output_dir or ""))
        csv_path = out / "photos_analysis.csv"

        # Immer bevorzugt frische CSV laden (enthält KI-Scores / Zwischenstand)
        if csv_path.is_file():
            try:
                photos = load_photos_from_csv(csv_path)
                plan = plan_from_photos(photos)
                output_dir = out
                self._last_photos = photos
                self._last_plan = plan
                self._last_output = output_dir
            except Exception as exc:
                messagebox.showerror("Laden fehlgeschlagen", str(exc))
                return
        elif photos is None or plan is None or output_dir is None:
            messagebox.showinfo(
                "Keine Analyse",
                "Kein Ausgabeordner mit photos_analysis.csv.\n\n"
                "Nach einem (auch abgebrochenen) Lauf mit KI liegt die Analyse "
                "dort – ohne neue KI-Kosten fortsetzbar.",
            )
            return

        output_dir = Path(output_dir)
        has_selected = any(p.is_selected for p in photos)
        has_draft = draft_exists(output_dir)
        has_ai = analysis_has_ai_scores(photos)
        has_candidates = any(p.is_candidate for p in photos)
        has_analysis = len(photos) > 0

        if not has_selected and not has_draft:
            if has_analysis:
                msg = (
                    "Es gibt eine Analyse-CSV, aber noch keine finale Auswahl.\n\n"
                )
                if has_ai:
                    msg += "KI-Bewertungen sind bereits gespeichert – keine neue KI nötig.\n\n"
                elif has_candidates:
                    msg += "Technische Analyse ist vorhanden – Auswahl ohne KI möglich.\n\n"
                else:
                    msg += (
                        "Technische Analyse ist vorhanden (auch ohne GPS/KI).\n"
                        "Es wird ein Album-Kapitel erzeugt.\n\n"
                    )
                msg += (
                    "Auswahl jetzt aus der Analyse erzeugen (ohne KI-Kosten) "
                    "und danach prüfen?"
                )
                if not messagebox.askyesno("Auswahl aus Analyse", msg, parent=self):
                    return
                try:
                    target = int(self.target_var.get())
                except (TypeError, ValueError, tk.TclError):
                    target = 80
                try:
                    self.status_var.set("Erzeuge Auswahl aus Analyse…")
                    self.update_idletasks()
                    coverage = (
                        float(self.coverage_intensity_var.get())
                        if self.coverage_var.get()
                        else 0.0
                    )
                    people = (
                        float(self.people_intensity_var.get())
                        if self.people_var.get()
                        else 0.0
                    )
                    plan, order = rebuild_selection_from_analysis(
                        photos,
                        target,
                        coverage_intensity=coverage,
                        people_balance_intensity=people,
                    )
                    write_csv(photos, output_dir / "photos_analysis.csv")
                    self._last_photos = photos
                    self._last_plan = plan
                    self._last_order = order
                    self._last_output = output_dir
                    self.status_var.set(f"Auswahl erzeugt ({len(order)} Bilder)")
                except Exception as exc:
                    messagebox.showerror("Auswahl erzeugen fehlgeschlagen", str(exc))
                    return
            else:
                messagebox.showinfo(
                    "Keine Auswahl",
                    "In diesem Ordner sind weder ausgewählte Bilder noch ein "
                    "Auswahl-Entwurf vorhanden.\n\n"
                    "Bitte zuerst „Auswahl starten“ (KI ist optional – "
                    "ohne GPS wird ein Album-Kapitel gebaut).",
                )
                return
        elif has_draft and not has_selected:
            messagebox.showinfo(
                "Entwurf gefunden",
                "Es gibt einen gespeicherten Auswahl-Entwurf "
                "(selection_draft.json).\n"
                "Er wird jetzt geladen – ohne neue Analyse/KI.",
                parent=self,
            )

        win = open_review(
            self,
            photos,
            plan,
            Path(output_dir),
            on_saved=lambda: self.status_var.set("Auswahl gespeichert"),
        )

        def _restore_wheel(event, w=win) -> None:
            if event.widget is w:
                try:
                    self._install_body_wheel()
                except Exception:
                    pass

        try:
            win.bind("<Destroy>", _restore_wheel, add="+")
        except tk.TclError:
            pass


def _report_startup_error() -> None:
    """Zeigt einen Startfehler als Dialog und schreibt ihn in eine Datei."""
    import traceback

    err = traceback.format_exc()
    try:
        log = Path(__file__).resolve().parent.parent / "fehler_beim_start.txt"
        log.write_text(err, encoding="utf-8")
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Fotobuch – Startfehler",
            "Das Programm konnte nicht starten:\n\n"
            + err
            + "\n\n(Diese Meldung steht auch in der Datei 'fehler_beim_start.txt'.)",
        )
        root.destroy()
    except Exception:
        print(err)


def main() -> int:
    try:
        from .utils import ensure_utf8_stdio

        ensure_utf8_stdio()
    except Exception:
        pass
    try:
        app = PhotobookApp()
    except Exception:
        _report_startup_error()
        return 1

    # Sofort sichtbar machen (manche Windows-Setups legen das Fenster hinten an)
    try:
        app.lift()
        app.attributes("-topmost", True)
        app.after(400, lambda: app.attributes("-topmost", False))
        app.focus_force()
    except tk.TclError:
        pass

    app.mainloop()
    return 0 if getattr(app, "_init_ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
