"""Einfache, optisch aufgeräumte Desktop-Oberfläche für den Photobook Curator."""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pipeline import PipelineConfig

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
}


class PhotobookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fotobuch-Auswahl")
        self.minsize(720, 640)
        self.geometry("780x700")
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

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._progress_queue: queue.Queue[tuple[str, float]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._status_shown = False       # tqdm-Zwischenstand als eine ersetzbare Zeile
        self._status_mark = "log_status"
        self._worker: threading.Thread | None = None
        self._last_photos = None
        self._last_plan = None
        self._last_order = None
        self._last_output: Path | None = None
        self._pipeline_ready = False
        self._pipeline_error: str | None = None
        self._setup_style()
        self._build()
        self.after(150, self._drain_queues)
        # Schwere Module (OpenCV/MediaPipe) erst NACH dem Fenster laden,
        # sonst wirkt der Start wie ein leeres schwarzes Konsolenfenster.
        self.after(200, self._warmup_backend)

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

    def _build(self) -> None:
        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True)

        hero = ttk.Frame(root, style="Hero.TFrame", padding=(22, 18))
        hero.pack(fill=tk.X)
        ttk.Label(hero, text="Fotobuch", style="HeroTitle.TLabel").pack(anchor=tk.W)
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

    def _append_log(self, text: str) -> None:
        """Feste Log-Zeile (bleibt stehen)."""
        self.log.configure(state=tk.NORMAL)
        if self._status_shown:
            self.log.delete(self._status_mark, tk.END)
            self._status_shown = False
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _append_status(self, text: str) -> None:
        """Sich fortlaufend ersetzende Zeile (tqdm-Fortschritt) – zeigt, dass es läuft."""
        self.log.configure(state=tk.NORMAL)
        if self._status_shown:
            self.log.delete(self._status_mark, tk.END)
        else:
            self.log.mark_set(self._status_mark, tk.END)
            self.log.mark_gravity(self._status_mark, tk.LEFT)
        self.log.insert(tk.END, text)
        self._status_shown = True
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_progress(self, label: str, frac: float) -> None:
        self.phase_var.set(label)
        self.progress["value"] = max(0, min(100, int(round(frac * 100))))
        if label and label != "Fertig":
            self.status_var.set(label)

    def _drain_queues(self) -> None:
        try:
            while True:
                item = self._log_queue.get_nowait()
                if isinstance(item, tuple):
                    mode, text = item
                else:
                    mode, text = "line", item
                if mode == "status":
                    self._append_status(text)
                else:
                    self._append_log(text)
        except queue.Empty:
            pass
        try:
            while True:
                label, frac = self._progress_queue.get_nowait()
                self._set_progress(label, frac)
        except queue.Empty:
            pass
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
        self._append_log("Start…")
        self._worker = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.is_alive():
            self._cancel_event.set()
            self.cancel_btn.configure(state=tk.DISABLED)
            self.status_var.set("Wird abgebrochen…")
            self.phase_var.set("Abbrechen… (stoppt nach dem aktuellen Schritt)")
            self._append_log("Abbruch angefordert…")

    def _run(self, cfg: Any) -> None:
        class QueueWriter:
            def __init__(self, q: queue.Queue[str], original) -> None:
                self.q = q
                self.original = original
                self._buf = ""

            def write(self, s: str) -> int:
                if self.original:
                    try:
                        self.original.write(s)
                    except Exception:
                        pass
                self._buf += s
                # Segmente an \n (feste Zeile) und \r (tqdm-Zwischenstand) trennen,
                # damit der Fortschritt live sichtbar ist statt erst am Phasenende.
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
                    self._buf = self._buf[idx + 1:]
                    if seg.strip():
                        self.q.put((mode, seg))
                return len(s)

            def flush(self) -> None:
                if self.original:
                    try:
                        self.original.flush()
                    except Exception:
                        pass

        def on_progress(label: str, frac: float) -> None:
            self._progress_queue.put((label, frac))

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = QueueWriter(self._log_queue, old_out)  # type: ignore[assignment]
        sys.stderr = QueueWriter(self._log_queue, old_err)  # type: ignore[assignment]
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
            self._progress_queue.put(("Fertig", 1.0))
            self.after(0, lambda: self.status_var.set("Fertig"))
            self.after(0, lambda r=result: self._on_finished(r, cfg))
        except Exception as exc:
            from .pipeline import PipelineCancelled as _Cancelled

            if isinstance(exc, _Cancelled):
                self._log_queue.put("Abgebrochen – es wurden keine Ordner geschrieben.")
                self._progress_queue.put(("Abgebrochen", 0.0))
                self.after(0, lambda: self.status_var.set("Abgebrochen"))
            else:
                self._log_queue.put(f"Fehler: {exc}")
                self._progress_queue.put(("Fehler", 0.0))
                self.after(0, lambda: self.status_var.set("Fehler"))
                self.after(0, lambda: messagebox.showerror("Fehler", str(exc)))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.after(0, lambda: self.start_btn.configure(state=tk.NORMAL))
            self.after(0, lambda: self.cancel_btn.configure(state=tk.DISABLED))

    def _on_finished(self, result: dict, cfg: Any) -> None:
        if result.get("dry_run"):
            messagebox.showinfo(
                "Dry-Run",
                "Kostenschätzung fertig. Siehe Verlauf für Details.",
            )
            return

        if cfg.enable_map_preview and not result.get("exported"):
            from .map_preview import open_map_preview

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
        open_review = messagebox.askyesno(
            "Fertig",
            f"Auswahl erstellt in:\n{cfg.output_dir}\n\n"
            "Jetzt die Bilder als Vorschau prüfen und einzelne rausnehmen/hinzufügen?",
        )
        if open_review:
            self._open_review()

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
