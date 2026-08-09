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
    "5. „Auswahl starten“ – unter Analyse-Schritte siehst du den Ablauf:\n"
    "   Orange = läuft gerade, Grün = fertig, Blass = übersprungen.\n"
    "   Bei vielen Fotos kann das mehrere Minuten dauern.\n"
    "6. Wenn fertig: „Auswahl prüfen“ – einzelne Bilder rausnehmen oder\n"
    "   Alternativen / Dokumente hinzufügen, dann speichern.\n\n"
    "Tipp: Zum Aktualisieren des Programms „Programm aktualisieren.bat“\n"
    "im PhotoTool-Ordner nutzen. Mehr Details stehen in START.md."
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
        self.minsize(760, 720)
        self.geometry("820x780")
        self.configure(bg=COLORS["bg"])
        self._set_icon()

        self.found_var = tk.StringVar(value="")
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

        hero = ttk.Frame(root, style="Hero.TFrame", padding=(22, 18))
        hero.pack(fill=tk.X)
        hero_top = ttk.Frame(hero, style="Hero.TFrame")
        hero_top.pack(fill=tk.X)
        ttk.Label(hero_top, text="Fotobuch", style="HeroTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(hero_top, text="Hilfe", style="Help.TButton", command=self._show_help).pack(
            side=tk.RIGHT
        )
        ttk.Label(
            hero,
            text="Urlaubsfotos automatisch sortieren, filtern und als Kapitel vorbereiten.",
            style="HeroSub.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        body = ttk.Frame(root, style="App.TFrame", padding=18)
        body.pack(fill=tk.BOTH, expand=True)

        card = ttk.Frame(body, style="Card.TFrame", padding=16)
        card.pack(fill=tk.X)

        self._folder_row(card, "Fotos-Ordner", "Deine Japan-/Urlaubsfotos", self.input_var, self._pick_input)
        ttk.Label(card, textvariable=self.found_var, style="Field.TLabel").pack(anchor=tk.W, pady=(4, 0))
        ttk.Separator(card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)
        self._folder_row(card, "Ausgabe-Ordner", "Hier landen Auswahl und Übersicht", self.output_var, self._pick_output)

        settings = ttk.LabelFrame(body, text="  Einstellungen  ", style="Card.TLabelframe", padding=14)
        settings.pack(fill=tk.X, pady=(14, 0))

        count_row = ttk.Frame(settings, style="Card.TFrame")
        count_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(count_row, text="Zielanzahl Bilder", style="Body.TLabel").pack(side=tk.LEFT)
        spin = ttk.Spinbox(count_row, from_=10, to=500, textvariable=self.target_var, width=8)
        spin.pack(side=tk.RIGHT)

        for text, var in (
            ("Ortsnamen per Internet bestimmen", self.geocode_var),
            ("Gesichtserkennung / Augen zu", self.faces_var),
            ("Serien/Bursts (beste 1–2 behalten)", self.bursts_var),
            ("Dokumente & Screenshots separat (Optional-Pool)", self.aside_var),
            ("Finger vor der Linse erkennen & aussortieren", self.finger_var),
            ("Tages-Abdeckung (nicht alles vom ersten Tag)", self.coverage_var),
            ("Personen-Balance (nicht immer dieselbe Person)", self.people_var),
            ("Kapitel-/Karten-Vorschau vor dem Export", self.map_preview_var),
            ("KI-Bewertung aktivieren (Anthropic API)", self.ai_var),
            ("Nur Kosten schätzen (kein echter KI-Lauf)", self.dry_run_var),
        ):
            chk = ttk.Checkbutton(
                settings, text=text, variable=var, command=self._sync_dependent_controls
            )
            chk.pack(anchor=tk.W, pady=2)
            if var is self.dry_run_var:
                self.dry_run_chk = chk

        cov_row = ttk.Frame(settings, style="Card.TFrame")
        cov_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(cov_row, text="Abdeckung-Stärke", style="Field.TLabel").pack(side=tk.LEFT)
        self.coverage_label = ttk.Label(cov_row, text="50%", style="Field.TLabel")
        self.coverage_label.pack(side=tk.RIGHT)
        self.coverage_scale = ttk.Scale(
            settings,
            from_=0.1,
            to=1.0,
            variable=self.coverage_intensity_var,
            command=self._on_coverage_scale,
        )
        self.coverage_scale.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(
            settings,
            text="Nur wirksam, wenn „Tages-Abdeckung“ aktiv. Links = sanft, rechts = stark gleichmäßig.",
            style="Field.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        people_row = ttk.Frame(settings, style="Card.TFrame")
        people_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(people_row, text="Personen-Stärke", style="Field.TLabel").pack(side=tk.LEFT)
        self.people_label = ttk.Label(people_row, text="50%", style="Field.TLabel")
        self.people_label.pack(side=tk.RIGHT)
        self.people_scale = ttk.Scale(
            settings,
            from_=0.1,
            to=1.0,
            variable=self.people_intensity_var,
            command=self._on_people_scale,
        )
        self.people_scale.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(
            settings,
            text="Nur wirksam, wenn „Personen-Balance“ aktiv. Links = sanft, rechts = stark ausgewogen.",
            style="Field.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        key_box = ttk.Frame(settings, style="Card.TFrame")
        key_box.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(key_box, text="API-Key (optional)", style="Field.TLabel").pack(anchor=tk.W)
        self.api_entry = ttk.Entry(key_box, textvariable=self.api_key_var, show="•")
        self.api_entry.pack(fill=tk.X, pady=(4, 0))

        actions = ttk.Frame(body, style="App.TFrame")
        actions.pack(fill=tk.X, pady=(14, 8))
        self.status_var = tk.StringVar(value="Fenster geöffnet – lade Erkennungsmodule…")
        ttk.Label(actions, textvariable=self.status_var, style="Sub.TLabel").pack(side=tk.LEFT)
        self.map_btn = ttk.Button(
            actions, text="Karte zeigen", style="Browse.TButton", command=self._open_map_preview
        )
        self.map_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.review_btn = ttk.Button(
            actions, text="Auswahl prüfen", style="Browse.TButton", command=self._open_review
        )
        self.review_btn.pack(side=tk.RIGHT, padx=(0, 8))
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

        prog_row = ttk.Frame(body, style="App.TFrame")
        prog_row.pack(fill=tk.X, pady=(0, 4))
        self.phase_var = tk.StringVar(value="")
        ttk.Label(prog_row, textvariable=self.phase_var, style="Field.TLabel").pack(anchor=tk.W)
        self.progress = ttk.Progressbar(prog_row, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(4, 0))

        phase_box = ttk.LabelFrame(
            body, text="  Analyse-Schritte  ", style="Card.TLabelframe", padding=8
        )
        phase_box.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(
            phase_box,
            text="Grau = noch offen · Orange = läuft · Grün = fertig · Blass = übersprungen",
            style="Field.TLabel",
        ).pack(anchor=tk.W)
        self._phase_inner = ttk.Frame(phase_box, style="Card.TFrame")
        self._phase_inner.pack(fill=tk.X, pady=(6, 0))
        self._build_phase_chips()

        self.next_step_var = tk.StringVar(
            value="Nächster Schritt: Fotos- und Ausgabe-Ordner wählen, dann „Auswahl starten“."
        )
        ttk.Label(body, textvariable=self.next_step_var, style="Next.TLabel").pack(
            anchor=tk.W, pady=(8, 0)
        )

        log_frame = ttk.LabelFrame(body, text="  Verlauf  ", style="Card.TLabelframe", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        log_row = ttk.Frame(log_frame, style="Card.TFrame")
        log_row.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(
            log_row,
            height=10,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=COLORS["log_bg"],
            fg=COLORS["log_fg"],
            insertbackground=COLORS["log_fg"],
            relief=tk.FLAT,
            font=("Consolas", 9),
            padx=10,
            pady=8,
        )
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_row, command=self.log.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scroll.set)

        self._sync_dependent_controls()

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
        """Regler/Felder nur aktiv, wenn die zugehörige Option angehakt ist."""
        def enable(widget, on: bool) -> None:
            try:
                widget.state(["!disabled"] if on else ["disabled"])
            except Exception:
                pass

        enable(self.coverage_scale, bool(self.coverage_var.get()))
        enable(self.people_scale, bool(self.people_var.get()))
        ai_on = bool(self.ai_var.get())
        enable(self.api_entry, ai_on)
        enable(self.dry_run_chk, ai_on)
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
        ttk.Label(parent, text=hint, style="Field.TLabel").pack(anchor=tk.W, pady=(0, 4))
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X)
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
                msg = ""
            self.after(0, lambda: self.found_var.set(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Ausgabe-Ordner wählen")
        if path:
            self.output_var.set(path)

    def _show_help(self) -> None:
        messagebox.showinfo("Hilfe – Fotobuch", HELP_TEXT, parent=self)

    def _set_next_step(self, text: str) -> None:
        self.next_step_var.set(text)

    def _build_phase_chips(self) -> None:
        for child in self._phase_inner.winfo_children():
            child.destroy()
        self._phase_labels.clear()
        cols = 4
        for i, step in enumerate(PHASE_STEPS):
            status = self._phase_status.get(step.id, "pending")
            bg_key, fg_key = PHASE_STYLE.get(status, PHASE_STYLE["pending"])
            lbl = tk.Label(
                self._phase_inner,
                text=f"  {step.label}  ",
                bg=COLORS[bg_key],
                fg=COLORS[fg_key],
                font=("Segoe UI Semibold", 9),
                padx=4,
                pady=4,
            )
            lbl.grid(row=i // cols, column=i % cols, padx=3, pady=3, sticky="ew")
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
        self.status_var.set("Arbeitet…")
        self.phase_var.set("Start…")
        self.progress["value"] = 0
        self._pending_status = None
        self._reset_phase_board(cfg)
        self._set_next_step(
            "Analyse läuft… Orange = aktueller Schritt, Grün = fertig. Bitte warten."
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

    def _on_finished(self, result: dict, cfg: Any) -> None:
        if result.get("dry_run"):
            self._set_next_step(
                "Kostenschätzung fertig. Für echten Lauf „Nur Kosten schätzen“ aus und erneut starten."
            )
            messagebox.showinfo(
                "Dry-Run",
                "Kostenschätzung fertig. Siehe Verlauf für Details.",
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
        from .review_export import load_photos_from_csv, plan_from_photos
        from .review_gui import open_review

        photos = self._last_photos
        plan = self._last_plan
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

        if not any(p.is_selected for p in photos):
            messagebox.showinfo(
                "Keine Auswahl",
                "In diesem Ordner sind keine ausgewählten Bilder markiert.",
            )
            return

        open_review(self, photos, plan, Path(output_dir), on_saved=lambda: self.status_var.set("Auswahl gespeichert"))


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
