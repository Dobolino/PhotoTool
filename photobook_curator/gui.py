"""Einfache Desktop-Oberfläche für den Photobook Curator (tkinter)."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import PipelineConfig, run_pipeline


class PhotobookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fotobuch-Auswahl")
        self.minsize(640, 520)
        self.geometry("720x560")

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
        self._build()
        self.after(150, self._drain_log)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Fotobuch aus Urlaubsfotos zusammenstellen", font=("", 14, "bold")).pack(
            anchor=tk.W, **pad
        )
        ttk.Label(
            frm,
            text="Ordner wählen, Zielanzahl einstellen, Start drücken.",
            foreground="#444",
        ).pack(anchor=tk.W, padx=12, pady=(0, 10))

        self._row_folder(frm, "Fotos-Ordner (Eingabe)", self.input_var, self._pick_input)
        self._row_folder(frm, "Ausgabe-Ordner", self.output_var, self._pick_output)

        opts = ttk.LabelFrame(frm, text="Einstellungen", padding=10)
        opts.pack(fill=tk.X, **pad)

        row = ttk.Frame(opts)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Zielanzahl Bilder:").pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=10, to=500, textvariable=self.target_var, width=8).pack(
            side=tk.LEFT, padx=8
        )

        ttk.Checkbutton(
            opts, text="Ortsnamen per Internet bestimmen (Nominatim)", variable=self.geocode_var
        ).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            opts, text="Gesichtserkennung überspringen (schneller)", variable=self.skip_faces_var
        ).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            opts, text="KI-Bewertung aktivieren (Anthropic API)", variable=self.ai_var
        ).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            opts, text="Nur Kosten schätzen (Dry-Run, keine echte KI-Anfrage)", variable=self.dry_run_var
        ).pack(anchor=tk.W, pady=2)

        key_row = ttk.Frame(opts)
        key_row.pack(fill=tk.X, pady=6)
        ttk.Label(key_row, text="API-Key (optional):").pack(side=tk.LEFT)
        ttk.Entry(key_row, textvariable=self.api_key_var, show="*", width=48).pack(
            side=tk.LEFT, padx=8, fill=tk.X, expand=True
        )

        self.start_btn = ttk.Button(frm, text="Start", command=self._start)
        self.start_btn.pack(anchor=tk.E, **pad)

        log_frame = ttk.LabelFrame(frm, text="Fortschritt / Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)
        log_row = ttk.Frame(log_frame)
        log_row.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(log_row, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_row, command=self.log.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scroll.set)

    def _row_folder(
        self, parent: ttk.Frame, label: str, var: tk.StringVar, command
    ) -> None:
        box = ttk.Frame(parent)
        box.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(box, text=label).pack(anchor=tk.W)
        row = ttk.Frame(box)
        row.pack(fill=tk.X, pady=2)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Durchsuchen…", command=command).pack(side=tk.LEFT, padx=(8, 0))

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
            messagebox.showerror(
                "Eingabeordner fehlt",
                "Bitte einen vorhandenen Fotos-Ordner wählen.",
            )
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
            self._log_queue.put(f"Fertig: {result}")
            self._log_queue.put(f"Ergebnisordner: {cfg.output_dir}")
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Fertig",
                    f"Auswahl erstellt.\n\nOrdner:\n{cfg.output_dir}\n\n"
                    "Schau in selected\\ und inhaltsverzeichnis.md",
                ),
            )
        except Exception as exc:
            self._log_queue.put(f"Fehler: {exc}")
            self.after(0, lambda: messagebox.showerror("Fehler", str(exc)))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.after(0, lambda: self.start_btn.configure(state=tk.NORMAL))


def main() -> int:
    app = PhotobookApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
