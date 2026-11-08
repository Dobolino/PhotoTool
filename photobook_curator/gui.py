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
from tkinter import font as tkfont
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

FONT_UI = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

PHASE_STYLE = {
    "pending": ("phase_pending_bg", "phase_pending_fg"),
    "running": ("phase_run_bg", "phase_run_fg"),
    "done": ("phase_done_bg", "phase_done_fg"),
    "skipped": ("phase_skip_bg", "phase_skip_fg"),
}

# Some Tk/X11 font backends render the ellipsis as legacy bytes. Plain dots are
# portable in controls and preserve the original strings in the translation data.
_translated_text = t


def t(key: str, **kwargs: Any) -> str:
    return _translated_text(key, **kwargs).replace("…", "...")

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
            frac_w=0.90,
            frac_h=0.90,
            min_width=900,
            min_height=660,
            width=1180,
            height=800,
        )
        self._boot_lbl = tk.Label(
            self,
            text="Fotobuch wird geladen…",
            bg=_FALLBACK_COLORS["bg"],
            fg=_FALLBACK_COLORS["ink"],
            font=(FONT_UI, 13),
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
                frac_w=0.90,
                frac_h=0.90,
                min_width=900,
                min_height=660,
                width=1180,
                height=800,
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
        self._log_open = False
        self._responsive_wide: bool | None = None
        self._current_project = None
        self._loaded_config_settings: dict = {}
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
        self.max_per_day_var = tk.StringVar(value=str(getattr(self.app_settings, "max_per_day", 0)))
        self.max_per_chapter_var = tk.StringVar(value=str(getattr(self.app_settings, "max_per_chapter", 0)))
        self.people_var = tk.BooleanVar(value=False)
        self.people_intensity_var = tk.DoubleVar(value=0.5)
        self.book_pages_var = tk.StringVar(value="0")
        self.photos_per_page_var = tk.StringVar(value="2.5")
        self.reserved_pages_var = tk.StringVar(value="4")
        self.storytelling_var = tk.DoubleVar(value=0.5)
        self.profile_var = tk.StringVar(value="balanced")
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
        self._ui_queue: queue.Queue = queue.Queue()
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
            font=(FONT_UI, 12, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X)
        tk.Label(
            box,
            text="Details stehen in fehler_beim_start.txt und start_log.txt",
            bg=c["bg"],
            fg=c["muted"],
            font=(FONT_UI, 10),
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
        try:
            self._save_open_reviews()
        except OSError as exc:
            messagebox.showerror(t("project_save_failed"), str(exc), parent=self)
            return
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
        global FONT_UI
        available = {family.casefold(): family for family in tkfont.families(self)}
        FONT_UI = next(
            (available[name.casefold()] for name in
             (FONT_UI, "Segoe UI", "DejaVu Sans", "Nimbus Sans L", "Helvetica")
             if name.casefold() in available),
            tkfont.nametofont("TkDefaultFont").actual("family"),
        )
        self._font_family = FONT_UI
        from . import ui_widgets
        ui_widgets.FONT_UI = FONT_UI
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family=FONT_UI, size=12)
        self.option_add("*Font", (FONT_UI, 12))
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        font_ui = (FONT_UI, 12)
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
            font=(FONT_UI, 9, "bold"),
        )
        style.configure(
            "Title.TLabel",
            background=c["bg"],
            foreground=c["ink"],
            font=(FONT_UI, 20, "bold"),
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
            font=(FONT_UI, 12),
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
            font=(FONT_UI, 22, "bold"),
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
            font=(FONT_UI, 12, "bold"),
            padding=(20, 12),
            background=c.get("cta", c["accent"]),
            foreground=c.get("cta_ink", c.get("hero_fg", "#FFFFFF")),
        )
        style.map(
            "Start.TButton",
            background=[("active", c.get("cta_hover", c["accent_hover"])), ("disabled", c["line"])],
            foreground=[("disabled", c["muted"]), ("active", c.get("cta_ink", c.get("hero_fg", "#FFFFFF")))],
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
            self.option_add("*TCombobox*Listbox.selectForeground", c.get("on_accent", c.get("hero_fg", "#FFFFFF")))
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
            font=(FONT_UI, 12, "bold"),
        )
        style.configure(
            "Help.TButton",
            font=(FONT_UI, 12, "bold"),
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

        style.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=c["bg"], foreground=c["muted"],
                        lightcolor=c["bg"], bordercolor=c["line"])
        style.map("TNotebook.Tab", background=[("selected", c["surface"]), ("active", c["chip_bg"])],
                  foreground=[("selected", c["ink"]), ("active", c["ink"])])
        style.configure("TNotebook.Tab", font=(FONT_UI, 12, "bold"), padding=(20, 12))
        style.configure("Analysis.Horizontal.TProgressbar", thickness=24)
        for button_style in ("Browse.TButton", "Start.TButton"):
            border = c.get("cta", c["accent"]) if button_style == "Start.TButton" else c["line"]
            style.configure(button_style, relief="flat", borderwidth=1,
                            bordercolor=border, lightcolor=border, darkcolor=border,
                            focuscolor=c["accent"])
        style.map("Browse.TButton", bordercolor=[("focus", c["accent"]), ("active", c["accent"]), ("disabled", c["line"])])
        for widget_style in ("TEntry", "TCombobox", "AI.TCombobox", "TSpinbox"):
            style.configure(widget_style, font=(FONT_UI, 12), lightcolor=c["line"], darkcolor=c["line"])

    def _build(self) -> None:
        from .main_workspace import build_workspace
        self._translate = t
        build_workspace(self, COLORS, t)

    def _mark_profile_custom(self, *_args) -> None:
        if getattr(self, "_applying_profile", False):
            return
        self.profile_var.set("custom")
        for n, (profile_id, _label) in enumerate(self._profile_choices):
            if profile_id == "custom":
                self._profile_combo.current(n)
                break

    def _sync_project_actions(self, *_args) -> None:
        output = self.output_var.get().strip()
        available = bool(output and (Path(output) / "photos_analysis.csv").is_file())
        state = tk.NORMAL if available and not self._is_analysis_running() else tk.DISABLED
        for button in (self.review_btn, self.map_btn, self._relink_btn):
            button.configure(state=state)

    def _toggle_log(self) -> None:
        self._log_open = not self._log_open
        if self._log_open:
            self._log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        else:
            self._log_frame.pack_forget()
        self._details_toggle.configure(text=t("hide_details" if self._log_open else "show_details"))

    def _refresh_page_budget(self, *_args) -> None:
        try:
            pages = int(self.book_pages_var.get())
            if pages == 0:
                self._budget_hint_var.set(t("budget_manual_hint"))
                self._target_spin.state(["!disabled"])
                return
            from .story_budget import calculate_book_budget
            budget = calculate_book_budget(pages, float(self.photos_per_page_var.get()),
                                           int(self.reserved_pages_var.get()))
            self.target_var.set(budget.target_count)
            self._target_spin.state(["disabled"])
            self._budget_hint_var.set(t("budget_calculated", n=budget.target_count,
                                        pages=budget.photo_pages))
        except (ValueError, TypeError, tk.TclError):
            self._budget_hint_var.set(t("budget_invalid"))

    def _open_project_manager(self) -> None:
        if self._is_analysis_running():
            messagebox.showinfo(t("project_open"), t("project_wait"), parent=self)
            return
        from .project_dialog import show_project_manager
        show_project_manager(self, COLORS, on_open=self._load_project_into_form,
                             current_input=self.input_var.get(), current_output=self.output_var.get(),
                             language=getattr(self.app_settings, "language", "de"))

    def _save_open_reviews(self) -> None:
        """A failed autosave must keep the current project and its windows intact."""
        for child in list(self.winfo_children()):
            save = getattr(child, "_autosave_draft", None)
            if save is not None:
                save()
                error = getattr(child, "_draft_save_error", None)
                if error:
                    raise OSError(str(error))

    def _apply_selected_profile(self, _event=None) -> None:
        from .travel_profiles import get_profile
        position = self._profile_combo.current()
        if position < 0:
            return
        profile_id = self._profile_choices[position][0]
        self.profile_var.set(profile_id)
        self._apply_config_settings(get_profile(profile_id).settings)

    def _apply_config_settings(self, settings: dict) -> None:
        was_applying = getattr(self, "_applying_profile", False)
        self._applying_profile = True
        try:
            self._loaded_config_settings.update(settings)
            mapping = {
                "target_n": "target_var", "geocode": "geocode_var", "enable_faces": "faces_var",
                "enable_bursts": "bursts_var", "enable_document_aside": "aside_var",
                "enable_finger_filter": "finger_var", "enable_accidental_filter": "accidental_var",
                "enable_weak_night_filter": "weak_night_var", "enable_content_clusters": "content_var",
                "enable_local_aesthetic": "aesthetic_var", "enable_video_frames": "video_var",
                "timezone_offset_hours": "timezone_offset_var", "max_per_day": "max_per_day_var",
                "max_per_chapter": "max_per_chapter_var", "book_pages": "book_pages_var",
                "photos_per_page": "photos_per_page_var", "reserved_pages": "reserved_pages_var",
                "storytelling_intensity": "storytelling_var", "enable_map_preview": "map_preview_var",
                "ai_provider": "ai_provider_var", "dry_run": "dry_run_var",
            }
            for key, name in mapping.items():
                if key in settings:
                    getattr(self, name).set(settings[key])
            if settings.get("ai_provider") == "ollama":
                self.ollama_model_var.set(settings.get("ai_model") or "llava")
            for key, enabled_name, intensity_name in (
                ("coverage_intensity", "coverage_var", "coverage_intensity_var"),
                ("people_balance_intensity", "people_var", "people_intensity_var"),
            ):
                if key in settings:
                    value = float(settings[key])
                    getattr(self, enabled_name).set(value > 0)
                    if value > 0:
                        getattr(self, intensity_name).set(value)
            self._sync_ai_provider_combo_display()
            self._sync_dependent_controls()
            self._refresh_page_budget()
            self._refresh_cost_estimate()
        finally:
            self._applying_profile = was_applying

    def _load_project_into_form(self, project) -> bool:
        try:
            self._save_open_reviews()
        except OSError as exc:
            messagebox.showerror(t("project_save_failed"), str(exc), parent=self)
            return False
        self._current_project = project
        self._loaded_config_settings = {}
        self._last_ai_cost = None
        self.input_var.set(str(project.input_dir))
        self.output_var.set(str(project.output_dir))
        self.profile_var.set(project.profile_id)
        self._apply_config_settings(project.settings)
        for n, (profile_id, _label) in enumerate(self._profile_choices):
            if profile_id == project.profile_id:
                self._profile_combo.current(n)
                break
        self._project_name_var.set(project.name)
        self._last_photos = self._last_plan = self._last_order = self._last_output = None
        self._update_found_count(str(project.input_dir))
        self._set_next_step(t("project_loaded", name=project.name))
        return True

    def _open_source_relink(self) -> None:
        from .source_relink_dialog import open_source_relink
        from .review_export import load_photos_from_csv
        from .selection_draft import apply_selection_draft, load_selection_draft
        output_text = self.output_var.get().strip()
        if not output_text:
            messagebox.showinfo(t("relink_sources"), t("relink_need_project"), parent=self)
            return
        output_dir = Path(output_text)
        try:
            photos = self._last_photos
            if photos is None or self._last_output != output_dir:
                photos = load_photos_from_csv(output_dir / "photos_analysis.csv")
                draft = load_selection_draft(output_dir)
                if draft:
                    apply_selection_draft(photos, draft)

            def saved() -> None:
                from .projects import load_project
                from .review_export import plan_from_photos
                self._last_photos = photos
                self._last_plan = plan_from_photos(photos)
                self._last_order = None
                self._last_output = output_dir
                if (output_dir / "phototool_project.json").is_file():
                    project = load_project(output_dir, remember=False)
                    self._current_project = project
                    self.input_var.set(str(project.input_dir))
                    self._update_found_count(str(project.input_dir))
                self._set_next_step(t("sources_relinked"))

            open_source_relink(self, photos, output_dir, on_saved=saved)
        except (OSError, ValueError) as exc:
            messagebox.showerror(t("relink_sources"), str(exc), parent=self)

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
        from .main_workspace import text
        return [
            ("none", text(self, "Lokale Auswahl (kostenlos)", "Local selection (free)")),
            ("gemini", "Google Gemini"),
            ("anthropic", "Anthropic Claude"),
            ("ollama", text(self, "Ollama auf diesem Gerät", "Ollama on this device")),
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
        self._refresh_run_summary()
        if not hasattr(self, "api_entry"):
            return
        provider = self._selected_ai_provider()
        self.ai_var.set(provider != "none")
        self.coverage_scale.state(["!disabled"] if self.coverage_var.get() else ["disabled"])
        self.people_scale.state(["!disabled"] if self.people_var.get() else ["disabled"])
        self._key_row.pack_forget()
        self.api_entry.pack_forget()
        self._ollama_hint_lbl.pack_forget()
        self._ollama_lbl_row.pack_forget()
        self.ollama_model_combo.pack_forget()
        self._dry_row.pack_forget()
        if provider in ("gemini", "anthropic"):
            self._key_row.pack(fill=tk.X, pady=(12, 0))
            self.api_entry.pack(fill=tk.X, pady=(6, 0))
            self._bind_active_api_entry()
        elif provider == "ollama":
            self._ollama_hint_lbl.pack(fill=tk.X, pady=(12, 0))
            self._ollama_lbl_row.pack(fill=tk.X, pady=(12, 0))
            self.ollama_model_combo.pack(fill=tk.X, pady=(6, 0))
        self._dry_row.pack(fill=tk.X, pady=(18, 0))
        self.ai_blurb_var.set(self._mode_description_var.get())

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
        from .main_workspace import refresh_texts
        refresh_texts(self)
        from .travel_profiles import profile_choices
        self._profile_choices = profile_choices(self.app_settings.language)
        self._profile_combo.configure(values=[name for _, name in self._profile_choices])
        for n, (profile_id, _label) in enumerate(self._profile_choices):
            if profile_id == self.profile_var.get():
                self._profile_combo.current(n)
                break
        self._sync_ai_provider_combo_display()
        self._refresh_page_budget()
        self._refresh_run_summary()

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
                self._post_ui(self._backend_loaded)
            except Exception:
                self._pipeline_error = traceback.format_exc()
                self._post_ui(self._backend_load_failed)

        self._warmup_worker = threading.Thread(target=worker, daemon=True)
        self._warmup_worker.start()

    def _post_ui(self, callback) -> None:
        """Workers enqueue callbacks; only the main poll touches the Tk runtime."""
        self._ui_queue.put(callback)

    def _backend_loaded(self) -> None:
        if not self._is_analysis_running():
            self.status_var.set("Bereit")
        self._append_log("Erkennungsmodule geladen.")

    def _backend_load_failed(self) -> None:
        self.status_var.set("Module fehlgeschlagen")
        messagebox.showerror(
            "Module fehlen",
            "Die Erkennungsmodule konnten nicht geladen werden.\n\n"
            "Oft hilft: „Fotobuch starten.bat“ erneut ausführen "
            "(repariert eine unvollständige Installation).\n\n"
            + (self._pipeline_error or "")[-1500:],
            parent=self,
        )

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
        output = self.output_var.get().strip()
        excluded = [Path(output)] if output else []
        generation = getattr(self, "_count_generation", 0) + 1
        self._count_generation = generation

        def worker() -> None:
            try:
                from .scan import find_images

                n = len(find_images(Path(path), exclude_dirs=excluded))
                msg = t("found_photos", n=n) if n else t("found_none")
            except Exception:
                n = 0
                msg = ""
            def show_count() -> None:
                if self._count_generation == generation:
                    self._set_found_count(n, msg)
            self._post_ui(show_count)

        threading.Thread(target=worker, daemon=True).start()

    def _set_found_count(self, n: int, msg: str) -> None:
        self._found_count = int(n or 0)
        self.found_var.set(msg)
        self._refresh_cost_estimate()

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Ausgabe-Ordner wählen")
        if path:
            self.output_var.set(path)
            if self.input_var.get().strip():
                self._update_found_count(self.input_var.get().strip())

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
            font=(FONT_UI, 10),
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
        self._open_selection_settings("quality")

    def _open_selection_settings(self, section: str = "quality") -> None:
        if self._is_analysis_running():
            return
        from .main_workspace import open_settings_sheet
        open_settings_sheet(self, section)

    def _close_selection_settings(self) -> None:
        try:
            self._selection_caps()
            if int(self.book_pages_var.get()) > 0:
                from .story_budget import calculate_book_budget
                calculate_book_budget(int(self.book_pages_var.get()), float(self.photos_per_page_var.get()),
                                      int(self.reserved_pages_var.get()))
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror(t("album_invalid"), str(exc), parent=self._settings_sheet)
            return
        if self._settings_sheet is not None:
            self._settings_sheet.grab_release()
            self._settings_sheet.withdraw()
        self._advanced_open = False
        self._refresh_run_summary()

    def _refresh_run_summary(self, *_args) -> None:
        from .main_workspace import text
        if not hasattr(self, "_mode_title_var"):
            return
        for label, variable in self._location_labels:
            raw = variable.get().strip()
            label.configure(text=Path(raw).name if raw else text(self, "Noch nicht gewählt", "Not selected"))
        try:
            day, chapter = self._selection_caps()
            parts = []
            if day:
                parts.append(text(self, f"Bis zu {day} Fotos je Tag", f"Up to {day} photos per day"))
            if chapter:
                parts.append(text(self, f"{chapter} je Kapitel", f"{chapter} per chapter"))
            parts.append(text(self, "Favoriten bleiben geschützt", "Favorites stay protected"))
            self._selection_summary_var.set(" · ".join(parts))
        except (ValueError, tk.TclError):
            self._selection_summary_var.set(text(self, "Bildgrenzen in den Einstellungen prüfen.", "Check photo limits in settings."))
        provider = self._selected_ai_provider()
        names = {"gemini": "Google Gemini", "anthropic": "Anthropic Claude", "ollama": "Ollama"}
        dry = bool(self.dry_run_var.get())
        if dry:
            title = text(self, "Nur Kostenschätzung – keine fertige Auswahl", "Cost estimate only – no finished selection")
            if provider == "none":
                description = text(self, "Bitte KI-Anbieter wählen oder die Kostenschätzung ausschalten.", "Choose an AI provider or turn off cost estimation.")
            else:
                description = text(self, f"Anbieter: {names.get(provider, provider)}. Es werden Kandidaten gezählt und Kosten geschätzt. Keine KI-Bewertung und kein Album-Export.",
                                   f"Provider: {names.get(provider, provider)}. Candidates and costs are estimated. No AI review or album export.")
            action = text(self, "Kosten schätzen" if provider != "none" else "KI-Einstellungen prüfen", "Estimate cost" if provider != "none" else "Check AI settings")
        elif provider != "none":
            title = text(self, f"Zusätzlich mit KI · {names.get(provider, provider)}", f"Additional AI review · {names.get(provider, provider)}")
            description = text(self, "Zuerst lokal analysieren, dann nur Kandidaten mit KI bewerten. Gespeicherte lokale Ergebnisse werden wiederverwendet.",
                               "Analyze locally first, then review only shortlisted candidates with AI. Saved local results are reused.")
            action = text(self, "Auswahl mit KI erstellen", "Create selection with AI")
        else:
            title = text(self, "Lokale Auswahl · kostenlos und ohne KI", "Local selection · free and without AI")
            description = text(self, "Qualität, ähnliche Serien und Reisetage werden berücksichtigt. Danach prüfst du die Auswahl und kannst optional KI ergänzen.",
                               "Quality, similar bursts and travel days are considered. Review the selection afterwards and optionally add AI.")
            action = text(self, "Lokale Auswahl erstellen", "Create local selection")
        self._mode_title_var.set(title)
        self._mode_description_var.set(description)
        self._mode_label.configure(fg=COLORS["phase_run_bg"] if dry else COLORS["ink"])
        self._critical_run_mode = dry or provider != "none"
        if dry:
            footer_text = text(self, f"Nur Kostenschätzung · {names.get(provider, 'kein KI-Anbieter')}",
                               f"Cost estimate only · {names.get(provider, 'no AI provider')}")
        elif provider != "none":
            footer_text = text(self, f"Mit KI · {names.get(provider, provider)}", f"With AI · {names.get(provider, provider)}")
        else:
            footer_text = text(self, "Originale bleiben erhalten.", "Original photographs are preserved.")
        self._footer_hint.configure(text=footer_text, fg=COLORS["phase_run_bg"] if dry else COLORS["muted"])
        if not self._is_analysis_running():
            self.start_btn.configure(text=action)
        if hasattr(self, "_sheet_mode_var"):
            self._sheet_mode_var.set(title)
        if hasattr(self, "_layout_chrome"):
            self._layout_chrome(getattr(self, "_content_width", self.winfo_width() - 48))

    def _show_main_view(self, view: str = "setup") -> None:
        self._view_mode = view
        self._setup_view.pack_forget()
        self._analysis_view.pack_forget()
        for widget in (*self._selection_action_widgets, self.cancel_btn):
            widget.pack_forget()
        if view == "analysis":
            self._analysis_view.pack(fill=tk.X)
            self.cancel_btn.pack(side=tk.LEFT)
            self._analysis_mode_var.set(self._mode_title_var.get())
        else:
            self._setup_view.pack(fill=tk.X)
            self._footer_hint.pack(side=tk.LEFT, padx=(0, 28))
            self.review_btn.pack(side=tk.LEFT, padx=(0, 12))
            self.start_btn.pack(side=tk.LEFT)
        for widget in self._setup_controls:
            widget.configure(state=tk.DISABLED if view == "analysis" else tk.NORMAL)
        self._layout_chrome(getattr(self, "_content_width", self.winfo_width() - 48))
        self._body_canvas.yview_moveto(0)

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
                font=(FONT_UI, 8),
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
        percent = max(0, min(100, int(round(frac * 100))))
        self.progress["value"] = percent
        self._percent_var.set(f"{percent} %")
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

        for _ in range(40):
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                self.report_callback_exception(type(exc), exc, exc.__traceback__)

        self.after(100, self._drain_queues)

    def _selection_caps(self) -> tuple[int, int]:
        """Read strict nonnegative integers, including user-typed Spinbox text."""
        values = []
        for key, var in (
            ("max_per_day", self.max_per_day_var),
            ("max_per_chapter", self.max_per_chapter_var),
        ):
            try:
                raw = str(var.get()).strip()
                if not raw.isdecimal():
                    raise ValueError
                value = int(raw)
            except (ValueError, TypeError, tk.TclError):
                raise ValueError(f"{t(key)}: Bitte eine ganze Zahl ab 0 eingeben.") from None
            values.append(value)
        return values[0], values[1]

    def _save_selection_caps(self, max_per_day: int, max_per_chapter: int) -> None:
        from dataclasses import replace
        from .settings import save_settings

        settings = replace(
            load_settings(), max_per_day=max_per_day, max_per_chapter=max_per_chapter
        )
        save_settings(settings)
        self.app_settings = settings

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Läuft bereits", "Bitte warten, die Verarbeitung läuft noch.")
            return

        if self.dry_run_var.get() and self._selected_ai_provider() == "none":
            self._open_selection_settings("ai")
            return

        try:
            max_per_day, max_per_chapter = self._selection_caps()
        except ValueError as exc:
            messagebox.showerror("Ungültige Bildgrenze", str(exc), parent=self)
            return

        input_text = self.input_var.get().strip()
        output_text = self.output_var.get().strip()
        if not input_text:
            messagebox.showerror("Eingabeordner fehlt", "Bitte einen vorhandenen Fotos-Ordner wählen.")
            return
        if not output_text:
            messagebox.showerror("Ausgabeordner fehlt", "Bitte einen Ausgabe-Ordner wählen.")
            return
        input_dir = Path(input_text)
        output_dir = Path(output_text)
        if not input_dir.is_dir():
            messagebox.showerror("Eingabeordner fehlt", "Bitte einen vorhandenen Fotos-Ordner wählen.")
            return
        if input_dir.resolve() == output_dir.resolve():
            messagebox.showerror(
                "Ausgabeordner wählen",
                "Fotos und Ausgabe benötigen unterschiedliche Ordner.",
                parent=self,
            )
            return
        try:
            self._save_open_reviews()
        except OSError as exc:
            messagebox.showerror(t("project_save_failed"), str(exc), parent=self)
            return
        # A new analysis must not race a previous review's autosave into the
        # same project's CSV/draft. Other trip windows can remain open.
        for child in list(self.winfo_children()):
            review_output = getattr(child, "_modern_output_dir", getattr(child, "output_dir", None))
            if (review_output is not None and Path(review_output).resolve() == output_dir.resolve()
                    and callable(getattr(child, "_autosave_draft", None))):
                child._close()
                if child.winfo_exists():
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
        ai_model = (
            self._loaded_config_settings.get("ai_model")
            if self._loaded_config_settings.get("ai_provider") == ai_provider else None
        )
        dry_run = bool(self.dry_run_var.get())
        if ai_on and ai_provider == "ollama":
            ai_model = (self.ollama_model_var.get() or "").strip() or None
            if not dry_run:
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

        try:
            values = dict(
                input_dir=input_dir.resolve(),
                output_dir=output_dir.resolve(),
                target_n=int(self.target_var.get()),
                book_pages=int(self.book_pages_var.get()),
                photos_per_page=float(self.photos_per_page_var.get()),
                reserved_pages=int(self.reserved_pages_var.get()),
                storytelling_intensity=float(self.storytelling_var.get()),
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
                max_per_day=max_per_day,
                max_per_chapter=max_per_chapter,
                people_balance_intensity=people_balance_intensity,
                enable_map_preview=map_preview,
                skip_export=map_preview,  # Export erst nach Bestätigung in der Vorschau
            )
            from dataclasses import fields
            allowed = {field.name for field in fields(PipelineConfig)}
            values = {**self._loaded_config_settings, **values}
            cfg = PipelineConfig(**{key: value for key, value in values.items() if key in allowed})
            if cfg.book_pages < 0 or cfg.reserved_pages < 0:
                raise ValueError(t("budget_invalid"))
            if cfg.book_pages:
                from .story_budget import calculate_book_budget
                cfg.target_n = calculate_book_budget(cfg.book_pages, cfg.photos_per_page,
                                                    cfg.reserved_pages).target_count
            if cfg.target_n <= 0:
                raise ValueError(t("target_invalid"))
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror(t("album_invalid"), str(exc), parent=self)
            return

        try:
            self._save_selection_caps(max_per_day, max_per_chapter)
        except OSError as exc:
            messagebox.showwarning(
                "Einstellungen nicht gespeichert",
                f"Die Bildgrenzen gelten für diesen Lauf, konnten aber nicht gespeichert werden:\n{exc}",
                parent=self,
            )

        try:
            from .projects import project_from_config, save_project
            same_project = self._current_project and self._current_project.output_dir.resolve() == output_dir.resolve()
            name = self._current_project.name if same_project else input_dir.name
            project = project_from_config(cfg, name=name, profile_id=self.profile_var.get())
            save_project(project)
            self._current_project = project
            self._project_name_var.set(project.name)
        except (OSError, ValueError) as exc:
            messagebox.showerror(t("project_save_failed"), str(exc), parent=self)
            return

        self._cancel_event.clear()
        self._result_note_var.set("")
        self._show_main_view("analysis")
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
            self._post_ui(lambda: self.status_var.set("Fertig"))
            self._post_ui(
                lambda: self._set_next_step(
                    "Fertig. Nächster Schritt: „Auswahl prüfen“ – Bilder rausnehmen "
                    "oder Alternativen hinzufügen."
                ),
            )
            self._post_ui(lambda r=result: self._on_finished(r, cfg))
        except Exception as exc:
            from .pipeline import PipelineCancelled as _Cancelled

            if isinstance(exc, _Cancelled):
                self._log_queue.put("Abgebrochen – es wurden keine Ordner geschrieben.")
                self._progress_queue.put(("Abgebrochen", 0.0))
                self._post_ui(lambda: self.status_var.set("Abgebrochen"))
                self._post_ui(lambda: self._result_note_var.set("Analyse abgebrochen. Du kannst die Einstellungen anpassen und erneut starten."))
                self._post_ui(
                    lambda: self._set_next_step(
                        "Abgebrochen. Du kannst die Optionen anpassen und erneut starten."
                    ),
                )
            else:
                self._log_queue.put(f"Fehler: {exc}")
                self._progress_queue.put(("Fehler", 0.0))
                self._post_ui(lambda: self.status_var.set("Fehler"))
                self._post_ui(lambda: self._result_note_var.set("Die Analyse konnte nicht abgeschlossen werden. Details stehen im Fehlerdialog."))
                self._post_ui(
                    lambda: self._set_next_step(
                        "Fehler aufgetreten – siehe Verlauf. Danach erneut versuchen."
                    ),
                )
                self._post_ui(lambda error_text=str(exc): messagebox.showerror("Fehler", error_text))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self._post_ui(lambda: self.start_btn.configure(state=tk.NORMAL))
            self._post_ui(lambda: self.cancel_btn.configure(state=tk.DISABLED))
            # Nächster sinnvoller Schritt: „Auswahl prüfen“ optisch hervorheben
            self._post_ui(self._sync_project_actions)
            self._post_ui(lambda: self.review_btn.configure(style="Start.TButton"))

            self._post_ui(self._finish_analysis_view)

    def _on_finished(self, result: dict, cfg: Any) -> None:
        from .main_workspace import text
        self._remember_ai_cost(result)
        self._show_main_view("setup")
        if result.get("dry_run"):
            ai = result.get("ai") or {}
            usd = float(ai.get("usd_total_estimate") or 0)
            candidates = int(ai.get("candidates") or result.get("candidates") or 0)
            self._result_note_var.set(text(self,
                f"Schätzung: ca. ${usd:.2f} für {candidates} Kandidaten. Keine KI-Bewertung und keine fertige Auswahl erstellt.",
                f"Estimate: about ${usd:.2f} for {candidates} candidates. No AI review or finished selection was created."))
            return
        count = int(result.get("selected") or len(result.get("order") or []))
        self._result_note_var.set(text(self,
            f"{count} Fotos sind bereit. Prüfe deine Auswahl und exportiere dein Album.",
            f"{count} photos are ready. Review your selection and export your album."))
        if result.get("audit_warning"):
            self._result_note_var.set(self._result_note_var.get() + "\n" + result["audit_warning"])
        if cfg.enable_map_preview and not result.get("exported"):
            from .map_preview import open_map_preview
            open_map_preview(self, result.get("photo_objects") or [], result.get("plan"), cfg.output_dir,
                             order=result.get("order"), await_export=True,
                             on_confirm=lambda: self._confirm_export_after_preview(result, cfg),
                             on_cancel=lambda: self._cancel_export_after_preview(cfg))

    def _finish_analysis_view(self) -> None:
        self._worker = None
        self._show_main_view("setup")
        self.start_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        self._sync_project_actions()
        self._refresh_run_summary()
        self.review_btn.configure(style="Start.TButton")

    def _confirm_export_after_preview(self, result: dict, cfg: PipelineConfig) -> None:
        from .pipeline import export_book_outputs

        photos = result.get("photo_objects") or self._last_photos
        plan = result.get("plan") or self._last_plan
        order = result.get("order") or self._last_order
        if photos is None or plan is None or order is None:
            messagebox.showerror("Export", "Keine Auswahl zum Exportieren vorhanden.")
            return
        try:
            exported = export_book_outputs(
                photos,
                plan,
                order,
                cfg.output_dir,
                write_map=True,
            )
            self._append_log(f"Export fertig: {cfg.output_dir}")
            self.status_var.set("Exportiert")
            if exported.get("audit_warning"):
                messagebox.showwarning("Prüfbericht", exported["audit_warning"], parent=self)
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

    def _ask_open_review(self, cfg: Any) -> None:
        from .main_workspace import text
        self._show_main_view("setup")
        self._result_note_var.set(text(self, "Deine Auswahl ist bereit. Jetzt prüfen und das Album exportieren.",
                                       "Your selection is ready. Review it and export the album."))
        self._sync_project_actions()

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

    def _open_existing_review(self) -> None:
        folder = filedialog.askdirectory(title="Vorhandenen Ausgabeordner öffnen", parent=self)
        if not folder:
            return
        if not (Path(folder) / "photos_analysis.csv").is_file():
            messagebox.showinfo("Kein Ausgabeordner",
                "Bitte den Ordner mit photos_analysis.csv auswählen. Eine neue Analyse ist nicht nötig.",
                parent=self)
            return
        output_dir = Path(folder)
        try:
            if (output_dir / "phototool_project.json").is_file():
                from .projects import load_project
                if not self._load_project_into_form(load_project(output_dir)):
                    return
            else:
                # CSV-only albums predate project metadata. Never combine the
                # previous trip's source/settings with this album on next start.
                self._save_open_reviews()
                self._current_project = None
                self._loaded_config_settings = {}
                self.ai_provider_var.set("none")
                self.book_pages_var.set("0")
                self.input_var.set("")
                self._count_generation = getattr(self, "_count_generation", 0) + 1
                self._found_count = 0
                self.found_var.set("")
                self.output_var.set(folder)
                self._last_photos = self._last_plan = self._last_order = self._last_output = None
                self._mark_profile_custom()
                self._project_name_var.set(t("legacy_album"))
        except (OSError, ValueError) as exc:
            messagebox.showerror(t("project_open"), str(exc), parent=self)
            return
        self._open_review()

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
        elif (photos is None or plan is None or output_dir is None
              or out.resolve() != Path(output_dir).resolve()):
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
                    max_per_day, max_per_chapter = self._selection_caps()
                    plan, order = rebuild_selection_from_analysis(
                        photos,
                        target,
                        coverage_intensity=coverage,
                        people_balance_intensity=people,
                        storytelling_intensity=float(self.storytelling_var.get()),
                        max_per_day=max_per_day,
                        max_per_chapter=max_per_chapter,
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
