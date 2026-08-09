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
from .selection_draft import (
    apply_selection_draft,
    load_selection_draft,
    save_selection_draft,
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
# Wenige PhotoImage-Updates pro Tick → weniger Ruckeln beim Scrollen
_THUMBS_PER_TICK = 4
_SLIDE_MAX = 960  # max. Kantenlänge in der Diashow


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
        self.minsize(900, 640)
        self.resizable(True, True)
        self.configure(bg=COLORS["bg"])
        self._open_large()

        self.photos = photos
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.on_saved = on_saved

        # Startzustand: Auswahl aus CSV, ggf. Entwurf überschreibt/ergänzt
        self.kept: set[int] = {i for i, p in enumerate(photos) if p.is_selected}
        self._draft_note = ""
        draft = load_selection_draft(self.output_dir)
        if draft and draft.get("kept"):
            applied = apply_selection_draft(photos, draft)
            if applied:
                self.kept = set(applied)
                self._draft_note = (
                    f"Entwurf geladen ({len(self.kept)} Bilder) – "
                    f"zuletzt {str(draft.get('updated_at') or '')[:19]}"
                )
        self.baseline: set[int] = set(self.kept)
        self._photo_images: list[ImageTk.PhotoImage] = []  # Referenzen halten
        self._thumb_cache: dict[int, ImageTk.PhotoImage] = {}
        self._slide_cache: dict[int, ImageTk.PhotoImage] = {}
        self._tile_state: dict[tuple[str, int], dict] = {}
        self._thumb_labels: dict[int, list[tk.Label]] = {}
        self._pending_thumbs: set[int] = set()
        self._load_queue: queue.Queue[int | None] = queue.Queue()
        self._ready_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._slide_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._pending_slides: set[int] = set()
        self._scroll_job: str | None = None
        self._wheel_bound = False
        self._grid_cols = 6
        self._added_grid: ttk.Frame | None = None
        self._added_count = 0
        self._slideshow = False
        self._slide_indices: list[int] = []
        self._slide_pos = 0
        self._slide_img_ref: ImageTk.PhotoImage | None = None
        self._loader = threading.Thread(target=self._thumb_worker, daemon=True)
        self._loader.start()

        self._setup_style()
        self._build()
        self._render()
        self._autosave_draft()
        self.after(50, self._drain_thumbs)
        self.after(60, self._drain_slides)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Left>", self._slide_key_prev)
        self.bind("<Right>", self._slide_key_next)
        self.bind("<space>", self._slide_key_toggle)
        self.bind("<Return>", self._slide_key_toggle)
        self.bind("<Escape>", self._slide_key_escape)
        self.bind("<Delete>", self._slide_key_remove)
        self.bind("<BackSpace>", self._slide_key_remove)

    def _open_large(self) -> None:
        """Groß öffnen (möglichst maximiert), frei skalierbar."""
        try:
            self.update_idletasks()
            # Windows: maximiert; sonst ~92% der Bildschirmfläche
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            sw = max(1024, int(self.winfo_screenwidth()))
            sh = max(700, int(self.winfo_screenheight()))
            w = int(sw * 0.92)
            h = int(sh * 0.88)
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except tk.TclError:
            self.geometry("1200x800")

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
        self._hero_hint = tk.Label(
            band,
            text="Raster: Klick = raus/rein · Diashow: großes Bild, Pfeile + Leertaste.",
            bg=COLORS["accent"],
            fg="#D5E4DE",
            font=("Segoe UI", 10),
        )
        self._hero_hint.pack(anchor=tk.W, pady=(4, 0))

        bar = ttk.Frame(self, style="Rev.TFrame", padding=(16, 10))
        bar.pack(fill=tk.X)
        self.count_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.count_var, style="RevHead.TLabel").pack(side=tk.LEFT)
        self.mode_btn = ttk.Button(
            bar, text="Diashow-Ansicht", command=self._toggle_slideshow
        )
        self.mode_btn.pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(bar, text="Speichern & Ordner neu schreiben", style="RevSave.TButton", command=self._save).pack(
            side=tk.RIGHT
        )
        ttk.Button(bar, text="Schließen (Entwurf bleibt)", command=self._close).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        if self._draft_note:
            ttk.Label(self, text=self._draft_note, style="RevMuted.TLabel").pack(
                anchor=tk.W, padx=16, pady=(0, 4)
            )
        ttk.Label(
            self,
            text="Änderungen werden automatisch als selection_draft.json gesichert "
            "(Absturz/Pause → später „Auswahl prüfen“ fortsetzen, ohne neue KI).",
            style="RevMuted.TLabel",
        ).pack(anchor=tk.W, padx=16, pady=(0, 6))

        self._body = ttk.Frame(self, style="Rev.TFrame")
        self._body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self._grid_host = ttk.Frame(self._body, style="Rev.TFrame")
        self._grid_host.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self._grid_host, bg=COLORS["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(self._grid_host, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = ttk.Frame(self.canvas, style="Rev.TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.inner.bind("<Configure>", self._schedule_scrollregion)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # Mausrad nur über dem Canvas – nicht global (weniger Konflikte/Ruckeln)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # Linux
        self.canvas.bind("<Button-4>", lambda e: self._scroll_units(-3))
        self.canvas.bind("<Button-5>", lambda e: self._scroll_units(3))

        self._slide_host = ttk.Frame(self._body, style="Rev.TFrame")
        self._build_slideshow_ui()

    def _schedule_scrollregion(self, _event=None) -> None:
        if self._scroll_job is not None:
            try:
                self.after_cancel(self._scroll_job)
            except Exception:
                pass
        self._scroll_job = self.after(80, self._update_scrollregion)

    def _update_scrollregion(self) -> None:
        self._scroll_job = None
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_canvas_configure(self, event) -> None:
        try:
            self.canvas.itemconfigure(self._win, width=event.width)
        except tk.TclError:
            return
        # Spaltenanzahl an Fensterbreite anpassen
        cols = max(4, min(10, int(event.width) // (THUMB + 28)))
        if cols != self._grid_cols:
            self._grid_cols = cols

    def _bind_wheel(self, _event=None) -> None:
        if not self._wheel_bound:
            self.bind_all("<MouseWheel>", self._on_mousewheel)
            self._wheel_bound = True

    def _unbind_wheel(self, _event=None) -> None:
        if self._wheel_bound:
            try:
                self.unbind_all("<MouseWheel>")
            except Exception:
                pass
            self._wheel_bound = False

    def _scroll_units(self, units: int) -> None:
        if self.winfo_exists():
            self.canvas.yview_scroll(units, "units")

    def _on_mousewheel(self, event) -> None:
        # Nur scrollen, wenn Zeiger über diesem Review-Fenster liegt
        try:
            if not self.winfo_exists():
                return
            x, y = self.winfo_pointerxy()
            widget = self.winfo_containing(x, y)
            if widget is None:
                return
            # Gehört der Widget-Pfad zu diesem Fenster?
            w = widget
            ok = False
            while w is not None:
                if w == self or w == self.canvas or w == self.inner:
                    ok = True
                    break
                w = w.master if hasattr(w, "master") else None
            if not ok:
                return
        except tk.TclError:
            return
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return
        # Größere Schritte, weniger Events → spürbar flüssiger
        steps = -1 if delta > 0 else 1
        if abs(delta) >= 120:
            steps = int(-1 * (delta / 120))
        self._scroll_units(steps * 2)

    def _build_slideshow_ui(self) -> None:
        host = self._slide_host
        tip = ttk.Label(
            host,
            text="← → blättern · Leertaste = raus/rein · Entf = entfernen · Esc = zurück zum Raster",
            style="RevMuted.TLabel",
        )
        tip.pack(anchor=tk.W, pady=(0, 8))

        stage = tk.Frame(host, bg=COLORS["ink"], padx=8, pady=8)
        stage.pack(fill=tk.BOTH, expand=True)
        self._slide_image_lbl = tk.Label(
            stage,
            text="Bild wird geladen…",
            bg=COLORS["ink"],
            fg="#E8E2D8",
            font=("Segoe UI", 12),
            cursor="hand2",
        )
        self._slide_image_lbl.pack(fill=tk.BOTH, expand=True)
        self._slide_image_lbl.bind("<Button-1>", self._slide_toggle_current)

        meta = ttk.Frame(host, style="Rev.TFrame", padding=(0, 10, 0, 0))
        meta.pack(fill=tk.X)
        self._slide_status = tk.StringVar(value="")
        self._slide_caption = tk.StringVar(value="")
        ttk.Label(meta, textvariable=self._slide_status, style="RevHead.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(meta, textvariable=self._slide_caption, style="RevMuted.TLabel").pack(
            anchor=tk.W, pady=(2, 0)
        )

        controls = ttk.Frame(host, style="Rev.TFrame", padding=(0, 12, 0, 0))
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="← Zurück", command=self._slide_prev).pack(side=tk.LEFT)
        ttk.Button(controls, text="Weiter →", command=self._slide_next).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._slide_toggle_btn = ttk.Button(
            controls,
            text="Rausnehmen",
            style="RevSave.TButton",
            command=self._slide_toggle_current,
        )
        self._slide_toggle_btn.pack(side=tk.LEFT, padx=(24, 0))
        ttk.Button(
            controls, text="Zurück zum Raster", command=self._exit_slideshow
        ).pack(side=tk.RIGHT)

    def _thumb_worker(self) -> None:
        while True:
            idx = self._load_queue.get()
            if idx is None:
                break
            # Negative Indizes = Diashow-Vollbild; positive = Thumbnail
            want_slide = idx < 0
            real = (-idx - 1) if want_slide else idx
            photo = self.photos[real]
            try:
                img = load_image(photo.path)
                if want_slide:
                    img.thumbnail((_SLIDE_MAX, _SLIDE_MAX), Image.Resampling.BILINEAR)
                    self._slide_queue.put((real, img.copy()))
                else:
                    # BILINEAR ist für Thumbs schnell genug
                    img.thumbnail((THUMB, THUMB), Image.Resampling.BILINEAR)
                    canvas_img = Image.new("RGB", (THUMB, THUMB), (245, 241, 233))
                    x = (THUMB - img.width) // 2
                    y = (THUMB - img.height) // 2
                    canvas_img.paste(img, (x, y))
                    self._ready_queue.put((real, canvas_img))
            except Exception:
                if want_slide:
                    self._slide_queue.put((real, None))
                else:
                    self._ready_queue.put((real, None))

    def _request_thumb(self, idx: int) -> None:
        if idx in self._thumb_cache or idx in self._pending_thumbs:
            return
        self._pending_thumbs.add(idx)
        self._load_queue.put(idx)

    def _request_slide(self, idx: int) -> None:
        if idx in self._slide_cache or idx in self._pending_slides:
            return
        self._pending_slides.add(idx)
        # Worker-Konvention: negativer Schlüssel = großes Bild
        self._load_queue.put(-(idx + 1))

    def _drain_thumbs(self) -> None:
        updated = 0
        try:
            while updated < _THUMBS_PER_TICK:
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
                updated += 1
        except queue.Empty:
            pass
        if updated:
            self._schedule_scrollregion()
        if self.winfo_exists():
            # Etwas längerer Abstand, wenn gerade viel geladen wird
            delay = 30 if updated else 80
            self.after(delay, self._drain_thumbs)

    def _drain_slides(self) -> None:
        try:
            while True:
                idx, img = self._slide_queue.get_nowait()
                self._pending_slides.discard(idx)
                if img is None:
                    continue
                tk_img = ImageTk.PhotoImage(img)
                self._slide_cache[idx] = tk_img
                self._photo_images.append(tk_img)
                if (
                    self._slideshow
                    and self._slide_indices
                    and 0 <= self._slide_pos < len(self._slide_indices)
                    and self._slide_indices[self._slide_pos] == idx
                ):
                    self._show_slide_image(idx)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._drain_slides)

    def _update_count(self) -> None:
        self.count_var.set(f"{len(self.kept)} Bilder ausgewählt (Entwurf auto-gespeichert)")
        if self._slideshow:
            self._refresh_slide_meta()

    def _display_indices(self) -> list[int]:
        return sorted(self.baseline | self.kept)

    def _toggle_slideshow(self) -> None:
        if self._slideshow:
            self._exit_slideshow()
        else:
            self._enter_slideshow()

    def _enter_slideshow(self) -> None:
        indices = self._display_indices()
        if not indices:
            messagebox.showinfo(
                "Keine Bilder",
                "Noch keine Auswahl zum Durchblättern. "
                "Füge zuerst Bilder hinzu oder starte die Analyse.",
            )
            return
        current_idx = None
        if self._slide_indices and 0 <= self._slide_pos < len(self._slide_indices):
            current_idx = self._slide_indices[self._slide_pos]
        self._slideshow = True
        self._slide_indices = indices
        if current_idx is not None and current_idx in indices:
            self._slide_pos = indices.index(current_idx)
        else:
            self._slide_pos = 0
        try:
            self._grid_host.pack_forget()
        except tk.TclError:
            pass
        self._slide_host.pack(fill=tk.BOTH, expand=True)
        self.mode_btn.configure(text="Raster-Ansicht")
        self._hero_hint.configure(
            text="Diashow: großes Bild prüfen · Leertaste = raus/rein · Esc = Raster."
        )
        self._unbind_wheel()
        self._show_current_slide()
        try:
            self.focus_set()
        except tk.TclError:
            pass

    def _exit_slideshow(self) -> None:
        if not self._slideshow:
            return
        self._slideshow = False
        try:
            self._slide_host.pack_forget()
        except tk.TclError:
            pass
        self._grid_host.pack(fill=tk.BOTH, expand=True)
        self.mode_btn.configure(text="Diashow-Ansicht")
        self._hero_hint.configure(
            text="Raster: Klick = raus/rein · Diashow: großes Bild, Pfeile + Leertaste."
        )
        # Raster an geänderte Auswahl anpassen
        self._render()

    def _show_current_slide(self) -> None:
        if not self._slide_indices:
            return
        self._slide_pos = max(0, min(self._slide_pos, len(self._slide_indices) - 1))
        idx = self._slide_indices[self._slide_pos]
        self._refresh_slide_meta()
        cached = self._slide_cache.get(idx)
        if cached is not None:
            self._show_slide_image(idx)
        else:
            try:
                self._slide_image_lbl.configure(
                    image="", text="Bild wird geladen…", fg="#E8E2D8"
                )
            except tk.TclError:
                pass
            self._slide_img_ref = None
            self._request_slide(idx)
        # Nachbarn vorladen
        for offset in (1, -1, 2):
            n = self._slide_pos + offset
            if 0 <= n < len(self._slide_indices):
                self._request_slide(self._slide_indices[n])

    def _show_slide_image(self, idx: int) -> None:
        tk_img = self._slide_cache.get(idx)
        if tk_img is None:
            return
        self._slide_img_ref = tk_img
        try:
            self._slide_image_lbl.configure(image=tk_img, text="")
        except tk.TclError:
            pass

    def _refresh_slide_meta(self) -> None:
        if not self._slide_indices:
            self._slide_status.set("Keine Bilder")
            self._slide_caption.set("")
            return
        pos = max(0, min(self._slide_pos, len(self._slide_indices) - 1))
        idx = self._slide_indices[pos]
        photo = self.photos[idx]
        kept = idx in self.kept
        state = "DABEI" if kept else "ENTFERNT"
        self._slide_status.set(
            f"{pos + 1} / {len(self._slide_indices)}  ·  {state}  ·  "
            f"{len(self.kept)} ausgewählt"
        )
        meta = photo.scene_type or photo.chapter_type or ""
        score = photo.final_score or photo.technical_score
        self._slide_caption.set(f"{photo.filename}  ·  {meta}  ·  Score {score:.0f}")
        try:
            self._slide_toggle_btn.configure(
                text="Wieder reinnehmen" if not kept else "Rausnehmen"
            )
        except tk.TclError:
            pass

    def _slide_prev(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if self._slide_pos > 0:
            self._slide_pos -= 1
            self._show_current_slide()

    def _slide_next(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if self._slide_pos < len(self._slide_indices) - 1:
            self._slide_pos += 1
            self._show_current_slide()

    def _slide_toggle_current(self, _event=None) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        idx = self._slide_indices[self._slide_pos]
        if idx in self.kept:
            self.kept.remove(idx)
        else:
            self.kept.add(idx)
            self.baseline.add(idx)
        self._update_count()
        self._autosave_draft()
        # Visuell im Raster vorbereiten, falls Tile existiert
        self._apply_tile_visual(("keep", idx))
        self._refresh_slide_meta()

    def _slide_key_prev(self, _event=None) -> None:
        if self._slideshow:
            self._slide_prev()

    def _slide_key_next(self, _event=None) -> None:
        if self._slideshow:
            self._slide_next()

    def _slide_key_toggle(self, _event=None) -> None:
        if self._slideshow:
            self._slide_toggle_current()
            return "break"

    def _slide_key_remove(self, _event=None) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        idx = self._slide_indices[self._slide_pos]
        if idx in self.kept:
            self.kept.remove(idx)
            self._update_count()
            self._autosave_draft()
            self._apply_tile_visual(("keep", idx))
            self._refresh_slide_meta()
        return "break"

    def _slide_key_escape(self, _event=None) -> None:
        if self._slideshow:
            self._exit_slideshow()
            return "break"

    def _autosave_draft(self) -> None:
        try:
            save_selection_draft(self.output_dir, self.photos, self.kept)
        except Exception:
            pass

    def _ensure_added_section(self) -> ttk.Frame:
        try:
            if self._added_grid is not None and self._added_grid.winfo_exists():
                return self._added_grid
        except tk.TclError:
            pass
        wrap = ttk.Frame(self.inner, style="Rev.TFrame", padding=(8, 10))
        children = self.inner.winfo_children()
        if children:
            wrap.pack(fill=tk.X, anchor=tk.NW, before=children[0])
        else:
            wrap.pack(fill=tk.X, anchor=tk.NW)
        ttk.Label(wrap, text="Neu hinzugefügt (diese Sitzung)", style="RevHead.TLabel").pack(
            anchor=tk.W
        )
        self._added_grid = ttk.Frame(wrap, style="Rev.TFrame")
        self._added_grid.pack(fill=tk.X, pady=(4, 0))
        return self._added_grid

    def _remove_add_tiles(self, idx: int) -> None:
        for key in list(self._tile_state.keys()):
            if key == ("add", idx):
                state = self._tile_state.pop(key)
                try:
                    state["outer"].destroy()
                except tk.TclError:
                    pass
        if idx in self._thumb_labels:
            self._thumb_labels[idx] = [
                lbl for lbl in self._thumb_labels[idx] if lbl.winfo_exists()
            ]

    def _render(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._tile_state.clear()
        self._thumb_labels.clear()
        self._added_grid = None
        self._added_count = 0
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
        cols = self._grid_cols
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
        cols = self._grid_cols
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
                cursor="hand2",
            )
            overlay.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
            state["overlay"] = overlay
            self._bind_tile_click(overlay, state.get("toggle"))
        elif mode == "add" and idx not in self.kept:
            overlay = tk.Label(
                inner,
                text="+ HINZUFÜGEN",
                bg=COLORS["accent"],
                fg="white",
                font=("Segoe UI Semibold", 8),
                cursor="hand2",
            )
            overlay.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
            state["overlay"] = overlay
            # Wichtig: Overlay liegt oben – ohne Bind greift der Klick nicht
            self._bind_tile_click(overlay, state.get("toggle"))

    @staticmethod
    def _bind_tile_click(widget, toggle) -> None:
        if toggle is None or widget is None:
            return
        try:
            widget.bind("<Button-1>", toggle)
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass

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
            cursor="hand2",
        )
        info.pack(pady=(4, 2))

        def toggle(_event=None, i=idx, m=mode, folder_name=folder):
            if m == "add":
                if i in self.kept:
                    return
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
                # Kein volles Neu-Laden: Kachel entfernen + oben als „neu“ zeigen
                self._remove_add_tiles(i)
                grid = self._ensure_added_section()
                col = self._added_count % self._grid_cols
                row = self._added_count // self._grid_cols
                self._added_count += 1
                self._tile(grid, i, col, row, mode="keep", folder=folder_name)
                self._update_count()
                self._autosave_draft()
                self._schedule_scrollregion()
            else:
                if i in self.kept:
                    self.kept.remove(i)
                else:
                    self.kept.add(i)
                self._update_count()
                self._apply_tile_visual(("keep", i))
                self._autosave_draft()

        key = (mode, idx)
        self._tile_state[key] = {
            "outer": outer,
            "inner": inner,
            "info": info,
            "lbl": lbl,
            "overlay": None,
            "toggle": toggle,
        }
        # Klicks auf alle sichtbaren Teile (inkl. Overlay/+HINZUFÜGEN)
        for widget in (lbl, info, inner, outer):
            self._bind_tile_click(widget, toggle)
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
                cursor="hand2",
            )
            badge.place(relx=0.02, rely=0.02, anchor=tk.NW)
            self._bind_tile_click(badge, toggle)

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
        try:
            # Finaler Export ersetzt den Entwurf
            from .selection_draft import draft_path

            dp = draft_path(self.output_dir)
            if dp.is_file():
                dp.unlink()
        except Exception:
            pass
        self._close()

    def _close(self) -> None:
        self._autosave_draft()
        self._unbind_wheel()
        if self._scroll_job is not None:
            try:
                self.after_cancel(self._scroll_job)
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
    # transient macht das Fenster manchmal „klein gebunden“ an den Parent –
    # für Review lieber eigenständig groß und maximierbar.
    try:
        win.lift()
        win.focus_force()
    except tk.TclError:
        pass
    return win
