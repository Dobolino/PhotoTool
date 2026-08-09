"""Einfache, optisch aufgeräumte Desktop-Oberfläche für den Photobook Curator."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import PipelineConfig, run_pipeline

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

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.target_var = tk.IntVar(value=80)
        self.geocode_var = tk.BooleanVar(value=True)
        self.ai_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.skip_faces_var = tk.BooleanVar(value=False)
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._last_photos = None
        self._last_plan = None
        self._last_output: Path | None = None
        self._setup_style()
        self._build()
        self.after(150, self._drain_log)

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
            ("Gesichtserkennung überspringen (schneller)", self.skip_faces_var),
            ("KI-Bewertung aktivieren (Anthropic API)", self.ai_var),
            ("Nur Kosten schätzen (kein echter KI-Lauf)", self.dry_run_var),
        ):
            ttk.Checkbutton(settings, text=text, variable=var).pack(anchor=tk.W, pady=2)

        key_box = ttk.Frame(settings, style="Card.TFrame")
        key_box.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(key_box, text="API-Key (optional)", style="Field.TLabel").pack(anchor=tk.W)
        ttk.Entry(key_box, textvariable=self.api_key_var, show="•").pack(fill=tk.X, pady=(4, 0))

        actions = ttk.Frame(body, style="App.TFrame")
        actions.pack(fill=tk.X, pady=(14, 8))
        self.status_var = tk.StringVar(value="Bereit")
        ttk.Label(actions, textvariable=self.status_var, style="Sub.TLabel").pack(side=tk.LEFT)
        self.review_btn = ttk.Button(
            actions, text="Auswahl prüfen", style="Browse.TButton", command=self._open_review
        )
        self.review_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.start_btn = ttk.Button(actions, text="Auswahl starten", style="Start.TButton", command=self._start)
        self.start_btn.pack(side=tk.RIGHT)

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

    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="Fotos-Ordner wählen")
        if path:
            self.input_var.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Ausgabe-Ordner wählen")
        if path:
            self.output_var.set(path)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _drain_log(self) -> None:
        try:
            while True:
                self._append_log(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

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

        cfg = PipelineConfig(
            input_dir=input_dir.resolve(),
            output_dir=output_dir.resolve(),
            target_n=int(self.target_var.get()),
            geocode=bool(self.geocode_var.get()),
            ai_review=bool(self.ai_var.get()),
            dry_run=bool(self.dry_run_var.get()),
            skip_faces=bool(self.skip_faces_var.get()),
        )

        self.start_btn.configure(state=tk.DISABLED)
        self.status_var.set("Arbeitet…")
        self._append_log("Start…")
        self._worker = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._worker.start()

    def _run(self, cfg: PipelineConfig) -> None:
        import sys

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
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    if line.strip():
                        self.q.put(line)
                return len(s)

            def flush(self) -> None:
                if self.original:
                    try:
                        self.original.flush()
                    except Exception:
                        pass

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = QueueWriter(self._log_queue, old_out)  # type: ignore[assignment]
        sys.stderr = QueueWriter(self._log_queue, old_err)  # type: ignore[assignment]
        try:
            result = run_pipeline(cfg)
            summary = {
                k: v
                for k, v in result.items()
                if k not in ("photo_objects", "plan", "order")
            }
            self._log_queue.put(f"Fertig: {summary}")
            self._log_queue.put(f"Ergebnisordner: {cfg.output_dir}")
            self._last_photos = result.get("photo_objects")
            self._last_plan = result.get("plan")
            self._last_output = result.get("output_dir") or cfg.output_dir
            self.after(0, lambda: self.status_var.set("Fertig"))
            self.after(0, lambda r=result: self._on_finished(r, cfg))
        except Exception as exc:
            self._log_queue.put(f"Fehler: {exc}")
            self.after(0, lambda: self.status_var.set("Fehler"))
            self.after(0, lambda: messagebox.showerror("Fehler", str(exc)))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.after(0, lambda: self.start_btn.configure(state=tk.NORMAL))

    def _on_finished(self, result: dict, cfg: PipelineConfig) -> None:
        if result.get("dry_run"):
            messagebox.showinfo(
                "Dry-Run",
                "Kostenschätzung fertig. Siehe Verlauf für Details.",
            )
            return
        open_review = messagebox.askyesno(
            "Fertig",
            f"Auswahl erstellt in:\n{cfg.output_dir}\n\n"
            "Jetzt die Bilder als Vorschau prüfen und einzelne rausnehmen/hinzufügen?",
        )
        if open_review:
            self._open_review()

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


def main() -> int:
    app = PhotobookApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
