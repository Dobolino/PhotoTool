"""Variante 3 – Geführter Assistent (Schritt-für-Schritt) für den Photobook Curator.

Eigenständige, schlanke Oberfläche, die dieselbe Pipeline wie die Hauptoberfläche
nutzt. Start:  python -m photobook_curator.gui_wizard
Die klassische Oberfläche (gui.py) bleibt unverändert daneben bestehen.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox

from .pipeline import PipelineCancelled, PipelineConfig, run_pipeline

# Variante-3-Palette: helles Papier + kräftiger Terrakotta-Akzent
C = {
    "paper": "#FFFDFB",
    "surface": "#FFFFFF",
    "soft": "#FBF7F2",
    "ink": "#2A241F",
    "muted": "#9A8E80",
    "line": "#EFE7DB",
    "accent": "#C75B35",
    "accent_dark": "#AE4C2A",
    "accent_soft": "#FBE8DD",
    "accent_ink": "#B24A2E",
    "ok": "#2F7D5B",
}

STEP_TITLES = ["Fotos wählen", "Optionen", "Auswahl läuft", "Fertig"]


class WizardApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fotobuch-Assistent")
        self.minsize(640, 620)
        self.geometry("720x680")
        self.configure(bg=C["paper"])
        self._set_icon()

        # Schriftarten
        self.f_big = tkfont.Font(family="Segoe UI Semibold", size=18)
        self.f_h = tkfont.Font(family="Segoe UI Semibold", size=12)
        self.f = tkfont.Font(family="Segoe UI", size=10)
        self.f_small = tkfont.Font(family="Segoe UI", size=9)

        # Zustand
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.found_var = tk.StringVar(value="")
        self.target_var = tk.IntVar(value=80)
        self.target_lbl_var = tk.StringVar(value="80")
        self.geocode_var = tk.BooleanVar(value=True)
        self.faces_var = tk.BooleanVar(value=True)
        self.bursts_var = tk.BooleanVar(value=True)
        self.aside_var = tk.BooleanVar(value=True)
        self.finger_var = tk.BooleanVar(value=False)
        self.coverage_var = tk.BooleanVar(value=False)
        self.people_var = tk.BooleanVar(value=False)
        self.map_var = tk.BooleanVar(value=False)
        self.ai_var = tk.BooleanVar(value=False)
        self.dry_var = tk.BooleanVar(value=False)
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.phase_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")

        self.step = 0
        self._advanced_open = False
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._log_q: queue.Queue = queue.Queue()
        self._prog_q: queue.Queue = queue.Queue()
        self._result: dict | None = None
        self._last_output: Path | None = None

        self._build()
        self._goto(0)
        self.after(120, self._drain)

    # ---------- Grundgerüst ----------
    def _build(self) -> None:
        head = tk.Frame(self, bg=C["paper"])
        head.pack(fill=tk.X, padx=26, pady=(22, 8))
        tk.Label(head, text="Fotobuch", font=tkfont.Font(family="Georgia", size=20, weight="bold"),
                 bg=C["paper"], fg=C["ink"]).pack(side=tk.LEFT)
        self.help_btn = tk.Label(head, text="?  Hilfe", font=self.f, bg=C["accent_soft"],
                                 fg=C["accent_ink"], padx=12, pady=4, cursor="hand2")
        self.help_btn.pack(side=tk.RIGHT)
        self.help_btn.bind("<Button-1>", lambda _e: self._show_help())

        # Schritt-Anzeige (Stepper)
        self.stepper = tk.Frame(self, bg=C["paper"])
        self.stepper.pack(fill=tk.X, padx=26, pady=(0, 6))
        self._dots: list[tk.Label] = []
        for i, name in enumerate(STEP_TITLES):
            if i > 0:
                tk.Frame(self.stepper, bg=C["line"], height=2, width=28).pack(side=tk.LEFT, pady=10, padx=4)
            d = tk.Label(self.stepper, text=str(i + 1), font=self.f_small, width=3,
                         bg=C["soft"], fg=C["muted"])
            d.pack(side=tk.LEFT)
            self._dots.append(d)
            tk.Label(self.stepper, text=name, font=self.f_small, bg=C["paper"],
                     fg=C["muted"]).pack(side=tk.LEFT, padx=(5, 2))

        # Inhaltsbereich (zentrierte Spalte, feste Maximalbreite)
        body = tk.Frame(self, bg=C["paper"])
        body.pack(fill=tk.BOTH, expand=True, padx=26, pady=(6, 0))
        self.card = tk.Frame(body, bg=C["surface"], highlightbackground=C["line"],
                             highlightthickness=1)
        self.card.pack(fill=tk.BOTH, expand=True)
        self.content = tk.Frame(self.card, bg=C["surface"])
        self.content.pack(fill=tk.BOTH, expand=True, padx=28, pady=24)

        # Navigationsleiste
        nav = tk.Frame(self, bg=C["paper"])
        nav.pack(fill=tk.X, padx=26, pady=16)
        self.back_btn = self._btn(nav, "← Zurück", self._back, kind="ghost")
        self.back_btn.pack(side=tk.LEFT)
        self.next_btn = self._btn(nav, "Weiter →", self._next, kind="primary")
        self.next_btn.pack(side=tk.RIGHT)

    def _btn(self, parent, text, cmd, kind="primary"):
        if kind == "primary":
            b = tk.Label(parent, text=text, font=self.f_h, bg=C["accent"], fg="white",
                         padx=20, pady=11, cursor="hand2")
            b.bind("<Enter>", lambda _e: b.configure(bg=C["accent_dark"]))
            b.bind("<Leave>", lambda _e: b.configure(bg=C["accent"]))
        else:
            b = tk.Label(parent, text=text, font=self.f, bg=C["surface"], fg=C["muted"],
                         padx=16, pady=10, cursor="hand2",
                         highlightbackground=C["line"], highlightthickness=1)
        b.bind("<Button-1>", lambda _e: cmd())
        return b

    def _switch_row(self, parent, text, var, hint=""):
        row = tk.Frame(parent, bg=C["surface"])
        row.pack(fill=tk.X, pady=3)
        cb = tk.Checkbutton(row, text=text, variable=var, font=self.f, bg=C["surface"],
                            fg=C["ink"], activebackground=C["surface"], selectcolor=C["soft"],
                            anchor="w", cursor="hand2", highlightthickness=0, bd=0)
        cb.pack(side=tk.LEFT)
        if hint:
            tk.Label(row, text=hint, font=self.f_small, bg=C["surface"], fg=C["muted"]).pack(side=tk.RIGHT)
        return row

    def _clear_content(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    # ---------- Navigation ----------
    def _goto(self, n: int) -> None:
        self.step = max(0, min(3, n))
        for i, d in enumerate(self._dots):
            if i == self.step:
                d.configure(bg=C["accent"], fg="white")
            elif i < self.step:
                d.configure(bg=C["accent_soft"], fg=C["accent_ink"])
            else:
                d.configure(bg=C["soft"], fg=C["muted"])
        [self._step_folders, self._step_options, self._step_run, self._step_done][self.step]()
        # Nav-Zustände
        self.back_btn.pack_configure()
        if self.step == 0:
            self.back_btn.pack_forget()
        else:
            self.back_btn.pack(side=tk.LEFT)
        if self.step in (2, 3):
            self.next_btn.pack_forget()
        else:
            self.next_btn.pack(side=tk.RIGHT)
            self.next_btn.configure(text="Auswahl starten →" if self.step == 1 else "Weiter →")

    def _back(self) -> None:
        if self.step == 3:
            self._goto(1)
        elif self.step > 0:
            self._goto(self.step - 1)

    def _next(self) -> None:
        if self.step == 0:
            if not Path(self.input_var.get().strip() or "_").is_dir():
                messagebox.showerror("Fotos-Ordner fehlt", "Bitte einen vorhandenen Fotos-Ordner wählen.")
                return
            if not self.output_var.get().strip():
                messagebox.showerror("Ausgabe-Ordner fehlt", "Bitte einen Ausgabe-Ordner wählen.")
                return
            self._goto(1)
        elif self.step == 1:
            self._goto(2)

    # ---------- Schritt 1: Ordner ----------
    def _step_folders(self) -> None:
        self._clear_content()
        c = self.content
        tk.Label(c, text="Schritt 1 von 4", font=self.f_small, bg=C["surface"], fg=C["muted"]).pack(anchor="w")
        tk.Label(c, text="Wo sind deine Fotos?", font=self.f_big, bg=C["surface"], fg=C["ink"]).pack(anchor="w", pady=(2, 16))

        self._folder_block(c, "Fotos-Ordner", "Deine Urlaubsfotos (z. B. Japan)", self.input_var, self._pick_input)
        tk.Label(c, textvariable=self.found_var, font=self.f_small, bg=C["surface"], fg=C["ok"]).pack(anchor="w", pady=(4, 14))
        self._folder_block(c, "Ausgabe-Ordner", "Hier landet die Auswahl (neuer, leerer Ordner)", self.output_var, self._pick_output)

        box = tk.Frame(c, bg=C["soft"])
        box.pack(fill=tk.X, pady=(20, 0))
        inner = tk.Frame(box, bg=C["soft"])
        inner.pack(fill=tk.X, padx=14, pady=12)
        top = tk.Frame(inner, bg=C["soft"])
        top.pack(fill=tk.X)
        tk.Label(top, text="Wie viele Bilder ins Buch?", font=self.f, bg=C["soft"], fg=C["ink"]).pack(side=tk.LEFT)
        tk.Label(top, textvariable=self.target_lbl_var, font=self.f_h, bg=C["accent_soft"],
                 fg=C["accent_ink"], padx=10).pack(side=tk.RIGHT)
        sc = tk.Scale(inner, from_=10, to=300, orient=tk.HORIZONTAL, variable=self.target_var,
                      showvalue=False, bg=C["soft"], fg=C["ink"], troughcolor=C["line"],
                      highlightthickness=0, sliderrelief=tk.FLAT, command=self._on_target)
        sc.pack(fill=tk.X, pady=(6, 0))
        if self.input_var.get().strip():
            self._update_found(self.input_var.get().strip())

    def _folder_block(self, parent, title, hint, var, cmd):
        tk.Label(parent, text=title, font=self.f_h, bg=C["surface"], fg=C["ink"]).pack(anchor="w")
        tk.Label(parent, text=hint, font=self.f_small, bg=C["surface"], fg=C["muted"]).pack(anchor="w", pady=(0, 4))
        row = tk.Frame(parent, bg=C["surface"])
        row.pack(fill=tk.X)
        e = tk.Entry(row, textvariable=var, font=self.f, bg=C["soft"], fg=C["ink"],
                     relief=tk.FLAT, highlightbackground=C["line"], highlightthickness=1)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        self._btn(row, "Ordner wählen", cmd, kind="ghost").pack(side=tk.LEFT, padx=(8, 0))

    def _on_target(self, _v=None) -> None:
        self.target_lbl_var.set(f"ca. {int(self.target_var.get())}")

    def _pick_input(self) -> None:
        p = filedialog.askdirectory(title="Fotos-Ordner wählen")
        if p:
            self.input_var.set(p)
            self._update_found(p)

    def _pick_output(self) -> None:
        p = filedialog.askdirectory(title="Ausgabe-Ordner wählen")
        if p:
            self.output_var.set(p)

    def _update_found(self, path: str) -> None:
        self.found_var.set("Zähle Bilder…")

        def work():
            try:
                from .scan import find_images
                n = len(find_images(Path(path)))
                msg = f"✓ {n} Bilder gefunden" if n else "Keine Bilder in diesem Ordner gefunden"
            except Exception:
                msg = ""
            self.after(0, lambda: self.found_var.set(msg))

        threading.Thread(target=work, daemon=True).start()

    # ---------- Schritt 2: Optionen ----------
    def _step_options(self) -> None:
        self._clear_content()
        c = self.content
        tk.Label(c, text="Schritt 2 von 4", font=self.f_small, bg=C["surface"], fg=C["muted"]).pack(anchor="w")
        tk.Label(c, text="Was soll der Assistent beachten?", font=self.f_big, bg=C["surface"], fg=C["ink"]).pack(anchor="w", pady=(2, 4))
        tk.Label(c, text="Die Standardeinstellungen passen für die meisten. Du kannst einfach auf „Auswahl starten“.",
                 font=self.f_small, bg=C["surface"], fg=C["muted"], wraplength=560, justify="left").pack(anchor="w", pady=(0, 12))

        self._switch_row(c, "Schlechte Gesichter abwerten (Augen zu, angeschnitten)", self.faces_var)
        self._switch_row(c, "Aus Serien nur die besten 1–2 behalten", self.bursts_var)
        self._switch_row(c, "Screenshots & Dokumente separat sammeln", self.aside_var)
        self._switch_row(c, "Ortsnamen aus GPS bestimmen (Internet)", self.geocode_var)
        self._switch_row(c, "Nicht alles vom ersten Tag (Tages-Abdeckung)", self.coverage_var)
        self._switch_row(c, "Nicht immer dieselbe Person (Personen-Balance)", self.people_var)
        self._switch_row(c, "Finger vor der Linse aussortieren", self.finger_var)
        self._switch_row(c, "Kapitel-Karte als HTML erzeugen", self.map_var)

        # „Mehr einstellen“ (KI)
        self.adv_toggle = tk.Label(c, text=("▾ Weniger" if self._advanced_open else "▸ Mehr einstellen (KI-Bewertung)"),
                                   font=self.f, bg=C["surface"], fg=C["accent_ink"], cursor="hand2")
        self.adv_toggle.pack(anchor="w", pady=(12, 0))
        self.adv_toggle.bind("<Button-1>", lambda _e: self._toggle_advanced())
        self.adv_box = tk.Frame(c, bg=C["soft"])
        if self._advanced_open:
            self._fill_advanced()

    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self.adv_toggle.configure(text="▾ Weniger")
            self._fill_advanced()
        else:
            self.adv_toggle.configure(text="▸ Mehr einstellen (KI-Bewertung)")
            self.adv_box.pack_forget()
            for w in self.adv_box.winfo_children():
                w.destroy()

    def _fill_advanced(self) -> None:
        self.adv_box.pack(fill=tk.X, pady=(8, 0))
        inner = tk.Frame(self.adv_box, bg=C["soft"])
        inner.pack(fill=tk.X, padx=14, pady=12)
        self._switch_row(inner, "KI-Bewertung aktivieren (Anthropic API, kostenpflichtig)", self.ai_var)
        self._switch_row(inner, "Nur Kosten schätzen (kein echter KI-Lauf)", self.dry_var)
        tk.Label(inner, text="API-Key (optional)", font=self.f_small, bg=C["soft"], fg=C["muted"]).pack(anchor="w", pady=(6, 0))
        tk.Entry(inner, textvariable=self.api_key_var, font=self.f, show="•", bg=C["surface"],
                 relief=tk.FLAT, highlightbackground=C["line"], highlightthickness=1).pack(fill=tk.X, ipady=5)

    # ---------- Schritt 3: Lauf ----------
    def _step_run(self) -> None:
        self._clear_content()
        c = self.content
        tk.Label(c, text="Schritt 3 von 4", font=self.f_small, bg=C["surface"], fg=C["muted"]).pack(anchor="w")
        tk.Label(c, text="Der Assistent wählt aus…", font=self.f_big, bg=C["surface"], fg=C["ink"]).pack(anchor="w", pady=(2, 16))

        tk.Label(c, textvariable=self.phase_var, font=self.f_h, bg=C["surface"], fg=C["ink"]).pack(anchor="w")
        self.bar_bg = tk.Frame(c, bg=C["line"], height=12)
        self.bar_bg.pack(fill=tk.X, pady=(6, 2))
        self.bar_fg = tk.Frame(self.bar_bg, bg=C["accent"], height=12, width=0)
        self.bar_fg.place(x=0, y=0, relheight=1.0, relwidth=0.0)
        tk.Label(c, textvariable=self.detail_var, font=self.f_small, bg=C["surface"], fg=C["muted"],
                 anchor="w").pack(fill=tk.X)

        logwrap = tk.Frame(c, bg=C["soft"])
        logwrap.pack(fill=tk.BOTH, expand=True, pady=(14, 10))
        self.log = tk.Text(logwrap, height=8, wrap=tk.WORD, state=tk.DISABLED, bg=C["soft"],
                           fg=C["muted"], relief=tk.FLAT, font=self.f_small, padx=10, pady=8,
                           highlightthickness=0)
        self.log.pack(fill=tk.BOTH, expand=True)

        self.cancel_btn = self._btn(c, "Abbrechen", self._do_cancel, kind="ghost")
        self.cancel_btn.pack(anchor="e")

        self._start_run()

    def _start_run(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._cancel.clear()
        self.phase_var.set("Start…")
        self._set_bar(0.0)
        cfg = PipelineConfig(
            input_dir=Path(self.input_var.get().strip()).resolve(),
            output_dir=Path(self.output_var.get().strip()).resolve(),
            target_n=int(self.target_var.get()),
            geocode=bool(self.geocode_var.get()),
            ai_review=bool(self.ai_var.get()),
            dry_run=bool(self.dry_var.get()),
            enable_faces=bool(self.faces_var.get()),
            enable_bursts=bool(self.bursts_var.get()),
            enable_document_aside=bool(self.aside_var.get()),
            enable_finger_filter=bool(self.finger_var.get()),
            coverage_intensity=0.5 if self.coverage_var.get() else 0.0,
            people_balance_intensity=0.5 if self.people_var.get() else 0.0,
            enable_map_preview=bool(self.map_var.get()),
        )
        key = self.api_key_var.get().strip()
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
        self._worker = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._worker.start()

    def _run(self, cfg: PipelineConfig) -> None:
        import sys

        class QW:
            def __init__(self, q, orig):
                self.q, self.orig, self._buf = q, orig, ""

            def write(self, s):
                if self.orig:
                    try:
                        self.orig.write(s)
                    except Exception:
                        pass
                self._buf += s
                while True:
                    nl, cr = self._buf.find("\n"), self._buf.find("\r")
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

            def flush(self):
                pass

        old_o, old_e = sys.stdout, sys.stderr
        sys.stdout = QW(self._log_q, old_o)
        sys.stderr = QW(self._log_q, old_e)
        try:
            res = run_pipeline(cfg, progress=lambda l, f, *a: self._prog_q.put((l, f)),
                               cancel_check=self._cancel.is_set)
            self._result = res
            self._last_output = res.get("output_dir") or cfg.output_dir
            self._prog_q.put(("Fertig", 1.0))
            self.after(0, lambda: self._goto(3))
        except PipelineCancelled:
            self._log_q.put(("line", "Abgebrochen – es wurden keine Ordner geschrieben."))
            self.after(0, lambda: self.phase_var.set("Abgebrochen"))
            self.after(0, lambda: self.cancel_btn.configure(text="Zurück", fg=C["accent_ink"]))
            self.after(0, lambda: self.cancel_btn.bind("<Button-1>", lambda _e: self._goto(1)))
        except Exception as exc:
            self._log_q.put(("line", f"Fehler: {exc}"))
            self.after(0, lambda: self.phase_var.set("Fehler"))
            self.after(0, lambda e=exc: messagebox.showerror("Fehler", str(e)))
        finally:
            sys.stdout, sys.stderr = old_o, old_e

    def _do_cancel(self) -> None:
        if self._worker and self._worker.is_alive():
            self._cancel.set()
            self.phase_var.set("Wird abgebrochen…")
            self.detail_var.set("stoppt nach dem aktuellen Schritt")

    def _set_bar(self, frac: float) -> None:
        try:
            self.bar_fg.place_configure(relwidth=max(0.0, min(1.0, frac)))
        except tk.TclError:
            pass

    # ---------- Schritt 4: Fertig ----------
    def _step_done(self) -> None:
        self._clear_content()
        c = self.content
        res = self._result or {}
        n_sel = res.get("selected") or len(res.get("order") or [])
        regions = res.get("regions") or []
        tk.Label(c, text="Schritt 4 von 4", font=self.f_small, bg=C["surface"], fg=C["muted"]).pack(anchor="w")
        tk.Label(c, text="Fertig! 🎉", font=self.f_big, bg=C["surface"], fg=C["ink"]).pack(anchor="w", pady=(2, 10))

        info = tk.Frame(c, bg=C["soft"])
        info.pack(fill=tk.X)
        inn = tk.Frame(info, bg=C["soft"])
        inn.pack(fill=tk.X, padx=14, pady=12)
        tk.Label(inn, text=f"{n_sel} Bilder ausgewählt", font=self.f_h, bg=C["soft"], fg=C["ink"]).pack(anchor="w")
        if regions:
            tk.Label(inn, text="Kapitel: " + ", ".join(str(r) for r in regions[:8]) + ("…" if len(regions) > 8 else ""),
                     font=self.f_small, bg=C["soft"], fg=C["muted"], wraplength=540, justify="left").pack(anchor="w", pady=(4, 0))
        tk.Label(inn, text=f"Ordner: {self._last_output}", font=self.f_small, bg=C["soft"],
                 fg=C["muted"], wraplength=540, justify="left").pack(anchor="w", pady=(4, 0))

        tk.Label(c, text="Jetzt empfohlen: die Auswahl kurz durchsehen und einzelne Bilder raus-/reinnehmen.",
                 font=self.f, bg=C["surface"], fg=C["ink"], wraplength=560, justify="left").pack(anchor="w", pady=(16, 10))

        self._btn(c, "Auswahl prüfen  →", self._open_review, kind="primary").pack(anchor="w")
        row = tk.Frame(c, bg=C["surface"])
        row.pack(anchor="w", pady=(10, 0))
        self._btn(row, "Ordner öffnen", self._open_folder, kind="ghost").pack(side=tk.LEFT)
        if self.map_var.get():
            self._btn(row, "Karte zeigen", self._open_map, kind="ghost").pack(side=tk.LEFT, padx=(8, 0))
        self._btn(row, "Neues Fotobuch", lambda: self._goto(0), kind="ghost").pack(side=tk.LEFT, padx=(8, 0))

    def _open_review(self) -> None:
        res = self._result or {}
        photos = res.get("photo_objects")
        plan = res.get("plan")
        out = self._last_output
        try:
            if photos is None or plan is None:
                from .review_export import load_photos_from_csv, plan_from_photos
                csv = Path(out) / "photos_analysis.csv"
                if not csv.is_file():
                    messagebox.showinfo("Keine Auswahl", "Keine Analyse gefunden.")
                    return
                photos = load_photos_from_csv(csv)
                plan = plan_from_photos(photos)
            if not any(getattr(p, "is_selected", False) for p in photos):
                messagebox.showinfo("Keine Auswahl", "Es sind keine Bilder ausgewählt.")
                return
            from .review_gui import open_review
            open_review(self, photos, plan, Path(out))
        except Exception as exc:
            messagebox.showerror("Auswahl prüfen", str(exc))

    def _open_map(self) -> None:
        res = self._result or {}
        try:
            from .map_preview import open_map_preview
            open_map_preview(self, res.get("photo_objects") or [], res.get("plan"),
                             Path(self._last_output), order=res.get("order"))
        except Exception as exc:
            messagebox.showerror("Karte", str(exc))

    def _open_folder(self) -> None:
        try:
            if self._last_output:
                os.startfile(str(self._last_output))  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("Ordner", str(self._last_output))

    # ---------- Hilfe ----------
    def _show_help(self) -> None:
        messagebox.showinfo(
            "Hilfe – so funktioniert’s",
            "1) Fotos-Ordner und einen neuen Ausgabe-Ordner wählen, Zielanzahl einstellen.\n"
            "2) Optionen prüfen (Standard passt meist) → „Auswahl starten“.\n"
            "3) Warten – der Balken zeigt den Fortschritt, „Abbrechen“ ist jederzeit möglich.\n"
            "4) „Auswahl prüfen“: Bilder per Klick raus-/reinnehmen, dann speichern.\n\n"
            "Das Ergebnis liegt im Ausgabe-Ordner unter „selected“.",
        )

    # ---------- Queues ----------
    def _drain(self) -> None:
        last_status = None
        try:
            while True:
                mode, text = self._log_q.get_nowait()
                if mode == "status":
                    last_status = text
                else:
                    self._log_line(text)
        except queue.Empty:
            pass
        last_prog = None
        try:
            while True:
                last_prog = self._prog_q.get_nowait()
        except queue.Empty:
            pass
        if last_prog is not None:
            label, frac = last_prog
            self.phase_var.set(label)
            self._set_bar(float(frac))
        if last_status is not None:
            t = last_status.strip()
            self.detail_var.set(t[:90] + "…" if len(t) > 90 else t)
        self.after(120, self._drain)

    def _log_line(self, text: str) -> None:
        try:
            self.log.configure(state=tk.NORMAL)
            self.log.insert(tk.END, text + "\n")
            self.log.see(tk.END)
            self.log.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _set_icon(self) -> None:
        try:
            from PIL import Image, ImageDraw, ImageTk
            n = 64
            img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([2, 2, n - 3, n - 3], radius=12, fill=C["accent"])
            d.rectangle([14, 18, 50, 46], fill="#FFFDFB")
            d.polygon([(18, 44), (28, 30), (36, 44)], fill="#9A8E80")
            d.ellipse([40, 22, 47, 29], fill="#E8B04B")
            self._icon_img = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass


def _report_startup_error() -> None:
    import traceback
    err = traceback.format_exc()
    try:
        (Path(__file__).resolve().parent.parent / "fehler_beim_start.txt").write_text(err, encoding="utf-8")
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("Fotobuch-Assistent – Startfehler", "Konnte nicht starten:\n\n" + err)
        r.destroy()
    except Exception:
        print(err)


def main() -> int:
    try:
        WizardApp().mainloop()
        return 0
    except Exception:
        _report_startup_error()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
