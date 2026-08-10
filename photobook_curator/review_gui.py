"""Thumbnail-Review: Auswahl prüfen, Bilder rausnehmen oder Alternativen hinzufügen."""

from __future__ import annotations

import itertools
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from .i18n import sync_language_from_settings, t
from .models import BookPlan, Photo
from .review_export import (
    alternatives_for_index,
    apply_manual_selection,
    candidate_alternatives,
    chapter_sections,
)
from .selection_draft import (
    apply_selection_draft,
    load_selection_draft,
    save_selection_draft,
)
from .settings import load_settings, save_settings, theme_colors
from .utils import load_image_scaled, load_thumb_cached

COLORS = theme_colors()

THUMB = 120
LABEL_H = 28  # Beschriftungsband unter dem Bild (vertikal zentrierter Text)
CELL_W = THUMB + 28
CELL_H = 4 + THUMB + 4 + LABEL_H + 8  # Rand, Bild, Band, Abstand
HEADER_H = 44
ALT_BTN_H = 40
GRID_PAD = 14
STRIP = 64
STRIP_WINDOW = 9  # ungerade: aktuelle Bildmitte + Nachbarn
# PhotoImage-Updates pro Tick (UI bleibt flüssig, Ordner füllt sich schneller)
_THUMBS_PER_TICK = 12
_THUMB_PENDING_MAX = 64
_SLIDE_MAX = 720  # max. Kantenlänge in der Diashow (kleiner = schneller)
_LOADER_THREADS = 3
_ALT_LIMIT = 6  # Varianten pro Kapitel (weniger Widgets = flüssiger)
_SLIDE_CACHE_MAX = 24

# Kameranummer / kurzer Stem aus Dateiname (DSCF0491, IMG_0260, …)
_IMAGE_NUM_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])((?:DSCF?|IMG_?|P|DSC)\d{3,}|\d{4,})(?:$|[^A-Za-z0-9])",
    re.IGNORECASE,
)


