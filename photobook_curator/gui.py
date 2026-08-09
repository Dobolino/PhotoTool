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

# Ruhige Foto-Editor-Palette (kein Lila, kein Neon)
COLORS = {
    "bg": "#F3EFE7",
    "surface": "#FFFCF7",
    "ink": "#1F1A17",
    "muted": "#6E645C",
    "line": "#D9D0C4",
    "accent": "#2F5D50",
    "accent_hover": "#244A40",
    "accent_soft": "#E2EDE8",
    "danger": "#8B3A2C",
    "log_bg": "#1C2421",
    "log_fg": "#D7E0DB",
    "phase_pending_bg": "#E8E2D8",
    "phase_pending_fg": "#6E645C",
    "phase_run_bg": "#C45C26",
    "phase_run_fg": "#FFF8F2",
    "phase_done_bg": "#2F7D4F",
    "phase_done_fg": "#FFFFFF",
    "phase_skip_bg": "#F0EBE3",
    "phase_skip_fg": "#A89F95",
}

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

HELP_TEXT = (
    "Kurzanleitung\n"
    "─────────────\n\n"
    "1. Fotos-Ordner wählen (z. B. iCloud-/Urlaubsfotos).\n"
    "2. Ausgabe-Ordner wählen (am besten leer / neu).\n"
    "3. Zielanzahl einstellen (z. B. 80).\n"
    "4. Optionen nach Bedarf lassen oder anpassen.\n"
    "5. „Auswahl starten“ – Schritte werden farbig angezeigt.\n"
    "6. Wenn fertig: „Auswahl prüfen / fortsetzen“, anpassen, speichern.\n\n"
    "Auswahl prüfen\n"
    "  Raster: Klick auf ein Bild = raus / wieder rein.\n"
    "  Diashow: Button „Diashow-Ansicht“ – großes Bild,\n"
    "  Vorschau-Streifen der Nachbarbilder, ← → blättern,\n"
    "  Leertaste = raus/rein, Esc = zurück zum Raster.\n"
    "  Unten Alternativen / Dokumente zum Hinzufügen.\n\n"
    "Pause / Absturz / Update\n"
    "  In der Prüfung wird selection_draft.json automatisch gesichert.\n"
    "  photos_analysis.csv enthält nach der KI den Zwischenstand –\n"
    "  fortsetzen geht ohne neuen KI-Lauf (keine doppelten Kosten).\n"
    "  Auch wenn die Analyse mit einer älteren Programmversion lief:\n"
    "  denselben Ausgabe-Ordner wählen → „Auswahl prüfen / fortsetzen“.\n"
    "  Nur wenn die CSV fehlt oder du einen neuen Ausgabe-Ordner nimmst,\n"
    "  brauchst du einen neuen Lauf.\n\n"
    "KI-Kosten siehst du unter der Zielanzahl. „Nur Kosten schätzen“\n"
    "misst zuerst den Betrag zum Vergleichen.\n\n"
    "Tipp: „Programm aktualisieren.bat“ für Updates. Details: START.md."
)

