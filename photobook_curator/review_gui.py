"""Thumbnail-Review: Auswahl prüfen, Bilder rausnehmen oder Alternativen hinzufügen."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from .models import BookPlan, Photo
from .review_export import (
    apply_manual_selection,
    candidate_alternatives,
    chapter_sections,
)
from .utils import load_image

COLORS = {
    "bg": "#F3EFE7",
    "surface": "#FFFCF7",
    "ink": "#1F1A17",
    "muted": "#6E645C",
    "line": "#D9D0C4",
    "accent": "#2F5D50",
    "accent_hover": "#244A40",
    "reject": "#8B3A2C",
    "keep_border": "#2F5D50",
    "reject_border": "#C4B8AA",
}

THUMB = 140


class ReviewWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        photos: list[Photo],
        plan: BookPlan,
        output_dir: Path,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.title("Auswahl prüfen")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.configure(bg=COLORS["bg"])

        self.photos = photos
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.on_saved = on_saved

        # Startzustand: aktuell ausgewählte (Baseline bleibt für die Anzeige)
        self.kept: set[int] = {i for i, p in enumerate(photos) if p.is_selected}
        self.baseline: set[int] = set(self.kept)
        self._photo_images: list[ImageTk.PhotoImage] = []  # Referenzen halten
        self._thumb_cache: dict[int, ImageTk.PhotoImage] = {}
        self._tile_state: dict[tuple[str, int], dict] = {}
        self._thumb_labels: dict[int, list[tk.Label]] = {}
        self._pending_thumbs: set[int] = set()
        self._load_queue: queue.Queue[int | None] = queue.Queue()
        self._ready_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._loader = threading.Thread(target=self._thumb_worker, daemon=True)
        self._loader.start()

        self._setup_style()
        self._build()
        self._render()
        self.after(40, self._drain_thumbs)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Rev.TFrame", background=COLORS["bg"])
        style.configure("RevCard.TFrame", background=COLORS["surface"])
        style.configure(
            "RevHead.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "RevMuted.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "RevSave.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 8),
            background=COLORS["accent"],
            foreground="#FFFFFF",
        )
        style.map(
            "RevSave.TButton",
            background=[("active", COLORS["accent_hover"])],
        )

    def _build(self) -> None:
        hero = ttk.Frame(self, style="Rev.TFrame")
        hero.pack(fill=tk.X)
        band = tk.Frame(hero, bg=COLORS["accent"], padx=20, pady=14)
        band.pack(fill=tk.X)
        tk.Label(
            band,
            text="Auswahl prüfen",
            bg=COLORS["accent"],
            fg="#F7F3EC",
            font=("Georgia", 15, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            band,
            text="Klick auf ein Bild = raus / wieder rein. Unten Alternativen zum Hinzufügen.",
            bg=COLORS["accent"],
            fg="#D5E4DE",
            font=("Segoe UI", 10),
        ).pack(anchor=tk.W, pady=(4, 0))

        bar = ttk.Frame(self, style="Rev.TFrame", padding=(16, 10))
        bar.pack(fill=tk.X)
        self.count_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.count_var, style="RevHead.TLabel").pack(side=tk.LEFT)
        ttk.Button(bar, text="Speichern & Ordner neu schreiben", style="RevSave.TButton", command=self._save).pack(
            side=tk.RIGHT
        )
        ttk.Button(bar, text="Abbrechen", command=self._close).pack(side=tk.RIGHT, padx=(0, 8))

        container = ttk.Frame(self, style="Rev.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.canvas = tk.Canvas(container, bg=COLORS["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = ttk.Frame(self.canvas, style="Rev.TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._win, width=e.width),
        )
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event) -> None:
        if self.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _thumb_worker(self) -> None:
        while True:
            idx = self._load_queue.get()
            if idx is None:
                break
            photo = self.photos[idx]
            try:
                img = load_image(photo.path)
                img.thumbnail((THUMB, THUMB), Image.Resampling.LANCZOS)
                canvas_img = Image.new("RGB", (THUMB, THUMB), (245, 241, 233))
                x = (THUMB - img.width) // 2
                y = (THUMB - img.height) // 2
                canvas_img.paste(img, (x, y))
                self._ready_queue.put((idx, canvas_img))
            except Exception:
                self._ready_queue.put((idx, None))

    def _request_thumb(self, idx: int) -> None:
        if idx in self._thumb_cache or idx in self._pending_thumbs:
            return
        self._pending_thumbs.add(idx)
        self._load_queue.put(idx)

    def _drain_thumbs(self) -> None:
        try:
            while True:
                idx, canvas_img = self._ready_queue.get_nowait()
                self._pending_thumbs.discard(idx)
                if canvas_img is None:
                    continue
                tk_img = ImageTk.PhotoImage(canvas_img)
                self._thumb_cache[idx] = tk_img
                self._photo_images.append(tk_img)
                for lbl in self._thumb_labels.get(idx, []):
                    try:
                        if lbl.winfo_exists():
                            lbl.configure(image=tk_img, text="", width=0, height=0)
                    except tk.TclError:
                        pass
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(40, self._drain_thumbs)

    def _update_count(self) -> None:
        self.count_var.set(f"{len(self.kept)} Bilder ausgewählt")

    def _render(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._tile_state.clear()
        self._thumb_labels.clear()
        self._update_count()

        display = sorted(self.baseline | self.kept)
        sections = chapter_sections(self.photos, display)
        if not sections:
            ttk.Label(
                self.inner,
                text="Keine Bilder in der Auswahl. Füge unten Alternativen hinzu oder brich ab.",
                style="RevMuted.TLabel",
            ).pack(anchor=tk.W, padx=8, pady=16)

        for title, folder, indices in sections:
            show_alts = not folder.startswith("99_")
            self._section(title, folder, indices, alternatives=show_alts)

        from .documents import ASIDE_FOLDER, aside_indices

        aside = [
            i
            for i in aside_indices(self.photos)
            if i not in self.kept and not self.photos[i].is_duplicate
        ]
        if aside:
            aside.sort(
                key=lambda i: (
                    self.photos[i].aside_type or "",
                    self.photos[i].filename,
                )
            )
            self._alt_block(
                "Optional: Dokumente & Screenshots (tippen = ins Buch)",
                aside[:40],
                folder=ASIDE_FOLDER,
            )

        if not sections:
            alts = [
                i
                for i, p in enumerate(self.photos)
                if p.is_candidate
                and not p.is_duplicate
                and not getattr(p, "is_aside", False)
                and i not in self.kept
            ]
            alts.sort(
                key=lambda i: self.photos[i].final_score or self.photos[i].technical_score,
                reverse=True,
            )
            if alts:
                self._alt_block("Vorschläge", alts[:16])

    def _section(
        self,
        title: str,
        folder: str,
        indices: list[int],
        alternatives: bool = False,
    ) -> None:
        wrap = ttk.Frame(self.inner, style="Rev.TFrame", padding=(8, 10))
        wrap.pack(fill=tk.X, anchor=tk.NW)
        ttk.Label(wrap, text=title, style="RevHead.TLabel").pack(anchor=tk.W)
        ttk.Label(
            wrap,
            text="Grün = dabei · Grau/durchgestrichen = entfernt (nochmal klicken = wieder rein)",
            style="RevMuted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))

        grid = ttk.Frame(wrap, style="Rev.TFrame")
        grid.pack(fill=tk.X)
        cols = 5
        for n, idx in enumerate(indices):
            self._tile(grid, idx, n % cols, n // cols, mode="keep", folder=folder)

        if alternatives:
            alts = [i for i in candidate_alternatives(self.photos, folder) if i not in self.kept]
            if alts:
                self._alt_block(
                    f"Alternativen für „{title}“", alts, parent=wrap, folder=folder
                )

    def _alt_block(
        self,
        title: str,
        indices: list[int],
        parent: Optional[ttk.Frame] = None,
        folder: str = "",
    ) -> None:
        host = parent or self.inner
        box = ttk.Frame(host, style="Rev.TFrame", padding=(0, 8, 0, 0))
        box.pack(fill=tk.X)
        ttk.Label(box, text=title, style="RevMuted.TLabel").pack(anchor=tk.W)
        grid = ttk.Frame(box, style="Rev.TFrame")
        grid.pack(fill=tk.X, pady=(4, 0))
        cols = 5
        for n, idx in enumerate(indices):
            self._tile(grid, idx, n % cols, n // cols, mode="add", folder=folder)

    def _apply_tile_visual(self, key: tuple[str, int]) -> None:
        state = self._tile_state.get(key)
        if not state:
            return
        mode, idx = key
        kept = idx in self.kept
        border = COLORS["keep_border"] if kept else COLORS["reject_border"]
        outer: tk.Frame = state["outer"]
        info: tk.Label = state["info"]
        inner: tk.Frame = state["inner"]
        try:
            outer.configure(bg=border)
            info.configure(
                fg=COLORS["muted"] if (mode == "keep" and not kept) else COLORS["ink"]
            )
        except tk.TclError:
            return

        old = state.get("overlay")
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
            state["overlay"] = None

        if mode == "keep" and not kept:
            overlay = tk.Label(
                inner,
                text="ENTFERNT",
                bg=COLORS["reject"],
                fg="white",
                font=("Segoe UI Semibold", 8),
            )
            overlay.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
            state["overlay"] = overlay
        elif mode == "add" and idx not in self.kept:
            overlay = tk.Label(
                inner,
                text="+ HINZUFÜGEN",
                bg=COLORS["accent"],
                fg="white",
                font=("Segoe UI Semibold", 8),
            )
            overlay.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
            state["overlay"] = overlay

    def _tile(
        self,
        parent: ttk.Frame,
        idx: int,
        col: int,
        row: int,
        mode: str,
        folder: str = "",
    ) -> None:
        kept = idx in self.kept
        border = COLORS["keep_border"] if kept else COLORS["reject_border"]
        outer = tk.Frame(parent, bg=border, padx=2, pady=2)
        outer.grid(row=row, column=col, padx=6, pady=6, sticky=tk.NW)

        inner = tk.Frame(outer, bg=COLORS["surface"])
        inner.pack()

        photo = self.photos[idx]
        caption = photo.filename
        if len(caption) > 22:
            caption = caption[:19] + "…"
        meta = photo.scene_type or photo.chapter_type or ""
        score = photo.final_score or photo.technical_score

        tk_img = self._thumb_cache.get(idx)
        if tk_img is not None:
            lbl = tk.Label(inner, image=tk_img, bg=COLORS["surface"], cursor="hand2")
        else:
            lbl = tk.Label(
                inner,
                text="…",
                width=16,
                height=8,
                bg=COLORS["line"],
                cursor="hand2",
                fg=COLORS["muted"],
                font=("Segoe UI", 10),
            )
            self._thumb_labels.setdefault(idx, []).append(lbl)
            self._request_thumb(idx)
        lbl.pack()

        info = tk.Label(
            inner,
            text=f"{caption}\n{meta} · {score:.0f}",
            bg=COLORS["surface"],
            fg=COLORS["muted"] if (mode == "keep" and not kept) else COLORS["ink"],
            font=("Segoe UI", 8),
            justify=tk.CENTER,
        )
        info.pack(pady=(4, 2))

        key = (mode, idx)
        self._tile_state[key] = {
            "outer": outer,
            "inner": inner,
            "info": info,
            "lbl": lbl,
            "overlay": None,
        }
        self._apply_tile_visual(key)

        warn = None
        if getattr(photo, "finger_on_lens", False) or "finger_on_lens" in photo.flags:
            warn = "Finger"
        elif getattr(photo, "bad_face", False) or "eyes_closed" in photo.flags:
            warn = (
                "Augen zu"
                if getattr(photo, "eyes_closed", False) or "eyes_closed" in photo.flags
                else "Gesicht?"
            )
        if warn:
            badge = tk.Label(
                inner,
                text=warn,
                bg="#A65B2A",
                fg="white",
                font=("Segoe UI Semibold", 7),
            )
            badge.place(relx=0.02, rely=0.02, anchor=tk.NW)

        def toggle(_event=None, i=idx, m=mode, folder_name=folder):
            if m == "add":
                self.kept.add(i)
                self.baseline.add(i)
                if folder_name:
                    self.photos[i].chapter_folder = folder_name
                    if folder_name.startswith("99_") or getattr(self.photos[i], "is_aside", False):
                        self.photos[i].chapter_type = "Optional"
                        self.photos[i].region = self.photos[i].region or "Optional"
                    else:
                        self.photos[i].chapter_type = (
                            "Transit"
                            if "Transit" in folder_name
                            else "Essen"
                            if folder_name.endswith("essen")
                            else "Hauptteil"
                        )
                # Struktur ändert sich (Kapitel/Alternativen) → neu zeichnen
                self._render()
            else:
                if i in self.kept:
                    self.kept.remove(i)
                else:
                    self.kept.add(i)
                self._update_count()
                self._apply_tile_visual(("keep", i))

        for widget in (lbl, info, inner, outer):
            widget.bind("<Button-1>", toggle)

    def _save(self) -> None:
        if not self.kept:
            if not messagebox.askyesno(
                "Keine Bilder",
                "Es ist kein Bild mehr ausgewählt. Trotzdem speichern (leere Auswahl)?",
            ):
                return
        try:
            order = apply_manual_selection(
                self.photos,
                self.plan,
                sorted(self.kept),
                self.output_dir,
            )
        except Exception as exc:
            messagebox.showerror("Fehler beim Speichern", str(exc))
            return
        messagebox.showinfo(
            "Gespeichert",
            f"{len(order)} Bilder geschrieben nach:\n{self.output_dir / 'selected'}",
        )
        if self.on_saved:
            self.on_saved()
        self._close()

    def _close(self) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self._load_queue.put(None)
        self.destroy()


def open_review(
    master: tk.Misc,
    photos: list[Photo],
    plan: BookPlan,
    output_dir: Path,
    on_saved: Optional[Callable[[], None]] = None,
) -> ReviewWindow:
    win = ReviewWindow(master, photos, plan, output_dir, on_saved=on_saved)
    win.transient(master)
    win.focus_set()
    return win