def short_tile_label(filename: str, max_len: int = 12) -> str:
    """Kurze Kachel-Beschriftung: Bildnummer oder gekürzter Dateiname."""
    stem = Path(filename or "").stem
    if not stem:
        return "?"
    match = _IMAGE_NUM_RE.search(stem)
    if match:
        label = match.group(1)
    else:
        # oft reicht der vordere Teil (ohne lange Hash-/Export-Suffixe)
        label = stem.split("_")[0] if "_" in stem else stem
    if len(label) > max_len:
        return label[: max_len - 1] + "…"
    return label


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
        sync_language_from_settings()
        self.settings = load_settings()
        global COLORS
        COLORS = theme_colors(self.settings.theme)
        self.title(t("review_title"))
        self.resizable(True, True)
        self.configure(bg=COLORS["bg"])
        self._open_large()
        # Nach Style/Build erneut – manche Windows-Setups setzen zoomed erst dann um
        self.after(80, self._open_large)

        self.photos = photos
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.on_saved = on_saved
        self._filter_mode = "all"  # all | kept | removed
        self._chapter_filter = ""  # Diashow: "" = alle
        self._grid_folder = ""  # Raster: genau ein Ordner
        self._folder_labels: list[tuple[str, str]] = []  # (folder, title)
        self._known_folders: list[str] = []  # Session: auch leere Ordner nach Verschieben
        self._auto_advance = bool(self.settings.slideshow_auto_advance)
        self._show_alt_panel = bool(self.settings.slideshow_show_alternative)
        self._alt_idx: int | None = None
        self._alt_img_ref: ImageTk.PhotoImage | None = None
        self._chapters: list[str] = []

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
        self._pending_thumbs: set[int] = set()
        # Indizes die noch geladen werden sollen (nicht verwerfen bei Warteschlangen-Limit)
        self._wanted_thumbs: dict[int, int] = {}  # idx → beste (niedrigste) Priorität
        self._thumb_failed: set[int] = set()
        # PriorityQueue: (prio, seq, job) — job = ("thumb"|"slide", idx) oder None=Stop
        self._load_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._load_seq = itertools.count()
        self._ready_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._slide_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._pending_slides: set[int] = set()
        self._wheel_bound = False
        self._grid_cols = 6
        self._session_added: set[int] = set()  # als Variante hinzugefügt
        self._expanded_alts: set[str] = set()
        self._canvas_img_ids: dict[int, int] = {}  # photo idx → canvas image id
        self._canvas_border_ids: dict[tuple, int] = {}  # (mode, idx[, folder]) → rect
        self._hit_tiles: list[dict] = []
        self._status_flash_job: str | None = None
        self._slideshow = False
        self._thumb_request_budget = 0
        self._slide_indices: list[int] = []
        self._slide_pos = 0
        self._slide_img_ref: ImageTk.PhotoImage | None = None
        self._slide_showing_idx: int | None = None
        self._strip_frames: dict[int, tk.Frame] = {}
        self._strip_thumb_labels: dict[int, tk.Label] = {}
        self._placeholder_img: ImageTk.PhotoImage | None = None
        self._loaders = [
            threading.Thread(target=self._thumb_worker, daemon=True)
            for _ in range(_LOADER_THREADS)
        ]
        for loader in self._loaders:
            loader.start()

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
        self.bind("<a>", self._slide_key_take_alt)
        self.bind("<A>", self._slide_key_take_alt)
        self.bind("<Prior>", self._slide_key_chapter_prev)  # PageUp
        self.bind("<Next>", self._slide_key_chapter_next)  # PageDown

    def _open_large(self) -> None:
        """Groß öffnen (möglichst maximiert), frei skalierbar."""
        from .window_layout import place_window

        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        try:
            # Windows: maximiert
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        place_window(
            self,
            frac_w=0.94,
            frac_h=0.90,
            min_width=1000,
            min_height=700,
            width=1280,
            height=860,
        )

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
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "RevCardHead.TLabel",
            background=COLORS["surface"],
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
            "RevCardMuted.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "RevSave.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(16, 10),
            background=COLORS["accent"],
            foreground=COLORS.get("hero_fg", "#FFFFFF"),
        )
        style.map(
            "RevSave.TButton",
            background=[("active", COLORS["accent_hover"])],
        )
        style.configure(
            "Rev.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 9),
            background=COLORS.get("chip_bg", COLORS["surface"]),
            foreground=COLORS["ink"],
        )
        style.map(
            "Rev.TButton",
            background=[("active", COLORS["line"])],
        )
        style.configure(
            "Rev.TRadiobutton",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=("Segoe UI", 10),
            focuscolor=COLORS["bg"],
        )
        style.map("Rev.TRadiobutton", background=[("active", COLORS["bg"])])

    def _build(self) -> None:
        from .ui_widgets import PaddedButton

        # Nacht-Header wie Hauptfenster (kein alter Akzent-Banner)
        tk.Frame(self, bg=COLORS["accent"], height=3).pack(fill=tk.X)
        header = tk.Frame(self, bg=COLORS["bg"], padx=20, pady=14)
        header.pack(fill=tk.X)
        titles = tk.Frame(header, bg=COLORS["bg"])
        titles.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            titles,
            text=t("review_title"),
            bg=COLORS["bg"],
            fg=COLORS["ink"],
            font=("Segoe UI Semibold", 20),
        ).pack(anchor=tk.W)
        self._hero_hint = tk.Label(
            titles,
            text=t("review_hint_grid"),
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            wraplength=720,
            justify=tk.LEFT,
        )
        self._hero_hint.pack(anchor=tk.W, pady=(4, 0))

        actions = tk.Frame(header, bg=COLORS["bg"])
        actions.pack(side=tk.RIGHT)
        PaddedButton(
            actions,
            t("save_export"),
            COLORS,
            command=self._save,
            primary=True,
            padx=16,
            pady=10,
        ).pack(side=tk.RIGHT)
        PaddedButton(
            actions,
            t("close_draft"),
            COLORS,
            command=self._close,
            padx=14,
            pady=10,
        ).pack(side=tk.RIGHT, padx=(0, 10))

        bar = tk.Frame(self, bg=COLORS["bg"], padx=20)
        bar.pack(fill=tk.X, pady=(0, 8))
        self.count_var = tk.StringVar()
        tk.Label(
            bar,
            textvariable=self.count_var,
            bg=COLORS["bg"],
            fg=COLORS["ink"],
            font=("Segoe UI Semibold", 11),
        ).pack(side=tk.LEFT)
        self.mode_btn = PaddedButton(
            bar,
            t("slideshow"),
            COLORS,
            command=self._toggle_slideshow,
            padx=14,
            pady=8,
        )
        self.mode_btn.pack(side=tk.LEFT, padx=(16, 0))

        # Ordner-Navigation (ein Kapitel/Ordner nach dem anderen)
        nav = tk.Frame(self, bg=COLORS["bg"], padx=20)
        nav.pack(fill=tk.X, pady=(0, 8))
        self._folder_meta = tk.StringVar(value="")
        PaddedButton(
            nav,
            t("chapter_jump_prev"),
            COLORS,
            command=self._grid_folder_prev,
            padx=12,
            pady=8,
        ).pack(side=tk.LEFT)
        self._grid_folder_var = tk.StringVar(value="")
        self._grid_folder_combo = ttk.Combobox(
            nav,
            textvariable=self._grid_folder_var,
            state="readonly",
            width=42,
        )
        self._grid_folder_combo.pack(side=tk.LEFT, padx=10, ipady=4)
        self._grid_folder_combo.bind("<<ComboboxSelected>>", self._on_grid_folder_chosen)
        PaddedButton(
            nav,
            t("chapter_jump_next"),
            COLORS,
            command=self._grid_folder_next,
            padx=12,
            pady=8,
        ).pack(side=tk.LEFT)
        tk.Label(
            nav,
            textvariable=self._folder_meta,
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(14, 0))

        # Kein Banner mehr – Hinweis steht kurz in der Zählerzeile / Hilfe
        if self._draft_note:
            self.after(100, lambda: self._flash_status(self._draft_note))

        self._body = tk.Frame(self, bg=COLORS["bg"])
        self._body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))

        self._grid_host = tk.Frame(self._body, bg=COLORS["bg"])
        self._grid_host.pack(fill=tk.BOTH, expand=True)

        # Reines Canvas-Raster (keine eingebetteten Frames) → kein Windows-Ghosting
        self.canvas = tk.Canvas(
            self._grid_host,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
            yscrollincrement=40,
        )
        self._vscroll = tk.Scrollbar(
            self._grid_host,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
            bg=COLORS.get("chip_bg", COLORS["surface"]),
            troughcolor=COLORS["bg"],
            activebackground=COLORS["accent"],
            width=14,
        )
        self.canvas.configure(yscrollcommand=self._vscroll.set)
        self._vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", self._on_grid_click)
        self.canvas.bind("<Button-3>", self._on_grid_right_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda _e: self._scroll_units(-3))
        self.canvas.bind("<Button-5>", lambda _e: self._scroll_units(3))
        self._install_wheel()

        self._slide_host = tk.Frame(self._body, bg=COLORS["bg"])
        self._build_slideshow_ui()
        self._ensure_placeholder()
        self._refresh_folder_nav(select_first=True)

    def _ensure_placeholder(self) -> None:
        if self._placeholder_img is not None:
            return
        img = Image.new("RGB", (THUMB, THUMB), COLORS.get("thumb_pad", COLORS["line"]))
        self._placeholder_img = ImageTk.PhotoImage(img)
        self._photo_images.append(self._placeholder_img)

    def _on_canvas_configure(self, event) -> None:
        if self._slideshow or event.width < 80:
            return
        cols = max(3, min(10, max(1, int(event.width) // CELL_W)))
        if cols == self._grid_cols:
            return
        self._grid_cols = cols
        try:
            top = self.canvas.yview()[0]
        except tk.TclError:
            top = 0.0
        self._render()
        try:
            self.canvas.yview_moveto(top)
        except tk.TclError:
            pass

    def _install_wheel(self) -> None:
        if self._wheel_bound:
            return
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_linux_scroll_up)
        self.bind_all("<Button-5>", self._on_linux_scroll_down)
        self._wheel_bound = True

    def _unbind_wheel(self, _event=None) -> None:
        if not self._wheel_bound:
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.unbind_all(seq)
            except Exception:
                pass
        self._wheel_bound = False

    def _pointer_in_grid(self) -> bool:
        try:
            if not self.winfo_exists() or self._slideshow:
                return False
            x, y = self.winfo_pointerxy()
            widget = self.winfo_containing(x, y)
            w = widget
            while w is not None:
                if w in (self.canvas, self._vscroll, self._grid_host):
                    return True
                w = getattr(w, "master", None)
            return False
        except tk.TclError:
            return False

    def _scroll_units(self, units: int) -> None:
        if self.winfo_exists() and not self._slideshow:
            self.canvas.yview_scroll(units, "units")

    def _on_linux_scroll_up(self, _event=None) -> None:
        if self._pointer_in_grid():
            self._scroll_units(-3)

    def _on_linux_scroll_down(self, _event=None) -> None:
        if self._pointer_in_grid():
            self._scroll_units(3)

    def _on_mousewheel(self, event) -> str | None:
        if not self._pointer_in_grid():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return None
        steps = -1 if delta > 0 else 1
        if abs(delta) >= 120:
            steps = int(-1 * (delta / 120))
        self._scroll_units(max(-8, min(8, steps * 3)))
        return "break"

    def _build_slideshow_ui(self) -> None:
        host = self._slide_host
        self._slide_tip = ttk.Label(host, text=t("slide_tip"), style="RevMuted.TLabel")
        self._slide_tip.pack(anchor=tk.W, pady=(0, 6))

        tools = ttk.Frame(host, style="Rev.TFrame")
        tools.pack(fill=tk.X, pady=(0, 8))
        self._filter_var = tk.StringVar(value=self._filter_mode)
        for mode, key in (
            ("all", "filter_all"),
            ("kept", "filter_kept"),
            ("removed", "filter_removed"),
        ):
            ttk.Radiobutton(
                tools,
                text=t(key),
                value=mode,
                variable=self._filter_var,
                command=self._on_filter_changed,
                style="Rev.TRadiobutton",
            ).pack(side=tk.LEFT, padx=(0, 8))

        self._chapter_var = tk.StringVar(value=t("chapter_all"))
        self._chapter_combo = ttk.Combobox(
            tools, textvariable=self._chapter_var, state="readonly", width=28
        )
        self._chapter_combo.pack(side=tk.LEFT, padx=(12, 0))
        self._chapter_combo.bind("<<ComboboxSelected>>", self._on_chapter_changed)

        self._auto_btn = ttk.Button(
            tools,
            text=t("auto_on") if self._auto_advance else t("auto_off"),
            command=self._toggle_auto_advance,
        )
        self._auto_btn.pack(side=tk.RIGHT)

        stage_row = ttk.Frame(host, style="Rev.TFrame")
        stage_row.pack(fill=tk.BOTH, expand=True)

        stage_bg = COLORS.get("slide_stage", COLORS["ink"])
        stage = tk.Frame(stage_row, bg=stage_bg, padx=8, pady=8)
        stage.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._slide_image_lbl = tk.Label(
            stage,
            text=t("loading_image"),
            bg=stage_bg,
            fg=COLORS.get("slide_fg", "#E8E2D8"),
            font=("Segoe UI", 12),
            cursor="hand2",
        )
        self._slide_image_lbl.pack(fill=tk.BOTH, expand=True)
        self._slide_image_lbl.bind("<Button-1>", self._slide_toggle_current)
        self._slide_image_lbl.bind("<MouseWheel>", self._slide_mousewheel)
        self._slide_image_lbl.bind("<Button-4>", lambda e: self._slide_prev())
        self._slide_image_lbl.bind("<Button-5>", lambda e: self._slide_next())

        # Umgebung + Meta + Bild-Navigation: direkt unter dem Bild, zentriert
        below = tk.Frame(stage, bg=stage_bg)
        below.pack(fill=tk.X, pady=(10, 0))
        below_inner = tk.Frame(below, bg=stage_bg)
        below_inner.pack(anchor=tk.CENTER)

        tk.Label(
            below_inner,
            text=t("surroundings"),
            bg=stage_bg,
            fg=COLORS.get("slide_fg", "#E8E2D8"),
            font=("Segoe UI", 9),
        ).pack(anchor=tk.CENTER)
        self._strip_bar = tk.Frame(below_inner, bg=stage_bg)
        self._strip_bar.pack(anchor=tk.CENTER, pady=(4, 0))
        self._strip_bar.bind("<MouseWheel>", self._slide_mousewheel)

        self._slide_status = tk.StringVar(value="")
        self._slide_caption = tk.StringVar(value="")
        tk.Label(
            below_inner,
            textvariable=self._slide_status,
            bg=stage_bg,
            fg=COLORS.get("slide_fg", "#E8E2D8"),
            font=("Segoe UI Semibold", 10),
            justify=tk.CENTER,
        ).pack(anchor=tk.CENTER, pady=(10, 0))
        tk.Label(
            below_inner,
            textvariable=self._slide_caption,
            bg=stage_bg,
            fg=COLORS.get("muted", "#A8A0B8"),
            font=("Segoe UI", 9),
            justify=tk.CENTER,
        ).pack(anchor=tk.CENTER, pady=(2, 0))

        controls = tk.Frame(below_inner, bg=stage_bg)
        controls.pack(anchor=tk.CENTER, pady=(12, 4))
        ttk.Button(controls, text=t("prev"), command=self._slide_prev).pack(side=tk.LEFT)
        ttk.Button(controls, text=t("next"), command=self._slide_next).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._slide_toggle_btn = ttk.Button(
            controls,
            text=t("remove"),
            style="RevSave.TButton",
            command=self._slide_toggle_current,
        )
        self._slide_toggle_btn.pack(side=tk.LEFT, padx=(16, 0))

        self._alt_panel = tk.Frame(
            stage_row, bg=stage_bg, padx=8, pady=8, width=320
        )
        self._alt_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        self._alt_panel.pack_propagate(False)
        self._alt_title_lbl = tk.Label(
            self._alt_panel,
            text=t("alt_title"),
            bg=stage_bg,
            fg=COLORS.get("slide_fg", "#E8E2D8"),
            font=("Segoe UI Semibold", 10),
        )
        self._alt_title_lbl.pack(anchor=tk.W)
        self._alt_image_lbl = tk.Label(
            self._alt_panel,
            text=t("alt_none"),
            bg=stage_bg,
            fg=COLORS.get("slide_fg", "#E8E2D8"),
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        self._alt_image_lbl.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        self._alt_image_lbl.bind("<Button-1>", self._slide_take_alternative)
        self._alt_caption = tk.StringVar(value="")
        tk.Label(
            self._alt_panel,
            textvariable=self._alt_caption,
            bg=stage_bg,
            fg=COLORS.get("slide_fg", "#E8E2D8"),
            font=("Segoe UI", 9),
            wraplength=280,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)
        self._alt_take_btn = ttk.Button(
            self._alt_panel, text=t("alt_take"), command=self._slide_take_alternative
        )
        self._alt_take_btn.pack(anchor=tk.W, pady=(8, 0))
        if not self._show_alt_panel:
            self._alt_panel.pack_forget()

        foot = ttk.Frame(host, style="Rev.TFrame", padding=(0, 8, 0, 0))
        foot.pack(fill=tk.X)
        ttk.Button(foot, text=t("back_grid"), command=self._exit_slideshow).pack(
            side=tk.RIGHT
        )

    def _enqueue_job(self, kind: str, idx: int, priority: int) -> None:
        self._load_queue.put((priority, next(self._load_seq), (kind, idx)))

    def _thumb_worker(self) -> None:
        while True:
            _prio, _seq, job = self._load_queue.get()
            if job is None:
                break
            kind, real = job
            if real < 0 or real >= len(self.photos):
                continue
            photo = self.photos[real]
            try:
                if kind == "slide":
                    # Ein Decode für großes Bild; Thumb gleich mit erzeugen
                    img = load_image_scaled(photo.path, _SLIDE_MAX)
                    self._slide_queue.put((real, img.copy()))
                    if real not in self._thumb_cache:
                        thumb = img.copy()
                        thumb.thumbnail((THUMB, THUMB), Image.Resampling.BILINEAR)
                        pad = COLORS.get("thumb_pad", "#F5F1E9")
                        canvas_img = Image.new("RGB", (THUMB, THUMB), pad)
                        x = (THUMB - thumb.width) // 2
                        y = (THUMB - thumb.height) // 2
                        canvas_img.paste(thumb, (x, y))
                        self._ready_queue.put((real, canvas_img))
                else:
                    img = load_thumb_cached(photo.path, THUMB)
                    pad = COLORS.get("thumb_pad", "#F5F1E9")
                    canvas_img = Image.new("RGB", (THUMB, THUMB), pad)
                    x = (THUMB - img.width) // 2
                    y = (THUMB - img.height) // 2
                    canvas_img.paste(img, (x, y))
                    self._ready_queue.put((real, canvas_img))
            except Exception:
                if kind == "slide":
                    self._slide_queue.put((real, None))
                else:
                    self._ready_queue.put((real, None))

    def _request_thumb(self, idx: int, priority: int = 40) -> None:
        """Thumb anfordern – nie still verwerfen; Limit nur drosselt die parallele Queue."""
        if idx in self._thumb_cache or idx in self._thumb_failed:
            return
        if idx in self._pending_thumbs:
            return
        prev = self._wanted_thumbs.get(idx)
        if prev is None or priority < prev:
            self._wanted_thumbs[idx] = priority
        self._flush_thumb_requests()

    def _flush_thumb_requests(self) -> None:
        """Füllt die Lade-Queue aus _wanted_thumbs nach, sobald Platz ist."""
        while self._wanted_thumbs and len(self._pending_thumbs) < _THUMB_PENDING_MAX:
            idx = min(self._wanted_thumbs, key=self._wanted_thumbs.get)
            prio = self._wanted_thumbs.pop(idx)
            if idx in self._thumb_cache or idx in self._thumb_failed or idx in self._pending_thumbs:
                continue
            self._pending_thumbs.add(idx)
            self._enqueue_job("thumb", idx, prio)

    def _request_slide(self, idx: int, priority: int = 10) -> None:
        if idx in self._slide_cache or idx in self._pending_slides:
            return
        if len(self._pending_slides) > 12 and priority > 2:
            return
        self._pending_slides.add(idx)
        self._enqueue_job("slide", idx, priority)
        self._request_thumb(idx, priority=priority + 5)

    def _trim_slide_cache(self) -> None:
        """Alte Diashow-Bilder verwerfen, damit RAM/Tk nicht anschwellen."""
        if len(self._slide_cache) <= _SLIDE_CACHE_MAX:
            return
        keep: set[int] = set()
        if self._slide_indices and 0 <= self._slide_pos < len(self._slide_indices):
            for off in range(-2, 5):
                n = self._slide_pos + off
                if 0 <= n < len(self._slide_indices):
                    keep.add(self._slide_indices[n])
        if self._alt_idx is not None:
            keep.add(self._alt_idx)
        for idx in list(self._slide_cache.keys()):
            if idx not in keep and len(self._slide_cache) > _SLIDE_CACHE_MAX // 2:
                self._slide_cache.pop(idx, None)

    def _drain_thumbs(self) -> None:
        updated = 0
        try:
            while updated < _THUMBS_PER_TICK:
                idx, canvas_img = self._ready_queue.get_nowait()
                self._pending_thumbs.discard(idx)
                if canvas_img is None:
                    self._thumb_failed.add(idx)
                    continue
                tk_img = ImageTk.PhotoImage(canvas_img)
                self._thumb_cache[idx] = tk_img
                self._photo_images.append(tk_img)
                img_id = self._canvas_img_ids.get(idx)
                if img_id is not None:
                    try:
                        self.canvas.itemconfigure(img_id, image=tk_img)
                    except tk.TclError:
                        pass
                if self._slideshow:
                    if (
                        self._slide_showing_idx == idx
                        and idx not in self._slide_cache
                    ):
                        self._show_slide_placeholder(idx)
                    if idx in self._strip_frames:
                        self._apply_strip_thumb(idx)
                updated += 1
        except queue.Empty:
            pass
        # Nach abgeschlossenen Jobs die zurückgestellten Ordner-Bilder nachschieben
        self._flush_thumb_requests()
        if self.winfo_exists():
            delay = 25 if (updated or self._wanted_thumbs or self._pending_thumbs) else 100
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
                if self._slideshow and self._slide_showing_idx == idx:
                    self._show_slide_image(idx)
                if self._slideshow and self._alt_idx == idx:
                    self._alt_img_ref = tk_img
                    try:
                        self._alt_image_lbl.configure(image=tk_img, text="")
                    except tk.TclError:
                        pass
                self._trim_slide_cache()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._drain_slides)

    def _update_count(self) -> None:
        self.count_var.set(t("selected_count", n=len(self.kept)))
        if self._slideshow:
            self._refresh_slide_meta()

    def _display_indices(self) -> list[int]:
        """Alle Bilder der Review-Menge (Baseline ∪ Kept)."""
        return sorted(self.baseline | self.kept)

    def _chapter_list(self) -> list[str]:
        return [folder for folder, _title in self._folder_entries()]

    def _folder_title(self, folder: str) -> str:
        return folder.replace("/", " · ").replace("\\", " · ").replace("_", " ")

    def _folder_entries(self) -> list[tuple[str, str]]:
        """[(folder, title), ...] in Buch-Reihenfolge; leere Session-Ordner bleiben navigierbar."""
        display = self._display_indices()
        sections = chapter_sections(self.photos, display)
        by_folder = {folder: title for title, folder, _idx in sections}
        from .documents import ASIDE_FOLDER, aside_indices

        aside = [
            i
            for i in aside_indices(self.photos)
            if i not in self.kept and not self.photos[i].is_duplicate
        ]
        if aside:
            by_folder.setdefault(ASIDE_FOLDER, self._folder_title(ASIDE_FOLDER))

        for folder in by_folder:
            if folder not in self._known_folders:
                self._known_folders.append(folder)
        if self._grid_folder and self._grid_folder not in self._known_folders:
            self._known_folders.append(self._grid_folder)

        return [
            (folder, by_folder.get(folder) or self._folder_title(folder))
            for folder in self._known_folders
        ]

    def _refresh_folder_nav(self, select_first: bool = False) -> None:
        self._folder_labels = self._folder_entries()
        titles = [title for _f, title in self._folder_labels]
        try:
            self._grid_folder_combo.configure(values=titles)
        except tk.TclError:
            return
        if not self._folder_labels:
            self._grid_folder = ""
            self._grid_folder_var.set("")
            self._folder_meta.set("")
            return
        folders = [f for f, _t in self._folder_labels]
        if select_first or self._grid_folder not in folders:
            self._grid_folder = folders[0]
        title = dict(self._folder_labels).get(self._grid_folder, self._folder_title(self._grid_folder))
        self._grid_folder_var.set(title)
        self._update_folder_meta()

    def _update_folder_meta(self) -> None:
        folders = [f for f, _t in self._folder_labels]
        if not folders or not self._grid_folder:
            self._folder_meta.set("")
            return
        try:
            i = folders.index(self._grid_folder) + 1
        except ValueError:
            i = 1
        n_in = sum(
            1
            for idx in self._display_indices()
            if (self.photos[idx].chapter_folder or "") == self._grid_folder
        )
        # Aside-Pool zählen
        from .documents import ASIDE_FOLDER, aside_indices

        if self._grid_folder == ASIDE_FOLDER:
            n_in = max(
                n_in,
                len(
                    [
                        j
                        for j in aside_indices(self.photos)
                        if j not in self.kept and not self.photos[j].is_duplicate
                    ]
                ),
            )
        self._folder_meta.set(
            f"{t('folder_of', i=i, n=len(folders))}  ·  {t('folder_count', n=n_in)}"
        )

    def _on_grid_folder_chosen(self, _event=None) -> None:
        title = self._grid_folder_var.get()
        for folder, label in self._folder_labels:
            if label == title:
                self._grid_folder = folder
                break
        self._apply_folder_change(reset_slide=True)

    def _grid_folder_prev(self) -> None:
        folders = [f for f, _t in self._folder_labels]
        if not folders:
            return
        try:
            i = folders.index(self._grid_folder)
        except ValueError:
            i = 0
        self._grid_folder = folders[(i - 1) % len(folders)]
        self._apply_folder_change(reset_slide=True)

    def _grid_folder_next(self) -> None:
        folders = [f for f, _t in self._folder_labels]
        if not folders:
            return
        try:
            i = folders.index(self._grid_folder)
        except ValueError:
            i = 0
        self._grid_folder = folders[(i + 1) % len(folders)]
        self._apply_folder_change(reset_slide=True)

    def _apply_folder_change(self, *, reset_slide: bool = False) -> None:
        """Ordnerwechsel: Raster neu zeichnen oder Diashow auf diesen Ordner setzen."""
        self._refresh_folder_nav()
        if self._slideshow:
            self._sync_slide_chapter_to_grid_folder()
            self._reapply_slide_filter(keep_photo=not reset_slide)
            return
        self._render()
        try:
            self.canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def _sync_slide_chapter_to_grid_folder(self) -> None:
        """Diashow-Kapitel-Filter = aktueller Ordner aus der oberen Navigation."""
        folder = self._grid_folder or ""
        self._chapter_filter = folder
        try:
            self._chapters = self._chapter_list()
            values = [t("chapter_all")] + [
                c for c in self._chapters if c != folder
            ]
            if folder:
                values = [t("chapter_all"), folder] + [
                    c for c in self._chapters if c != folder
                ]
            self._chapter_combo.configure(values=values)
            self._chapter_var.set(folder if folder else t("chapter_all"))
        except tk.TclError:
            pass

    def _move_photo_to_folder(self, idx: int, target_folder: str) -> None:
        """Bild in einen anderen Kapitelordner legen; Entwurf speichert chapter_folder."""
        if idx < 0 or idx >= len(self.photos) or not target_folder:
            return
        photo = self.photos[idx]
        current = photo.chapter_folder or ""
        if current == target_folder and not (
            photo.is_aside and not target_folder.startswith("99_")
        ):
            return
        self._assign_chapter(idx, target_folder)
        self.kept.add(idx)
        self.baseline.add(idx)
        photo.is_selected = True
        self._autosave_draft()
        self._flash_status(t("moved_to", folder=self._folder_title(target_folder)))
        self._refresh_folder_nav()
        # Im aktuellen Ordner bleiben – Bild ist dort weg; Ziel per ←/→ oder Combobox
        self._render()

    def _filtered_slide_indices(self) -> list[int]:
        indices = self._display_indices()
        if self._chapter_filter:
            indices = [
                i
                for i in indices
                if (self.photos[i].chapter_folder or self.photos[i].region or "")
                == self._chapter_filter
            ]
        if self._filter_mode == "kept":
            indices = [i for i in indices if i in self.kept]
        elif self._filter_mode == "removed":
            indices = [i for i in indices if i not in self.kept]
        return indices

    def _refresh_chapter_combo(self) -> None:
        self._chapters = self._chapter_list()
        values = [t("chapter_all")] + self._chapters
        try:
            self._chapter_combo.configure(values=values)
            if self._chapter_filter and self._chapter_filter in self._chapters:
                self._chapter_var.set(self._chapter_filter)
            else:
                self._chapter_filter = ""
                self._chapter_var.set(t("chapter_all"))
        except tk.TclError:
            pass

    def _on_filter_changed(self) -> None:
        self._filter_mode = self._filter_var.get() or "all"
        self._reapply_slide_filter(keep_photo=True)

    def _on_chapter_changed(self, _event=None) -> None:
        val = self._chapter_var.get()
        if val == t("chapter_all") or not val:
            self._chapter_filter = ""
        else:
            self._chapter_filter = val
            # Obere Ordner-Navigation mitziehen
            if val in {f for f, _t in self._folder_labels}:
                self._grid_folder = val
                self._refresh_folder_nav()
        self._reapply_slide_filter(keep_photo=True)

    def _toggle_auto_advance(self) -> None:
        self._auto_advance = not self._auto_advance
        try:
            self._auto_btn.configure(
                text=t("auto_on") if self._auto_advance else t("auto_off")
            )
        except tk.TclError:
            pass
        try:
            self.settings.slideshow_auto_advance = self._auto_advance
            save_settings(self.settings)
        except Exception:
            pass

    def _reapply_slide_filter(self, keep_photo: bool = True) -> None:
        current = None
        if keep_photo and self._slide_indices and 0 <= self._slide_pos < len(self._slide_indices):
            current = self._slide_indices[self._slide_pos]
        indices = self._filtered_slide_indices()
        self._slide_indices = indices
        if current is not None and current in indices:
            self._slide_pos = indices.index(current)
        else:
            self._slide_pos = 0
        if self._slideshow:
            if not indices:
                try:
                    self._slide_image_lbl.configure(
                        image="", text=t("no_slide_photos")
                    )
                except tk.TclError:
                    pass
                self._slide_status.set(t("no_slide_photos"))
                self._clear_alt_panel()
                return
            self._show_current_slide()

    def _toggle_slideshow(self) -> None:
        if self._slideshow:
            self._exit_slideshow()
        else:
            self._enter_slideshow()

    def _enter_slideshow(self) -> None:
        if not self._display_indices():
            messagebox.showinfo(
                t("review_title"),
                t("no_slide_photos"),
            )
            return
        self._slideshow = True
        # Gleicher Ordner wie im Raster
        self._sync_slide_chapter_to_grid_folder()
        indices = self._filtered_slide_indices()
        # Fallback: wenn Ordner leer (Filter), alle Bilder zeigen
        if not indices and self._chapter_filter:
            self._chapter_filter = ""
            try:
                self._chapter_var.set(t("chapter_all"))
            except tk.TclError:
                pass
            indices = self._filtered_slide_indices()
        self._slide_indices = indices
        self._slide_pos = 0
        try:
            self._grid_host.pack_forget()
        except tk.TclError:
            pass
        self._slide_host.pack(fill=tk.BOTH, expand=True)
        self.mode_btn.configure(text=t("grid_view"))
        self._hero_hint.configure(text=t("review_hint_slide"))
        if self._show_alt_panel:
            try:
                self._alt_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
            except tk.TclError:
                pass
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
        self.mode_btn.configure(text=t("slideshow"))
        self._hero_hint.configure(text=t("review_hint_grid"))
        self._render()

    def _show_current_slide(self) -> None:
        if not self._slide_indices:
            return
        self._slide_pos = max(0, min(self._slide_pos, len(self._slide_indices) - 1))
        idx = self._slide_indices[self._slide_pos]
        self._slide_showing_idx = idx
        self._refresh_slide_meta()
        self._rebuild_filmstrip()
        self._refresh_alt_panel()
        cached = self._slide_cache.get(idx)
        if cached is not None:
            self._show_slide_image(idx)
        else:
            if not self._show_slide_placeholder(idx):
                try:
                    self._slide_image_lbl.configure(
                        image="",
                        text=t("loading_image"),
                        fg=COLORS.get("slide_fg", "#E8E2D8"),
                    )
                except tk.TclError:
                    pass
                self._slide_img_ref = None
            self._request_slide(idx, priority=0)
        # Nur nahe Nachbarn vorladen (weniger OneDrive-Last)
        for dist in (1, 2):
            for n in (self._slide_pos + dist, self._slide_pos - dist):
                if 0 <= n < len(self._slide_indices):
                    self._request_slide(self._slide_indices[n], priority=dist)

    def _show_slide_placeholder(self, idx: int) -> bool:
        tk_img = self._thumb_cache.get(idx)
        if tk_img is None:
            self._request_thumb(idx, priority=1)
            return False
        self._slide_img_ref = tk_img
        try:
            self._slide_image_lbl.configure(image=tk_img, text="")
        except tk.TclError:
            return False
        return True

    def _show_slide_image(self, idx: int) -> None:
        tk_img = self._slide_cache.get(idx)
        if tk_img is None:
            return
        self._slide_img_ref = tk_img
        try:
            self._slide_image_lbl.configure(image=tk_img, text="")
        except tk.TclError:
            pass

    def _filmstrip_range(self) -> list[int]:
        if not self._slide_indices:
            return []
        half = STRIP_WINDOW // 2
        start = max(0, self._slide_pos - half)
        end = min(len(self._slide_indices), start + STRIP_WINDOW)
        start = max(0, end - STRIP_WINDOW)
        return list(range(start, end))

    def _rebuild_filmstrip(self) -> None:
        try:
            for child in self._strip_bar.winfo_children():
                child.destroy()
        except tk.TclError:
            return
        self._strip_frames.clear()
        self._strip_thumb_labels.clear()
        positions = self._filmstrip_range()
        stage_bg = COLORS.get("slide_stage", COLORS["ink"])
        try:
            self._strip_bar.configure(bg=stage_bg)
        except tk.TclError:
            pass
        for pos in positions:
            idx = self._slide_indices[pos]
            kept = idx in self.kept
            is_current = pos == self._slide_pos
            size = STRIP + 12 if is_current else STRIP
            accent = COLORS["accent"]
            border = accent if is_current else (
                COLORS["keep_border"] if kept else COLORS["reject_border"]
            )
            # Äußerer Ring markiert die aktuelle Position klar
            ring_pad = 3 if is_current else 0
            ring = tk.Frame(
                self._strip_bar,
                bg=accent if is_current else stage_bg,
                padx=ring_pad,
                pady=ring_pad,
                cursor="hand2",
            )
            ring.pack(side=tk.LEFT, padx=5 if is_current else 3, pady=2)
            pad = 3 if is_current else 1
            outer = tk.Frame(ring, bg=border, padx=pad, pady=pad, cursor="hand2")
            outer.pack()
            inner = tk.Frame(outer, bg=COLORS["surface"], width=size, height=size)
            inner.pack()
            inner.pack_propagate(False)
            tk_img = self._thumb_cache.get(idx)
            if tk_img is not None:
                lbl = tk.Label(inner, image=tk_img, bg=COLORS["surface"], cursor="hand2")
            else:
                lbl = tk.Label(
                    inner,
                    text="…",
                    bg=COLORS["line"],
                    fg=COLORS["muted"],
                    font=("Segoe UI", 9),
                    cursor="hand2",
                )
                self._request_thumb(idx, priority=8)
            lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            if is_current:
                # Kleiner Indikator oben am aktuellen Bild
                here = tk.Label(
                    inner,
                    text="●",
                    bg=COLORS["surface"],
                    fg=accent,
                    font=("Segoe UI", 8),
                    cursor="hand2",
                )
                here.place(relx=0.5, rely=0.0, anchor=tk.N)
                here.bind("<Button-1>", lambda e, p=pos: self._jump_slide(p))
            if not kept:
                mark = tk.Label(
                    inner,
                    text="×",
                    bg=COLORS["reject"],
                    fg="white",
                    font=("Segoe UI Semibold", 8),
                    cursor="hand2",
                )
                mark.place(relx=1.0, rely=0.0, anchor=tk.NE)
                mark.bind("<Button-1>", lambda e, p=pos: self._jump_slide(p))

            def jump(_event=None, p=pos):
                self._jump_slide(p)

            for w in (ring, outer, inner, lbl):
                w.bind("<Button-1>", jump)
            self._strip_frames[idx] = outer
            self._strip_thumb_labels[idx] = lbl

    def _jump_slide(self, pos: int) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if 0 <= pos < len(self._slide_indices):
            self._slide_pos = pos
            self._show_current_slide()

    def _apply_strip_thumb(self, idx: int) -> None:
        lbl = self._strip_thumb_labels.get(idx)
        tk_img = self._thumb_cache.get(idx)
        if lbl is None or tk_img is None:
            return
        try:
            if lbl.winfo_exists():
                lbl.configure(image=tk_img, text="", bg=COLORS["surface"])
        except tk.TclError:
            pass

    def _refresh_strip_borders(self) -> None:
        """Nach Keep/Remove Filmstrip neu aufbauen (aktuelles Bild bleibt markiert)."""
        if not self._slideshow:
            return
        self._rebuild_filmstrip()

    def _refresh_slide_meta(self) -> None:
        if not self._slide_indices:
            self._slide_status.set(t("no_slide_photos"))
            self._slide_caption.set("")
            return
        pos = max(0, min(self._slide_pos, len(self._slide_indices) - 1))
        idx = self._slide_indices[pos]
        photo = self.photos[idx]
        kept = idx in self.kept
        state = t("kept_state") if kept else t("removed_state")
        folder = photo.chapter_folder or photo.region or ""
        self._slide_status.set(
            f"{pos + 1} / {len(self._slide_indices)}  ·  {state}  ·  "
            f"{t('selected_count', n=len(self.kept))}"
        )
        meta = photo.scene_type or photo.chapter_type or ""
        score = photo.final_score or photo.technical_score
        self._slide_caption.set(
            f"{photo.filename}  ·  {folder}  ·  {meta}  ·  Score {score:.0f}"
        )
        try:
            self._slide_toggle_btn.configure(
                text=t("restore") if not kept else t("remove")
            )
        except tk.TclError:
            pass

    def _clear_alt_panel(self) -> None:
        self._alt_idx = None
        self._alt_img_ref = None
        try:
            self._alt_image_lbl.configure(image="", text=t("alt_none"))
            self._alt_caption.set("")
            self._alt_take_btn.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _refresh_alt_panel(self) -> None:
        if not self._show_alt_panel or not self._slide_indices:
            self._clear_alt_panel()
            return
        idx = self._slide_indices[self._slide_pos]
        alts = alternatives_for_index(self.photos, idx, self.kept, limit=1)
        if not alts:
            self._clear_alt_panel()
            return
        alt = alts[0]
        self._alt_idx = alt
        photo = self.photos[alt]
        score = photo.final_score or photo.technical_score
        self._alt_caption.set(f"{photo.filename}  ·  Score {score:.0f}")
        try:
            self._alt_take_btn.configure(state=tk.NORMAL)
        except tk.TclError:
            pass
        cached = self._slide_cache.get(alt) or self._thumb_cache.get(alt)
        if cached is not None:
            self._alt_img_ref = cached
            try:
                self._alt_image_lbl.configure(image=cached, text="")
            except tk.TclError:
                pass
        else:
            try:
                self._alt_image_lbl.configure(image="", text=t("loading_image"))
            except tk.TclError:
                pass
            self._request_slide(alt, priority=2)
            self._request_thumb(alt, priority=3)

    def _slide_take_alternative(self, _event=None) -> None:
        if not self._slideshow or self._alt_idx is None or not self._slide_indices:
            return
        cur = self._slide_indices[self._slide_pos]
        alt = self._alt_idx
        folder = self.photos[cur].chapter_folder or ""
        if cur in self.kept:
            self.kept.remove(cur)
            self.photos[cur].is_selected = False
        self.kept.add(alt)
        self.baseline.add(alt)
        self._session_added.add(alt)
        self._assign_chapter(alt, folder)
        if folder:
            self._flash_status(t("added_to_chapter", folder=folder))
        self._update_count()
        self._autosave_draft()
        # Aktuelle Position auf Alternative legen (bleibt in „alle“/„dabei“)
        if alt not in self._slide_indices:
            self._reapply_slide_filter(keep_photo=False)
            if alt in self._slide_indices:
                self._slide_pos = self._slide_indices.index(alt)
        else:
            self._slide_pos = self._slide_indices.index(alt)
        self._show_current_slide()

    def _slide_chapter_of(self, idx: int) -> str:
        return self.photos[idx].chapter_folder or self.photos[idx].region or ""

    def _slide_chapter_prev(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        cur_ch = self._slide_chapter_of(self._slide_indices[self._slide_pos])
        for pos in range(self._slide_pos - 1, -1, -1):
            if self._slide_chapter_of(self._slide_indices[pos]) != cur_ch:
                # Anfang dieses Kapitels
                ch = self._slide_chapter_of(self._slide_indices[pos])
                start = pos
                while start > 0 and self._slide_chapter_of(self._slide_indices[start - 1]) == ch:
                    start -= 1
                self._slide_pos = start
                self._show_current_slide()
                return

    def _slide_chapter_next(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        cur_ch = self._slide_chapter_of(self._slide_indices[self._slide_pos])
        for pos in range(self._slide_pos + 1, len(self._slide_indices)):
            if self._slide_chapter_of(self._slide_indices[pos]) != cur_ch:
                self._slide_pos = pos
                self._show_current_slide()
                return

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
        removed = False
        if idx in self.kept:
            self.kept.remove(idx)
            removed = True
        else:
            self.kept.add(idx)
            self.baseline.add(idx)
        self._update_count()
        self._autosave_draft()
        self._apply_tile_visual(("keep", idx))
        self._refresh_slide_meta()
        self._refresh_strip_borders()
        self._refresh_alt_panel()
        if removed and self._auto_advance:
            # Bei Filter „Dabei“ fällt das Bild raus → Liste neu, sonst weiter
            if self._filter_mode == "kept":
                self._reapply_slide_filter(keep_photo=False)
            else:
                self._slide_next()

    def _slide_mousewheel(self, event) -> None:
        if not self._slideshow:
            return
        delta = int(getattr(event, "delta", 0) or 0)
        if delta > 0:
            self._slide_prev()
        elif delta < 0:
            self._slide_next()
        return "break"

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
            self._refresh_strip_borders()
            self._refresh_alt_panel()
            if self._auto_advance:
                if self._filter_mode == "kept":
                    self._reapply_slide_filter(keep_photo=False)
                else:
                    self._slide_next()
        return "break"

    def _slide_key_take_alt(self, _event=None) -> None:
        if self._slideshow:
            self._slide_take_alternative()
            return "break"

    def _slide_key_chapter_prev(self, _event=None) -> None:
        if self._slideshow:
            # PageUp = vorheriger Ordner (wie oben)
            self._grid_folder_prev()
            return "break"

    def _slide_key_chapter_next(self, _event=None) -> None:
        if self._slideshow:
            # PageDown = nächster Ordner (wie oben)
            self._grid_folder_next()
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

    def _flash_status(self, text: str) -> None:
        """Kurz Feedback in der Zählerzeile, dann wieder normale Anzahl."""
        try:
            self.count_var.set(text)
        except tk.TclError:
            return
        if self._status_flash_job is not None:
            try:
                self.after_cancel(self._status_flash_job)
            except Exception:
                pass
        self._status_flash_job = self.after(2200, self._update_count)

    def _assign_chapter(self, idx: int, folder_name: str) -> None:
        """Kapitelordner setzen – Entwurf + Speichern schreiben chapter_folder mit."""
        if not folder_name:
            return
        from .documents import ASIDE_FOLDER

        self.photos[idx].chapter_folder = folder_name
        if folder_name == ASIDE_FOLDER or folder_name.startswith("99_"):
            self.photos[idx].is_aside = True
            self.photos[idx].chapter_type = "Optional"
            self.photos[idx].region = self.photos[idx].region or "Optional"
        else:
            # Wichtig: sonst schreibt Speichern wieder 99_Optional_Dokumente
            self.photos[idx].is_aside = False
            self.photos[idx].chapter_type = (
                "Transit"
                if "Transit" in folder_name
                else "Essen"
                if folder_name.replace("\\", "/").endswith("/essen")
                or folder_name.replace("\\", "/").endswith("essen")
                else "Hauptteil"
            )
        self.photos[idx].is_selected = True

    def _place_in_chapter(self, idx: int, folder_name: str) -> None:
        """Variante ins Kapitel legen und Raster neu zeichnen."""
        folder = folder_name or self.photos[idx].chapter_folder or "Unbestimmt"
        self._assign_chapter(idx, folder)
        self._session_added.add(idx)
        self._flash_status(t("added_to_chapter", folder=folder))
        self._autosave_draft()
        self._refresh_folder_nav()
        self._render()

    def _hit_at(self, event) -> dict | None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for hit in reversed(self._hit_tiles):
            x1, y1, x2, y2 = hit["box"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return hit
        return None

    def _on_grid_click(self, event) -> None:
        if self._slideshow:
            return
        hit = self._hit_at(event)
        if not hit:
            return
        kind = hit["kind"]
        if kind == "photo":
            self._toggle_photo(hit["idx"], hit["mode"], hit.get("folder") or "")
        elif kind == "alt_toggle":
            key = hit["key"]
            if key in self._expanded_alts:
                self._expanded_alts.discard(key)
            else:
                self._expanded_alts.add(key)
            try:
                top = self.canvas.yview()[0]
            except tk.TclError:
                top = 0.0
            self._render()
            try:
                self.canvas.yview_moveto(top)
            except tk.TclError:
                pass

    def _on_grid_right_click(self, event) -> None:
        """Rechtsklick: Bild in anderen Ordner verschieben."""
        if self._slideshow:
            return
        hit = self._hit_at(event)
        if not hit or hit.get("kind") != "photo":
            return
        idx = int(hit["idx"])
        mode = hit.get("mode") or "keep"
        # Nur behaltene / hinzufügbare Bilder verschieben
        if mode == "add" and idx not in self.kept:
            # Erst ins Buch legen, dann verschieben-Menü – oder direkt mit Zielordner
            pass
        folders = [f for f, _t in self._folder_labels if f != (hit.get("folder") or self._grid_folder)]
        # Alle bekannten Ordner inkl. aktueller Liste
        if not folders:
            folders = [f for f, _t in self._folder_entries() if f != self._grid_folder]
        if not folders:
            return
        menu = tk.Menu(self, tearoff=0, bg=COLORS["surface"], fg=COLORS["ink"])
        menu.add_command(label=t("move_to"), state=tk.DISABLED)
        for folder in folders:
            label = self._folder_title(folder)
            menu.add_command(
                label=label,
                command=lambda f=folder, i=idx: self._move_photo_to_folder(i, f),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_photo(self, idx: int, mode: str, folder: str) -> None:
        if mode == "add":
            if idx in self.kept:
                return
            self.kept.add(idx)
            self.baseline.add(idx)
            self._place_in_chapter(idx, folder)
            return
        if idx in self.kept:
            self.kept.remove(idx)
            self.photos[idx].is_selected = False
        else:
            self.kept.add(idx)
            self.photos[idx].is_selected = True
        self._update_count()
        self._paint_tile_state(idx, mode, folder)
        self._autosave_draft()

    def _paint_tile_state(self, idx: int, mode: str, folder: str) -> None:
        key = (mode, idx, folder)
        border_id = self._canvas_border_ids.get(key) or self._canvas_border_ids.get(("keep", idx, folder))
        if border_id is None:
            # Fallback: neu zeichnen
            try:
                top = self.canvas.yview()[0]
            except tk.TclError:
                top = 0.0
            self._render()
            try:
                self.canvas.yview_moveto(top)
            except tk.TclError:
                pass
            return
        kept = idx in self.kept
        border = COLORS["keep_border"] if kept else COLORS["reject_border"]
        try:
            self.canvas.itemconfigure(border_id, outline=border)
            # Overlay-Text aktualisieren
            tag = f"ov_{mode}_{idx}_{folder}"
            self.canvas.delete(tag)
            coords = self.canvas.coords(border_id)
            if len(coords) >= 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                if mode == "keep" and not kept:
                    self.canvas.create_text(
                        cx,
                        cy,
                        text=t("removed_state"),
                        fill=COLORS.get("hero_fg", "#FFFFFF"),
                        font=("Segoe UI Semibold", 9),
                        anchor=tk.CENTER,
                        tags=("grid", tag),
                    )
                elif mode == "add" and idx not in self.kept:
                    self.canvas.create_text(
                        cx,
                        cy,
                        text="+",
                        fill=COLORS.get("hero_fg", "#FFFFFF"),
                        font=("Segoe UI Semibold", 14),
                        anchor=tk.CENTER,
                        tags=("grid", tag),
                    )
        except tk.TclError:
            pass

    def _render(self) -> None:
        """Zeichnet nur den aktuellen Ordner – scrollt ohne Geisterbilder."""
        self._ensure_placeholder()
        self.canvas.delete("grid")
        self._canvas_img_ids.clear()
        self._canvas_border_ids.clear()
        self._hit_tiles.clear()
        self._update_count()
        self._update_folder_meta()

        width = max(self.canvas.winfo_width(), CELL_W * self._grid_cols + GRID_PAD * 2)
        cols = max(3, min(10, width // CELL_W))
        self._grid_cols = cols
        y = GRID_PAD

        from .documents import ASIDE_FOLDER, aside_indices

        display = sorted(self.baseline | self.kept)
        sections = chapter_sections(self.photos, display)
        current = self._grid_folder
        if not current and self._folder_labels:
            current = self._folder_labels[0][0]
            self._grid_folder = current

        active = [(title, folder, indices) for title, folder, indices in sections if folder == current]
        drew_photos = False

        if active:
            for title, folder, indices in active:
                y = self._draw_section(
                    title,
                    folder,
                    indices,
                    y,
                    cols,
                    show_alts=not folder.startswith("99_"),
                )
                drew_photos = True
        elif current and current != ASIDE_FOLDER:
            # Leerer Ordner (z. B. alles verschoben) – Varianten trotzdem anbieten
            title = self._folder_title(current)
            self.canvas.create_text(
                GRID_PAD,
                y + 8,
                anchor=tk.NW,
                text=title,
                fill=COLORS["ink"],
                font=("Segoe UI Semibold", 12),
                tags=("grid",),
            )
            self.canvas.create_text(
                GRID_PAD,
                y + 32,
                anchor=tk.NW,
                text=t("empty_folder"),
                fill=COLORS["muted"],
                font=("Segoe UI", 10),
                tags=("grid",),
            )
            y += HEADER_H + 16
            if not current.startswith("99_"):
                alts = candidate_alternatives(
                    self.photos,
                    current,
                    limit=_ALT_LIMIT,
                    exclude=self.kept,
                )
                if alts:
                    y = self._draw_alt_section(
                        title,
                        current,
                        alts,
                        y,
                        cols,
                        collapsed=current not in self._expanded_alts,
                    )
                    drew_photos = True

        if current == ASIDE_FOLDER:
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
                # Im Optional-Ordner Varianten direkt aufklappen
                self._expanded_alts.add(ASIDE_FOLDER)
                y = self._draw_alt_section(
                    "Optional: Dokumente & Screenshots",
                    ASIDE_FOLDER,
                    aside[:40],
                    y,
                    cols,
                    collapsed=False,
                )
                drew_photos = True
            elif not active:
                self.canvas.create_text(
                    GRID_PAD,
                    y + 8,
                    anchor=tk.NW,
                    text=t("empty_folder"),
                    fill=COLORS["muted"],
                    font=("Segoe UI", 10),
                    tags=("grid",),
                )
                y += 40

        if not current and not sections:
            self.canvas.create_text(
                GRID_PAD,
                y + 8,
                anchor=tk.NW,
                text="Keine Bilder in der Auswahl. Füge Alternativen hinzu oder brich ab.",
                fill=COLORS["muted"],
                font=("Segoe UI", 10),
                tags=("grid",),
            )
            y += 40
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
                y = self._draw_alt_section(
                    "Vorschläge",
                    "__suggestions__",
                    alts[:_ALT_LIMIT],
                    y,
                    cols,
                    collapsed="__suggestions__" not in self._expanded_alts,
                )
                drew_photos = True

        if not drew_photos and current and current != ASIDE_FOLDER and not active:
            pass  # empty_folder-Text steht schon

        y += GRID_PAD
        self.canvas.configure(scrollregion=(0, 0, width, max(y, 100)))
        # Nach dem Zeichnen ausstehende Thumbs anstoßen (falls Queue vorher voll war)
        self._flush_thumb_requests()

    def _draw_section(
        self,
        title: str,
        folder: str,
        indices: list[int],
        y: int,
        cols: int,
        *,
        show_alts: bool,
    ) -> int:
        self.canvas.create_text(
            GRID_PAD,
            y,
            anchor=tk.NW,
            text=title,
            fill=COLORS["ink"],
            font=("Segoe UI Semibold", 12),
            tags=("grid",),
        )
        self.canvas.create_text(
            GRID_PAD,
            y + 20,
            anchor=tk.NW,
            text=t("in_chapter_hint"),
            fill=COLORS["muted"],
            font=("Segoe UI", 9),
            tags=("grid",),
        )
        y += HEADER_H
        y = self._draw_photo_rows(indices, folder, "keep", y, cols)

        if show_alts:
            alts = candidate_alternatives(
                self.photos,
                folder,
                limit=_ALT_LIMIT,
                exclude=self.kept,
            )
            if alts:
                y = self._draw_alt_section(
                    title,
                    folder,
                    alts,
                    y,
                    cols,
                    collapsed=folder not in self._expanded_alts,
                )
        y += 10
        return y

    def _draw_alt_section(
        self,
        title: str,
        key: str,
        indices: list[int],
        y: int,
        cols: int,
        *,
        collapsed: bool,
    ) -> int:
        indices = [i for i in indices if i not in self.kept]
        if not indices:
            return y
        action = (
            t("show_variants", n=len(indices))
            if collapsed
            else t("hide_variants")
        )
        # Volle Breite der Rasterzeile, Text mittig
        row_w = max(CELL_W * max(cols, 1), self.canvas.winfo_width() - GRID_PAD * 2 - 18)
        btn_w = max(280, row_w)
        btn_h = ALT_BTN_H
        x1, y1 = GRID_PAD, y
        x2, y2 = x1 + btn_w, y1 + btn_h
        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill=COLORS.get("chip_bg", COLORS["surface"]),
            outline=COLORS["line"],
            tags=("grid",),
        )
        short = (title or "").strip()
        if len(short) > 36:
            short = short[:34] + "…"
        text = f"{action}   ·   {short}" if short else action
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=COLORS["ink"],
            font=("Segoe UI Semibold", 10),
            anchor=tk.CENTER,
            tags=("grid",),
        )
        self._hit_tiles.append(
            {"kind": "alt_toggle", "key": key, "box": (x1, y1, x2, y2)}
        )
        y += btn_h + 10
        if not collapsed:
            y = self._draw_photo_rows(indices, key if key != "__suggestions__" else "", "add", y, cols)
        return y

    def _draw_photo_rows(
        self,
        indices: list[int],
        folder: str,
        mode: str,
        y: int,
        cols: int,
    ) -> int:
        for n, idx in enumerate(indices):
            col = n % cols
            if col == 0 and n:
                y += CELL_H
            x = GRID_PAD + col * CELL_W
            self._draw_tile(x, y, idx, mode, folder)
        if indices:
            y += CELL_H
        return y

    def _draw_tile(self, x: int, y: int, idx: int, mode: str, folder: str) -> None:
        kept = idx in self.kept
        border = COLORS["keep_border"] if (mode == "add" or kept) else COLORS["reject_border"]
        if mode == "add":
            border = COLORS["accent"] if idx not in self.kept else COLORS["keep_border"]
        tile_w = THUMB + 12
        tile_h = CELL_H - 8
        img_x1, img_y1 = x + 4, y + 4
        img_x2, img_y2 = x + 8 + THUMB, y + 8 + THUMB
        label_y1 = img_y2 + 2
        label_y2 = y + tile_h - 2
        label_cx = x + tile_w / 2
        label_cy = (label_y1 + label_y2) / 2

        # Kachel-Hintergrund
        self.canvas.create_rectangle(
            x,
            y,
            x + tile_w,
            y + tile_h,
            fill=COLORS["surface"],
            outline="",
            tags=("grid",),
        )
        border_id = self.canvas.create_rectangle(
            img_x1,
            img_y1,
            img_x2,
            img_y2,
            outline=border,
            width=2,
            tags=("grid",),
        )
        key = (mode, idx, folder)
        self._canvas_border_ids[key] = border_id

        tk_img = self._thumb_cache.get(idx) or self._placeholder_img
        img_id = self.canvas.create_image(
            (img_x1 + img_x2) / 2,
            (img_y1 + img_y2) / 2,
            image=tk_img,
            tags=("grid",),
        )
        self._canvas_img_ids[idx] = img_id
        if idx not in self._thumb_cache:
            # Obere Zeilen zuerst; Varianten etwas später
            row_boost = max(0, int(y) // max(CELL_H, 1))
            base = 20 if mode == "keep" else 40
            self._request_thumb(idx, priority=base + min(row_boost, 30))

        photo = self.photos[idx]
        caption = short_tile_label(photo.filename)
        fg = COLORS["muted"] if (mode == "keep" and not kept) else COLORS["ink"]
        # Beschriftungsband: Text horizontal + vertikal mittig
        self.canvas.create_rectangle(
            img_x1,
            label_y1,
            img_x2,
            label_y2,
            fill=COLORS.get("chip_bg", COLORS["bg"]),
            outline="",
            tags=("grid",),
        )
        self.canvas.create_text(
            label_cx,
            label_cy,
            text=caption,
            fill=fg,
            font=("Segoe UI Semibold", 9),
            anchor=tk.CENTER,
            tags=("grid",),
        )

        # Badges / Overlays
        warn = None
        if getattr(photo, "finger_on_lens", False) or "finger_on_lens" in photo.flags:
            warn = "Finger"
        elif getattr(photo, "is_accidental", False) or "accidental" in photo.flags:
            warn = "Fehlausl."
        elif getattr(photo, "is_weak_night", False) or "weak_night" in photo.flags:
            warn = "Nacht?"
        elif getattr(photo, "bad_face", False) or "eyes_closed" in photo.flags:
            warn = (
                "Augen zu"
                if getattr(photo, "eyes_closed", False) or "eyes_closed" in photo.flags
                else "Gesicht?"
            )
        elif "looking_away" in photo.flags or getattr(photo, "looking_at_camera", None) is False:
            warn = "Blick weg"
        elif getattr(photo, "smiling", None) is True or "smiling" in photo.flags:
            warn = None  # positives Signal, kein Warn-Badge
        if warn:
            self.canvas.create_rectangle(
                x + 8,
                y + 8,
                x + 70,
                y + 24,
                fill=COLORS.get("phase_run_bg", "#C47A3A"),
                outline="",
                tags=("grid",),
            )
            self.canvas.create_text(
                x + 12,
                y + 16,
                anchor=tk.W,
                text=warn,
                fill=COLORS.get("phase_run_fg", "#FFF8F0"),
                font=("Segoe UI Semibold", 7),
                tags=("grid",),
            )
        elif mode == "keep" and idx in self._session_added:
            self.canvas.create_rectangle(
                x + 8,
                y + 8,
                x + 72,
                y + 24,
                fill=COLORS["accent"],
                outline="",
                tags=("grid",),
            )
            self.canvas.create_text(
                x + 12,
                y + 16,
                anchor=tk.W,
                text=t("new_badge"),
                fill=COLORS.get("hero_fg", "#FFFFFF"),
                font=("Segoe UI Semibold", 7),
                tags=("grid",),
            )

        tag = f"ov_{mode}_{idx}_{folder}"
        img_cx = (img_x1 + img_x2) / 2
        img_cy = (img_y1 + img_y2) / 2
        if mode == "keep" and not kept:
            self.canvas.create_text(
                img_cx,
                img_cy,
                text=t("removed_state"),
                fill=COLORS.get("hero_fg", "#FFFFFF"),
                font=("Segoe UI Semibold", 9),
                anchor=tk.CENTER,
                tags=("grid", tag),
            )
        elif mode == "add" and idx not in self.kept:
            self.canvas.create_text(
                img_cx,
                img_cy,
                text="+",
                fill=COLORS.get("hero_fg", "#FFFFFF"),
                font=("Segoe UI Semibold", 16),
                anchor=tk.CENTER,
                tags=("grid", tag),
            )

        self._hit_tiles.append(
            {
                "kind": "photo",
                "idx": idx,
                "mode": mode,
                "folder": folder,
                "box": (x, y, x + tile_w, y + tile_h),
            }
        )

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
        if self._status_flash_job is not None:
            try:
                self.after_cancel(self._status_flash_job)
            except Exception:
                pass
            self._status_flash_job = None
        for _ in self._loaders:
            self._load_queue.put((0, next(self._load_seq), None))
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