OPTIONS_HELP = (
    "Was die Optionen steuern\n"
    "────────────────────────\n\n"
    "Zielanzahl Bilder\n"
    "  Ungefähre Anzahl Fotos im fertigen Buch (z. B. 80 oder 400).\n\n"
    "Ortsnamen per Internet\n"
    "  GPS → Städtenamen (Englisch), z. B. Tokyo, Kyoto.\n"
    "  Speichert Treffer in geocode_cache.json.\n\n"
    "Gesichtserkennung / Augen zu\n"
    "  Findet Gesichter, markiert geschlossene Augen / schlechte\n"
    "  Ausschnitte – solche Fotos werden eher abgewertet.\n\n"
    "Serien/Bursts\n"
    "  Ähnliche Fotos kurz hintereinander → nur die besten 1–2 behalten.\n\n"
    "Dokumente & Screenshots separat\n"
    "  Tickets, Maps, Chats usw. nicht automatisch ins Buch, sondern\n"
    "  in den Ordner optional_dokumente/ (später manuell reinnehmbar).\n\n"
    "Finger vor der Linse\n"
    "  Typische Fehlaufnahmen mit Finger/Hand vor der Kamera aussortieren.\n\n"
    "Tages-Abdeckung (+ Stärke)\n"
    "  Verhindert, dass fast alles vom ersten Tag kommt.\n"
    "  Stärke: sanft bis stark gleichmäßig über die Tage.\n\n"
    "Personen-Balance (+ Stärke)\n"
    "  Verhindert, dass immer dieselbe Person das Album dominiert.\n\n"
    "Kapitel-/Karten-Vorschau\n"
    "  Vor dem Kopieren Kapitel und Karte zeigen, dann bestätigen.\n\n"
    "KI-Bewertung (Anthropic API)\n"
    "  Sendet Kandidatenbilder an die KI zur Qualitäts-/Szenenbewertung.\n"
    "  Kostet Geld – siehe die Kostenzeile unter der Zielanzahl.\n\n"
    "Nur Kosten schätzen\n"
    "  Kein echter KI-Aufruf: zählt nur Kandidaten und schätzt den Betrag.\n"
    "  Gut zum Vergleichen, bevor du den echten Lauf startest.\n\n"
    "API-Key\n"
    "  Dein Anthropic-Schlüssel (nur nötig bei echter KI-Bewertung)."
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
        self.title("Fotobuch-Auswahl")
        self.minsize(720, 620)
        self.geometry("780x680")
        self.configure(bg=COLORS["bg"])
        self._set_icon()
        self._advanced_open = False

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
        self.coverage_var = tk.BooleanVar(value=False)
        self.coverage_intensity_var = tk.DoubleVar(value=0.5)
        self.people_var = tk.BooleanVar(value=False)
        self.people_intensity_var = tk.DoubleVar(value=0.5)
        self.map_preview_var = tk.BooleanVar(value=False)
        self.ai_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._found_count = 0
        self._last_ai_cost: dict[str, Any] | None = None
        self._candidate_factor = 4.0

        self._log_queue: queue.Queue = queue.Queue()
        self._progress_queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
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
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.after(100, self._drain_queues)
        # Schwere Module (OpenCV/MediaPipe) erst NACH dem Fenster laden,
        # sonst wirkt der Start wie ein leeres schwarzes Konsolenfenster.
        self.after(200, self._warmup_backend)

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
        self.destroy()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        font_ui = ("Segoe UI", 10)
        font_title = ("Georgia", 18, "bold")
        font_sub = ("Segoe UI", 10)
        font_label = ("Segoe UI", 9)

        style.configure("App.TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["surface"])
        style.configure(
            "Card.TLabelframe",
            background=COLORS["surface"],
            foreground=COLORS["ink"],
            bordercolor=COLORS["line"],
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=COLORS["surface"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Title.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=font_title,
        )
        style.configure(
            "Sub.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=font_sub,
        )
        style.configure(
            "Field.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=font_label,
        )
        style.configure(
            "Body.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["ink"],
            font=font_ui,
        )
        style.configure(
            "Hero.TFrame",
            background=COLORS["accent"],
        )
        style.configure(
            "HeroTitle.TLabel",
            background=COLORS["accent"],
            foreground="#F7F3EC",
            font=("Georgia", 16, "bold"),
        )
        style.configure(
            "HeroSub.TLabel",
            background=COLORS["accent"],
            foreground="#D5E4DE",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Browse.TButton",
            font=font_ui,
            padding=(12, 6),
        )
        style.configure(
            "Start.TButton",
            font=("Segoe UI Semibold", 11),
            padding=(18, 10),
            background=COLORS["accent"],
            foreground="#FFFFFF",
        )
        style.map(
            "Start.TButton",
            background=[("active", COLORS["accent_hover"]), ("disabled", "#9AA9A3")],
            foreground=[("disabled", "#EEF2F0")],
        )
        style.configure(
            "TCheckbutton",
            background=COLORS["surface"],
            foreground=COLORS["ink"],
            font=font_ui,
            focuscolor=COLORS["surface"],
        )
        style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            foreground=COLORS["ink"],
            padding=6,
        )
        style.configure(
            "TSpinbox",
            fieldbackground="#FFFFFF",
            foreground=COLORS["ink"],
            padding=4,
        )
        style.configure(
            "Next.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["accent"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Help.TButton",
            font=("Segoe UI", 9),
            padding=(10, 4),
        )

    def _build(self) -> None:
        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True)

        hero = ttk.Frame(root, style="Hero.TFrame", padding=(18, 12))
        hero.pack(fill=tk.X)
        hero_top = ttk.Frame(hero, style="Hero.TFrame")
        hero_top.pack(fill=tk.X)
        ttk.Label(hero_top, text="Fotobuch", style="HeroTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(hero_top, text="Hilfe", style="Help.TButton", command=self._show_help).pack(
            side=tk.RIGHT
        )

        body = ttk.Frame(root, style="App.TFrame", padding=14)
        body.pack(fill=tk.BOTH, expand=True)

        card = ttk.Frame(body, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X)

        self._folder_row(card, "Fotos-Ordner", "", self.input_var, self._pick_input)
        ttk.Label(card, textvariable=self.found_var, style="Field.TLabel").pack(anchor=tk.W, pady=(2, 0))
        ttk.Separator(card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        self._folder_row(card, "Ausgabe-Ordner", "", self.output_var, self._pick_output)

        settings = ttk.LabelFrame(body, text="  Einstellungen  ", style="Card.TLabelframe", padding=12)
        settings.pack(fill=tk.X, pady=(12, 0))

        count_row = ttk.Frame(settings, style="Card.TFrame")
        count_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(count_row, text="Zielanzahl Bilder", style="Body.TLabel").pack(side=tk.LEFT)
        spin = ttk.Spinbox(
            count_row,
            from_=10,
            to=500,
            textvariable=self.target_var,
            width=8,
            command=self._refresh_cost_estimate,
        )
        spin.pack(side=tk.RIGHT)
        try:
            self.target_var.trace_add("write", lambda *_: self._refresh_cost_estimate())
            self.ai_var.trace_add("write", lambda *_: self._refresh_cost_estimate())
        except Exception:
            pass
        ttk.Label(settings, textvariable=self.cost_var, style="Field.TLabel").pack(
            anchor=tk.W, pady=(0, 6)
        )

        # Kern-Optionen immer sichtbar – Rest unter „Weitere Optionen“
        for text, var in (
            ("Ortsnamen per Internet", self.geocode_var),
            ("Gesichtserkennung / Augen zu", self.faces_var),
            ("Serien/Bursts (beste 1–2)", self.bursts_var),
            ("Dokumente & Screenshots separat", self.aside_var),
        ):
            ttk.Checkbutton(
                settings, text=text, variable=var, command=self._sync_dependent_controls
            ).pack(anchor=tk.W, pady=1)

        opt_row = ttk.Frame(settings, style="Card.TFrame")
        opt_row.pack(fill=tk.X, pady=(8, 0))
        self.advanced_toggle = ttk.Button(
            opt_row,
            text="Weitere Optionen ▸",
            style="Help.TButton",
            command=self._toggle_advanced,
        )
        self.advanced_toggle.pack(side=tk.LEFT)
        ttk.Button(
            opt_row,
            text="Optionen erklären",
            style="Help.TButton",
            command=self._show_options_help,
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.advanced_frame = ttk.Frame(settings, style="Card.TFrame")
        for text, var in (
            ("Finger vor der Linse aussortieren", self.finger_var),
            ("Tages-Abdeckung", self.coverage_var),
            ("Personen-Balance", self.people_var),
            ("Kapitel-/Karten-Vorschau vor Export", self.map_preview_var),
            ("KI-Bewertung (Anthropic API)", self.ai_var),
            ("Nur Kosten schätzen", self.dry_run_var),
        ):
            chk = ttk.Checkbutton(
                self.advanced_frame,
                text=text,
                variable=var,
                command=self._sync_dependent_controls,
            )
            chk.pack(anchor=tk.W, pady=1)
            if var is self.dry_run_var:
                self.dry_run_chk = chk

        self.coverage_block = ttk.Frame(self.advanced_frame, style="Card.TFrame")
        cov_row = ttk.Frame(self.coverage_block, style="Card.TFrame")
        cov_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(cov_row, text="Abdeckung-Stärke", style="Field.TLabel").pack(side=tk.LEFT)
        self.coverage_label = ttk.Label(cov_row, text="50%", style="Field.TLabel")
        self.coverage_label.pack(side=tk.RIGHT)
        self.coverage_scale = ttk.Scale(
            self.coverage_block,
            from_=0.1,
            to=1.0,
            variable=self.coverage_intensity_var,
            command=self._on_coverage_scale,
        )
        self.coverage_scale.pack(fill=tk.X, pady=(2, 0))

        self.people_block = ttk.Frame(self.advanced_frame, style="Card.TFrame")
        people_row = ttk.Frame(self.people_block, style="Card.TFrame")
        people_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(people_row, text="Personen-Stärke", style="Field.TLabel").pack(side=tk.LEFT)
        self.people_label = ttk.Label(people_row, text="50%", style="Field.TLabel")
        self.people_label.pack(side=tk.RIGHT)
        self.people_scale = ttk.Scale(
            self.people_block,
            from_=0.1,
            to=1.0,
            variable=self.people_intensity_var,
            command=self._on_people_scale,
        )
        self.people_scale.pack(fill=tk.X, pady=(2, 0))

        self.ai_block = ttk.Frame(self.advanced_frame, style="Card.TFrame")
        ttk.Label(self.ai_block, text="API-Key", style="Field.TLabel").pack(anchor=tk.W, pady=(6, 0))
        self.api_entry = ttk.Entry(self.ai_block, textvariable=self.api_key_var, show="•")
        self.api_entry.pack(fill=tk.X, pady=(2, 0))

        actions = ttk.Frame(body, style="App.TFrame")
        actions.pack(fill=tk.X, pady=(12, 6))
        self.start_btn = ttk.Button(actions, text="Auswahl starten", style="Start.TButton", command=self._start)
        self.start_btn.pack(side=tk.RIGHT)
        self.cancel_btn = ttk.Button(
            actions,
            text="Abbrechen",
            style="Browse.TButton",
            command=self._cancel,
            state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.review_btn = ttk.Button(
            actions,
            text="Auswahl prüfen / fortsetzen",
            style="Browse.TButton",
            command=self._open_review,
        )
        self.review_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.map_btn = ttk.Button(
            actions, text="Karte", style="Browse.TButton", command=self._open_map_preview
        )
        self.map_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self.next_step_var = tk.StringVar(
            value="Nächster Schritt: Ordner wählen, dann „Auswahl starten“."
        )
        ttk.Label(body, textvariable=self.next_step_var, style="Next.TLabel").pack(
            anchor=tk.W, pady=(0, 4)
        )
        self.status_var = tk.StringVar(value="Lade Erkennungsmodule…")
        ttk.Label(body, textvariable=self.status_var, style="Sub.TLabel").pack(anchor=tk.W)

        prog_row = ttk.Frame(body, style="App.TFrame")
        prog_row.pack(fill=tk.X, pady=(6, 0))
        self.phase_var = tk.StringVar(value="")
        ttk.Label(prog_row, textvariable=self.phase_var, style="Field.TLabel").pack(anchor=tk.W)
        self.progress = ttk.Progressbar(prog_row, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(2, 0))

        phase_box = ttk.LabelFrame(
            body,
            text="  Schritte  (orange = läuft, grün = fertig)  ",
            style="Card.TLabelframe",
            padding=6,
        )
        phase_box.pack(fill=tk.X, pady=(8, 0))
        self._phase_inner = ttk.Frame(phase_box, style="Card.TFrame")
        self._phase_inner.pack(fill=tk.X)
        self._build_phase_chips()

        log_frame = ttk.LabelFrame(body, text="  Verlauf  ", style="Card.TLabelframe", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        log_row = ttk.Frame(log_frame, style="Card.TFrame")
        log_row.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(
            log_row,
            height=4,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=COLORS["log_bg"],
            fg=COLORS["log_fg"],
            insertbackground=COLORS["log_fg"],
            relief=tk.FLAT,
            font=("Consolas", 9),
            padx=8,
            pady=6,
        )
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_row, command=self.log.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scroll.set)

        self._sync_dependent_controls()
        self._refresh_cost_estimate()

    def _set_icon(self) -> None:
        """Ersetzt das Standard-Tk-Icon (blaue Feder) durch ein eigenes."""
        try:
            from PIL import Image, ImageDraw, ImageTk

            n = 64
            img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([2, 2, n - 3, n - 3], radius=12, fill="#2F5D50")
            # weißes „Foto/Buch"-Feld mit kleiner Landschaft
            d.rectangle([14, 18, 50, 46], fill="#F7F3EC")
            d.polygon([(18, 44), (28, 30), (36, 44)], fill="#6B705C")   # Berg
            d.polygon([(32, 44), (40, 34), (48, 44)], fill="#8B5A2B")   # Berg 2
            d.ellipse([40, 22, 47, 29], fill="#BC6C25")                 # Sonne
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
        cfg.enable_map_preview = bool(self.map_preview_var.get())
        cfg.people_balance_intensity = (
            float(self.people_intensity_var.get()) if self.people_var.get() else 0.0
        )
        return cfg

    def _sync_dependent_controls(self) -> None:
        """Regler nur zeigen, wenn die Option an ist; KI-Felder abhängig von KI-Haken."""
        def enable(widget, on: bool) -> None:
            try:
                widget.state(["!disabled"] if on else ["disabled"])
            except Exception:
                pass

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
            if self.ai_var.get():
                self.ai_block.pack(fill=tk.X)
            else:
                self.ai_block.pack_forget()

        ai_on = bool(self.ai_var.get())
        enable(self.api_entry, ai_on)
        enable(self.dry_run_chk, ai_on)
        enable(self.coverage_scale, bool(self.coverage_var.get()))
        enable(self.people_scale, bool(self.people_var.get()))
        # Schritt-Tafel vor dem Start an Optionen anpassen
        if not self._is_analysis_running():
            self._reset_phase_board(self._ui_phase_config())

    def _folder_row(
        self,
        parent: ttk.Frame,
        title: str,
        hint: str,
        var: tk.StringVar,
        command,
    ) -> None:
        ttk.Label(parent, text=title, style="Body.TLabel").pack(anchor=tk.W)
        if hint:
            ttk.Label(parent, text=hint, style="Field.TLabel").pack(anchor=tk.W, pady=(0, 4))
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(2, 0))
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Durchsuchen", style="Browse.TButton", command=command).pack(
            side=tk.LEFT, padx=(8, 0)
        )

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
        self.found_var.set("Zähle Bilder…")

        def worker() -> None:
            try:
                from .scan import find_images

                n = len(find_images(Path(path)))
                msg = f"{n} Bilder gefunden" if n else "Keine Bilder in diesem Ordner gefunden"
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

            if not bool(self.ai_var.get()):
                self.cost_var.set("KI-Kosten: aus (keine API-Kosten)")
                return
            try:
                target = int(self.target_var.get())
            except (TypeError, ValueError, tk.TclError):
                target = 80
            n_cand = estimate_candidate_count(
                target, self._found_count, self._candidate_factor
            )
            est = estimate_cost(n_cand)
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
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("520x480")
        win.transient(self)
        win.configure(bg=COLORS["bg"])
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
        ttk.Button(win, text="Schließen", command=win.destroy).pack(pady=(0, 10))

    def _show_help(self) -> None:
        self._show_text_window("Hilfe – Fotobuch", HELP_TEXT + "\n\n" + OPTIONS_HELP)

    def _show_options_help(self) -> None:
        self._show_text_window("Optionen erklärt", OPTIONS_HELP)

    def _set_next_step(self, text: str) -> None:
        self.next_step_var.set(text)

    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self.advanced_frame.pack(fill=tk.X, pady=(6, 0))
            self.advanced_toggle.configure(text="Weitere Optionen ▾")
            self._sync_dependent_controls()
        else:
            self.advanced_frame.pack_forget()
            self.advanced_toggle.configure(text="Weitere Optionen ▸")

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
            for step in PHASE_STEPS:
                st = self._phase_status.get(step.id)
                if st == "running":
                    self._phase_status[step.id] = "done"
                elif st == "pending":
                    # z. B. Dry-Run: nicht gelaufene Reste als übersprungen
                    self._phase_status[step.id] = "skipped"
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

        api_key = self.api_key_var.get().strip()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key

        if self.ai_var.get() and not os.environ.get("ANTHROPIC_API_KEY") and not self.dry_run_var.get():
            messagebox.showerror(
                "API-Key fehlt",
                "Für die KI-Bewertung brauchst du einen Anthropic API-Key,\n"
                "oder aktiviere „Nur Kosten schätzen“.",
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
            ai_review=bool(self.ai_var.get()),
            dry_run=bool(self.dry_run_var.get()),
            enable_faces=bool(self.faces_var.get()),
            enable_bursts=bool(self.bursts_var.get()),
            enable_document_aside=bool(self.aside_var.get()),
            enable_finger_filter=bool(self.finger_var.get()),
            coverage_intensity=coverage_intensity,
            people_balance_intensity=people_balance_intensity,
            enable_map_preview=map_preview,
            skip_export=map_preview,  # Export erst nach Bestätigung in der Vorschau
        )

        self._cancel_event.clear()
        self.start_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.review_btn.configure(state=tk.DISABLED)
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
            self.after(0, lambda: self.review_btn.configure(state=tk.NORMAL))
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

        if not has_selected and not has_draft:
            if has_ai or has_candidates:
                msg = (
                    "Es gibt eine Analyse-CSV, aber noch keine finale Auswahl.\n\n"
                )
                if has_ai:
                    msg += "KI-Bewertungen sind bereits gespeichert – keine neue KI nötig.\n\n"
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
                    "Bitte zuerst „Auswahl starten“ (ohne „Nur Kosten schätzen“).",
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

        open_review(
            self,
            photos,
            plan,
            Path(output_dir),
            on_saved=lambda: self.status_var.set("Auswahl gespeichert"),
        )


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
        app = PhotobookApp()
        # Sofort sichtbar machen (manche Windows-Setups legen das Fenster hinten an)
        try:
            app.lift()
            app.attributes("-topmost", True)
            app.after(400, lambda: app.attributes("-topmost", False))
            app.focus_force()
        except tk.TclError:
            pass
        app.mainloop()
        return 0
    except Exception:
        _report_startup_error()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
